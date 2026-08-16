"""Servizio promemoria: APScheduler + persistenza SQLite.

I promemoria vengono salvati nel database e ripristinati all'avvio del
container, quindi sopravvivono ai riavvii. I job one-shot che risultano
scaduti mentre il bot era spento vengono scartati.
"""

from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("zima-bot.reminders")

# Unità supportate per i tempi relativi (30m, 2h, 1d, 1w, 45min...).
_REL_UNITS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
    "min": 60,
}


class ReminderParseError(ValueError):
    """Errore di parsing di un tempo per /remind."""


def parse_reminder_when(spec: str, now: datetime | None = None) -> datetime:
    """Interpreta il tempo di un promemoria.

    Formati supportati:
      - relativi:  ``30m``, ``2h``, ``1d``, ``1h30m``, ``45min``, ``1w``
      - ora del giorno: ``18:30`` (oggi, o domani se già passata)
      - ``domani 09:00``
    """
    now = now or datetime.now()
    spec = spec.strip().lower()
    if not spec:
        raise ReminderParseError("Specifica un tempo, es. 30m, 2h, 1d, 18:30.")

    # "domani HH:MM"
    if spec.startswith("domani"):
        rest = spec[len("domani") :].strip()
        if not rest:
            raise ReminderParseError('Usa "domani HH:MM", es. domani 09:00.')
        clock = _parse_clock(rest)
        target = (now + timedelta(days=1)).replace(
            hour=clock[0], minute=clock[1], second=0, microsecond=0
        )
        return target

    # "HH:MM" (oggi, o domani se già passata)
    clock = _parse_clock(spec)
    if clock is not None:
        target = now.replace(hour=clock[0], minute=clock[1], second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return target

    # Tempo relativo: "30m", "2h", "1d", "1h30m", "45min", "1w"
    parts = re.findall(r"(\d+)(min|[smhdw])", spec)
    if parts and "".join(num + unit for num, unit in parts) == spec:
        total = sum(int(num) * _REL_UNITS[unit] for num, unit in parts)
        if total > 0:
            return now + timedelta(seconds=total)

    raise ReminderParseError(
        "Formato non riconosciuto. Esempi: /remind 30m pausa, "
        "/remind 2h controllo, /remind 18:30 cena, /remind domani 09:00 riunione."
    )


def _parse_clock(spec: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", spec)
    if not match:
        return None
    hours, minutes = int(match.group(1)), int(match.group(2))
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        raise ReminderParseError(f"Orario non valido: {spec!r}.")
    return hours, minutes


class ReminderService:
    """Gestisce lo scheduling dei promemoria su AsyncIOScheduler."""

    def __init__(self, bot, db) -> None:
        self.bot = bot
        self.db = db
        self.scheduler = AsyncIOScheduler()

    def start(self) -> None:
        self._restore()
        self.scheduler.start()
        logger.info("Scheduler promemoria avviato (%d job attivi)", len(self.scheduler.get_jobs()))

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    # ------------------------------------------------------------------
    # API usata dagli handler
    # ------------------------------------------------------------------

    def add(
        self,
        user_id: int,
        chat_id: int,
        message: str,
        run_at: str | None = None,
        cron_expr: str | None = None,
    ) -> int:
        """Salva e programma un promemoria; restituisce l'ID."""
        reminder_id = self.db.add_reminder(
            user_id, chat_id, message, run_at=run_at, cron_expr=cron_expr
        )
        if cron_expr:
            self._schedule_cron(user_id, chat_id, message, reminder_id, cron_expr)
        else:
            self._schedule_date(
                user_id, chat_id, message, reminder_id, datetime.fromisoformat(run_at)
            )
        return reminder_id

    def delete(self, user_id: int, reminder_id: int) -> bool:
        """Elimina un promemoria (database + job). True se esisteva."""
        if not self.db.delete_reminder(user_id, reminder_id):
            return False
        try:
            self.scheduler.remove_job(self._job_id(reminder_id))
        except Exception:  # noqa: BLE001 - il job potrebbe non esistere
            pass
        return True

    # ------------------------------------------------------------------
    # Interni
    # ------------------------------------------------------------------

    def _restore(self) -> None:
        for row in self.db.all_reminders():
            try:
                if row["cron_expr"]:
                    self._schedule_cron(
                        row["user_id"], row["chat_id"], row["message"], row["id"], row["cron_expr"]
                    )
                elif row["run_at"]:
                    run_at = datetime.fromisoformat(row["run_at"])
                    if run_at <= datetime.now():
                        # Scaduto mentre il bot era spento: scartalo.
                        self.db.delete_reminder(row["user_id"], row["id"])
                        continue
                    self._schedule_date(
                        row["user_id"], row["chat_id"], row["message"], row["id"], run_at
                    )
            except Exception:  # noqa: BLE001
                logger.exception("Promemoria %s non ripristinato", row["id"])

    @staticmethod
    def _job_id(reminder_id: int) -> str:
        return f"remind-{reminder_id}"

    def _schedule_date(
        self,
        user_id: int,
        chat_id: int,
        message: str,
        reminder_id: int,
        run_at: datetime,
    ) -> None:
        self.scheduler.add_job(
            self._fire,
            "date",
            run_date=run_at,
            id=self._job_id(reminder_id),
            misfire_grace_time=60,
            args=[user_id, chat_id, message, reminder_id, False],
        )

    def _schedule_cron(
        self,
        user_id: int,
        chat_id: int,
        message: str,
        reminder_id: int,
        cron_expr: str,
    ) -> None:
        trigger = CronTrigger.from_crontab(cron_expr)
        self.scheduler.add_job(
            self._fire,
            trigger,
            id=self._job_id(reminder_id),
            args=[user_id, chat_id, message, reminder_id, True],
        )

    async def _fire(
        self, user_id: int, chat_id: int, message: str, reminder_id: int, recurring: bool
    ) -> None:
        text = f"⏰ <b>Promemoria</b> #{reminder_id}\n\n{html.escape(message)}"
        try:
            await self.bot.send_message(chat_id, text, disable_notification=False)
        except Exception:  # noqa: BLE001
            logger.exception("Invio del promemoria #%s fallito", reminder_id)

        if not recurring:
            self.db.delete_reminder(user_id, reminder_id)
