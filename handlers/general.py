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
    "🐳 <code>/docker</code> — stato dei container"
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
