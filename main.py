"""Entry point del bot Telegram privato per ZimaOS."""

from __future__ import annotations

import asyncio
import logging
import sqlite3

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import ConfigError, Settings
from handlers import (
    docker_handler,
    downloader,
    general,
    notes,
    pastebin,
    ping,
    reminders,
    sysinfo,
)
from middlewares.access import AccessControlMiddleware
from services.scheduler import ReminderService
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
    try:
        db = Database(settings.db_path)
    except sqlite3.OperationalError as exc:
        logger.error(
            "Impossibile inizializzare il database SQLite in %s: %s. "
            "Verifica che il volume /data sia scrivibile e che ci sia "
            "spazio libero su disco.",
            settings.db_path,
            exc,
        )
        raise SystemExit(1) from exc
    dp["db"] = db
    dp["settings"] = settings

    # Directory per download e paste (create se assenti).
    settings.downloads_dir.mkdir(parents=True, exist_ok=True)
    settings.pastes_dir.mkdir(parents=True, exist_ok=True)

    # Servizio promemoria (APScheduler), condiviso via DI.
    reminder_service = ReminderService(bot, db)
    dp["scheduler"] = reminder_service
    reminder_service.start()

    # Router dei comandi, suddivisi per funzionalità. L'ordine conta:
    # downloader prima di pastebin (i messaggi con URL media vincono).
    dp.include_router(general.router)
    dp.include_router(sysinfo.router)
    dp.include_router(notes.router)
    dp.include_router(ping.router)
    dp.include_router(docker_handler.router)
    dp.include_router(downloader.router)
    dp.include_router(reminders.router)
    dp.include_router(pastebin.router)

    # Scarta gli update accumulati mentre il bot era offline.
    await bot.delete_webhook(drop_pending_updates=True)

    logger.info(
        "Bot avviato. Utenti autorizzati: %s",
        ", ".join(str(uid) for uid in sorted(settings.allowed_user_ids)),
    )
    try:
        await dp.start_polling(bot)
    finally:
        reminder_service.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except ConfigError as exc:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger("zima-bot").error("Errore di configurazione: %s", exc)
        raise SystemExit(1) from exc
    except (KeyboardInterrupt, SystemExit):
        logging.getLogger("zima-bot").info("Bot arrestato.")
