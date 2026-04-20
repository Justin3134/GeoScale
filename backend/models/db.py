import os
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker

# Use an absolute path so the DB is always found regardless of the working
# directory the server is started from.
_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "geoscale.db")

engine = create_engine(
    f"sqlite:///{_DB_PATH}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(String, primary_key=True)
    company_url = Column(String)
    goal = Column(Text)
    country = Column(String)
    language = Column(String, default="en")
    status = Column(String, default="running")  # running | paused | meeting_booked
    strategy_json = Column(Text, nullable=True)  # retained for schema compatibility
    require_human_approval = Column(Integer, default=1)  # 0=auto, 1=require human approval
    created_at = Column(DateTime, default=datetime.utcnow)


class AgentAction(Base):
    __tablename__ = "agent_actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(String, index=True)
    stream = Column(String, default="system")  # people | opportunities | system
    action_type = Column(String)  # scan | think | act | wait | escalate | error
    action = Column(Text)
    reasoning = Column(Text)
    outcome = Column(Text)
    channel = Column(String)  # linkedin | reddit | naver | weibo | quora | apify | browser-use | llm
    live_url = Column(String, nullable=True)
    session_ended = Column(Integer, nullable=True, default=0)  # 0=active, 1=ended
    timestamp = Column(DateTime, default=datetime.utcnow)


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(String, index=True)
    name = Column(String)
    title = Column(String)
    company = Column(String)
    linkedin_url = Column(String)
    email = Column(String, nullable=True)
    score = Column(Integer)  # 1-10 ICP fit
    status = Column(String, default="identified")  # identified | contacted | replied | meeting
    platform = Column(String, default="linkedin")  # linkedin | reddit | naver | quora | weibo | zhihu
    source_post_url = Column(String, nullable=True)
    source_comment_text = Column(Text, nullable=True)
    reply_text = Column(Text, nullable=True)
    reply_language = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Opportunity(Base):
    __tablename__ = "opportunities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(String, index=True)
    type = Column(String)  # event | hackathon | press | community | accelerator
    title = Column(String)
    description = Column(Text, nullable=True)
    url = Column(String)
    contact_url = Column(String, nullable=True)
    contact_email = Column(String, nullable=True)
    score = Column(Integer, default=5)
    status = Column(String, default="identified")  # identified | contacted | replied | booked
    pitch_text = Column(Text, nullable=True)
    pitch_language = Column(String, nullable=True)
    analysis = Column(Text, nullable=True)  # AI explanation of why this opportunity fits
    created_at = Column(DateTime, default=datetime.utcnow)


class ChannelStat(Base):
    __tablename__ = "channel_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(String, index=True)
    channel = Column(String)
    sent = Column(Integer, default=0)
    replied = Column(Integer, default=0)


class CompanySignal(Base):
    """Buying-intent signal scraped by the signals stream.

    A signal is company-level (not person-level) and gets resolved into one
    or more leads downstream by `streams/signals.py`.
    """

    __tablename__ = "company_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(String, index=True)
    type = Column(String)  # funding | hiring | engagement
    company_name = Column(String)
    signal_text = Column(Text)
    signal_url = Column(String, nullable=True)
    suggested_role = Column(String, nullable=True)
    status = Column(String, default="new")  # new | resolved | contacted | skipped
    resolved_lead_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)


def _ensure_column(table: str, column: str, ddl_type: str) -> None:
    """SQLite-only: idempotently add a column that's missing on an old DB."""
    try:
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))
    except OperationalError:
        # Column already exists, or table missing — both safe to ignore.
        pass


_ensure_column("agent_actions", "live_url", "TEXT")
_ensure_column("agent_actions", "session_ended", "INTEGER DEFAULT 0")
_ensure_column("campaigns", "strategy_json", "TEXT")
_ensure_column("campaigns", "require_human_approval", "INTEGER DEFAULT 1")
_ensure_column("opportunities", "analysis", "TEXT")
