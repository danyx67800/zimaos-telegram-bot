"""Gestore /docker: stato dei container sull'host via socket Docker."""

from __future__ import annotations

import html

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from utils import docker_stats

router = Router(name="docker")


@router.message(Command("docker"))
async def cmd_docker(message: Message) -> None:
    if not docker_stats.is_available():
        await message.answer(
            "🐳 <b>Socket Docker non disponibile</b>\n\n"
            "Il file <code>/var/run/docker.sock</code> non è montato nel "
            "container. Aggiungi al docker-compose:\n"
            "<code>/var/run/docker.sock:/var/run/docker.sock:ro</code>"
        )
        return

    try:
        containers = docker_stats.list_containers(all_containers=True)
    except Exception as exc:  # noqa: BLE001 - vogliamo mostrare qualunque errore
        await message.answer(f"⚠️ Impossibile interrogare Docker: {exc}")
        return

    if not containers:
        await message.answer("🐳 Nessun container presente sull'host.")
        return

    running = sum(1 for c in containers if c.get("State") == "running")
    lines = [
        f"🐳 <b>Container Docker</b> — {running}/{len(containers)} in esecuzione\n"
    ]

    for container in containers:
        state = container.get("State", "unknown")
        icon = "🟢" if state == "running" else "🔴"
        name = html.escape((container.get("Names") or ["?"])[0].lstrip("/"))
        image = html.escape(container.get("Image", "?"))
        status = html.escape(container.get("Status", "?"))
        lines.append(f"{icon} <b>{name}</b> <i>({image})</i>\n   {status}")

    await message.answer("\n".join(lines))
