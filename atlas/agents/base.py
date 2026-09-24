"""A small async agent: a system prompt, a set of tools, and the tool-use loop."""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import anthropic

from atlas.config import settings

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


class Agent:
    def __init__(self, name: str, system: str, tools: list[Tool], effort: str,
                 client: anthropic.AsyncAnthropic | None = None, max_tokens: int = 16000):
        self.name, self.system, self.effort, self.max_tokens = name, system, effort, max_tokens
        self.tools = {t.name: t for t in tools}
        self.client = client or anthropic.AsyncAnthropic()

    async def _call_tool(self, block) -> dict:
        tool = self.tools.get(block.name)
        try:
            if tool is None:
                raise KeyError(f"unknown tool {block.name}")
            content, is_error = await tool(**(block.input or {})), False
        except Exception as exc:  # the model gets the error and can recover or explain
            log.exception("%s tool %s failed", self.name, block.name)
            content, is_error = f"Error: {exc}", True
        return {"type": "tool_result", "tool_use_id": block.id, "content": content, "is_error": is_error}

    async def run(self, messages: list[dict]) -> str:
        """Loop until the model stops calling tools. `messages` is extended in place."""
        for _ in range(MAX_STEPS):
            response = await self.client.beta.messages.create(
                model=settings.model,
                max_tokens=self.max_tokens,
                system=self.system,          # frozen text: keeps the cached prefix stable
                tools=[t.spec() for t in self.tools.values()],
                messages=messages,
                output_config={"effort": self.effort},
                cache_control={"type": "ephemeral"},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "refusal":
                return "I can't help with that one."
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason != "tool_use" or not tool_uses:
                return "".join(b.text for b in response.content if b.type == "text").strip()

            # Run parallel tool calls concurrently; all results go back in one user turn.
            results = await asyncio.gather(*(self._call_tool(b) for b in tool_uses))
            messages.append({"role": "user", "content": list(results)})
        return "I ran out of steps working on that. Try asking something narrower."

    async def ask(self, request: str) -> str:
        return await self.run([{"role": "user", "content": request}])
