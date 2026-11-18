"""After the session: the organiser review and the data export."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session as Db

from .. import ai, serialize
from .. import models as m
from ..db import get_db
from ..security import Actor, current_actor, load_deliberation, organiser_only

router = APIRouter(prefix="/api")
VIEWS = ("support", "oppose", "undecided")


@router.get("/deliberations/{delib_id}/review")
def review(delib_id: str, actor: Actor = Depends(current_actor), db: Db = Depends(get_db)):
    d = load_deliberation(db, delib_id, actor, manage=True)
    s = d.sessions[-1] if d.sessions else None
    flow = serialize.flow(d, db, staff=False)
    labels = {c["id"]: c["label"] for c in flow["concepts"]}
    parts = [p for p in d.participants if p.invite_status == "accepted"]
    pids = [p.id for p in parts]
    surveys = db.scalars(select(m.SurveyResponse).where(m.SurveyResponse.participant_id.in_(pids or [None]))).all()
    pre = {str(x.participant_id): x for x in surveys if x.phase == "pre"}
    post = {str(x.participant_id): x for x in surveys if x.phase == "post"}
    by_resp = {x.id: str(x.participant_id) for x in surveys}
    refl = db.scalars(select(m.ReflectionConcept).where(m.ReflectionConcept.survey_response_id.in_(list(by_resp) or [None]))).all()
    points = db.scalars(select(m.ReflectionPoint).where(m.ReflectionPoint.survey_response_id.in_(list(by_resp) or [None]))).all()
    pre_stance: dict[tuple[str, str], str] = {}
    for st in db.scalars(select(m.PrivateStance).where(m.PrivateStance.participant_id.in_(pids or [None]), m.PrivateStance.phase == "pre").order_by(m.PrivateStance.set_at)).all():
        pre_stance[(str(st.participant_id), str(st.concept_id))] = st.value
    entry_concept = {e["id"]: e["concept_id"] for e in flow["entries"]}
    topics = []
    for c in [c for c in flow["concepts"] if c["kind"] == "option"]:
        family = {c["id"]} | {x["id"] for x in flow["concepts"] if x["parent_id"] == c["id"]}
        entries = [e for e in flow["entries"] if e["concept_id"] in family]
        tally = {e["id"]: {"moved": 0, "reinforced": 0, "not_persuasive": 0} for e in entries}
        for pt in points:
            if str(pt.entry_id) in tally:
                tally[str(pt.entry_id)][pt.effect] += 1
        before = {v: 0 for v in VIEWS} | {"none": 0}
        after = {v: 0 for v in VIEWS} | {"none": 0}
        responses = []
        for p in parts:
            if p.is_simulated:
                continue
            pid = str(p.id)
            r = next((x for x in refl if by_resp[x.survey_response_id] == pid and str(x.concept_id) == c["id"]), None)
            b = (r.view_before if r else None) or pre_stance.get((pid, c["id"]))
            a = r.view_after if r else None
            before[b or "none"] += 1
            after[a or "none"] += 1
            responses.append({
                "participant_id": pid, "view_before": b, "view_after": a, "certainty_after": r.certainty_after if r else None,
                "moved_note": r.moved_note if r else None, "not_persuasive_note": r.not_persuasive_note if r else None, "submitted": pid in post,
                "points": [{"entry_id": str(pt.entry_id), "effect": pt.effect} for pt in points if by_resp[pt.survey_response_id] == pid and entry_concept.get(str(pt.entry_id)) in family],
                "said": [e["id"] for e in entries if e["speaker"] == pid],
            })
        topics.append({
            "concept_id": c["id"], "label": c["label"], "before": before, "after": after, "responses": responses,
            "subpoints": [{"id": x["id"], "label": x["label"], "raised_by": x["raised_by"]} for x in flow["concepts"] if x["parent_id"] == c["id"]],
            "entries": [dict(e, subpoint=labels[e["concept_id"]] if e["concept_id"] != c["id"] else None, **tally[e["id"]]) for e in entries],
        })
    msgs = db.scalars(select(m.Message).where(m.Message.session_id == s.id).order_by(m.Message.seq)).all() if s else []
    whispers = db.scalars(select(m.PartnerWhisper).where(m.PartnerWhisper.participant_id.in_(pids or [None]))).all()
    return {
        "deliberation": serialize.tile(d, db),
        "people": [{"id": str(p.id), "name": p.person.full_name, "pseudonym": p.pseudonym, "simulated": p.is_simulated} for p in parts]
        + ([{"id": str(d.moderator.id), "name": d.moderator.person.full_name, "pseudonym": "Moderator", "simulated": False, "moderator": True}] if d.moderator else []),
        "topics": topics, "transcript": [ai.message_json(x) for x in msgs],
        "surveys": [{"participant_id": pid, "pre": pre[pid].answers if pid in pre else None, "post": post[pid].answers if pid in post else None} for pid in [str(p.id) for p in parts if not p.is_simulated]],
        "whispers": {"shown": len(whispers), "acted_on": len([w for w in whispers if w.acted_on_message])},
    }


@router.get("/deliberations/{delib_id}/export")
def export(delib_id: str, names: bool = False, actor: Actor = Depends(organiser_only), db: Db = Depends(get_db)):
    """Everything about one deliberation as JSON. Pseudonymous unless names=true.

    Private partner chats are left out. People who did not consent to research
    use are left out of the pseudonymous export's survey and stance data.
    """
    d = load_deliberation(db, delib_id, actor)
    s = d.sessions[-1] if d.sessions else None
    cids = [c.id for c in d.concepts]
    pids = [p.id for p in d.participants]
    consented = {p.id for p in d.participants if names or p.consent_research or p.is_simulated}

    def row(obj, *cols):
        return {c: (str(v) if hasattr(v, "hex") and not isinstance(v, (int, float)) else serialize.iso(v) if hasattr(v, "isoformat") else float(v) if v.__class__.__name__ == "Decimal" else v) for c in cols for v in [getattr(obj, c)]}

    entries = db.scalars(select(m.FlowEntry).where(m.FlowEntry.concept_id.in_(cids or [None])).order_by(m.FlowEntry.created_at)).all()
    surveys = db.scalars(select(m.SurveyResponse).where(m.SurveyResponse.participant_id.in_(list(consented) or [None]))).all()
    sids = [x.id for x in surveys]
    return {
        "schema_version": 1, "exported_at": serialize.iso(m.now()), "pseudonymous": not names,
        "deliberation": row(d, "id", "title", "process", "framing_question", "stage", "stage_changed_at", "created_at") | {"moderator_id": str(d.moderator_id) if d.moderator_id else None},
        "sessions": [row(x, "id", "scheduled_start", "duration_minutes", "format", "started_at", "ended_at") for x in d.sessions],
        "documents": [row(x, "id", "file_name", "file_ext", "sha256", "char_count", "indexed_at") for x in d.documents],
        "eval_runs": [row(x, "id", "suite", "coach_model", "judge_model", "prompt_version", "health_score", "status", "started_at", "finished_at")
                      | {"metrics": [row(k, "metric", "result", "goal", "higher_is_better", "attainment") for k in x.metrics]} for x in d.eval_runs],
        "participants": [row(p, "id", "pseudonym", "invite_status", "consent_research", "is_simulated", "joined_at") | ({"full_name": p.person.full_name, "email": p.person.email} if names else {}) for p in d.participants],
        "messages": [row(x, "id", "session_id", "seq", "speaker_kind", "participant_id", "moderator_id", "body", "sent_at") for x in (db.scalars(select(m.Message).where(m.Message.session_id == s.id).order_by(m.Message.seq)).all() if s else [])],
        "flow_concepts": [row(c, "id", "parent_id", "kind", "label", "position", "seeded", "raised_by_participant", "raised_by_moderator", "raised_in_message", "raised_at", "tagged_by_kind", "tagger_model", "status") for c in d.concepts],
        "flow_entries": [row(e, "id", "concept_id", "participant_id", "moderator_id", "message_id", "topic_parent_id", "supersedes_id", "position", "paraphrase", "tag", "tagged_by_kind", "tagger_model", "tagger_prompt_version", "confidence", "status", "created_at") for e in entries],
        "private_stances": [row(x, "id", "participant_id", "concept_id", "phase", "value", "certainty", "set_at") for x in db.scalars(select(m.PrivateStance).where(m.PrivateStance.participant_id.in_(list(consented) or [None]))).all()],
        "survey_responses": [row(x, "id", "participant_id", "phase", "answers", "submitted_at") for x in surveys],
        "reflection_concepts": [row(x, "survey_response_id", "concept_id", "view_before", "view_after", "certainty_after", "moved_note", "not_persuasive_note") for x in db.scalars(select(m.ReflectionConcept).where(m.ReflectionConcept.survey_response_id.in_(sids or [None]))).all()],
        "reflection_points": [row(x, "survey_response_id", "entry_id", "effect") for x in db.scalars(select(m.ReflectionPoint).where(m.ReflectionPoint.survey_response_id.in_(sids or [None]))).all()],
        "partner_whispers": [row(x, "id", "participant_id", "session_id", "concept_id", "body", "model", "prompt_version", "after_seq", "shown_at", "acted_on_message") for x in db.scalars(select(m.PartnerWhisper).where(m.PartnerWhisper.participant_id.in_(pids or [None]))).all()],
    }
