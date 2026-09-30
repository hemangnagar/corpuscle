"""Model adapters. One real (Anthropic), one scripted (tests and offline demos).

Both return objects shaped like an Anthropic Message: .content (blocks with .type and, per
type, .text or .id/.name/.input), .stop_reason, .model. The loop in triage.py cares about
nothing else, so a scripted run exercises every code path a live run does.
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Protocol

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "medium"
KEY_VAR = "CORPUSCLE_ANTHROPIC_KEY"
BASE_URL_VAR = "CORPUSCLE_ANTHROPIC_BASE_URL"
DIRECT_BASE_URL = "https://api.anthropic.com"


def client_kwargs(env: dict | None = None) -> dict:
    """How the agent finds its credentials.

    CORPUSCLE_ANTHROPIC_KEY wins: the agent then talks straight to api.anthropic.com (or
    CORPUSCLE_ANTHROPIC_BASE_URL), ignoring any ANTHROPIC_BASE_URL a hosting harness set for
    its own traffic. Some hosts refuse to pass a variable named ANTHROPIC_API_KEY into a
    session, so the project-specific name is the reliable one. With it unset, the SDK's
    normal resolution applies: ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, or an `ant auth
    login` profile.
    """
    env = os.environ if env is None else env
    key = env.get(KEY_VAR)
    if key:
        return {"api_key": key, "base_url": env.get(BASE_URL_VAR, DIRECT_BASE_URL)}
    return {}


class Model(Protocol):
    model_id: str

    def create(self, *, system: str, messages: list[dict], tools: list[dict]): ...


class AnthropicModel:
    """Claude through the official SDK. Credentials per client_kwargs(): CORPUSCLE_ANTHROPIC_KEY
    first, else the SDK's own resolution. Server-side refusal fallback is on by default so a
    safety decline re-runs on a fallback model inside the same call."""

    def __init__(self, model_id: str | None = None, effort: str = DEFAULT_EFFORT, fallbacks: bool = True, max_tokens: int = 16000):
        import anthropic
        self.model_id = model_id or os.environ.get("CORPUSCLE_MODEL", DEFAULT_MODEL)
        self.effort, self.fallbacks, self.max_tokens = effort, fallbacks, max_tokens
        self.client = anthropic.Anthropic(**client_kwargs())

    def create(self, *, system: str, messages: list[dict], tools: list[dict]):
        kw = dict(model=self.model_id, max_tokens=self.max_tokens,
                  system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                  tools=tools, messages=messages, output_config={"effort": self.effort})
        if self.fallbacks:
            return self.client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kw)
        return self.client.messages.create(**kw)


def text(t: str):
    return SimpleNamespace(type="text", text=t)


def tool_use(name: str, input: dict, id: str | None = None):
    return SimpleNamespace(type="tool_use", name=name, input=input, id=id or f"toolu_{name}_{abs(hash(repr(input))) % 10**8}")


@dataclass
class ScriptedModel:
    """Replays a fixed sequence of turns. Each turn is a list of blocks; a turn with any tool_use
    block stops with tool_use, otherwise end_turn. Records what it was asked, for assertions."""
    turns: list[list]
    model_id: str = "scripted"
    stop_reasons: list[str] = field(default_factory=list)
    requests: list[dict] = field(default_factory=list)

    def create(self, *, system: str, messages: list[dict], tools: list[dict]):
        self.requests.append({"system": system, "messages": list(messages), "tools": tools})
        i = len(self.requests) - 1
        if i >= len(self.turns):
            content, stop = [text("(script exhausted)")], "end_turn"
        else:
            content = self.turns[i]
            stop = self.stop_reasons[i] if i < len(self.stop_reasons) else ("tool_use" if any(b.type == "tool_use" for b in content) else "end_turn")
        return SimpleNamespace(content=content, stop_reason=stop, model=self.model_id, stop_details=None)
