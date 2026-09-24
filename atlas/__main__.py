"""Run Atlas: `python -m atlas`."""
import logging

from atlas.bot import AtlasBot
from atlas.config import settings


def main() -> None:
    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # the Telegram poll loop is noisy
    if not settings.telegram_token:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in .env (create a bot with @BotFather).")
    AtlasBot().run()


if __name__ == "__main__":
    main()
