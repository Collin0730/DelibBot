"""Organiser and moderator endpoints: deliberations, materials, people, stages."""
from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as Db

from .. import ai, ingest, serialize, settings
from .. import models as m
from ..db import get_db
from ..realtime import hub, jobs
from ..security import Actor, current_actor, hash_password, load_deliberation, organiser_only, organiser_token, verify_password

router = APIRouter(prefix="/api")
EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def set_stage(db: Db, d: m.Deliberation, stage: str) -> None:
    d.stage = stage
    d.stage_changed_at = m.now()
    db.commit()
    hub.publish(d.id, {"type": "stage", "stage": stage})


def find_or_create_person(db: Db, name: str, email: str) -> m.Person:
    email = email.strip().lower()
    if not name.strip():
        raise HTTPException(422, "Add a name.")
    if not EMAIL.match(email):
        raise HTTPException(422, "Add a valid email address.")
    person = db.scalar(select(m.Person).where(m.Person.email == email))
    if not person:
        person = m.Person(full_name=name.strip(), email=email)
        db.add(person)
        db.flush()
    return person


# ---------------------------------------------------------------- sign-in
class Login(BaseModel):
    email: str
    password: str


@router.post("/auth/login")
def login(body: Login, db: Db = Depends(get_db)):
    org = db.scalar(select(m.Organiser).join(m.Person).where(m.Person.email == body.email.strip().lower()))
    if not org or not verify_password(body.password, org.password_hash):
        raise HTTPException(401, "That email and password do not match.")
    return {"token": organiser_token(org), "name": org.person.full_name}


@router.get("/me")
def me(actor: Actor = Depends(current_actor)):
    out = {"role": actor.role, "name": actor.name}
    if actor.participant:
        out["deliberation_id"] = str(actor.participant.deliberation_id)
    return out


@router.get("/health")
def health():
    return {"ok": True, "models": ai.model_status()}


# ---------------------------------------------------------------- deliberations
class DeliberationIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    framing_question: str = Field(min_length=1, max_length=1000)
    process: str | None = Field(default=None, max_length=200)
    moderator_id: str | None = None
    date: str | None = None  # optional rough date, YYYY-MM-DD


class DeliberationPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    framing_question: str | None = Field(default=None, min_length=1, max_length=1000)
    process: str | None = Field(default=None, max_length=200)
    moderator_id: str | None = None


def _moderator(db: Db, moderator_id: str | None) -> m.Moderator | None:
    if not moderator_id:
        return None
    mod = db.get(m.Moderator, moderator_id)
    if not mod or mod.removed_at:
        raise HTTPException(422, "That moderator is not available.")
    return mod


@router.get("/deliberations")
def list_deliberations(actor: Actor = Depends(current_actor), db: Db = Depends(get_db)):
    q = select(m.Deliberation).order_by(m.Deliberation.created_at.desc())
    if actor.role == "moderator":
        q = q.where(m.Deliberation.moderator_id == actor.moderator.id)
    elif actor.role != "organiser":
        raise HTTPException(403, "Only organisers and moderators can list deliberations.")
    return [serialize.tile(d, db) for d in db.scalars(q).all()]


@router.post("/deliberations", status_code=201)
def create_deliberation(body: DeliberationIn, actor: Actor = Depends(organiser_only), db: Db = Depends(get_db)):
    mod = _moderator(db, body.moderator_id)
    d = m.Deliberation(title=body.title.strip(), framing_question=body.framing_question.strip(), process=(body.process or "").strip() or None, moderator_id=mod.id if mod else None, created_by=actor.person.id)
    db.add(d)
    db.flush()
    if body.date:
        try:
            d.sessions.append(m.Session(scheduled_start=datetime.fromisoformat(body.date + "T10:00:00+00:00")))
        except ValueError:
            raise HTTPException(422, "The date must look like 2026-12-05.")
    db.commit()
    return serialize.workspace(d, db, actor)


