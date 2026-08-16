"""Gestore /ping: verifica di latenza e disponibilità di un host/URL."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from config import Settings
from utils.network import ping

router = Router(name="ping")


@router.message(Command("ping"))
async def cmd_ping(message: Message, command: CommandObject, settings: Settings) -> None:
    target = (command.args or "").strip()
    if not target:
        await message.answer(
            "📶 Usa: <code>/ping &lt;host o URL&gt;</code>\n"
            "Esempio: <code>/ping google.com</code>"
        )
        return

    await message.answer(f"📶 Verifico <code>{target}</code>…")

    result = ping(target, timeout=settings.ping_timeout)

    if result.reachable:
        text = (
            f"✅ <b>{result.host}</b> è raggiungibile\n\n"
            f"📍 IP: <code>{result.ip}</code>\n"
            f"🔌 Porta: <code>{result.port}</code>\n"
            f"⏱ Latenza: <b>{result.latency_ms} ms</b>"
        )
    else:
        text = (
            f"❌ <b>{result.host or target}</b> non è raggiungibile\n\n"
            f"⚠️ {result.error}"
        )

    await message.answer(text)
