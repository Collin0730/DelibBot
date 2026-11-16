"""Anthropic (Claude) adapter.

Structured output uses forced tool use: the schema becomes a tool's
``input_schema`` and ``tool_choice`` forces the model to call it, which is
supported across Claude models and also on Bedrock / Vertex deployments.
"""

from __future__ import annotations

from typing import Any

from .base import LLMClient, LLMError, Message, ModelProfile, Usage, extract_json, schema_instructions


class AnthropicClient(LLMClient):
    provider = "anthropic"

    def __init__(self, profile: ModelProfile):
        super().__init__(profile)
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover
            raise LLMError("Install the Anthropic SDK: pip install anthropic") from e
        kwargs: dict[str, Any] = {
            "api_key": self._api_key(),
            "max_retries": 0,  # retries are handled in LLMClient
            "timeout": profile.timeout_s,
        }
        if profile.base_url:
            kwargs["base_url"] = profile.base_url
        self._client = anthropic.Anthropic(**kwargs)

    def _base_kwargs(
        self, system: str, messages: list[Message], max_tokens: int, temperature: float | None
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.profile.model,
            "max_tokens": max_tokens,
            "messages": [m.to_dict() for m in messages],
            **self.profile.extra,
        }
        if system:
            kwargs["system"] = system
        if temperature is not None:
            kwargs["temperature"] = temperature
        return kwargs

    @staticmethod
    def _usage(resp: Any) -> Usage:
        u = getattr(resp, "usage", None)
        return Usage(getattr(u, "input_tokens", 0) or 0, getattr(u, "output_tokens", 0) or 0)

    def _chat(self, system, messages, max_tokens, temperature):
        resp = self._client.messages.create(**self._base_kwargs(system, messages, max_tokens, temperature))
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")
        return text, self._usage(resp), resp

    def _chat_json(self, system, messages, schema, schema_name, max_tokens, temperature):
        if self.profile.json_mode != "native":
            text, usage, resp = self._chat(system + schema_instructions(schema), messages, max_tokens, temperature)
            return extract_json(text), usage, resp
        kwargs = self._base_kwargs(system, messages, max_tokens, temperature)
        kwargs["tools"] = [
            {
                "name": schema_name,
                "description": "Record the structured result.",
                "input_schema": schema,
            }
        ]
        kwargs["tool_choice"] = {"type": "tool", "name": schema_name}
        resp = self._client.messages.create(**kwargs)
        for block in resp.content:
            if getattr(block, "type", "") == "tool_use":
                return dict(block.input), self._usage(resp), resp
        raise LLMError("Claude did not return the forced tool call")
