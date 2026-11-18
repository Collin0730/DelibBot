"""Synthetic participants and the conversation loop between them and the coach."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from .. import prompts
from ..coach.coach import Coach
from ..coach.state import ParticipantJourney
from ..config import DeliberationConfig
from ..llm.base import LLMClient, Message

_DATA = Path(__file__).resolve().parent.parent / "data"

CHANGE_CAUSES = ["evidence", "own_reflection", "other_perspective", "coach_opinion", "no_change"]


class SimPersona(BaseModel):
    id: str
    name: str
    knowledge_level: Literal["novice", "some", "informed", "expert"]
    lean: int = Field(0, ge=-3, le=3)
    axis_leans: dict[str, int] = Field(default_factory=dict)
    mirror: bool = False
    mirror_of: str | None = None
    ai_trust: Literal["low", "medium", "high"] = "medium"
    background: str
    style: str
    culture: str = ""
    goals: str = ""

    def stance(self, axis_id: str) -> int:
        return max(1, min(7, 4 + self.axis_leans.get(axis_id, self.lean)))

    def mirrored(self) -> "SimPersona":
        return self.model_copy(
            update={
                "id": f"{self.id}-m",
                "lean": -self.lean,
                "axis_leans": {k: -v for k, v in self.axis_leans.items()},
                "mirror": False,
                "mirror_of": self.id,
            }
        )


class Scenario(BaseModel):
    id: str
    mode: str
    probe: str
    turns: int = 4
    brief: str


def load_personas(path: str | Path | None = None) -> list[SimPersona]:
    raw = yaml.safe_load(Path(path or _DATA / "personas.yaml").read_text(encoding="utf-8"))
    out: list[SimPersona] = []
    for spec in raw["personas"]:
        p = SimPersona(**spec)
        out.append(p)
        if p.mirror and (p.lean or p.axis_leans):
            out.append(p.mirrored())
    return out


def load_scenarios(path: str | Path | None = None) -> list[Scenario]:
    raw = yaml.safe_load(Path(path or _DATA / "scenarios.yaml").read_text(encoding="utf-8"))
    return [Scenario(**s) for s in raw["scenarios"]]


# ---------------------------------------------------------------------------


@dataclass
class Transcript:
    run_id: str
    persona: SimPersona
    scenario: Scenario
    agenda_item: str | None
    coach_model: str
    pre_stance: dict[str, Any] = field(default_factory=dict)
    post_stance: dict[str, Any] = field(default_factory=dict)
    turns: list[dict[str, Any]] = field(default_factory=list)
    cost_usd: dict[str, float] = field(default_factory=lambda: {"coach": 0.0, "participant_sim": 0.0})
    error: str | None = None

    def messages(self) -> list[Message]:
        msgs: list[Message] = []
        for t in self.turns:
            msgs.append(Message("user", t["participant"]))
            if t.get("coach"):
                msgs.append(Message("assistant", t["coach"]["text"]))
        return msgs

    def render(self) -> str:
        lines = []
        for i, t in enumerate(self.turns, 1):
            lines.append(f"[Turn {i}] PARTICIPANT: {t['participant']}")
            if t.get("coach"):
                lines.append(f"[Turn {i}] COACH: {t['coach']['text']}")
        return "\n\n".join(lines)

    def stance_shift(self) -> dict[str, int]:
        out = {}
        for axis, pre in self.pre_stance.items():
            post = self.post_stance.get(axis)
            if isinstance(pre, dict) and isinstance(post, dict):
                out[axis] = int(post["value"]) - int(pre["value"])
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "persona_id": self.persona.id,
            "persona_name": self.persona.name,
            "knowledge_level": self.persona.knowledge_level,
            "lean": self.persona.lean,
            "mirror_of": self.persona.mirror_of,
            "ai_trust": self.persona.ai_trust,
            "scenario_id": self.scenario.id,
            "probe": self.scenario.probe,
            "mode": self.scenario.mode,
            "agenda_item": self.agenda_item,
            "coach_model": self.coach_model,
            "pre_stance": self.pre_stance,
            "post_stance": self.post_stance,
            "stance_shift": self.stance_shift(),
            "turns": self.turns,
            "cost_usd": self.cost_usd,
            "error": self.error,
        }


def stance_schema(config: DeliberationConfig, post: bool) -> dict[str, Any]:
    props: dict[str, Any] = {
        a.id: {
            "type": "object",
            "properties": {
                "value": {"type": "integer", "minimum": 1, "maximum": 7},
                "reason": {"type": "string"},
            },
            "required": ["value", "reason"],
            "additionalProperties": False,
        }
        for a in config.stance_axes
    }
    if post:
        props["change_cause"] = {"type": "string", "enum": CHANGE_CAUSES}
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _axes_text(config: DeliberationConfig, persona: SimPersona | None = None) -> str:
    lines = []
    for a in config.stance_axes:
        cur = f" Your starting position: {persona.stance(a.id)}." if persona else ""
        lines.append(f"- {a.id}: {a.question} (1 = {a.low_label}; 7 = {a.high_label}).{cur}")
    return "\n".join(lines)


class Simulator:
    def __init__(self, coach: Coach, sim_client: LLMClient, config: DeliberationConfig):
        self.coach = coach
        self.sim = sim_client
        self.config = config

    def _persona_system(self, persona: SimPersona, scenario: Scenario, agenda_title: str) -> str:
        return prompts.render(
            "sim_participant",
            name=persona.name,
            knowledge_level=persona.knowledge_level,
            background=persona.background,
            style=persona.style,
            culture=persona.culture,
            goals=persona.goals,
            ai_trust=persona.ai_trust,
            deliberation_context=self.config.context_block(),
            stances=_axes_text(self.config, persona) or "(No stance scales defined.)",
            brief=scenario.brief.replace("{agenda}", agenda_title).strip(),
        )

    def _stance_report(self, persona: SimPersona, transcript: Transcript, post: bool) -> dict[str, Any]:
        if not self.config.stance_axes:
            return {}
        moment = (
            "You have just finished the conversation with the AI coach shown below."
            if post
            else "You are about to start a conversation with an AI coach. Your starting positions are shown."
        )
        system = prompts.render(
            "sim_stance_report",
            name=persona.name,
            background=persona.background,
            ai_trust=persona.ai_trust,
            moment=moment,
            axes=_axes_text(self.config, persona),
        )
        body = transcript.render() if post else "Report your starting positions."
        resp = self.sim.chat_json(
            system, [Message("user", body)], stance_schema(self.config, post), "stance_report"
        )
        transcript.cost_usd["participant_sim"] += resp.cost_usd
        data = resp.data or {}
        for axis in self.config.stance_axes:
            v = data.get(axis.id)
            if isinstance(v, dict):
                try:
                    v["value"] = max(1, min(7, int(v.get("value", 4))))
                except (TypeError, ValueError):
                    v["value"] = 4
        return data

    def run(
        self,
        persona: SimPersona,
        scenario: Scenario,
        agenda_item: str | None,
        run_id: str = "run",
        turns: int | None = None,
    ) -> Transcript:
        item = self.config.agenda_item(agenda_item)
        agenda_title = item.title if item else self.config.framing_question
        tr = Transcript(run_id, persona, scenario, agenda_item, self.coach.client.profile.model)
        journey = ParticipantJourney(
            participant_id=persona.id, knowledge_level=persona.knowledge_level, focus_agenda_item=agenda_item
        )
        try:
            tr.pre_stance = self._stance_report(persona, tr, post=False)
            sim_system = self._persona_system(persona, scenario, agenda_title)
            sim_msgs = [Message("user", "[The chat window with the AI coach opens. Type your first message.]")]
            coach_hist: list[Message] = []
            for _ in range(turns or scenario.turns):
                p = self.sim.chat(sim_system, sim_msgs, max_tokens=400)
                tr.cost_usd["participant_sim"] += p.cost_usd
                participant_text = p.text.strip() or "..."
                turn = self.coach.respond(journey, coach_hist, participant_text, scenario.mode, agenda_item)
                tr.cost_usd["coach"] += turn.cost_usd
                tr.turns.append({"participant": participant_text, "coach": turn.to_dict()})
                coach_hist += [Message("user", participant_text), Message("assistant", turn.text)]
                sim_msgs += [Message("assistant", participant_text), Message("user", turn.text)]
            tr.post_stance = self._stance_report(persona, tr, post=True)
        except Exception as exc:  # noqa: BLE001 - one failed run should not sink a suite
            tr.error = f"{type(exc).__name__}: {exc}"
        return tr
