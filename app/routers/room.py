"""The live discussion: room state, messages, the flow, and the WebSocket."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as Db

from .. import ai, serialize
from .. import models as m
from ..db import SessionLocal, get_db
from ..realtime import Conn, hub, jobs
from ..security import Actor, current_actor, load_deliberation, participant_only, resolve_token

router = APIRouter(prefix="/api")


def _live_session(d: m.Deliberation) -> m.Session:
    if d.stage != "in_progress" or not d.sessions:
        raise HTTPException(409, "The discussion is not open right now.")
    return d.sessions[-1]


@router.get("/deliberations/{delib_id}/room")
def get_room(delib_id: str, actor: Actor = Depends(current_actor), db: Db = Depends(get_db)):
    return serialize.room(load_deliberation(db, delib_id, actor), db, actor)


@router.get("/deliberations/{delib_id}/flow")
def get_flow(delib_id: str, actor: Actor = Depends(current_actor), db: Db = Depends(get_db)):
    d = load_deliberation(db, delib_id, actor)
    return {"flow": serialize.flow(d, db, staff=actor.role != "participant"), "people": serialize.people(d)}


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


@router.post("/deliberations/{delib_id}/messages", status_code=201)
def send_message(delib_id: str, body: MessageIn, actor: Actor = Depends(current_actor), db: Db = Depends(get_db)):
    d = load_deliberation(db, delib_id, actor)
    s = _live_session(d)
    if actor.role == "participant":
        if actor.participant.invite_status != "accepted":
            raise HTTPException(403, "Accept your invite before joining the discussion.")
        msg = ai.post_message(db, s, body.body, participant=actor.participant)
    elif actor.role == "moderator":
        msg = ai.post_message(db, s, body.body, moderator=actor.moderator)
    else:
        raise HTTPException(403, "Organisers can watch the discussion but not post in it.")
    return ai.message_json(msg)


class StanceIn(BaseModel):
    concept_id: str
    value: str = Field(pattern="^(support|oppose|undecided)$")
    certainty: int | None = Field(default=None, ge=1, le=5)


@router.post("/deliberations/{delib_id}/stance")
def set_stance(delib_id: str, body: StanceIn, actor: Actor = Depends(participant_only), db: Db = Depends(get_db)):
    """A participant's private view on a row. Never shown to other participants."""
    d = load_deliberation(db, delib_id, actor)
    c = db.get(m.FlowConcept, body.concept_id)
    if not c or c.deliberation_id != d.id:
        raise HTTPException(404, "Row not found.")
    db.add(m.PrivateStance(participant_id=actor.participant.id, concept_id=c.id, phase="during" if d.stage == "in_progress" else "pre", value=body.value, certainty=body.certainty))
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- moderating the flow
class ReviewIn(BaseModel):
    status: str = Field(pattern="^(confirmed|rejected)$")


def _staff(actor: Actor) -> None:
    if actor.role == "participant":
        raise HTTPException(403, "Only the moderator can change the flow.")


@router.post("/concepts/{concept_id}/review")
def review_concept(concept_id: str, body: ReviewIn, actor: Actor = Depends(current_actor), db: Db = Depends(get_db)):
    _staff(actor)
    c = db.get(m.FlowConcept, concept_id)
    if not c:
        raise HTTPException(404, "Row not found.")
    d = load_deliberation(db, c.deliberation_id, actor, manage=True)
    c.status, c.reviewed_by, c.reviewed_at = body.status, actor.person.id, m.now()
    db.commit()
    hub.publish(d.id, {"type": "flow"})
    return serialize.flow(d, db, staff=True)


def _entry(db: Db, entry_id: str, actor: Actor) -> tuple[m.FlowEntry, m.Deliberation]:
    _staff(actor)
    e = db.get(m.FlowEntry, entry_id)
    if not e:
        raise HTTPException(404, "Entry not found.")
    c = db.get(m.FlowConcept, e.concept_id)
    return e, load_deliberation(db, c.deliberation_id, actor, manage=True)


@router.post("/entries/{entry_id}/review")
def review_entry(entry_id: str, body: ReviewIn, actor: Actor = Depends(current_actor), db: Db = Depends(get_db)):
    e, d = _entry(db, entry_id, actor)
    e.status, e.reviewed_by, e.reviewed_at = body.status, actor.person.id, m.now()
    if body.status == "confirmed":  # confirming an entry confirms the row it sits on
        c = db.get(m.FlowConcept, e.concept_id)
        if c.status == "proposed":
            c.status, c.reviewed_by, c.reviewed_at = "confirmed", actor.person.id, m.now()
    db.commit()
    hub.publish(d.id, {"type": "flow"})
    return serialize.flow(d, db, staff=True)


class CorrectIn(BaseModel):
    position: str = Field(pattern="^(support|dissent|question|clarify)$")
    paraphrase: str = Field(min_length=1, max_length=160)
    concept_id: str | None = None


@router.post("/entries/{entry_id}/correct")
def correct_entry(entry_id: str, body: CorrectIn, actor: Actor = Depends(current_actor), db: Db = Depends(get_db)):
    """Fix a wrong tag. The old entry stays in the history; the new one supersedes it."""
    e, d = _entry(db, entry_id, actor)
    concept_id = e.concept_id
    if body.concept_id:
        c = db.get(m.FlowConcept, body.concept_id)
        if not c or c.deliberation_id != d.id:
            raise HTTPException(422, "That row is not in this deliberation.")
        concept_id = c.id
    db.add(m.FlowEntry(
        concept_id=concept_id, participant_id=e.participant_id, moderator_id=e.moderator_id, message_id=e.message_id, topic_parent_id=e.topic_parent_id, supersedes_id=e.id,
        position=body.position, paraphrase=body.paraphrase.strip(), tag=e.tag, tagged_by_kind="moderator", tagged_by_person=actor.person.id, status="confirmed", reviewed_by=actor.person.id, reviewed_at=m.now(),
    ))
    db.commit()
    hub.publish(d.id, {"type": "flow"})
    return serialize.flow(d, db, staff=True)


@router.post("/deliberations/{delib_id}/standins/speak")
def standin_speak(delib_id: str, actor: Actor = Depends(current_actor), db: Db = Depends(get_db)):
    _staff(actor)
    d = load_deliberation(db, delib_id, actor, manage=True)
    s = _live_session(d)
    if not any(p.is_simulated for p in d.participants):
        raise HTTPException(409, "There are no AI stand-ins in this deliberation.")
    jobs.submit(ai._safe, ai.standin_reply, s.id, True)
    return {"ok": True}


# ---------------------------------------------------------------- live updates
@router.websocket("/ws/deliberations/{delib_id}")
async def room_socket(ws: WebSocket, delib_id: str, token: str = ""):
    with SessionLocal() as db:
        actor = resolve_token(db, token)
        try:
            d = load_deliberation(db, delib_id, actor) if actor else None
        except HTTPException:
            d = None
        if not d:
            await ws.close(code=4401)
            return
        conn = Conn(ws=ws, role=actor.role, participant_id=str(actor.participant.id) if actor.participant else None, name=actor.name)
        room = str(d.id)
    await ws.accept()
    hub.join(room, conn)
    hub.publish(room, {"type": "presence", "online": hub.online(room)})
    try:
        while True:
            await ws.receive_text()  # clients only send keep-alive pings
    except WebSocketDisconnect:
        pass
    finally:
        hub.leave(room, conn)
        hub.publish(room, {"type": "presence", "online": hub.online(room)})
