"""Shapes returned by the API."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session as Db

from . import ai
from . import models as m
from .realtime import hub
from .security import Actor


def iso(dt):
    return dt.isoformat() if dt else None


def session_json(s: m.Session | None) -> dict | None:
    if not s:
        return None
    return {"id": str(s.id), "scheduled_start": iso(s.scheduled_start), "duration_minutes": s.duration_minutes, "format": s.format, "started_at": iso(s.started_at), "ended_at": iso(s.ended_at)}


def counts(d: m.Deliberation, db: Db) -> dict:
    active = [p for p in d.participants if p.invite_status != "cancelled"]
    posts = set(db.scalars(select(m.SurveyResponse.participant_id).where(m.SurveyResponse.phase == "post", m.SurveyResponse.participant_id.in_([p.id for p in active] or [None]))).all())
    return {
        "documents": len(d.documents),
        "participants": len(active),
        "people": len([p for p in active if not p.is_simulated]),
        "standins": len([p for p in active if p.is_simulated]),
        "accepted": len([p for p in active if p.invite_status == "accepted"]),
        "cancelled": len(d.participants) - len(active),
        "reflections": len(posts),
    }


def tile(d: m.Deliberation, db: Db) -> dict:
    s = d.sessions[-1] if d.sessions else None
    run = latest_eval(d)
    return {
        "id": str(d.id), "title": d.title, "process": d.process, "framing_question": d.framing_question, "stage": d.stage,
        "moderator": {"id": str(d.moderator.id), "name": d.moderator.person.full_name} if d.moderator else None,
        "date": iso(s.scheduled_start) if s else None, "counts": counts(d, db),
        "eval_status": run.status if run else None, "eval_stale": eval_stale(d, run),
    }


def latest_eval(d: m.Deliberation) -> m.EvalRun | None:
    return d.eval_runs[-1] if d.eval_runs else None


def eval_stale(d: m.Deliberation, run: m.EvalRun | None) -> bool:
    if not run:
        return False
    return run.document_count != len(d.documents) or any(doc.uploaded_at > run.started_at for doc in d.documents)


def eval_json(d: m.Deliberation) -> dict | None:
    run = latest_eval(d)
    if not run:
        return None
    return {
        "id": str(run.id), "status": run.status, "progress": run.progress, "health": float(run.health_score) if run.health_score is not None else None,
        "stale": eval_stale(d, run), "error": run.error, "coach_model": run.coach_model, "judge_model": run.judge_model, "prompt_version": run.prompt_version,
        "cost_usd": float(run.cost_usd) if run.cost_usd is not None else None, "finished_at": iso(run.finished_at),
        "metrics": [
            {"metric": x.metric, "label": ai.EVAL_LABELS.get(x.metric, x.metric), "result": float(x.result), "goal": float(x.goal), "higher_is_better": x.higher_is_better, "attainment": float(x.attainment)}
            for x in sorted(run.metrics, key=lambda x: [k for k, *_ in ai.EVAL_METRICS].index(x.metric) if x.metric in ai.EVAL_LABELS else 99)
        ],
    }


def workspace(d: m.Deliberation, db: Db, actor: Actor) -> dict:
    full = actor.role == "organiser"
    surveys = db.execute(select(m.SurveyResponse.participant_id, m.SurveyResponse.phase).where(m.SurveyResponse.participant_id.in_([p.id for p in d.participants] or [None]))).all()
    done = {(str(pid), phase) for pid, phase in surveys}
    out = tile(d, db)
    out.update({
        "documents": [{"id": str(x.id), "file_name": x.file_name, "ext": x.file_ext, "chars": x.char_count, "indexed": bool(x.indexed_at)} for x in d.documents],
        "eval": eval_json(d),
        "options": [{"id": str(c.id), "label": c.label, "seeded": c.seeded} for c in d.concepts if c.kind == "option" and c.status == "confirmed"],
        "participants": [
            {
                "id": str(p.id), "name": p.person.full_name, "pseudonym": p.pseudonym, "status": p.invite_status, "simulated": p.is_simulated,
                "email": p.person.email if full and not p.is_simulated else None, "link": f"/join/{p.invite_token}" if full and not p.is_simulated else None,
                "joined": bool(p.joined_at), "pre_done": (str(p.id), "pre") in done, "post_done": (str(p.id), "post") in done,
            }
            for p in d.participants
        ],
        "session": session_json(d.sessions[-1] if d.sessions else None),
        "models": ai.model_status(),
    })
    return out


def flow(d: m.Deliberation, db: Db, staff: bool) -> dict:
    statuses = ("confirmed", "proposed") if staff else ("confirmed",)
    concepts = [c for c in d.concepts if c.status in statuses]
    ids = [c.id for c in concepts]
    entries = db.scalars(select(m.FlowEntry).where(m.FlowEntry.concept_id.in_(ids or [None]), m.FlowEntry.status.in_(statuses)).order_by(m.FlowEntry.created_at)).all()
    superseded = set(db.scalars(select(m.FlowEntry.supersedes_id).where(m.FlowEntry.supersedes_id.is_not(None), m.FlowEntry.status != "rejected", m.FlowEntry.concept_id.in_(
        select(m.FlowConcept.id).where(m.FlowConcept.deliberation_id == d.id)))).all())
    entries = [e for e in entries if e.id not in superseded]
    raiser = {c.id: c.raised_by_participant for c in concepts}
    answered = {e.concept_id for e in entries if e.status == "confirmed" and raiser.get(e.concept_id) != e.participant_id}
    return {
        "concepts": [
            {"id": str(c.id), "parent_id": str(c.parent_id) if c.parent_id else None, "kind": c.kind, "label": c.label, "status": c.status, "seeded": c.seeded,
             "raised_by": str(c.raised_by_participant or c.raised_by_moderator or "") or None, "raised_in_message": str(c.raised_in_message) if c.raised_in_message else None,
             "tagged_by": c.tagged_by_kind, "unanswered": c.status == "confirmed" and not c.seeded and c.id not in answered}
            for c in concepts
        ],
        "entries": [
            {"id": str(e.id), "concept_id": str(e.concept_id), "speaker": str(e.participant_id or e.moderator_id), "position": e.position, "paraphrase": e.paraphrase, "tag": e.tag,
             "status": e.status, "message_id": str(e.message_id) if e.message_id else None, "reply_to": str(e.topic_parent_id) if e.topic_parent_id else None,
             "tagged_by": e.tagged_by_kind, "confidence": float(e.confidence) if e.confidence is not None else None}
            for e in entries
        ],
    }


def people(d: m.Deliberation) -> list[dict]:
    online = set(hub.online(str(d.id)))
    out = []
    if d.moderator:
        out.append({"id": str(d.moderator.id), "name": d.moderator.person.full_name, "kind": "moderator", "simulated": False, "online": True})
    for p in d.participants:
        if p.invite_status == "accepted":
            out.append({"id": str(p.id), "name": p.person.full_name, "pseudonym": p.pseudonym, "kind": "participant", "simulated": p.is_simulated, "online": p.is_simulated or str(p.id) in online})
    return out


def room(d: m.Deliberation, db: Db, actor: Actor) -> dict:
    s = d.sessions[-1] if d.sessions else None
    msgs = db.scalars(select(m.Message).where(m.Message.session_id == s.id).order_by(m.Message.seq)).all() if s else []
    me = {"role": actor.role, "name": actor.name, "id": str(actor.participant.id) if actor.participant else str(actor.moderator.id) if actor.moderator else None}
    out = {
        "deliberation": {"id": str(d.id), "title": d.title, "process": d.process, "framing_question": d.framing_question, "stage": d.stage},
        "me": me, "people": people(d), "session": session_json(s), "messages": [ai.message_json(x) for x in msgs],
        "flow": flow(d, db, staff=actor.role != "participant"), "stances": {}, "whispers": [],
        "can_post": actor.role == "participant" or (actor.role == "moderator" and d.moderator_id == actor.moderator.id),
    }
    if actor.participant:
        for st in db.scalars(select(m.PrivateStance).where(m.PrivateStance.participant_id == actor.participant.id).order_by(m.PrivateStance.set_at)).all():
            out["stances"][str(st.concept_id)] = {"value": st.value, "certainty": st.certainty, "phase": st.phase}
        if s:
            out["whispers"] = [{"id": str(w.id), "body": w.body, "shown_at": iso(w.shown_at)} for w in db.scalars(select(m.PartnerWhisper).where(m.PartnerWhisper.participant_id == actor.participant.id, m.PartnerWhisper.session_id == s.id).order_by(m.PartnerWhisper.shown_at)).all()]
    return out


def partner_json(x: m.PartnerMessage) -> dict:
    return {"id": str(x.id), "role": x.role, "body": x.body, "sources": x.sources or [], "created_at": iso(x.created_at)}
