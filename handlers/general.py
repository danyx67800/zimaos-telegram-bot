"""Gestori generali: /start, /help e navigazione della tastiera in-line."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

router = Router(name="general")

WELCOME_TEXT = (
    "👋 <b>Ciao! Sono il tuo assistente privato per ZimaOS.</b>\n\n"
    "Scegli una sezione dalla tastiera qui sotto, oppure usa i comandi:\n"
    "📊 <code>/stats</code> — monitoraggio di sistema\n"
    "📝 <code>/notes</code> — note rapide e link\n"
    "📶 <code>/ping</code> — latenza di un host/URL\n"
    "🐳 <code>/docker</code> — stato dei container\n"
    "🎥 <code>/dl</code> — scarica video/audio (YouTube, TikTok, IG…)\n"
    "⏰ <code>/remind</code> — promemoria e timer\n"
    "📄 <code>/paste</code> — pastebin e gestione log"
)

# Descrizioni mostrate quando si preme un pulsante della sezione.
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


def _menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Statistiche", callback_data="section:stats"),
                InlineKeyboardButton(text="📝 Note", callback_data="section:notes"),
            ],
            [
                InlineKeyboardButton(text="📶 Ping", callback_data="section:ping"),
                InlineKeyboardButton(text="🐳 Docker", callback_data="section:docker"),
            ],
            [
                InlineKeyboardButton(text="🎥 Download", callback_data="section:downloader"),
                InlineKeyboardButton(text="⏰ Promemoria", callback_data="section:reminders"),
            ],
            [
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