@router.get("/deliberations/{delib_id}")
def get_deliberation(delib_id: str, actor: Actor = Depends(current_actor), db: Db = Depends(get_db)):
    return serialize.workspace(load_deliberation(db, delib_id, actor, manage=True), db, actor)


@router.patch("/deliberations/{delib_id}")
def patch_deliberation(delib_id: str, body: DeliberationPatch, actor: Actor = Depends(organiser_only), db: Db = Depends(get_db)):
    d = load_deliberation(db, delib_id, actor)
    data = body.model_dump(exclude_unset=True)
    if "title" in data:
        d.title = data["title"].strip()
    if "framing_question" in data:
        d.framing_question = data["framing_question"].strip()
    if "process" in data:
        d.process = (data["process"] or "").strip() or None
    if "moderator_id" in data:
        mod = _moderator(db, data["moderator_id"])
        d.moderator_id = mod.id if mod else None
    db.commit()
    return serialize.workspace(d, db, actor)


@router.delete("/deliberations/{delib_id}", status_code=204)
def delete_deliberation(delib_id: str, actor: Actor = Depends(organiser_only), db: Db = Depends(get_db)):
    d = load_deliberation(db, delib_id, actor)
    if d.stage not in ("none", "invited"):
        raise HTTPException(409, "A deliberation that has been scheduled or run cannot be deleted.")
    db.delete(d)
    db.commit()


