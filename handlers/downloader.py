"""Modulo Media Downloader: riconoscimento URL e download via yt-dlp.

Flusso: l'utente invia un link (o usa /dl), sceglie formato (audio/video),
poi destinazione (chat o server ZimaOS). Se il file supera i 50 MB viene
salvato sul server e comunicato il percorso locale.
"""

from __future__ import annotations

import asyncio
import html
import logging
import secrets
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, Filter
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import Settings
from utils import media_downloader as media

router = Router(name="downloader")

logger = logging.getLogger("zima-bot.downloader")

_SESSION_TTL_SECONDS = 30 * 60  # le sessioni scadono dopo 30 minuti
_sessions: dict[str, dict] = {}


def _cleanup_sessions() -> None:
    now = time.time()
    expired = [
        token
        for token, session in _sessions.items()
        if now - session["created"] > _SESSION_TTL_SECONDS
    ]
    for token in expired:
        _sessions.pop(token, None)


def _new_session(url: str, user_id: int) -> str:
    _cleanup_sessions()
    token = secrets.token_hex(6)
    _sessions[token] = {
        "url": url,
        "user_id": user_id,
        "mode": None,
        "created": time.time(),
    }
    return token


def _get_session(token: str) -> dict | None:
    session = _sessions.get(token)
    if session is None:
        return None
    if time.time() - session["created"] > _SESSION_TTL_SECONDS:
        _sessions.pop(token, None)
        return None
    return session


def _drop_session(token: str) -> None:
    _sessions.pop(token, None)


