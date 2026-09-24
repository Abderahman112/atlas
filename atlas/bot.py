"""Telegram front end. Only the owner (TELEGRAM_OWNER_ID) can talk to Atlas."""
from __future__ import annotations

import asyncio
import logging

import anthropic
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from atlas.agents import tools as T
from atlas.agents.team import build_team
from atlas.config import settings
from atlas.db import DB
from atlas.proactive import Proactive

log = logging.getLogger(__name__)

SHORTCUTS = {
    "today": "What do I have today? Schedule, anything due soon, and emails I need to answer.",
    "tomorrow": "What does tomorrow look like?",
    "week": "Give me an overview of this week: busy days, deadlines and exams.",
    "inbox": "Summarise my unread email: what needs a reply, what has a deadline, what's FYI.",
    "deadlines": "What's due in the next two weeks?",
    "coop": "How's my co-op hunt going and what should I do next?",
    "plan": "Plan the rest of my day. Ask me how I'm feeling first if I haven't said today.",
    "tasks": "List my open to-dos.",
}


def chunks(text: str, size: int = 4000):
    while text:
        cut = text.rfind("\n", 0, size) if len(text) > size else len(text)
        cut = cut if cut > 0 else size
        yield text[:cut]
        text = text[cut:].lstrip("\n")


class AtlasBot:
    def __init__(self):
        self.db = DB(settings.db_path)
        self.atlas = build_team(self.db)
        self.lock = asyncio.Lock()  # one conversation turn at a time
        self.app = Application.builder().token(settings.telegram_token).build()
        self.proactive = Proactive(self.db, self.atlas, self.push)

        owner = filters.User(user_id=settings.owner_id) if settings.owner_id else filters.ALL
        self.app.add_handler(CommandHandler("start", self.start))
        for cmd, prompt in SHORTCUTS.items():
            self.app.add_handler(CommandHandler(cmd, self.shortcut(prompt), filters=owner))
        self.app.add_handler(MessageHandler(owner & filters.TEXT & ~filters.COMMAND, self.on_text))
        self.app.add_error_handler(self.on_error)
        if settings.owner_id:
            self.proactive.schedule(self.app.job_queue)

    # --- outbound ---------------------------------------------------------------------------
    async def push(self, text: str) -> None:
        """Proactive message to the owner; also stored so follow-up questions have context."""
        if not settings.owner_id or not text:
            return
        self.db.add_message(settings.owner_id, "assistant", text)
        for part in chunks(text):
            await self.app.bot.send_message(settings.owner_id, part)

    # --- handlers ---------------------------------------------------------------------------
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        uid = update.effective_user.id
        if not settings.owner_id:
            await update.message.reply_text(
                f"Your Telegram user id is {uid}. Put TELEGRAM_OWNER_ID={uid} in .env and restart Atlas.")
        elif uid == settings.owner_id:
            await update.message.reply_text(
                "Atlas is here. Ask me anything, or try /today /tomorrow /week /inbox /deadlines /coop /plan /tasks")

    def shortcut(self, prompt: str):
        async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            await self.converse(update, prompt)
        return handler

    async def on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.converse(update, update.message.text)

    async def converse(self, update: Update, text: str) -> None:
        if not settings.owner_id:  # until the owner is configured, nobody gets answers
            await update.message.reply_text("Send /start to finish setup.")
            return
        chat_id = update.effective_chat.id
        async with self.lock:
            typing = asyncio.create_task(self._typing(chat_id))
            try:
                messages = self.db.history(chat_id)
                n = T.now()
                messages.append({"role": "user", "content": f"[{n:%a %Y-%m-%d %H:%M}] {text}"})
                reply = await self.atlas.run(messages)
            except anthropic.RateLimitError:
                reply = "I'm being rate-limited right now. Give me a minute and ask again."
            except anthropic.APIStatusError as exc:
                log.exception("Claude API error")
                reply = f"Something went wrong on my side (API {exc.status_code}). Try again shortly."
            except anthropic.APIConnectionError:
                reply = "I couldn't reach Claude. The server may be offline; try again in a bit."
            finally:
                typing.cancel()
            self.db.add_message(chat_id, "user", text)
            self.db.add_message(chat_id, "assistant", reply or "(no reply)")
        for part in chunks(reply or "(no reply)"):
            await update.message.reply_text(part)

    async def _typing(self, chat_id: int) -> None:
        while True:
            await self.app.bot.send_chat_action(chat_id, ChatAction.TYPING)
            await asyncio.sleep(4)

    async def on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        log.error("Unhandled error", exc_info=context.error)

    def run(self) -> None:
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)
