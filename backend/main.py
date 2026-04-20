import asyncio
import json
import uuid
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

load_dotenv()

from agent.country import get_country_config, list_countries  # noqa: E402
from agent import approval as _approval  # noqa: E402
from agent.loop import active_streams, run_agent  # noqa: E402
from agent.memory import get_signals  # noqa: E402
from agent.tools import healthcheck_apify, send_gmail  # noqa: E402
from models.db import (  # noqa: E402
    AgentAction,
    Campaign,
    CompanySignal,
    Lead,
    Opportunity,
    SessionLocal,
)

app = FastAPI(title="GeoScale", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Track running agent tasks so they can be cancelled on pause / shutdown.
_agent_tasks: dict[str, asyncio.Task] = {}


class DeployRequest(BaseModel):
    company_url: str
    country: str


class CampaignSettingsRequest(BaseModel):
    require_human_approval: bool


def _spawn_agent_task(campaign_id: str, company_url: str, country: str) -> None:
    """Create + register the long-running agent coroutine for a campaign."""
    existing = _agent_tasks.get(campaign_id)
    if existing and not existing.done():
        return
    task = asyncio.create_task(run_agent(campaign_id, company_url, country))
    _agent_tasks[campaign_id] = task

    def _cleanup(t: asyncio.Task, cid: str = campaign_id) -> None:
        _agent_tasks.pop(cid, None)

    task.add_done_callback(_cleanup)


@app.on_event("startup")
async def resume_running_campaigns() -> None:
    """Re-attach the agent loop to every campaign still marked as running.

    Without this, restarting the backend silently strands every active
    campaign — the DB still says `running`, but no coroutine is producing
    events, so the live browser panels stay empty forever.
    """
    db = SessionLocal()
    try:
        rows = (
            db.query(Campaign)
            .filter(Campaign.status == "running")
            .all()
        )
        targets = [(c.id, c.company_url, c.country) for c in rows]
    finally:
        db.close()

    for campaign_id, company_url, country in targets:
        _spawn_agent_task(campaign_id, company_url, country)


@app.post("/deploy")
async def deploy_agent(req: DeployRequest):
    """Deploy a new agent for a country. Starts the autonomous loop."""
    campaign_id = str(uuid.uuid4())
    cfg = get_country_config(req.country)

    db = SessionLocal()
    try:
        db.add(
            Campaign(
                id=campaign_id,
                company_url=req.company_url,
                goal="",
                country=req.country,
                language=cfg["language"],
                status="running",
                created_at=datetime.utcnow(),
            )
        )
        db.commit()
    finally:
        db.close()

    _spawn_agent_task(campaign_id, req.company_url, req.country)

    return {"campaign_id": campaign_id, "status": "running", "country": req.country}


@app.post("/campaign/{campaign_id}/resume")
async def resume_campaign(campaign_id: str):
    """Manually re-attach the agent loop to a campaign (e.g. after restart)."""
    db = SessionLocal()
    try:
        c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Campaign not found")
        if c.status != "running":
            c.status = "running"
            db.commit()
        company_url, country = c.company_url, c.country
    finally:
        db.close()

    _spawn_agent_task(campaign_id, company_url, country)
    return {"status": "running", "campaign_id": campaign_id}


@app.get("/countries")
def get_countries():
    return [
        {"name": name, "language": cfg["language"], "language_name": cfg["language_name"]}
        for name, cfg in [(c, get_country_config(c)) for c in list_countries()]
    ]


@app.get("/healthcheck/apify")
def apify_health():
    return healthcheck_apify()


@app.get("/stream/{campaign_id}")
async def stream_events(campaign_id: str):
    """SSE endpoint — frontend connects here for the live agent feed."""

    async def event_generator():
        seen = 0
        while True:
            events = active_streams.get(campaign_id, [])
            if seen > len(events):
                seen = len(events)
            new_events = events[seen:]
            for event in new_events:
                yield f"data: {json.dumps(event)}\n\n"
                seen += 1
            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _campaign_to_dict(c: Campaign, db) -> dict:
    leads = db.query(Lead).filter(Lead.campaign_id == c.id).all()
    signals = db.query(CompanySignal).filter(CompanySignal.campaign_id == c.id).all()
    actions_count = (
        db.query(AgentAction).filter(AgentAction.campaign_id == c.id).count()
    )
    return {
        "id": c.id,
        "country": c.country,
        "language": c.language,
        "goal": c.goal,
        "company_url": c.company_url,
        "status": c.status,
        "require_human_approval": bool(getattr(c, "require_human_approval", 0)),
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "total_leads": len(leads),
        "contacted": len(
            [l for l in leads if l.status in ("contacted", "replied", "meeting")]
        ),
        "replied": len([l for l in leads if l.status in ("replied", "meeting")]),
        "meetings": len([l for l in leads if l.status == "meeting"]),
        "total_signals": len(signals),
        "signals_contacted": len(
            [s for s in signals if s.status == "contacted"]
        ),
        "total_actions": actions_count,
    }


@app.get("/campaigns")
def get_campaigns():
    db = SessionLocal()
    try:
        campaigns = db.query(Campaign).order_by(Campaign.created_at.desc()).all()
        return [_campaign_to_dict(c, db) for c in campaigns]
    finally:
        db.close()


@app.get("/campaign/{campaign_id}")
def get_campaign(campaign_id: str):
    db = SessionLocal()
    try:
        c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Campaign not found")
        return _campaign_to_dict(c, db)
    finally:
        db.close()


@app.get("/campaign/{campaign_id}/leads")
def get_leads(campaign_id: str):
    db = SessionLocal()
    try:
        leads = (
            db.query(Lead)
            .filter(Lead.campaign_id == campaign_id)
            .order_by(Lead.score.desc(), Lead.id.desc())
            .all()
        )
        return [
            {
                "id": l.id,
                "name": l.name,
                "title": l.title,
                "company": l.company,
                "score": l.score,
                "status": l.status,
                "platform": l.platform,
                "source_post_url": l.source_post_url,
                "source_comment_text": l.source_comment_text,
                "reply_text": l.reply_text,
                "reply_language": l.reply_language,
                "linkedin_url": l.linkedin_url,
                "email": l.email,
            }
            for l in leads
        ]
    finally:
        db.close()


@app.get("/campaign/{campaign_id}/signals")
def get_campaign_signals(campaign_id: str):
    return get_signals(campaign_id, limit=200)


@app.get("/campaign/{campaign_id}/actions")
def get_actions(campaign_id: str):
    db = SessionLocal()
    try:
        actions = (
            db.query(AgentAction)
            .filter(AgentAction.campaign_id == campaign_id)
            .order_by(AgentAction.timestamp.asc())
            .all()
        )
        out: list[dict] = []
        for a in actions:
            preview = None
            if a.outcome:
                try:
                    preview = json.loads(a.outcome)
                except (TypeError, ValueError):
                    preview = None
            out.append(
                {
                    "type": a.action_type,
                    "stream": a.stream,
                    "action": a.action,
                    "reasoning": a.reasoning,
                    "channel": a.channel,
                    "live_url": a.live_url,
                    "session_ended": bool(a.session_ended),
                    "preview": preview,
                    "time": a.timestamp.isoformat() if a.timestamp else None,
                }
            )
        return out
    finally:
        db.close()


@app.get("/campaign/{campaign_id}/stats")
def get_stats(campaign_id: str):
    db = SessionLocal()
    try:
        leads = db.query(Lead).filter(Lead.campaign_id == campaign_id).all()
        signals = (
            db.query(CompanySignal)
            .filter(CompanySignal.campaign_id == campaign_id)
            .all()
        )
        actions = db.query(AgentAction).filter(AgentAction.campaign_id == campaign_id).count()
        return {
            "total_leads": len(leads),
            "contacted": len(
                [l for l in leads if l.status in ("contacted", "replied", "meeting")]
            ),
            "replied": len([l for l in leads if l.status in ("replied", "meeting")]),
            "meetings": len([l for l in leads if l.status == "meeting"]),
            "total_signals": len(signals),
            "signals_contacted": len(
                [s for s in signals if s.status == "contacted"]
            ),
            "total_actions": actions,
        }
    finally:
        db.close()


@app.post("/campaign/{campaign_id}/pause")
def pause_campaign(campaign_id: str):
    db = SessionLocal()
    try:
        c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Campaign not found")
        c.status = "paused"
        db.commit()
    finally:
        db.close()

    task = _agent_tasks.get(campaign_id)
    if task and not task.done():
        task.cancel()
    return {"status": "paused"}


@app.delete("/campaign/{campaign_id}")
def delete_campaign(campaign_id: str):
    """Cancel any running task and remove the campaign + all related rows."""
    task = _agent_tasks.pop(campaign_id, None)
    if task and not task.done():
        task.cancel()
    active_streams.pop(campaign_id, None)

    db = SessionLocal()
    try:
        c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Campaign not found")

        db.query(AgentAction).filter(AgentAction.campaign_id == campaign_id).delete(
            synchronize_session=False
        )
        db.query(Lead).filter(Lead.campaign_id == campaign_id).delete(
            synchronize_session=False
        )
        db.query(Opportunity).filter(
            Opportunity.campaign_id == campaign_id
        ).delete(synchronize_session=False)
        db.query(CompanySignal).filter(
            CompanySignal.campaign_id == campaign_id
        ).delete(synchronize_session=False)
        db.delete(c)
        db.commit()
    finally:
        db.close()

    return {"status": "deleted", "campaign_id": campaign_id}


@app.patch("/campaign/{campaign_id}/settings")
def update_campaign_settings(campaign_id: str, req: CampaignSettingsRequest):
    """Toggle require_human_approval (and any future per-campaign settings)."""
    db = SessionLocal()
    try:
        c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Campaign not found")
        c.require_human_approval = 1 if req.require_human_approval else 0
        db.commit()
    finally:
        db.close()
    return {"require_human_approval": req.require_human_approval}


@app.post("/campaign/{campaign_id}/approve/{approval_id}")
async def approve_action(campaign_id: str, approval_id: str):
    """Human approved a pending browser-use action."""
    found = _approval.resolve(approval_id, approved=True)
    if not found:
        raise HTTPException(status_code=404, detail="Approval not found or already resolved")
    return {"status": "approved"}


@app.post("/campaign/{campaign_id}/reject/{approval_id}")
async def reject_action(campaign_id: str, approval_id: str):
    """Human rejected a pending browser-use action."""
    found = _approval.resolve(approval_id, approved=False)
    if not found:
        raise HTTPException(status_code=404, detail="Approval not found or already resolved")
    return {"status": "rejected"}


async def _send_gmail_background(
    campaign_id: str,
    lead_id: int,
    linkedin_url: str | None,
    name: str,
    reply_text: str,
    to_email: str | None,
) -> None:
    """Run Browser-Use to open Gmail and send a cold-outreach email for a lead."""
    if not to_email:
        from agent.tools import _push_error
        _push_error(
            campaign_id,
            "gmail",
            f"Cannot send email for {name}: no email address on file.",
            stream="people",
        )
        return

    subject = f"Quick intro — {name}"
    result = await send_gmail(to_email, subject, reply_text, campaign_id)

    # Mark lead as contacted if Browser-Use succeeded
    success = isinstance(result, dict) and "error" not in str(result.get("result", "")).lower()
    if success:
        db = SessionLocal()
        try:
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if lead:
                lead.status = "contacted"
                db.commit()
        finally:
            db.close()


@app.post("/campaign/{campaign_id}/leads/{lead_id}/send-gmail")
async def send_gmail_lead(campaign_id: str, lead_id: int):
    """Trigger Browser-Use to send the drafted Gmail outreach for a specific lead."""
    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(
            Lead.id == lead_id, Lead.campaign_id == campaign_id
        ).first()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        if not lead.reply_text:
            raise HTTPException(status_code=400, detail="No draft message for this lead")
        to_email = lead.email
        linkedin_url = lead.linkedin_url
        name = lead.name or "Contact"
        reply_text = lead.reply_text
    finally:
        db.close()

    asyncio.create_task(
        _send_gmail_background(campaign_id, lead_id, linkedin_url, name, reply_text, to_email)
    )
    return {"status": "sending"}


@app.get("/health")
def health():
    return {"ok": True, "active_agents": len(_agent_tasks)}
