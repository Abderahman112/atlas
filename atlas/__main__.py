"""Run Atlas: `python -m atlas` (add --demo to try Atlas Town without any accounts)."""
import argparse
import asyncio
import logging
import os
import secrets

import uvicorn

from atlas.config import ROOT, settings


def access_token(assistant, demo: bool) -> str:
    if demo:
        return "demo"
    token = settings.ui_token or assistant.db.get("ui_token")
    if not token:
        token = secrets.token_urlsafe(24)
        assistant.db.set("ui_token", token)
    return token


async def serve(demo: bool) -> None:
    from atlas.service import Assistant
    from atlas.web import create_app

    client = None
    if demo:
        from atlas import demo as demo_mod
        demo_mod.install_fake_gmail()
        client = demo_mod.FakeClaude()
    elif not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
        raise SystemExit("Set ANTHROPIC_API_KEY in .env, or run `python -m atlas --demo` to try it without one.")

    assistant = Assistant(client, db_path=ROOT / "data" / "demo.db" if demo else None)
    token = access_token(assistant, demo)
    server = uvicorn.Server(uvicorn.Config(create_app(assistant, token), host=settings.ui_host,
                                           port=settings.ui_port, log_level="warning"))
    tasks = [asyncio.create_task(server.serve()), asyncio.create_task(assistant.proactive.run_scheduler())]

    bot = None
    if demo:
        tasks.append(asyncio.create_task(demo_mod.visitor(assistant)))
    elif settings.telegram_token:
        from atlas.bot import TelegramBot
        bot = TelegramBot(assistant)
        await bot.start_polling()
    else:
        logging.warning("No TELEGRAM_BOT_TOKEN: running with the web UI only.")

    logging.info("Atlas Town: http://%s:%s  (access token: %s)", settings.ui_host, settings.ui_port, token)
    try:
        await tasks[0]  # uvicorn exits on Ctrl+C
    finally:
        for t in tasks[1:]:
            t.cancel()
        if bot:
            await bot.stop()


def main() -> None:
    parser = argparse.ArgumentParser(prog="atlas")
    parser.add_argument("--demo", action="store_true", help="scripted agents and sample data, no accounts needed")
    args = parser.parse_args()
    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # the Telegram poll loop is noisy
    asyncio.run(serve(args.demo))


if __name__ == "__main__":
    main()
