"""Load model profiles and role assignments from YAML, and build clients."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from .base import LLMClient, LLMError, ModelProfile


class ModelRegistry(BaseModel):
    profiles: dict[str, ModelProfile]
    # Role name (coach, participant_sim, judge, journey, embedder) -> profile name
    roles: dict[str, str | None] = Field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "ModelRegistry":
        raw: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        profiles = {}
        for name, spec in (raw.get("profiles") or {}).items():
            profiles[name] = ModelProfile(name=name, **spec)
        reg = cls(profiles=profiles, roles=raw.get("roles") or {})
        for role, prof in reg.roles.items():
            if prof and prof not in reg.profiles:
                raise LLMError(f"Role '{role}' points to unknown profile '{prof}'")
        return reg

    def profile(self, name_or_role: str) -> ModelProfile:
        name = self.roles.get(name_or_role, name_or_role)
        if name not in self.profiles:
            raise LLMError(f"Unknown model profile or role: '{name_or_role}'")
        return self.profiles[name]

    def client(self, name_or_role: str) -> LLMClient:
        return build_client(self.profile(name_or_role))

    def has_role(self, role: str) -> bool:
        return bool(self.roles.get(role))


def build_client(profile: ModelProfile) -> LLMClient:
    if profile.provider == "anthropic":
        from .anthropic_client import AnthropicClient

        return AnthropicClient(profile)
    if profile.provider == "openai":
        from .openai_client import OpenAIClient

        return OpenAIClient(profile)
    if profile.provider == "openai_compatible":
        from .openai_client import OpenAICompatibleClient

        return OpenAICompatibleClient(profile)
    if profile.provider == "mock":
        from .mock_client import MockClient

        return MockClient(profile)
    raise LLMError(f"Unsupported provider: {profile.provider}")
