"""Gestori generali: /start, /help, menu in-line e azioni rapide."""

from __future__ import annotations

import time

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, Filter
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from handlers.docker_handler import send_docker_status
from handlers.notes import save_note
from handlers.reminders import add_reminder
from handlers.sysinfo import send_stats
from services.scheduler import ReminderService
from utils.db import Database

router = Router(name="general")

WELCOME_TEXT = (
    "👋 <b>Ciao! Sono il tuo assistente privato per ZimaOS.</b>\n\n"
    "Usa i pulsanti ⚡ per eseguire subito un comando, oppure scrivi:\n"
    "📊 <code>/stats</code> — monitoraggio di sistema\n"
    "📝 <code>/notes</code> — note rapide e link\n"
    "📶 <code>/ping</code> — latenza di un host/URL\n"
    "🐳 <code>/docker</code> — stato dei container\n"
    "🎥 <code>/dl</code> — scarica video/audio (YouTube, TikTok, IG…)\n"
    "⏰ <code>/remind</code> — promemoria e timer\n"
    "📄 <code>/paste</code> — pastebin e gestione log"
)

# Descrizioni mostrate quando si preme un pulsante "guida" della sezione.
# Le voci stats/notes/docker restano per compatibilità con vecchie tastiere
# (ora sono pulsanti rapidi ⚡ che eseguono direttamente il comando).
SECTION_INFO = {
    "stats": (
        "📊 <b>Monitoraggio di sistema</b>\n\n"
        "Usa <code>/stats</code> per vedere in tempo reale:\n"
        "• CPU, RAM e spazio su disco\n"
        "• Uptime di ZimaOS e del container"
    ),
    "notes": (
        "📝 <b>Note rapide</b>\n\n"
        "<code>/notes</code> — elenca le note\n"
        "<code>/notes add &lt;testo o link&gt;</code> — salva una nota\n"
        "<code>/notes del &lt;id&gt;</code> — elimina una nota"
    ),
    "ping": (
        "📶 <b>Ping</b>\n\n"
        "Usa <code>/ping &lt;host o URL&gt;</code> per verificare "
        "latenza e disponibilità di un server.\n"
        "Esempio: <code>/ping google.com</code>"
    ),
    "docker": (
        "🐳 <b>Docker</b>\n\n"
        "Usa <code>/docker</code> per vedere lo stato dei container "
        "sull'host. Richiede il mount del socket "
        "<code>/var/run/docker.sock</code>."
    ),
    "downloader": (
        "🎥 <b>Media Downloader</b>\n\n"
        "Invia un link (YouTube, Twitter/X, TikTok, Instagram, Reddit) "
        "oppure usa <code>/dl &lt;URL&gt;</code>.\n\n"
        "Puoi scegliere:\n"
        "• 🎵 Solo Audio (MP3)\n"
        "• 🎬 Video (MP4)\n\n"
        "Destinazione: 📱 chat Telegram oppure 💾 cartella "
        "<code>/app/downloads</code> su ZimaOS.\n"
        "I file oltre 50 MB vengono salvati automaticamente sul server."
    ),
    "reminders": (
        "⏰ <b>Promemoria &amp; Timer</b>\n\n"
        "<code>/remind 30m fai il backup</code> — tra 30 minuti\n"
        "<code>/remind 18:30 cena</code> — oggi alle 18:30\n"
        "<code>/remind domani 09:00 sveglia</code>\n"
        "<code>/remind_cron \"0 3 * * *\" backup</code> — ricorrente\n\n"
        "<code>/reminders</code> — elenca i promemoria attivi\n"
        "<code>/delremind &lt;id&gt;</code> — cancella un promemoria"
    ),
    "pastebin": (
        "📄 <b>Pastebin &amp; Gestione Log</b>\n\n"
        "<code>/paste &lt;testo o codice&gt;</code> — file .txt "
        "scaricabile (funziona anche con messaggi molto lunghi).\n"
        "Invia un file <code>.log</code>/<code>.txt</code> per vedere "
        "un riepilogo (prime/ultime righe).\n"
        "<code>/searchlog &lt;keyword&gt;</code> — cerca nel log inviato.\n\n"
        "I file si salvano in <code>/app/pastes</code> su ZimaOS."
    ),
}

# Stato delle azioni rapide in attesa di un messaggio dell'utente.
# user_id -> (azione, timestamp). Scade dopo _PENDING_TTL_SECONDS.
_PENDING_TTL_SECONDS = 10 * 60
_pending_actions: dict[int, tuple[str, float]] = {}


def _set_pending(user_id: int, action: str) -> None:
    _pending_actions[user_id] = (action, time.time())


