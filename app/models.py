"""The data model. One class per table; every table is also an API resource.

The flow in one paragraph: a FlowConcept is something on the table (an option,
or a sub-point under one) and records who raised it and in which message. A
FlowEntry is one person speaking to one concept (support, dissent, question or
clarify), tied to the message where they said it. Entries are append-only: a
change of view is a new entry, and a tagging correction is a new entry whose
supersedes_id points at the wrong one.

Names and emails live only in Person, so exports can leave that table out and
stay pseudonymous.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

STAGES = ("none", "invited", "scheduled", "in_progress", "pending_debrief", "complete")
INVITE_STATUSES = ("not_invited", "invited", "accepted", "declined", "cancelled")
POSITIONS = ("support", "dissent", "question", "clarify")
TAG_STATUSES = ("proposed", "confirmed", "rejected")
TAGGERS = ("participant", "moderator", "ai_tagger")
STANCES = ("support", "oppose", "undecided")
PHASES = ("pre", "during", "post")
EFFECTS = ("moved", "reinforced", "not_persuasive")


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_token() -> str:
    return secrets.token_urlsafe(24)


def _in(col: str, values: tuple[str, ...]) -> CheckConstraint:
    return CheckConstraint(f"{col} IN ({', '.join(repr(v) for v in values)})", name=f"{col}_valid")


def pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def fk(target: str, nullable: bool = False, ondelete: str | None = None, **kw) -> Mapped:
    return mapped_column(UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable, **kw)


def ts(nullable: bool = True, default=None) -> Mapped:
    return mapped_column(DateTime(timezone=True), nullable=nullable, default=default)


# ---------------------------------------------------------------- people
class Person(Base):
    __tablename__ = "person"
    id: Mapped[uuid.UUID] = pk()
    full_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = ts(False, now)


class Organiser(Base):
    __tablename__ = "organiser"
    id: Mapped[uuid.UUID] = pk()
    person_id: Mapped[uuid.UUID] = fk("person.id", unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    person: Mapped[Person] = relationship()


class Moderator(Base):
    __tablename__ = "moderator"
    id: Mapped[uuid.UUID] = pk()
    person_id: Mapped[uuid.UUID] = fk("person.id", unique=True)
    organisation: Mapped[str | None] = mapped_column(Text)
    access_token: Mapped[str] = mapped_column(String(64), unique=True, default=new_token)
    invited_at: Mapped[datetime | None] = ts()
    removed_at: Mapped[datetime | None] = ts()  # soft delete: past deliberations keep the link
    created_at: Mapped[datetime] = ts(False, now)
    person: Mapped[Person] = relationship()


# ---------------------------------------------------------------- setup
class Deliberation(Base):
    __tablename__ = "deliberation"
    __table_args__ = (_in("stage", STAGES),)
    id: Mapped[uuid.UUID] = pk()
    title: Mapped[str] = mapped_column(Text)
    process: Mapped[str | None] = mapped_column(Text)
    framing_question: Mapped[str] = mapped_column(Text)
    moderator_id: Mapped[uuid.UUID | None] = fk("moderator.id", nullable=True)
    stage: Mapped[str] = mapped_column(String(20), default="none")
    stage_changed_at: Mapped[datetime] = ts(False, now)
    created_by: Mapped[uuid.UUID | None] = fk("person.id", nullable=True)
    created_at: Mapped[datetime] = ts(False, now)
    moderator: Mapped[Moderator | None] = relationship()
    documents: Mapped[list["Document"]] = relationship(back_populates="deliberation", cascade="all, delete-orphan", order_by="Document.file_name")
    participants: Mapped[list["Participant"]] = relationship(back_populates="deliberation", cascade="all, delete-orphan", order_by="Participant.created_at")
    sessions: Mapped[list["Session"]] = relationship(back_populates="deliberation", cascade="all, delete-orphan", order_by="Session.created_at")
    concepts: Mapped[list["FlowConcept"]] = relationship(back_populates="deliberation", cascade="all, delete-orphan", order_by="FlowConcept.raised_at")
    eval_runs: Mapped[list["EvalRun"]] = relationship(back_populates="deliberation", cascade="all, delete-orphan", order_by="EvalRun.started_at")


class Document(Base):
    __tablename__ = "document"
    __table_args__ = (UniqueConstraint("deliberation_id", "file_name"),)
    id: Mapped[uuid.UUID] = pk()
    deliberation_id: Mapped[uuid.UUID] = fk("deliberation.id", ondelete="CASCADE")
    file_name: Mapped[str] = mapped_column(Text)
    file_ext: Mapped[str | None] = mapped_column(String(12))
    sha256: Mapped[str | None] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text, default="")  # extracted text; the original file is not kept
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    indexed_at: Mapped[datetime | None] = ts()
    uploaded_at: Mapped[datetime] = ts(False, now)
    deliberation: Mapped[Deliberation] = relationship(back_populates="documents")
    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="document", cascade="all, delete-orphan", order_by="DocumentChunk.seq")


class DocumentChunk(Base):
    __tablename__ = "document_chunk"
    id: Mapped[uuid.UUID] = pk()
    document_id: Mapped[uuid.UUID] = fk("document.id", ondelete="CASCADE", index=True)
    seq: Mapped[int] = mapped_column(Integer)
    locator: Mapped[str] = mapped_column(Text, default="")
    text: Mapped[str] = mapped_column(Text)
    document: Mapped[Document] = relationship(back_populates="chunks")


class EvalRun(Base):
    __tablename__ = "eval_run"
    id: Mapped[uuid.UUID] = pk()
    deliberation_id: Mapped[uuid.UUID] = fk("deliberation.id", ondelete="CASCADE", index=True)
    suite: Mapped[str] = mapped_column(Text, default="readiness")
    coach_model: Mapped[str] = mapped_column(Text, default="")
    judge_model: Mapped[str] = mapped_column(Text, default="")
    prompt_version: Mapped[str] = mapped_column(Text, default="")
    health_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    status: Mapped[str] = mapped_column(String(12), default="running")  # running | passed | below_goal | failed
    progress: Mapped[int] = mapped_column(Integer, default=0)
    document_count: Mapped[int] = mapped_column(Integer, default=0)
    conversations_total: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    conversations_done: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    details: Mapped[dict | None] = mapped_column(JSONB, deferred=True)  # per-conversation scores, reasons and transcripts
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 4))
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = ts(False, now)
    finished_at: Mapped[datetime | None] = ts()
    deliberation: Mapped[Deliberation] = relationship(back_populates="eval_runs")
    metrics: Mapped[list["EvalMetricResult"]] = relationship(cascade="all, delete-orphan", order_by="EvalMetricResult.metric")


class EvalMetricResult(Base):
    __tablename__ = "eval_metric_result"
    eval_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("eval_run.id", ondelete="CASCADE"), primary_key=True)
    metric: Mapped[str] = mapped_column(Text, primary_key=True)
    result: Mapped[float] = mapped_column(Numeric)
    goal: Mapped[float] = mapped_column(Numeric)
    higher_is_better: Mapped[bool] = mapped_column(Boolean)
    attainment: Mapped[float] = mapped_column(Numeric(5, 4))  # result against goal, capped at 1


# ---------------------------------------------------------------- sessions
class Participant(Base):
    __tablename__ = "participant"
    __table_args__ = (UniqueConstraint("deliberation_id", "person_id"), UniqueConstraint("deliberation_id", "pseudonym"), _in("invite_status", INVITE_STATUSES))
    id: Mapped[uuid.UUID] = pk()
    deliberation_id: Mapped[uuid.UUID] = fk("deliberation.id", ondelete="CASCADE", index=True)
    person_id: Mapped[uuid.UUID] = fk("person.id")
    pseudonym: Mapped[str] = mapped_column(Text)
    invite_status: Mapped[str] = mapped_column(String(12), default="not_invited")
    invite_token: Mapped[str] = mapped_column(String(64), unique=True, default=new_token)
    invited_at: Mapped[datetime | None] = ts()
    responded_at: Mapped[datetime | None] = ts()
    cancelled_at: Mapped[datetime | None] = ts()
    joined_at: Mapped[datetime | None] = ts()
    consent_research: Mapped[bool] = mapped_column(Boolean, default=False)
    knowledge_level: Mapped[str] = mapped_column(String(10), default="some")
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)  # an AI stand-in, never a real person
    persona: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = ts(False, now)
    deliberation: Mapped[Deliberation] = relationship(back_populates="participants")
    person: Mapped[Person] = relationship()


class Session(Base):
    __tablename__ = "session"
    id: Mapped[uuid.UUID] = pk()
    deliberation_id: Mapped[uuid.UUID] = fk("deliberation.id", ondelete="CASCADE", index=True)
    scheduled_start: Mapped[datetime | None] = ts()
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    format: Mapped[str] = mapped_column(String(12), default="online")
    started_at: Mapped[datetime | None] = ts()
    ended_at: Mapped[datetime | None] = ts()
    created_at: Mapped[datetime] = ts(False, now)
    deliberation: Mapped[Deliberation] = relationship(back_populates="sessions")


class Message(Base):
    __tablename__ = "message"
    __table_args__ = (
        UniqueConstraint("session_id", "seq"),
        CheckConstraint(
            "(speaker_kind = 'participant' AND participant_id IS NOT NULL AND moderator_id IS NULL) OR "
            "(speaker_kind = 'moderator' AND moderator_id IS NOT NULL AND participant_id IS NULL) OR "
            "(speaker_kind = 'system' AND participant_id IS NULL AND moderator_id IS NULL)",
            name="speaker_matches_kind",
        ),
    )
    id: Mapped[uuid.UUID] = pk()
    session_id: Mapped[uuid.UUID] = fk("session.id", ondelete="CASCADE", index=True)
    seq: Mapped[int] = mapped_column(Integer)
    speaker_kind: Mapped[str] = mapped_column(String(12))
    participant_id: Mapped[uuid.UUID | None] = fk("participant.id", nullable=True)
    moderator_id: Mapped[uuid.UUID | None] = fk("moderator.id", nullable=True)
    body: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime] = ts(False, now)


# ---------------------------------------------------------------- the flow
class FlowConcept(Base):
    __tablename__ = "flow_concept"
    __table_args__ = (
        CheckConstraint("(kind = 'option' AND parent_id IS NULL) OR (kind = 'subpoint' AND parent_id IS NOT NULL)", name="kind_matches_parent"),
        _in("status", TAG_STATUSES),
        _in("tagged_by_kind", TAGGERS),
    )
    id: Mapped[uuid.UUID] = pk()
    deliberation_id: Mapped[uuid.UUID] = fk("deliberation.id", ondelete="CASCADE", index=True)
    parent_id: Mapped[uuid.UUID | None] = fk("flow_concept.id", nullable=True, ondelete="CASCADE")
    kind: Mapped[str] = mapped_column(String(10))
    label: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)
    seeded: Mapped[bool] = mapped_column(Boolean, default=False)  # added by the organiser before the session
    raised_by_participant: Mapped[uuid.UUID | None] = fk("participant.id", nullable=True)
    raised_by_moderator: Mapped[uuid.UUID | None] = fk("moderator.id", nullable=True)
    raised_in_message: Mapped[uuid.UUID | None] = fk("message.id", nullable=True)
    raised_at: Mapped[datetime] = ts(False, now)
    tagged_by_kind: Mapped[str] = mapped_column(String(12), default="moderator")
    tagger_model: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="confirmed")
    reviewed_by: Mapped[uuid.UUID | None] = fk("person.id", nullable=True)
    reviewed_at: Mapped[datetime | None] = ts()
    deliberation: Mapped[Deliberation] = relationship(back_populates="concepts")


class FlowEntry(Base):
    __tablename__ = "flow_entry"
    __table_args__ = (
        CheckConstraint("(participant_id IS NULL) <> (moderator_id IS NULL)", name="one_speaker"),
        CheckConstraint("tagged_by_kind <> 'ai_tagger' OR tagger_model IS NOT NULL", name="ai_tag_has_model"),
        _in("position", POSITIONS),
        _in("status", TAG_STATUSES),
        _in("tagged_by_kind", TAGGERS),
    )
    id: Mapped[uuid.UUID] = pk()
    concept_id: Mapped[uuid.UUID] = fk("flow_concept.id", ondelete="CASCADE", index=True)
    participant_id: Mapped[uuid.UUID | None] = fk("participant.id", nullable=True, index=True)
    moderator_id: Mapped[uuid.UUID | None] = fk("moderator.id", nullable=True)
    message_id: Mapped[uuid.UUID | None] = fk("message.id", nullable=True, index=True)
    topic_parent_id: Mapped[uuid.UUID | None] = fk("flow_entry.id", nullable=True)  # the entry this one replies to
    supersedes_id: Mapped[uuid.UUID | None] = fk("flow_entry.id", nullable=True)  # tagging corrections only
    position: Mapped[str] = mapped_column(String(10))
    paraphrase: Mapped[str] = mapped_column(Text)
    tag: Mapped[str | None] = mapped_column(Text)
    tagged_by_kind: Mapped[str] = mapped_column(String(12))
    tagged_by_person: Mapped[uuid.UUID | None] = fk("person.id", nullable=True)
    tagger_model: Mapped[str | None] = mapped_column(Text)
    tagger_prompt_version: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    status: Mapped[str] = mapped_column(String(10), default="proposed")
    reviewed_by: Mapped[uuid.UUID | None] = fk("person.id", nullable=True)
    reviewed_at: Mapped[datetime | None] = ts()
    created_at: Mapped[datetime] = ts(False, now)


# ---------------------------------------------------------------- private views, partner, surveys
class PrivateStance(Base):
    __tablename__ = "private_stance"
    __table_args__ = (_in("phase", PHASES), _in("value", STANCES), CheckConstraint("certainty BETWEEN 1 AND 5", name="certainty_range"))
    id: Mapped[uuid.UUID] = pk()
    participant_id: Mapped[uuid.UUID] = fk("participant.id", ondelete="CASCADE", index=True)
    concept_id: Mapped[uuid.UUID] = fk("flow_concept.id", ondelete="CASCADE")
    phase: Mapped[str] = mapped_column(String(8))
    value: Mapped[str] = mapped_column(String(10))
    certainty: Mapped[int | None] = mapped_column(Integer)
    set_at: Mapped[datetime] = ts(False, now)


class PartnerMessage(Base):
    """The private chat between one participant and their partner."""
    __tablename__ = "partner_message"
    id: Mapped[uuid.UUID] = pk()
    participant_id: Mapped[uuid.UUID] = fk("participant.id", ondelete="CASCADE", index=True)
    session_id: Mapped[uuid.UUID | None] = fk("session.id", nullable=True, ondelete="SET NULL")
    role: Mapped[str] = mapped_column(String(10))  # user | assistant
    body: Mapped[str] = mapped_column(Text)
    mode: Mapped[str | None] = mapped_column(String(14))
    sources: Mapped[list | None] = mapped_column(JSONB)
    model: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = ts(False, now)


class PartnerWhisper(Base):
    """An unprompted nudge from the partner during a session. Kept for the non-steering audit."""
    __tablename__ = "partner_whisper"
    id: Mapped[uuid.UUID] = pk()
    participant_id: Mapped[uuid.UUID] = fk("participant.id", ondelete="CASCADE", index=True)
    session_id: Mapped[uuid.UUID] = fk("session.id", ondelete="CASCADE")
    concept_id: Mapped[uuid.UUID | None] = fk("flow_concept.id", nullable=True, ondelete="SET NULL")
    body: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    after_seq: Mapped[int] = mapped_column(Integer, default=0)
    shown_at: Mapped[datetime] = ts(False, now)
    acted_on_message: Mapped[uuid.UUID | None] = fk("message.id", nullable=True)


class SurveyResponse(Base):
    """One table for both surveys: phase 'pre' before the session, 'post' for the reflection."""
    __tablename__ = "survey_response"
    __table_args__ = (UniqueConstraint("participant_id", "phase"), CheckConstraint("phase IN ('pre', 'post')", name="survey_phase_valid"))
    id: Mapped[uuid.UUID] = pk()
    participant_id: Mapped[uuid.UUID] = fk("participant.id", ondelete="CASCADE", index=True)
    phase: Mapped[str] = mapped_column(String(8))
    answers: Mapped[dict] = mapped_column(JSONB, default=dict)
    submitted_at: Mapped[datetime] = ts(False, now)


class ReflectionConcept(Base):
    __tablename__ = "reflection_concept"
    survey_response_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("survey_response.id", ondelete="CASCADE"), primary_key=True)
    concept_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("flow_concept.id", ondelete="CASCADE"), primary_key=True)
    view_before: Mapped[str | None] = mapped_column(String(10))
    view_after: Mapped[str | None] = mapped_column(String(10))
    certainty_after: Mapped[int | None] = mapped_column(Integer)
    moved_note: Mapped[str | None] = mapped_column(Text)
    not_persuasive_note: Mapped[str | None] = mapped_column(Text)


class ReflectionPoint(Base):
    """'What moved me': links a reflection to the entry, and so to the person and message behind it."""
    __tablename__ = "reflection_point"
    __table_args__ = (_in("effect", EFFECTS),)
    survey_response_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("survey_response.id", ondelete="CASCADE"), primary_key=True)
    entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("flow_entry.id", ondelete="CASCADE"), primary_key=True)
    effect: Mapped[str] = mapped_column(String(16))


VIEWS_SQL = """
CREATE OR REPLACE VIEW v_current_entry AS
SELECT e.* FROM flow_entry e
WHERE e.status = 'confirmed'
  AND NOT EXISTS (SELECT 1 FROM flow_entry n WHERE n.supersedes_id = e.id AND n.status <> 'rejected');