# ---------------------------------------------------------------- materials and evaluation
@router.post("/deliberations/{delib_id}/documents")
async def upload_documents(delib_id: str, files: list[UploadFile] = File(...), actor: Actor = Depends(organiser_only), db: Db = Depends(get_db)):
    d = load_deliberation(db, delib_id, actor)
    existing = {x.file_name: x for x in d.documents}
    added, skipped = [], []
    for f in files:
        name = ingest.clean_name(f.filename)
        if name.startswith("."):
            continue
        data = await f.read()
        if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
            skipped.append({"file_name": name, "reason": f"Larger than {settings.MAX_UPLOAD_MB} MB."})
            continue
        try:
            doc = ingest.ingest(name, data)
        except Exception as exc:  # noqa: BLE001 - one bad file should not block the rest
            skipped.append({"file_name": name, "reason": str(exc) if isinstance(exc, ValueError) else f"{name}: could not be read."})
            continue
        if name in existing:
            if existing[name].sha256 == doc.sha256:
                continue
            db.delete(existing[name])
            db.flush()
        doc.deliberation_id = d.id
        db.add(doc)
        db.flush()
        existing[name] = doc
        added.append(name)
    db.commit()
    db.refresh(d)
    return {"added": added, "skipped": skipped, "deliberation": serialize.workspace(d, db, actor)}


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: str, actor: Actor = Depends(organiser_only), db: Db = Depends(get_db)):
    doc = db.get(m.Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found.")
    d = doc.deliberation
    d.documents.remove(doc)
    db.commit()
    return serialize.workspace(d, db, actor)


@router.post("/deliberations/{delib_id}/eval")
def start_eval(delib_id: str, actor: Actor = Depends(organiser_only), db: Db = Depends(get_db)):
    d = load_deliberation(db, delib_id, actor)
    if not d.documents:
        raise HTTPException(409, "Upload at least one document first.")
    run = serialize.latest_eval(d)
    if run and run.status == "running":
        raise HTTPException(409, "An evaluation is already running.")
    run = m.EvalRun(deliberation_id=d.id, coach_model=ai.profile_for("coach").model, judge_model=ai.profile_for("judge").model, prompt_version=ai.prompt_version(), document_count=len(d.documents))
    db.add(run)
    db.commit()
    db.refresh(d)
    jobs.submit(ai._safe, ai.run_eval, run.id)
    return serialize.workspace(d, db, actor)


# ---------------------------------------------------------------- options (seeded concepts)
class ConceptIn(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    parent_id: str | None = None


@router.post("/deliberations/{delib_id}/concepts")
def add_concept(delib_id: str, body: ConceptIn, actor: Actor = Depends(current_actor), db: Db = Depends(get_db)):
    d = load_deliberation(db, delib_id, actor, manage=True)
    parent = db.get(m.FlowConcept, body.parent_id) if body.parent_id else None
    if parent and (parent.deliberation_id != d.id or parent.parent_id):
        raise HTTPException(422, "A sub-point must sit under an option.")
    live = d.stage == "in_progress"
    c = m.FlowConcept(
        deliberation_id=d.id, parent_id=parent.id if parent else None, kind="subpoint" if parent else "option", label=body.label.strip(), position=len(d.concepts) + 1,
        seeded=not live, raised_by_moderator=actor.moderator.id if actor.moderator and live else None, tagged_by_kind="moderator", status="confirmed", reviewed_by=actor.person.id, reviewed_at=m.now(),
    )
    if live and not actor.moderator:
        c.seeded = True  # an organiser adding a row mid-session is not a speaker
    db.add(c)
    db.commit()
    db.refresh(d)
    hub.publish(d.id, {"type": "flow"})
    return serialize.workspace(d, db, actor)


@router.delete("/concepts/{concept_id}")
def delete_concept(concept_id: str, actor: Actor = Depends(organiser_only), db: Db = Depends(get_db)):
    c = db.get(m.FlowConcept, concept_id)
    if not c:
        raise HTTPException(404, "Option not found.")
    d = c.deliberation
    if d.stage not in ("none", "invited", "scheduled"):
        raise HTTPException(409, "Options cannot be removed once the deliberation has started.")
    d.concepts.remove(c)
    db.commit()
    return serialize.workspace(d, db, actor)


# ---------------------------------------------------------------- participants
class PersonIn(BaseModel):
    name: str
    email: str


def _participant(db: Db, participant_id: str, actor: Actor) -> m.Participant:
    p = db.get(m.Participant, participant_id)
    if not p:
        raise HTTPException(404, "Participant not found.")
    load_deliberation(db, p.deliberation_id, actor)
    return p


@router.post("/deliberations/{delib_id}/participants")
def add_participant(delib_id: str, body: PersonIn, actor: Actor = Depends(organiser_only), db: Db = Depends(get_db)):
    d = load_deliberation(db, delib_id, actor)
    if d.stage in ("pending_debrief", "complete"):
        raise HTTPException(409, "This deliberation has ended.")
    person = find_or_create_person(db, body.name, body.email)
    if any(p.person_id == person.id for p in d.participants):
        raise HTTPException(409, f"{person.email} is already on the list.")
    p = m.Participant(deliberation_id=d.id, person_id=person.id, pseudonym=ai._next_pseudonym(d))
    if d.stage != "none":  # invites have already gone out, so this person is invited straight away
        p.invite_status, p.invited_at = "invited", m.now()
    d.participants.append(p)
    db.commit()
    return serialize.workspace(d, db, actor)


class StandinsIn(BaseModel):
    count: int = Field(default=3, ge=1, le=4)


@router.post("/deliberations/{delib_id}/standins")
def add_standins(delib_id: str, body: StandinsIn, actor: Actor = Depends(current_actor), db: Db = Depends(get_db)):
    d = load_deliberation(db, delib_id, actor, manage=True)
    if d.stage in ("pending_debrief", "complete"):
        raise HTTPException(409, "This deliberation has ended.")
    if not ai.add_standins(db, d, body.count):
        raise HTTPException(409, "All four AI stand-ins are already in this deliberation.")
    db.commit()
    hub.publish(d.id, {"type": "people"})
    return serialize.workspace(d, db, actor)


@router.delete("/participants/{participant_id}")
def remove_participant(participant_id: str, actor: Actor = Depends(organiser_only), db: Db = Depends(get_db)):
    p = _participant(db, participant_id, actor)
    d = p.deliberation
    spoke = db.scalar(select(m.Message.id).where(m.Message.participant_id == p.id).limit(1))
    if spoke or (p.invite_status != "not_invited" and not p.is_simulated):
        raise HTTPException(409, "This person has already been invited. Cancel their invite instead.")
    d.participants.remove(p)
    db.commit()
    hub.publish(d.id, {"type": "people"})
    return serialize.workspace(d, db, actor)


@router.post("/participants/{participant_id}/cancel")
def cancel_invite(participant_id: str, actor: Actor = Depends(organiser_only), db: Db = Depends(get_db)):
    p = _participant(db, participant_id, actor)
    if p.deliberation.stage not in ("invited", "scheduled") or p.invite_status not in ("invited", "accepted"):
        raise HTTPException(409, "Invites can be cancelled after they are sent and before the session starts.")
    p.invite_status, p.cancelled_at = "cancelled", m.now()
    db.commit()
    return serialize.workspace(p.deliberation, db, actor)


@router.post("/participants/{participant_id}/reinvite")
def reinvite(participant_id: str, actor: Actor = Depends(organiser_only), db: Db = Depends(get_db)):
    p = _participant(db, participant_id, actor)
    if p.deliberation.stage not in ("invited", "scheduled") or p.invite_status != "cancelled":
        raise HTTPException(409, "Only a cancelled invite can be sent again, and only before the session starts.")
    p.invite_status, p.invited_at, p.cancelled_at, p.invite_token = "invited", m.now(), None, m.new_token()
    db.commit()
    return serialize.workspace(p.deliberation, db, actor)


# ---------------------------------------------------------------- stages
@router.post("/deliberations/{delib_id}/invites")
def send_invites(delib_id: str, actor: Actor = Depends(organiser_only), db: Db = Depends(get_db)):
    d = load_deliberation(db, delib_id, actor)
    if d.stage != "none":
        raise HTTPException(409, "Invites have already been sent.")
    if not any(not p.is_simulated for p in d.participants):
        raise HTTPException(409, "Add at least one participant first.")
    run = serialize.latest_eval(d)
    if not run or run.status not in ("passed", "below_goal"):
        raise HTTPException(409, "Run the evaluation on the Materials step before inviting anyone.")
    for p in d.participants:
        if p.invite_status == "not_invited":
            p.invite_status, p.invited_at = "invited", m.now()
    set_stage(db, d, "invited")
    return serialize.workspace(d, db, actor)


class ScheduleIn(BaseModel):
    scheduled_start: datetime
    duration_minutes: int = Field(default=120, ge=15, le=600)
    format: str = Field(default="online", pattern="^(online|in_person|hybrid)$")


@router.post("/deliberations/{delib_id}/schedule")
def schedule(delib_id: str, body: ScheduleIn, actor: Actor = Depends(organiser_only), db: Db = Depends(get_db)):
    d = load_deliberation(db, delib_id, actor)
    if d.stage not in ("invited", "scheduled"):
        raise HTTPException(409, "Send invites first." if d.stage == "none" else "This deliberation has already started.")
    s = d.sessions[-1] if d.sessions else None
    if not s:
        s = m.Session()
        d.sessions.append(s)
    s.scheduled_start, s.duration_minutes, s.format = body.scheduled_start, body.duration_minutes, body.format
    set_stage(db, d, "scheduled")
    return serialize.workspace(d, db, actor)


@router.post("/deliberations/{delib_id}/start")
def start(delib_id: str, actor: Actor = Depends(current_actor), db: Db = Depends(get_db)):
    d = load_deliberation(db, delib_id, actor, manage=True)
    if d.stage != "scheduled":
        raise HTTPException(409, "Only a scheduled deliberation can be started.")
    s = d.sessions[-1]
    s.started_at = m.now()
    set_stage(db, d, "in_progress")
    ai.post_message(db, s, "The deliberation has started. Framing question: " + d.framing_question, system=True)
    return serialize.workspace(d, db, actor)


@router.post("/deliberations/{delib_id}/end")
def end(delib_id: str, actor: Actor = Depends(current_actor), db: Db = Depends(get_db)):
    d = load_deliberation(db, delib_id, actor, manage=True)
    if d.stage != "in_progress":
        raise HTTPException(409, "This deliberation is not in progress.")
    s = d.sessions[-1]
    ai.post_message(db, s, "The deliberation has ended. Participants can now fill in their reflection.", system=True)
    s.ended_at = m.now()
    set_stage(db, d, "pending_debrief")
    return serialize.workspace(d, db, actor)


@router.post("/deliberations/{delib_id}/complete")
def complete(delib_id: str, actor: Actor = Depends(organiser_only), db: Db = Depends(get_db)):
    d = load_deliberation(db, delib_id, actor)
    if d.stage != "pending_debrief":
        raise HTTPException(409, "Only a deliberation that is pending debrief can be completed.")
    set_stage(db, d, "complete")
    return serialize.workspace(d, db, actor)


# ---------------------------------------------------------------- moderators
class ModeratorIn(BaseModel):
    name: str
    email: str
    organisation: str | None = None


def _moderators(db: Db) -> list[dict]:
    out = []
    for mod in db.scalars(select(m.Moderator).where(m.Moderator.removed_at.is_(None)).join(m.Person).order_by(m.Person.full_name)).all():
        mine = db.scalars(select(m.Deliberation).where(m.Deliberation.moderator_id == mod.id).order_by(m.Deliberation.created_at.desc())).all()
        item = lambda d: {"id": str(d.id), "title": d.title, "stage": d.stage, "date": serialize.iso(d.sessions[-1].scheduled_start) if d.sessions else None}  # noqa: E731
        out.append({
            "id": str(mod.id), "name": mod.person.full_name, "email": mod.person.email, "organisation": mod.organisation, "link": f"/m/{mod.access_token}",
            "current": [item(d) for d in mine if d.stage != "complete"], "past": [item(d) for d in mine if d.stage == "complete"],
        })
    return out


@router.get("/moderators")
def list_moderators(actor: Actor = Depends(organiser_only), db: Db = Depends(get_db)):
    return _moderators(db)


@router.post("/moderators", status_code=201)
def create_moderator(body: ModeratorIn, actor: Actor = Depends(organiser_only), db: Db = Depends(get_db)):
    person = find_or_create_person(db, body.name, body.email)
    mod = db.scalar(select(m.Moderator).where(m.Moderator.person_id == person.id))
    if mod and not mod.removed_at:
        raise HTTPException(409, f"{person.email} is already a moderator.")
    if mod:  # previously removed: bring them back with a fresh link
        mod.removed_at, mod.access_token, mod.invited_at = None, m.new_token(), m.now()
    else:
        mod = m.Moderator(person_id=person.id, invited_at=m.now())
        db.add(mod)
    mod.organisation = (body.organisation or "").strip() or None
    db.commit()
    return _moderators(db)


@router.delete("/moderators/{moderator_id}")
def remove_moderator(moderator_id: str, actor: Actor = Depends(organiser_only), db: Db = Depends(get_db)):
    mod = db.get(m.Moderator, moderator_id)
    if not mod or mod.removed_at:
        raise HTTPException(404, "Moderator not found.")
    unassigned = 0
    for d in db.scalars(select(m.Deliberation).where(m.Deliberation.moderator_id == mod.id, m.Deliberation.stage != "complete")).all():
        d.moderator_id = None  # past deliberations keep the link
        unassigned += 1
    mod.removed_at = m.now()
    db.commit()
    return {"unassigned": unassigned, "moderators": _moderators(db)}


def bootstrap_admin(db: Db) -> None:
    """Create the first organiser from ADMIN_EMAIL and ADMIN_PASSWORD if none exists."""
    if db.scalar(select(m.Organiser.id).limit(1)):
        return
    person = db.scalar(select(m.Person).where(m.Person.email == settings.ADMIN_EMAIL)) or m.Person(full_name=settings.ADMIN_NAME, email=settings.ADMIN_EMAIL)
    db.add(person)
    db.flush()
    db.add(m.Organiser(person_id=person.id, password_hash=hash_password(settings.ADMIN_PASSWORD)))
    db.commit()
