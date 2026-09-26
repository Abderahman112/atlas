"""Telegram front end. Only the owner (TELEGRAM_OWNER_ID) can talk to Atlas."""
from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from atlas.config import settings
from atlas.service import Assistant

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


class TelegramBot:
    def __init__(self, assistant: Assistant):
        self.assistant = assistant
        self.app = Application.builder().token(settings.telegram_token).build()
        owner = filters.User(user_id=settings.owner_id) if settings.owner_id else filters.ALL
        self.app.add_handler(CommandHandler("start", self.start))
        for cmd, prompt in SHORTCUTS.items():
            self.app.add_handler(CommandHandler(cmd, self.shortcut(prompt), filters=owner))
        self.app.add_handler(MessageHandler(owner & filters.TEXT & ~filters.COMMAND, self.on_text))
        self.app.add_error_handler(self.on_error)
        assistant.outlets.append(self.push)

    async def push(self, text: str) -> None:
        if settings.owner_id:
            for part in chunks(text):
                await self.app.bot.send_message(settings.owner_id, part)

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
        typing = asyncio.create_task(self._typing(update.effective_chat.id))
        try:
            reply = await self.assistant.chat(text, source="telegram")
        finally:
            typing.cancel()
        for part in chunks(reply):
            await update.message.reply_text(part)

    async def _typing(self, chat_id: int) -> None:
        while True:
            await self.app.bot.send_chat_action(chat_id, ChatAction.TYPING)
            await asyncio.sleep(4)

    async def on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        log.error("Unhandled error", exc_info=context.error)

    async def start_polling(self) -> None:
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

    async def stop(self) -> None:
        await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()
