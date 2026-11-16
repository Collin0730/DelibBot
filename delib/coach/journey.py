"""Update a participant's journey after a conversation (one cheap model call)."""

from __future__ import annotations

from .. import prompts
from ..config import DeliberationConfig
from ..llm.base import LLMClient, LLMResponse, Message
from .state import ParticipantJourney, StatedView

_STR_LIST = {"type": "array", "items": {"type": "string"}}

JOURNEY_SCHEMA = {
    "type": "object",
    "properties": {
        "topics_explored": _STR_LIST,
        "open_questions": _STR_LIST,
        "stated_views": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"topic": {"type": "string"}, "in_their_words": {"type": "string"}},
                "required": ["topic", "in_their_words"],
                "additionalProperties": False,
            },
        },
        "concerns_raised": _STR_LIST,
    },
    "required": ["topics_explored", "open_questions", "stated_views", "concerns_raised"],
    "additionalProperties": False,
}


def update_journey(
    client: LLMClient, config: DeliberationConfig, journey: ParticipantJourney, conversation: list[Message]
) -> LLMResponse:
    transcript = "\n".join(
        f"{'PARTICIPANT' if m.role == 'user' else 'COACH'}: {m.content}" for m in conversation
    )
    system = prompts.render("journey_update", deliberation_context=config.context_block())
    resp = client.chat_json(system, [Message("user", transcript)], JOURNEY_SCHEMA, "journey_update")
    data = resp.data or {}
    journey.conversations += 1
    _extend_unique(journey.topics_explored, data.get("topics_explored", []))
    _extend_unique(journey.open_questions, data.get("open_questions", []))
    _extend_unique(journey.concerns_raised, data.get("concerns_raised", []))
    for v in data.get("stated_views", []):
        journey.stated_views.append(
            StatedView(topic=v["topic"], in_their_words=v["in_their_words"], conversation=journey.conversations)
        )
    return resp


def _extend_unique(target: list[str], items: list[str]) -> None:
    lower = {t.lower() for t in target}
    for it in items:
        if it and it.lower() not in lower:
            target.append(it)
            lower.add(it.lower())
