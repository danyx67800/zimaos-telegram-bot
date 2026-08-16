"""Modulo Pastebin Locale & Gestione Log.

- /paste <testo> (o messaggio molto lungo): genera un file .txt scaricabile.
- Invio di un file .log/.txt: riepilogo (prime/ultime righe) + salvataggio
  nella cartella condivisa di ZimaOS.
- /searchlog <keyword>: cerca una parola nel log inviato più di recente.
"""

from __future__ import annotations

import html
import logging
import re
import secrets
import shutil
import tempfile
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, Filter
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import Settings

router = Router(name="pastebin")

logger = logging.getLogger("zima-bot.pastebin")

_TEXT_EXTENSIONS = {
    ".log", ".txt", ".md", ".json", ".yaml", ".yml", ".csv",
    ".conf", ".ini", ".xml", ".py", ".sh", ".js", ".ts", ".html",
}
_LONG_TEXT_THRESHOLD = 1024
_TTL_SECONDS = 30 * 60

# {token: testo} per il salvataggio di /paste; {user_id: percorso} per i log.
_pending_texts: dict[str, tuple[str, float]] = {}
_last_logs: dict[int, Path] = {}


def _cleanup_texts() -> None:
    now = time.time()
    expired = [t for t, (_, ts) in _pending_texts.items() if now - ts > _TTL_SECONDS]
    for token in expired:
        _pending_texts.pop(token, None)


def _keyboard_save_text(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💾 Salva su ZimaOS", callback_data=f"paste:save_text:{token}")]
        ]
    )


def _keyboard_save_log() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💾 Salva su ZimaOS", callback_data="paste:save_log")]
        ]
    )


def _summarize_log(path: Path, first_n: int = 15, last_n: int = 15) -> tuple[int, list[str], list[str]]:
    """Conta le righe e restituisce le prime N e le ultime N (lettura a flusso)."""
    first_lines: list[str] = []
    last_lines: deque[str] = deque(maxlen=last_n)
    total = 0
    with open(path, "r", errors="replace") as fh:
        for line in fh:
            total += 1
            if len(first_lines) < first_n:
                first_lines.append(line.rstrip("\n"))
            last_lines.append(line.rstrip("\n"))
    return total, first_lines, list(last_lines)


def _search_in_log(path: Path, keyword: str, max_results: int = 30) -> list[tuple[int, str]]:
    kw = keyword.lower()
    results: list[tuple[int, str]] = []
    with open(path, "r", errors="replace") as fh:
        for lineno, line in enumerate(fh, 1):
            if kw in line.lower():
                results.append((lineno, line.rstrip("\n")))
                if len(results) >= max_results:
                    break
    return results


def _truncate(line: str, limit: int = 150) -> str:
    return line if len(line) <= limit else line[: limit - 1] + "…"


async def _send_paste_document(
    bot: Bot, chat_id: int, text: str, filename: str
) -> None:
    await bot.send_document(
        chat_id,
        BufferedInputFile(text.encode("utf-8"), filename=filename),
        caption="📄 File pronto per il download.",
    )


class IsLongText(Filter):
    """Scatta solo per messaggi di testo molto lunghi (non comandi)."""

    async def __call__(self, message: Message) -> bool:
        if message.text is None or message.text.startswith("/"):
            return False
        return len(message.text) > _LONG_TEXT_THRESHOLD


# ---------------------------------------------------------------------------
# /paste e messaggi molto lunghi
# ---------------------------------------------------------------------------


@router.message(Command("paste"))
async def cmd_paste(
    message: Message, command: CommandObject, bot: Bot
) -> None:
    text = (command.args or "").strip()

    # Se non ci sono argomenti, usa il testo del messaggio a cui si risponde.
    if not text and message.reply_to_message is not None:
        text = (message.reply_to_message.text or "").strip()

    if not text:
        await message.answer(
            "📄 Usa: <code>/paste &lt;testo o codice&gt;</code>\n"
            "Oppure rispondi a un messaggio con <code>/paste</code>."
        )
        return

    _cleanup_texts()
    token = secrets.token_hex(6)
    _pending_texts[token] = (text, time.time())

    filename = f"paste-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
    await _send_paste_document(bot, message.chat.id, text, filename)
    await message.answer(
        "Scegli se salvarlo anche sul server:",
        reply_markup=_keyboard_save_text(token),
    )


@router.message(IsLongText())
async def auto_paste_long_text(message: Message, bot: Bot) -> None:
    _cleanup_texts()
    token = secrets.token_hex(6)
    _pending_texts[token] = (message.text, time.time())

    filename = f"paste-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
    await message.answer("📄 Messaggio molto lungo rilevato, ecco il file:")
    await _send_paste_document(bot, message.chat.id, message.text, filename)
    await message.answer(
        "Scegli se salvarlo anche sul server:",
        reply_markup=_keyboard_save_text(token),
    )


