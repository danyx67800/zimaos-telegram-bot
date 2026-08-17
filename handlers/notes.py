"""Gestore /notes: CRUD di note rapide e link su SQLite."""

from __future__ import annotations

import html

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from utils.db import Database

router = Router(name="notes")

USAGE = (
    "📝 <b>Note rapide</b>\n\n"
    "<code>/notes</code> — elenca le tue note\n"
    "<code>/notes add &lt;testo o link&gt;</code> — salva una nota\n"
    "<code>/notes del &lt;id&gt;</code> — elimina una nota"
)


async def send_notes_list(message: Message, db: Database, user_id: int) -> None:
    notes = db.list_notes(user_id)
    if not notes:
        await message.answer(
            "📝 Non hai ancora note. Aggiungine una con "
            "<code>/notes add &lt;testo o link&gt;</code>."
        )
        return

    lines = [f"📝 <b>Le tue note</b> ({len(notes)})"]
    for note in notes:
        content = html.escape(note["content"])
        if len(content) > 200:
            content = content[:197] + "…"
        lines.append(f"• <b>#{note['id']}</b> — {content}")

    await message.answer("\n".join(lines))


async def _delete_note(
    message: Message, db: Database, user_id: int, raw_id: str
) -> None:
    if not raw_id.isdigit():
        await message.answer(
            "❌ Specifica l'ID numerico della nota, es. <code>/notes del 3</code>."
        )
        return

    note_id = int(raw_id)
    if db.delete_note(user_id, note_id):
        await message.answer(f"🗑 Nota <b>#{note_id}</b> eliminata.")
    else:
        await message.answer(f"❌ Nessuna nota con ID <b>#{note_id}</b> trovata.")


@router.message(Command("notes"))
async def cmd_notes(
    message: Message, command: CommandObject, db: Database
) -> None:
    user_id = message.from_user.id if message.from_user else 0
    args = (command.args or "").strip()

    if not args:
        await send_notes_list(message, db, user_id)
        return

    parts = args.split(maxsplit=1)
    sub = parts[0].lower()

    if sub == "add":
        content = parts[1].strip() if len(parts) > 1 else ""
        if not content:
            await message.answer(
                "❌ Usa: <code>/notes add &lt;testo o link&gt;</code>"
            )
            return
        note_id = db.add_note(user_id, content)
        await message.answer(f"✅ Nota <b>#{note_id}</b> salvata.")
        return

    if sub in ("del", "delete", "rm"):
        await _delete_note(message, db, user_id, parts[1] if len(parts) > 1 else "")
        return

    # Sottocomando non riconosciuto: mostra la guida.
    await message.answer(USAGE)
