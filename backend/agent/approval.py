"""Human-in-the-loop approval gate for browser-use actions.

When require_human_approval is enabled for a campaign, the stream calls
`register()` to get an approval_id, embeds it in the preview event, then
calls `wait()`. The FastAPI layer calls `resolve()` when the human clicks
Approve or Reject on the dashboard.
"""

from __future__ import annotations

import asyncio
import uuid

from models.db import Campaign, SessionLocal

# Approval timeout: if the human doesn't respond within this window the
# action is automatically skipped to keep the stream from hanging forever.
APPROVAL_TIMEOUT_SECONDS = 5 * 60  # 5 minutes


class _ApprovalEntry:
    __slots__ = ("event", "approved")

    def __init__(self) -> None:
        self.event: asyncio.Event = asyncio.Event()
        self.approved: bool = False


# { approval_id: _ApprovalEntry }
_registry: dict[str, _ApprovalEntry] = {}


def register() -> str:
    """Create a new pending approval slot and return its ID."""
    aid = str(uuid.uuid4())
    _registry[aid] = _ApprovalEntry()
    return aid


async def wait(approval_id: str) -> bool:
    """Wait for the human to decide.  Returns True=approved, False=rejected/timed-out."""
    entry = _registry.get(approval_id)
    if entry is None:
        return False
    try:
        await asyncio.wait_for(entry.event.wait(), timeout=APPROVAL_TIMEOUT_SECONDS)
        return entry.approved
    except asyncio.TimeoutError:
        return False
    finally:
        _registry.pop(approval_id, None)


def resolve(approval_id: str, approved: bool) -> bool:
    """Set the decision for a pending approval.  Returns False if not found/expired."""
    entry = _registry.get(approval_id)
    if entry is None:
        return False
    entry.approved = approved
    entry.event.set()
    return True


def is_pending(approval_id: str) -> bool:
    """Return True if this approval_id is still waiting for a decision."""
    entry = _registry.get(approval_id)
    return entry is not None and not entry.event.is_set()


def get_require_approval(campaign_id: str) -> bool:
    """Read the campaign's require_human_approval flag from the DB."""
    db = SessionLocal()
    try:
        c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        return bool(getattr(c, "require_human_approval", 0) if c else 0)
    finally:
        db.close()