def _format_keyboard(callback_prefix: str, token: str) -> InlineKeyboardMarkup:
    """Tastiera con due pulsanti (audio/video oppure chat/server)."""
    if callback_prefix == "fmt":
        buttons = [
            InlineKeyboardButton(text="🎵 Solo Audio (MP3)", callback_data=f"dl:fmt:audio:{token}"),
            InlineKeyboardButton(text="🎬 Video (MP4)", callback_data=f"dl:fmt:video:{token}"),
        ]
    else:
        buttons = [
            InlineKeyboardButton(text="📱 Invia in Chat", callback_data=f"dl:dest:chat:{token}"),
            InlineKeyboardButton(text="💾 Salva su ZimaOS", callback_data=f"dl:dest:server:{token}"),
        ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


class HasMediaUrl(Filter):
    """Filtro che scatta solo quando il messaggio contiene un URL supportato."""

    async def __call__(self, message: Message) -> bool | dict:
        if message.text is None or message.text.startswith("/"):
            return False
        urls = media.extract_urls(message.text)
        supported = [u for u in urls if media.is_known_platform(u)]
        if not supported:
            return False
        return {"media_url": supported[0]}


@router.message(HasMediaUrl())
async def auto_detect_media(message: Message, media_url: str) -> None:
    user_id = message.from_user.id
    if user_id is None:
        return
    token = _new_session(media_url, user_id)
    await message.answer(
        "🔗 <b>Link supportato rilevato</b>\n\n"
        f"<code>{html.escape(media_url)}</code>\n\n"
        "Scegli il formato:",
        reply_markup=_format_keyboard("fmt", token),
    )


@router.message(Command("dl"))
async def cmd_dl(message: Message, command: CommandObject) -> None:
    user_id = message.from_user.id
    if user_id is None:
        return

    args = (command.args or "").strip()
    urls = media.extract_urls(args)
    if not urls:
        await message.answer(
            "📥 Usa: <code>/dl &lt;URL&gt;</code>\n"
            "Supporta YouTube, Twitter/X, TikTok, Instagram, Reddit e molti altri."
        )
        return

    url = urls[0]
    if not media.is_supported_url(url):
        await message.answer(f"❌ URL non supportato da yt-dlp:\n<code>{html.escape(url)}</code>")
        return

    token = _new_session(url, user_id)
    await message.answer(
        "📥 <b>Download media</b>\n\n"
        f"<code>{html.escape(url)}</code>\n\n"
        "Scegli il formato:",
        reply_markup=_format_keyboard("fmt", token),
    )


@router.callback_query(F.data.startswith("dl:fmt:"))
async def choose_format(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    token, mode = parts[3], parts[2]
    session = _get_session(token)
    if session is None or session["user_id"] != callback.from_user.id:
        await callback.answer("Sessione scaduta, invia di nuovo il link.", show_alert=True)
        return

    session["mode"] = mode
    label = "🎵 Audio MP3" if mode == "audio" else "🎬 Video MP4"

    if callback.message is None:
        await callback.answer()
        return

    await callback.message.edit_text(
        f"{label} — dove lo salvo?",
        reply_markup=_format_keyboard("dest", token),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("dl:dest:"))
async def choose_destination(
    callback: CallbackQuery, bot: Bot, settings: Settings
) -> None:
    parts = callback.data.split(":")
    token, destination = parts[3], parts[2]
    session = _get_session(token)
    if session is None or session["user_id"] != callback.from_user.id:
        await callback.answer("Sessione scaduta, invia di nuovo il link.", show_alert=True)
        return
    if session["mode"] is None:
        await callback.answer("Formato non selezionato.", show_alert=True)
        return

    _drop_session(token)

    if callback.message is None:
        await callback.answer()
        return

    await callback.answer()
    await callback.message.edit_text("⏳ <b>Download in corso…</b>\n\nPuò richiedere qualche minuto.")

    asyncio.create_task(
        _run_download(
            bot=bot,
            chat_id=callback.message.chat.id,
            user_id=callback.from_user.id,
            url=session["url"],
            mode=session["mode"],
            destination=destination,
            settings=settings,
        )
    )


async def _run_download(
    bot: Bot,
    chat_id: int,
    user_id: int,
    url: str,
    mode: str,
    destination: str,
    settings: Settings,
) -> None:
    """Esegue il download in background e gestisce l'esito."""
    workdir = Path(tempfile.gettempdir()) / f"zima-dl-{secrets.token_hex(4)}"
    try:
        result = await media.download_media(url, mode, workdir)
    except Exception as exc:  # noqa: BLE001 - errore di rete/yt-dlp generico
        logger.exception("download fallito per %s", url)
        await bot.send_message(chat_id, f"❌ <b>Download fallito</b>\n\n{html.escape(str(exc))}")
        return

    try:
        if destination == "chat" and result.size_bytes <= media.MAX_TELEGRAM_UPLOAD_BYTES:
            await _send_to_chat(bot, chat_id, result)
        else:
            saved = await _save_to_server(bot, chat_id, result, settings)
            if destination == "chat":
                await bot.send_message(
                    chat_id,
                    f"⚠️ Il file supera i 50 MB (limite Telegram): "
                    f"è stato salvato sul server.\n\n"
                    f"📁 <code>{html.escape(str(saved))}</code>",
                )
    except Exception as exc:  # noqa: BLE001
        logger.exception("invio/salvataggio fallito")
        await bot.send_message(chat_id, f"❌ Errore durante l'invio: {html.escape(str(exc))}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


async def _send_to_chat(bot: Bot, chat_id: int, result: media.MediaResult) -> None:
    file_input = FSInputFile(result.file_path)
    if result.ext == "mp3":
        await bot.send_audio(chat_id, file_input, title=result.title[:255])
    else:
        await bot.send_video(chat_id, file_input)
    await bot.send_message(
        chat_id,
        f"✅ <b>{html.escape(result.title[:200])}</b>\n"
        f"📦 {media.format_size(result.size_bytes)} — inviato in chat.",
    )


async def _save_to_server(
    bot: Bot,
    chat_id: int,
    result: media.MediaResult,
    settings: Settings,
) -> Path:
    settings.downloads_dir.mkdir(parents=True, exist_ok=True)
    target = _unique_path(settings.downloads_dir / result.file_path.name)
    shutil.move(str(result.file_path), str(target))
    await bot.send_message(
        chat_id,
        f"💾 <b>File salvato su ZimaOS</b>\n\n"
        f"📁 <code>{html.escape(str(target))}</code>\n"
        f"📦 {media.format_size(result.size_bytes)}",
    )
    return target


def _unique_path(path: Path) -> Path:
    """Evita sovrascritture aggiungendo un suffisso temporale se serve."""
    if not path.exists():
        return path
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return path.with_name(f"{path.stem}-{stamp}{path.suffix}")
