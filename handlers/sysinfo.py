"""Gestore /stats: monitoraggio di sistema in tempo reale."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from utils import sysinfo as si

router = Router(name="sysinfo")


def _refresh_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Aggiorna", callback_data="refresh:stats")]
        ]
    )


async def _stats_text() -> str:
    """Costruisce il report testuale delle metriche di sistema."""
    cpu = si.cpu_percent()
    mem = si.virtual_memory()
    sys_uptime = si.system_uptime_seconds()
    container_uptime = si.container_uptime_seconds()

    lines = [
        "<b>📊 Statistiche di sistema</b>\n",
        f"🖥 <b>CPU</b>: {cpu:.1f}%",
        (
            f"🧠 <b>RAM</b>: {si.format_bytes(mem['used'])} / "
            f"{si.format_bytes(mem['total'])} ({mem['percent']:.1f}%)"
        ),
        "\n<b>💾 Dischi</b>",
    ]

    for disk in si.disk_usage()[:6]:
        lines.append(
            f"• <code>{disk['mountpoint']}</code>: "
            f"{si.format_bytes(disk['used'])} / "
            f"{si.format_bytes(disk['total'])} ({disk['percent']:.1f}%)"
        )

    lines.append(f"\n⏱ <b>Uptime sistema</b>: {si.format_uptime(sys_uptime)}")
    if container_uptime is not None:
        lines.append(
            f"⏱ <b>Uptime container</b>: {si.format_uptime(container_uptime)}"
        )

    return "\n".join(lines)


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    await message.answer("⏳ Raccolgo le metriche di sistema…")
    await message.answer(await _stats_text(), reply_markup=_refresh_keyboard())


@router.callback_query(F.data == "refresh:stats")
async def refresh_stats(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer()
        return
    await callback.message.edit_text(
        await _stats_text(), reply_markup=_refresh_keyboard()
    )
    await callback.answer()
