"""Modulo Promemoria & Timer: comandi /remind, /remind_cron, /reminders, /delremind."""

from __future__ import annotations

import re
from datetime import datetime

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from services.scheduler import ReminderParseError, ReminderService, parse_reminder_when

router = Router(name="reminders")

USAGE_REMIND = (
    "⏰ <b>Promemoria</b>\n\n"
    "<code>/remind &lt;tempo&gt; &lt;messaggio&gt;</code>\n"
    "• Tempi relativi: <code>30m</code>, <code>2h</code>, <code>1d</code>, <code>1h30m</code>\n"
    "• Ora del giorno: <code>18:30</code> (oggi o domani se già passata)\n"
    "• <code>domani 09:00</code>\n\n"
    "Ricorrenti:\n"
    "<code>/remind_cron \"*/30 * * * *\" messaggio</code>\n\n"
    "Elenco: <code>/reminders</code> — Cancella: <code>/delremind &lt;id&gt;</code>"
)


def _format_run_at(run_at: str) -> str:
    try:
        return datetime.fromisoformat(run_at).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return run_at


async def add_reminder(message: Message, scheduler: ReminderService, spec_text: str) -> None:
    """Parsa '<tempo> <messaggio>' e crea un promemoria (usato da /remind e dal menù rapido)."""
    user_id = message.from_user.id
    if user_id is None:
        return

    parts = spec_text.strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(USAGE_REMIND)
        return

    when_spec, reminder_text = parts[0], parts[1].strip()

    try:
        run_at = parse_reminder_when(when_spec)
    except ReminderParseError as exc:
        await message.answer(f"❌ {exc}")
        return

    reminder_id = scheduler.add(
        user_id,
        message.chat.id,
        reminder_text,
        run_at=run_at.isoformat(timespec="seconds"),
    )

    await message.answer(
        f"✅ <b>Promemoria #{reminder_id} impostato</b>\n\n"
        f"🕐 <b>{run_at.strftime('%d/%m/%Y %H:%M')}</b>\n"
        f"📝 {reminder_text}"
    )


@router.message(Command("remind"))
async def cmd_remind(
    message: Message,
    command: CommandObject,
    scheduler: ReminderService,
) -> None:
    await add_reminder(message, scheduler, command.args or "")


@router.message(Command("remind_cron"))
async def cmd_remind_cron(
    message: Message,
    command: CommandObject,
    scheduler: ReminderService,
) -> None:
    user_id = message.from_user.id
    if user_id is None:
        return

    args = (command.args or "").strip()

    # Supporta sia la forma con virgolette sia quella senza: "*/30 * * * *" msg
    quoted = re.match(r'^"([^"]+)"\s+(.+)$', args) or re.match(r"^'([^']+)'\s+(.+)$", args)
    if quoted:
        cron_expr, reminder_text = quoted.group(1), quoted.group(2).strip()
    else:
        parts = args.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            await message.answer(USAGE_REMIND)
            return
        cron_expr, reminder_text = parts[0], parts[1].strip()

    # Validazione dell'espressione cron (5-6 campi, stile crontab).
    try:
        from apscheduler.triggers.cron import CronTrigger

        CronTrigger.from_crontab(cron_expr)
    except (ValueError, TypeError) as exc:
        await message.answer(
            f"❌ Espressione cron non valida: <code>{cron_expr}</code>\n"
            f"{exc}\n\nEsempio: <code>/remind_cron \"0 3 * * *\" backup</code>"
        )
        return

    reminder_id = scheduler.add(
        user_id, message.chat.id, reminder_text, cron_expr=cron_expr
    )

    await message.answer(
        f"✅ <b>Promemoria ricorrente #{reminder_id} attivo</b>\n\n"
        f"🔄 <code>{cron_expr}</code>\n"
        f"📝 {reminder_text}"
    )


async def send_reminders_list(message: Message, db: Database) -> None:
    """Invia l'elenco dei promemoria attivi (usato da /reminders e dal menù rapido)."""
    user_id = message.from_user.id
    if user_id is None:
        return

    reminders = db.list_reminders(user_id)
    if not reminders:
        await message.answer(
            "⏰ Nessun promemoria attivo.\n"
            "Crealo con <code>/remind 30m messaggio</code>."
        )
        return

    lines = [f"⏰ <b>Promemoria attivi</b> ({len(reminders)})"]
    for reminder in reminders:
        if reminder["cron_expr"]:
            when = f"🔄 <code>{reminder['cron_expr']}</code>"
        else:
            when = f"🕐 {_format_run_at(reminder['run_at'])}"
        lines.append(
            f"• <b>#{reminder['id']}</b> — {when}\n  📝 {reminder['message'][:100]}"
        )
    lines.append("\nPer cancellare: <code>/delremind &lt;id&gt;</code>")

    await message.answer("\n".join(lines))


@router.message(Command("reminders", "list_reminders"))
async def cmd_list_reminders(message: Message, db: Database) -> None:
    await send_reminders_list(message, db)


@router.message(Command("delremind"))
async def cmd_del_reminder(
    message: Message, command: CommandObject, scheduler: ReminderService
) -> None:
    user_id = message.from_user.id
    if user_id is None:
        return

    raw_id = (command.args or "").strip()
    if not raw_id.isdigit():
        await message.answer("❌ Specifica l'ID numerico, es. <code>/delremind 3</code>.")
        return

    reminder_id = int(raw_id)
    if scheduler.delete(user_id, reminder_id):
        await message.answer(f"🗑 Promemoria <b>#{reminder_id}</b> cancellato.")
    else:
        await message.answer(f"❌ Nessun promemoria con ID <b>#{reminder_id}</b>.")
