"""Entry point del bot Telegram privato per ZimaOS."""

from __future__ import annotations

import asyncio
import logging
import shutil
import sqlite3
import tempfile
from pathlib import Path

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


def _disk_usage_text(path: Path) -> str:
    """Descrive lo spazio libero sul filesystem che contiene `path`."""
    try:
        total, used, free = shutil.disk_usage(path)
    except OSError:
        return ""

    def fmt(num: float) -> str:
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if abs(num) < 1024.0:
                return f"{num:.1f} {unit}"
            num /= 1024.0
        return f"{num:.1f} PB"

    return f"Spazio su {path}: {fmt(free)} liberi di {fmt(total)}"


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
            "Impossibile inizializzare il database SQLite in %s: %s. %s",
            settings.db_path,
            exc,
            _disk_usage_text(settings.db_path.parent),
        )
        # Fallback: mantiene il bot attivo anche se il volume dati è pieno.
        fallback_path = Path(tempfile.gettempdir()) / "zima-bot-fallback.db"
        logger.warning(
            "Uso il database di fallback %s: note e promemoria NON persisteranno. "
            "Libera spazio su disco il prima possibile!",
            fallback_path,
        )
        try:
            db = Database(fallback_path)
        except sqlite3.OperationalError:
            logger.error(
                "Anche il fallback non è scrivibile: il disco è davvero pieno."
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
