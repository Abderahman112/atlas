"""The assistant itself, independent of how you reach it (Telegram, the web UI, or both)."""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

import anthropic

from atlas.agents import tools as T
from atlas.agents.team import build_team
from atlas.config import settings
from atlas.db import DB
from atlas.events import bus
from atlas.proactive import Proactive

log = logging.getLogger(__name__)


class Assistant:
    def __init__(self, client: anthropic.AsyncAnthropic | None = None, db_path=None):
        self.db = DB(db_path or settings.db_path)
        self.atlas = build_team(self.db, client)
        self.lock = asyncio.Lock()  # one conversation turn at a time
        self.outlets: list[Callable[[str], Awaitable[None]]] = []  # e.g. Telegram push
        self.proactive = Proactive(self.db, self.atlas, self.push)

    @property
    def chat_id(self) -> int:
        """Telegram and the web UI share one conversation, keyed by the owner's id."""
        return settings.owner_id or 1

    async def chat(self, text: str, source: str = "telegram") -> str:
        bus.emit("atlas", "message_in", text, source=source)
        async with self.lock:
            try:
                messages = self.db.history(self.chat_id, settings.history_messages)
                n = T.now()
                messages.append({"role": "user", "content": f"[{n:%a %Y-%m-%d %H:%M}] {text}"})
                reply = await self.atlas.run(messages) or "(no reply)"
            except anthropic.RateLimitError:
                reply = "I'm being rate-limited right now. Give me a minute and ask again."
            except anthropic.APIStatusError as exc:
                log.exception("Claude API error")
                reply = f"Something went wrong on my side (API {exc.status_code}). Try again shortly."
            except anthropic.APIConnectionError:
                reply = "I couldn't reach Claude. The server may be offline; try again in a bit."
            self.db.add_message(self.chat_id, "user", text)
            self.db.add_message(self.chat_id, "assistant", reply)
        bus.emit("atlas", "message_out", reply, source=source)
        return reply

    async def push(self, text: str) -> None:
        """A message Atlas starts on its own (brief, reminder, alert)."""
        if not text:
            return
        self.db.add_message(self.chat_id, "assistant", text)
        bus.emit("atlas", "message_out", text, source="proactive")
        for outlet in self.outlets:
            try:
                await outlet(text)
            except Exception:
                log.exception("push outlet failed")
