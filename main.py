"""Entry point del bot Telegram privato per ZimaOS."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import ConfigError, Settings
from handlers import docker_handler, general, notes, ping, sysinfo
from middlewares.access import AccessControlMiddleware
from utils.db import Database


async def main() -> None:
    settings = Settings.from_env()

    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logger = logging.getLogger("zima-bot")

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # Controllo accessi globale: blocca ogni update da utenti non autorizzati
    # prima che venga eseguito qualsiasi filtro o handler.
    dp.update.outer_middleware(AccessControlMiddleware(settings.allowed_user_ids))

    # Dipendenze condivise, iniettate negli handler tramite DI di aiogram.
    db = Database(settings.db_path)
    dp["db"] = db
    dp["settings"] = settings

    # Router dei comandi, suddivisi per funzionalità.
    dp.include_router(general.router)
    dp.include_router(sysinfo.router)
    dp.include_router(notes.router)
    dp.include_router(ping.router)
    dp.include_router(docker_handler.router)

    # Scarta gli update accumulati mentre il bot era offline.
    await bot.delete_webhook(drop_pending_updates=True)

    logger.info(
        "Bot avviato. Utenti autorizzati: %s",
        ", ".join(str(uid) for uid in sorted(settings.allowed_user_ids)),
    )
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except ConfigError as exc:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger("zima-bot").error("Errore di configurazione: %s", exc)
        raise SystemExit(1) from exc
    except (KeyboardInterrupt, SystemExit):
        logging.getLogger("zima-bot").info("Bot arrestato.")