CREATE OR REPLACE VIEW v_public_position AS
SELECT DISTINCT ON (concept_id, coalesce(participant_id, moderator_id))
       concept_id, participant_id, moderator_id, position, paraphrase, message_id, created_at
FROM v_current_entry
WHERE position IN ('support', 'dissent')
ORDER BY concept_id, coalesce(participant_id, moderator_id), created_at DESC;

CREATE OR REPLACE VIEW v_concept_summary AS
SELECT c.id AS concept_id, c.deliberation_id, c.parent_id, c.kind, c.label,
       c.raised_by_participant, c.raised_by_moderator, c.raised_at,
       count(*) FILTER (WHERE p.position = 'support') AS supporters,
       count(*) FILTER (WHERE p.position = 'dissent') AS dissenters,
       (SELECT count(*) FROM v_current_entry e
         WHERE e.concept_id = c.id AND e.participant_id IS DISTINCT FROM c.raised_by_participant) = 0 AS unanswered
FROM flow_concept c
LEFT JOIN v_public_position p ON p.concept_id = c.id
WHERE c.status = 'confirmed'
GROUP BY c.id;
"""
DROP_VIEWS_SQL = "DROP VIEW IF EXISTS v_concept_summary; DROP VIEW IF EXISTS v_public_position; DROP VIEW IF EXISTS v_current_entry;"
