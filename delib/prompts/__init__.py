"""Prompt templates. Placeholders use string.Template syntax ($name)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from string import Template

_DIR = Path(__file__).parent


@lru_cache(maxsize=None)
def _raw(name: str) -> str:
    return (_DIR / f"{name}.md").read_text(encoding="utf-8")


def render(_template: str, /, **values: object) -> str:
    """Render a template. Missing placeholders raise KeyError."""
    return Template(_raw(_template)).substitute({k: "" if v is None else str(v) for k, v in values.items()})


def load(name: str) -> str:
    return _raw(name)