def _get_pending(user_id: int) -> str | None:
    entry = _pending_actions.get(user_id)
    if entry is None:
        return None
    action, started = entry
    if time.time() - started > _PENDING_TTL_SECONDS:
        _pending_actions.pop(user_id, None)
        return None
    return action


def _clear_pending(user_id: int) -> None:
    _pending_actions.pop(user_id, None)


class HasPendingAction(Filter):
    """Scatta quando l'utente ha un'azione rapida in attesa (esclusi i comandi)."""

    def __init__(self, action: str) -> None:
        self.action = action

    async def __call__(self, message: Message) -> bool:
        if message.text is None or message.text.startswith("/"):
            return False
        if message.from_user is None:
            return False
        return _get_pending(message.from_user.id) == self.action


async def _ask_for_note(message: Message, user_id: int) -> None:
    _set_pending(user_id, "note")
    await message.answer(
        "📝 <b>Nuova nota</b>\n\n"
        "Inviami il testo o il link da salvare.\n"
        "(<code>/cancel</code> per annullare)"
    )


async def _ask_for_reminder(message: Message, user_id: int) -> None:
    _set_pending(user_id, "remind")
    await message.answer(
        "⏰ <b>Nuovo promemoria</b>\n\n"
        "Inviami <code>&lt;tempo&gt; &lt;messaggio&gt;</code>, es.:\n"
        "<code>30m fai il backup</code>\n"
        "<code>18:30 cena</code>\n"
        "<code>domani 09:00 sveglia</code>\n\n"
        "(<code>/cancel</code> per annullare)"
    )


def _menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            # ⚡ Azioni rapide: eseguono subito il comando.
            [
                InlineKeyboardButton(text="⚡ Stats", callback_data="quick:stats"),
                InlineKeyboardButton(text="⚡ Nuova nota", callback_data="quick:notes"),
            ],
            [
                InlineKeyboardButton(text="⚡ Docker", callback_data="quick:docker"),
                InlineKeyboardButton(text="⚡ Nuovo promemoria", callback_data="quick:reminders"),
            ],
            # ℹ️ Guide per i comandi che richiedono argomenti.
            [
                InlineKeyboardButton(text="📶 Ping", callback_data="section:ping"),
                InlineKeyboardButton(text="🎥 Download", callback_data="section:downloader"),
            ],
            [
                InlineKeyboardButton(text="🕐 Remind", callback_data="section:reminders"),
                InlineKeyboardButton(text="📄 Pastebin", callback_data="section:pastebin"),
            ],
        ]
    )


def _back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Menu", callback_data="section:home")]
        ]
    )


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(WELCOME_TEXT, reply_markup=_menu_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(WELCOME_TEXT, reply_markup=_menu_keyboard())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else None
    if user_id is not None:
        _clear_pending(user_id)
    await message.answer("↩️ Azione annullata.")


@router.message(HasPendingAction("note"))
async def capture_note(message: Message, db: Database) -> None:
    user_id = message.from_user.id
    _clear_pending(user_id)
    await save_note(message, db, user_id, message.text or "")


@router.message(HasPendingAction("remind"))
async def capture_reminder(message: Message, scheduler: ReminderService) -> None:
    user_id = message.from_user.id
    _clear_pending(user_id)
    await add_reminder(message, scheduler, message.text or "")


@router.callback_query(F.data.startswith("quick:"))
async def quick_callback(callback: CallbackQuery, db: Database) -> None:
    """Esegue le azioni rapide: Stats/Docker subito, Nota/Promemoria chiedono l'input."""
    action = callback.data.split(":", 1)[1]

    if callback.message is None:
        await callback.answer("Messaggio non più disponibile.", show_alert=True)
        return

    message = callback.message
    user_id = callback.from_user.id

    if action == "stats":
        await send_stats(message)
    elif action == "notes":
        await _ask_for_note(message, user_id)
    elif action == "docker":
        await send_docker_status(message)
    elif action == "reminders":
        await _ask_for_reminder(message, user_id)
    else:
        await callback.answer("Azione sconosciuta.", show_alert=True)
        return

    await callback.answer()


@router.callback_query(F.data.startswith("section:"))
async def section_callback(callback: CallbackQuery) -> None:
    section = callback.data.split(":", 1)[1]

    if callback.message is None:
        await callback.answer("Messaggio non più disponibile.", show_alert=True)
        return

    if section == "home":
        await callback.message.edit_text(WELCOME_TEXT, reply_markup=_menu_keyboard())
        await callback.answer()
        return

    text = SECTION_INFO.get(section)
    if text is None:
        await callback.answer("Sezione sconosciuta.", show_alert=True)
        return

    await callback.message.edit_text(text, reply_markup=_back_keyboard())
    await callback.answer()
