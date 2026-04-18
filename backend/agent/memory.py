from datetime import datetime

from models.db import (
    AgentAction,
    ChannelStat,
    CompanySignal,
    Lead,
    Opportunity,
    SessionLocal,
)


def log_action(
    campaign_id: str,
    action_type: str,
    action: str,
    reasoning: str,
    channel: str | None = None,
    outcome: str | None = None,
    stream: str = "system",
    live_url: str | None = None,
    session_ended: bool = False,
) -> None:
    db = SessionLocal()
    try:
        db.add(
            AgentAction(
                campaign_id=campaign_id,
                stream=stream,
                action_type=action_type,
                action=action,
                reasoning=reasoning,
                channel=channel,
                outcome=outcome,
                live_url=live_url,
                session_ended=1 if session_ended else 0,
                timestamp=datetime.utcnow(),
            )
        )
        db.commit()
    finally:
        db.close()


def get_recent_actions(campaign_id: str, limit: int = 10, stream: str | None = None) -> list[dict]:
    db = SessionLocal()
    try:
        q = db.query(AgentAction).filter(AgentAction.campaign_id == campaign_id)
        if stream:
            q = q.filter(AgentAction.stream == stream)
        actions = q.order_by(AgentAction.timestamp.desc()).limit(limit).all()
        return [
            {
                "stream": a.stream,
                "action": a.action,
                "reasoning": a.reasoning,
                "outcome": a.outcome,
                "channel": a.channel,
            }
            for a in actions
        ]
    finally:
        db.close()


def save_leads(campaign_id: str, leads: list[dict]) -> None:
    if not leads:
        return
    db = SessionLocal()
    try:
        for lead in leads:
            db.add(Lead(campaign_id=campaign_id, **lead))
        db.commit()
    finally:
        db.close()


def save_opportunities(campaign_id: str, opps: list[dict]) -> None:
    if not opps:
        return
    db = SessionLocal()
    try:
        for opp in opps:
            db.add(Opportunity(campaign_id=campaign_id, **opp))
        db.commit()
    finally:
        db.close()


def update_lead_status(
    campaign_id: str,
    source_post_url: str,
    status: str,
    reply_text: str | None = None,
) -> None:
    db = SessionLocal()
    try:
        lead = (
            db.query(Lead)
            .filter(Lead.campaign_id == campaign_id, Lead.source_post_url == source_post_url)
            .first()
        )
        if lead:
            lead.status = status
            if reply_text is not None:
                lead.reply_text = reply_text
            db.commit()
    finally:
        db.close()


def update_opportunity_status(
    campaign_id: str,
    url: str,
    status: str,
    pitch_text: str | None = None,
    contact_url: str | None = None,
    contact_email: str | None = None,
) -> None:
    db = SessionLocal()
    try:
        opp = (
            db.query(Opportunity)
            .filter(Opportunity.campaign_id == campaign_id, Opportunity.url == url)
            .first()
        )
        if opp:
            opp.status = status
            if pitch_text is not None:
                opp.pitch_text = pitch_text
            if contact_url is not None:
                opp.contact_url = contact_url
            if contact_email is not None:
                opp.contact_email = contact_email
            db.commit()
    finally:
        db.close()


def get_channel_stats(campaign_id: str) -> dict:
    db = SessionLocal()
    try:
        stats = db.query(ChannelStat).filter(ChannelStat.campaign_id == campaign_id).all()
        result: dict = {}
        for s in stats:
            reply_rate = round((s.replied / s.sent * 100), 1) if s.sent > 0 else 0
            result[s.channel] = {
                "sent": s.sent,
                "replied": s.replied,
                "reply_rate": reply_rate,
            }
        return result
    finally:
        db.close()


def save_signals(campaign_id: str, signals: list[dict]) -> list[int]:
    """Persist new CompanySignal rows. Returns the list of inserted IDs.

    Dedup-by-URL is best-effort: if a signal with the same `signal_url`
    already exists for the campaign, we skip it.
    """
    if not signals:
        return []
    inserted: list[int] = []
    db = SessionLocal()
    try:
        existing_urls = {
            row[0]
            for row in db.query(CompanySignal.signal_url)
            .filter(CompanySignal.campaign_id == campaign_id)
            .all()
            if row[0]
        }
        for s in signals:
            url = s.get("signal_url") or ""
            if url and url in existing_urls:
                continue
            row = CompanySignal(
                campaign_id=campaign_id,
                type=s.get("signal_type") or s.get("type") or "funding",
                company_name=(s.get("company_name") or "")[:160],
                signal_text=(s.get("signal_text") or "")[:1200],
                signal_url=url or None,
                suggested_role=(s.get("suggested_role") or "")[:80] or None,
                status="new",
            )
            db.add(row)
            db.flush()
            inserted.append(row.id)
            if url:
                existing_urls.add(url)
        db.commit()
    finally:
        db.close()
    return inserted


def update_signal_status(
    signal_id: int,
    status: str,
    resolved_lead_url: str | None = None,
) -> None:
    db = SessionLocal()
    try:
        row = db.query(CompanySignal).filter(CompanySignal.id == signal_id).first()
        if row:
            row.status = status
            if resolved_lead_url is not None:
                row.resolved_lead_url = resolved_lead_url
            db.commit()
    finally:
        db.close()


def get_signals(
    campaign_id: str,
    limit: int = 50,
    status: str | None = None,
) -> list[dict]:
    db = SessionLocal()
    try:
        q = db.query(CompanySignal).filter(CompanySignal.campaign_id == campaign_id)
        if status:
            q = q.filter(CompanySignal.status == status)
        rows = q.order_by(CompanySignal.created_at.desc()).limit(limit).all()
        return [
            {
                "id": r.id,
                "type": r.type,
                "company_name": r.company_name,
                "signal_text": r.signal_text,
                "signal_url": r.signal_url,
                "suggested_role": r.suggested_role,
                "status": r.status,
                "resolved_lead_url": r.resolved_lead_url,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    finally:
        db.close()


def increment_channel_sent(campaign_id: str, channel: str) -> None:
    db = SessionLocal()
    try:
        stat = (
            db.query(ChannelStat)
            .filter(ChannelStat.campaign_id == campaign_id, ChannelStat.channel == channel)
            .first()
        )
        if stat is None:
            stat = ChannelStat(campaign_id=campaign_id, channel=channel, sent=0, replied=0)
            db.add(stat)
        stat.sent = (stat.sent or 0) + 1
        db.commit()
    finally:
        db.close()
