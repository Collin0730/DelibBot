"""What a participant does through their invite link: accept, pre-survey, partner chat, reflection."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as Db

from .. import ai, serialize
from .. import models as m
from ..db import get_db
from ..security import Actor, participant_only

router = APIRouter(prefix="/api/p")


def _survey(db: Db, p: m.Participant, phase: str) -> m.SurveyResponse | None:
    return db.scalar(select(m.SurveyResponse).where(m.SurveyResponse.participant_id == p.id, m.SurveyResponse.phase == phase))


def _latest_stances(db: Db, p: m.Participant, phases: tuple[str, ...]) -> dict[str, m.PrivateStance]:
    out: dict[str, m.PrivateStance] = {}
    for st in db.scalars(select(m.PrivateStance).where(m.PrivateStance.participant_id == p.id, m.PrivateStance.phase.in_(phases)).order_by(m.PrivateStance.set_at)).all():
        out[str(st.concept_id)] = st
    return out


@router.get("/state")
def state(actor: Actor = Depends(participant_only), db: Db = Depends(get_db)):
    p, d = actor.participant, actor.participant.deliberation
    s = d.sessions[-1] if d.sessions else None
    return {
        "name": actor.name, "participant_id": str(p.id), "status": p.invite_status, "knowledge_level": p.knowledge_level,
        "deliberation": {"id": str(d.id), "title": d.title, "process": d.process, "framing_question": d.framing_question, "stage": d.stage,
                         "moderator": d.moderator.person.full_name if d.moderator else None},
        "session": serialize.session_json(s),
        "documents": [{"file_name": x.file_name, "chars": x.char_count} for x in d.documents],
        "options": [{"id": str(c.id), "label": c.label} for c in d.concepts if c.kind == "option" and c.status == "confirmed" and c.seeded],
        "pre_done": bool(_survey(db, p, "pre")), "post_done": bool(_survey(db, p, "post")),
        "partner_live": not ai.is_mock("coach"),
    }


class AcceptIn(BaseModel):
    consent_research: bool = False


@router.post("/accept")
def accept(body: AcceptIn, actor: Actor = Depends(participant_only), db: Db = Depends(get_db)):
    p = actor.participant
    if p.invite_status == "invited":
        p.invite_status, p.responded_at = "accepted", m.now()
    p.consent_research = body.consent_research
    db.commit()
    return state(actor, db)


class StanceItem(BaseModel):
    concept_id: str
    value: str = Field(pattern="^(support|oppose|undecided)$")
    certainty: int | None = Field(default=None, ge=1, le=5)


class PreSurveyIn(BaseModel):
    knowledge_level: str = Field(pattern="^(novice|some|informed|expert)$")
    hopes: str = Field(default="", max_length=2000)
    stances: list[StanceItem] = []


@router.post("/pre-survey")
def pre_survey(body: PreSurveyIn, actor: Actor = Depends(participant_only), db: Db = Depends(get_db)):
    p = actor.participant
    if p.invite_status != "accepted":
        raise HTTPException(409, "Accept your invite first.")
    p.knowledge_level = body.knowledge_level
    resp = _survey(db, p, "pre") or m.SurveyResponse(participant_id=p.id, phase="pre")
    resp.answers, resp.submitted_at = {"knowledge_level": body.knowledge_level, "hopes": body.hopes.strip()}, m.now()
    db.add(resp)
    ours = {str(c.id) for c in p.deliberation.concepts}
    for st in body.stances:
        if st.concept_id in ours:
            db.add(m.PrivateStance(participant_id=p.id, concept_id=st.concept_id, phase="pre", value=st.value, certainty=st.certainty))
    db.commit()
    return state(actor, db)


@router.get("/partner")
def partner_history(actor: Actor = Depends(participant_only), db: Db = Depends(get_db)):
    rows = db.scalars(select(m.PartnerMessage).where(m.PartnerMessage.participant_id == actor.participant.id).order_by(m.PartnerMessage.created_at)).all()
    return [serialize.partner_json(x) for x in rows]


class PartnerIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    mode: str = "auto"


@router.post("/partner")
def partner(body: PartnerIn, actor: Actor = Depends(participant_only), db: Db = Depends(get_db)):
    p = actor.participant
    if p.invite_status != "accepted":
        raise HTTPException(409, "Accept your invite first.")
    if not p.deliberation.documents:
        raise HTTPException(409, "The organiser has not added any materials yet, so the partner has nothing to draw on.")
    try:
        reply = ai.partner_reply(db, p, body.message.strip(), body.mode)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(502, "The partner could not answer just now. Please try again.") from exc
    return serialize.partner_json(reply)


# ---------------------------------------------------------------- reflection
@router.get("/reflection")
def reflection_form(actor: Actor = Depends(participant_only), db: Db = Depends(get_db)):
    p, d = actor.participant, actor.participant.deliberation
    flow = serialize.flow(d, db, staff=False)
    names = {x["id"]: x["name"] for x in serialize.people(d)}
    before = _latest_stances(db, p, ("pre",))
    topics = []
    for c in [c for c in flow["concepts"] if c["kind"] == "option"]:
        family = {c["id"]} | {x["id"] for x in flow["concepts"] if x["parent_id"] == c["id"]}
        labels = {x["id"]: x["label"] for x in flow["concepts"]}
        points = [
            {"entry_id": e["id"], "speaker": names.get(e["speaker"], "Someone"), "mine": e["speaker"] == str(p.id), "position": e["position"], "paraphrase": e["paraphrase"],
             "subpoint": labels[e["concept_id"]] if e["concept_id"] != c["id"] else None}
            for e in flow["entries"] if e["concept_id"] in family
        ]
        st = before.get(c["id"])
        topics.append({"concept_id": c["id"], "label": c["label"], "view_before": st.value if st else None, "points": [x for x in points if not x["mine"]]})
    done = _survey(db, p, "post")
    return {"open": d.stage in ("pending_debrief", "complete"), "submitted": bool(done), "topics": topics}


class PointIn(BaseModel):
    entry_id: str
    effect: str = Field(pattern="^(moved|reinforced|not_persuasive)$")


class TopicIn(BaseModel):
    concept_id: str
    view_after: str = Field(pattern="^(support|oppose|undecided)$")
    certainty_after: int | None = Field(default=None, ge=1, le=5)
    moved_note: str = Field(default="", max_length=2000)
    not_persuasive_note: str = Field(default="", max_length=2000)
    points: list[PointIn] = []


class ReflectionIn(BaseModel):
    topics: list[TopicIn] = []
    answers: dict = {}


@router.post("/reflection")
def submit_reflection(body: ReflectionIn, actor: Actor = Depends(participant_only), db: Db = Depends(get_db)):
    p, d = actor.participant, actor.participant.deliberation
    if d.stage not in ("pending_debrief", "complete"):
        raise HTTPException(409, "The reflection opens when the deliberation ends.")
    if _survey(db, p, "post"):
        raise HTTPException(409, "You have already submitted your reflection.")
    resp = m.SurveyResponse(participant_id=p.id, phase="post", answers={k: v for k, v in body.answers.items() if isinstance(k, str)})
    db.add(resp)
    db.flush()
    before = _latest_stances(db, p, ("pre",))
    concepts = {str(c.id): c for c in d.concepts}
    entry_ids = set(str(x) for x in db.scalars(select(m.FlowEntry.id).where(m.FlowEntry.concept_id.in_([c.id for c in d.concepts] or [None]))).all())
    seen_points: set[str] = set()
    for t in body.topics:
        if t.concept_id not in concepts:
            continue
        st = before.get(t.concept_id)
        db.add(m.ReflectionConcept(survey_response_id=resp.id, concept_id=t.concept_id, view_before=st.value if st else None, view_after=t.view_after, certainty_after=t.certainty_after,
                                   moved_note=t.moved_note.strip() or None, not_persuasive_note=t.not_persuasive_note.strip() or None))
        db.add(m.PrivateStance(participant_id=p.id, concept_id=t.concept_id, phase="post", value=t.view_after, certainty=t.certainty_after))
        for pt in t.points:
            if pt.entry_id in entry_ids and pt.entry_id not in seen_points:
                seen_points.add(pt.entry_id)
                db.add(m.ReflectionPoint(survey_response_id=resp.id, entry_id=pt.entry_id, effect=pt.effect))
    db.commit()
    return {"ok": True}
