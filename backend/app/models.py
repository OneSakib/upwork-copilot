from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    upwork_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True)
    url: Mapped[Optional[str]] = mapped_column(Text)
    title: Mapped[Optional[str]] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    scraped: Mapped[dict] = mapped_column(JSONB, default=dict)   # everything the extension sent
    parsed: Mapped[dict] = mapped_column(JSONB, default=dict)    # structured facts (client stats etc.)
    rules: Mapped[dict] = mapped_column(JSONB, default=dict)     # rule-engine output
    analysis: Mapped[dict] = mapped_column(JSONB, default=dict)  # LLM verdict
    research: Mapped[Optional[str]] = mapped_column(Text)
    verdict: Mapped[Optional[str]] = mapped_column(String(10))
    overall: Mapped[Optional[int]] = mapped_column(Integer)
    # analyzed | skipped | applied | interviewing | hired | rejected | no_response
    status: Mapped[str] = mapped_column(String(20), default="analyzed", index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    connects_spent: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    proposals: Mapped[list["Proposal"]] = relationship(
        back_populates="job", order_by="Proposal.version", cascade="all, delete-orphan"
    )


class Proposal(Base):
    __tablename__ = "proposals"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    hook: Mapped[Optional[str]] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    answers: Mapped[list] = mapped_column(JSONB, default=list)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    outcome: Mapped[str] = mapped_column(String(20), default="pending")
    lesson: Mapped[Optional[str]] = mapped_column(Text)  # AI post-mortem used for the next proposal
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    job: Mapped[Job] = relationship(back_populates="proposals")