@router.callback_query(F.data.startswith("paste:save_text:"))
async def save_text_callback(callback: CallbackQuery, settings: Settings) -> None:
    token = callback.data.split(":", 2)[2]
    entry = _pending_texts.get(token)
    if entry is None:
        await callback.answer("Sessione scaduta.", show_alert=True)
        return

    text, _ = entry
    _pending_texts.pop(token, None)

    settings.pastes_dir.mkdir(parents=True, exist_ok=True)
    filename = f"paste-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
    target = settings.pastes_dir / filename
    target.write_text(text, encoding="utf-8")

    await callback.answer("Salvato.")
    if callback.message is not None:
        await callback.message.answer(
            f"💾 <b>Testo salvato su ZimaOS</b>\n\n"
            f"📁 <code>{html.escape(str(target))}</code>\n"
            f"📦 {len(text.encode('utf-8'))} byte"
        )


# ---------------------------------------------------------------------------
# File di log/documenti
# ---------------------------------------------------------------------------


@router.message(F.document)
async def on_document(message: Message, bot: Bot) -> None:
    document = message.document
    filename = document.file_name or "file"
    suffix = Path(filename).suffix.lower()

    if suffix not in _TEXT_EXTENSIONS:
        return

    user_id = message.from_user.id
    if user_id is None:
        return

    # Scarica il file in una posizione temporanea.
    tmp_dir = Path(tempfile.gettempdir()) / f"zima-logs-{user_id}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename)
    dest = tmp_dir / f"{int(time.time())}-{safe_name}"

    try:
        file = await bot.get_file(document.file_id)
        with open(dest, "wb") as fh:
            await bot.download_file(file.file_path, destination=fh)
    except Exception as exc:  # noqa: BLE001
        logger.exception("download file fallito")
        await message.answer(f"❌ Impossibile scaricare il file: {exc}")
        return

    # Libera il log precedente dell'utente.
    previous = _last_logs.pop(user_id, None)
    if previous is not None and previous.exists():
        previous.unlink(missing_ok=True)
    _last_logs[user_id] = dest

    total, first_lines, last_lines = _summarize_log(dest)
    size_mb = dest.stat().st_size / (1024 * 1024)

    lines = [
        f"📄 <b>Riepilogo di {html.escape(filename)}</b>\n",
        f"📦 {size_mb:.2f} MB — {total} righe\n",
        "🔝 <b>Prime righe:</b>",
    ]
    lines += [f"<code>{_truncate(html.escape(l))}</code>" for l in first_lines]
    lines += ["\n🔻 <b>Ultime righe:</b>"]
    lines += [f"<code>{_truncate(html.escape(l))}</code>" for l in last_lines]
    lines += [
        "\n🔍 Cerca una parola con <code>/searchlog &lt;keyword&gt;</code>",
    ]

    await message.answer("\n".join(lines), reply_markup=_keyboard_save_log())


@router.callback_query(F.data == "paste:save_log")
async def save_log_callback(callback: CallbackQuery, settings: Settings) -> None:
    user_id = callback.from_user.id
    source = _last_logs.get(user_id)

    if source is None or not source.exists():
        await callback.answer("Nessun log recente da salvare.", show_alert=True)
        return

    settings.pastes_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = settings.pastes_dir / f"log-{stamp}-{source.name}"
    shutil.copy2(source, target)

    await callback.answer("Salvato.")
    if callback.message is not None:
        await callback.message.answer(
            f"💾 <b>Log salvato su ZimaOS</b>\n\n"
            f"📁 <code>{html.escape(str(target))}</code>"
        )


@router.message(Command("searchlog"))
async def cmd_search_log(message: Message, command: CommandObject) -> None:
    user_id = message.from_user.id
    if user_id is None:
        return

    keyword = (command.args or "").strip()
    if not keyword:
        await message.answer(
            "🔍 Usa: <code>/searchlog &lt;keyword&gt;</code>\n"
            "Cerca all'interno dell'ultimo file di log che hai inviato."
        )
        return

    source = _last_logs.get(user_id)
    if source is None or not source.exists():
        await message.answer(
            "❌ Nessun file di log inviato in precedenza. "
            "Invia prima un file <code>.log</code> o <code>.txt</code>."
        )
        return

    results = _search_in_log(source, keyword)
    if not results:
        await message.answer(f"🔍 Nessuna riga contenente <b>{html.escape(keyword)}</b>.")
        return

    lines = [f"🔍 <b>{len(results)}+ righe</b> con \"{html.escape(keyword)}\":"]
    for lineno, content in results:
        lines.append(f"<code>{lineno}:</code> {html.escape(_truncate(content))}")

    # Telegram limita i messaggi a ~4096 caratteri.
    answer = "\n".join(lines)
    if len(answer) > 4000:
        answer = answer[:3990] + "\n…"

    await message.answer(answer)
