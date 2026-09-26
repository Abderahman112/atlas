"""A small async agent: a system prompt, a set of tools, and the tool-use loop.
Every step is reported to the event bus so Atlas Town can show it live."""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import anthropic

from atlas.config import settings
from atlas.events import AgentState, bus

log = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_STEPS = 12


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    fn: Callable[..., Any] | Callable[..., Awaitable[Any]]

    def spec(self) -> dict:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}

    async def __call__(self, **kwargs) -> str:
        result = self.fn(**kwargs)
        if inspect.isawaitable(result):
            result = await result
        return result if isinstance(result, str) else json.dumps(result, default=str, ensure_ascii=False)


def schema(props: dict | None = None, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props or {}, "required": required or []}


def describe_call(name: str, args: dict) -> str:
    """One readable line for the town's speech bubbles, e.g. 'search_mail: is:unread'."""
    if not args:
        return name
    first = next(iter(args.values()))
    return f"{name}: {str(first)[:80]}"


class Agent:
    def __init__(self, name: str, system: str, tools: list[Tool], effort: str,
                 client: anthropic.AsyncAnthropic | None = None, max_tokens: int = 16000,
                 title: str | None = None, role: str = "", building: str = ""):
        self.name, self.system, self.max_tokens = name, system, max_tokens
        self.tools = {t.name: t for t in tools}
        self.client = client or anthropic.AsyncAnthropic()
        self.state = bus.register(AgentState(name, title or name.title(), role, building, effort=effort))

    async def _call_tool(self, block) -> dict:
        tool = self.tools.get(block.name)
        try:
            if tool is None:
                raise KeyError(f"unknown tool {block.name}")
            content, is_error = await tool(**(block.input or {})), False
        except Exception as exc:  # the model gets the error and can recover or explain
            log.exception("%s tool %s failed", self.name, block.name)
            content, is_error = f"Error: {exc}", True
        bus.emit(self.name, "tool_result", content[:300], tool=block.name, ok=not is_error)
        return {"type": "tool_result", "tool_use_id": block.id, "content": content, "is_error": is_error}

    def _count_usage(self, usage) -> None:
        s = self.state
        s.calls += 1
        s.input_tokens += getattr(usage, "input_tokens", 0) or 0
        s.output_tokens += getattr(usage, "output_tokens", 0) or 0
        s.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
        s.cache_write_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0

    async def run(self, messages: list[dict]) -> str:
        """Loop until the model stops calling tools. `messages` is extended in place."""
        if self.state.paused:
            bus.emit(self.name, "blocked", "Paused, request declined")
            return f"The {self.state.title} agent is paused by the user right now."
        try:
            for _ in range(MAX_STEPS):
                bus.set_status(self.name, "thinking", "Thinking…")
                response = await self.client.beta.messages.create(
                    model=settings.model,
                    max_tokens=self.max_tokens,
                    system=self.system,          # frozen text: keeps the cached prefix stable
                    tools=[t.spec() for t in self.tools.values()],
                    messages=messages,
                    output_config={"effort": self.state.effort},
                    cache_control={"type": "ephemeral"},
                    betas=[FALLBACK_BETA],
                    fallbacks="default",
                )
                self._count_usage(getattr(response, "usage", None))
                messages.append({"role": "assistant", "content": response.content})

                if response.stop_reason == "refusal":
                    bus.emit(self.name, "reply", "Declined the request")
                    return "I can't help with that one."
                tool_uses = [b for b in response.content if b.type == "tool_use"]
                if response.stop_reason != "tool_use" or not tool_uses:
                    text = "".join(b.text for b in response.content if b.type == "text").strip()
                    bus.emit(self.name, "reply", text)
                    return text

                for b in tool_uses:
                    self.state.tool_calls += 1
                    bus.emit(self.name, "tool_call", describe_call(b.name, b.input or {}),
                             tool=b.name, input=b.input)
                bus.set_status(self.name, "working", " · ".join(describe_call(b.name, b.input or {})
                                                                for b in tool_uses))
                # Run parallel tool calls concurrently; all results go back in one user turn.
                results = await asyncio.gather(*(self._call_tool(b) for b in tool_uses))
                messages.append({"role": "user", "content": list(results)})
            return "I ran out of steps working on that. Try asking something narrower."
        except Exception as exc:
            bus.emit(self.name, "error", str(exc))
            bus.set_status(self.name, "error", str(exc))
            raise
        finally:
            if self.state.status != "error":
                bus.set_status(self.name, "idle")

    async def ask(self, request: str) -> str:
        return await self.run([{"role": "user", "content": request}])
