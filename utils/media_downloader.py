"""Helper per il download di media tramite yt-dlp.

Tutte le operazioni pesanti vengono eseguite in un thread separato
(`asyncio.to_thread`) per non bloccare il loop di aiogram.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import yt_dlp

logger = logging.getLogger("zima-bot.downloader")

# Limite API Telegram per i file inviati da un bot.
MAX_TELEGRAM_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

# Piattaforme riconosciute automaticamente nei messaggi (dominio -> check rapido).
KNOWN_PLATFORMS = {
    "youtube.com",
    "youtu.be",
    "m.youtube.com",
    "music.youtube.com",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "vm.tiktok.com",
    "instagram.com",
    "reddit.com",
    "www.reddit.com",
}

_URL_RE = re.compile(r"https?://[^\s<>\"']+")


@dataclass
class MediaResult:
    """Risultato di un download completato."""

    title: str
    file_path: Path
    size_bytes: int
    ext: str


def extract_urls(text: str) -> list[str]:
    """Estrae tutti gli URL http(s) da un testo."""
    return _URL_RE.findall(text or "")


def _hostname(url: str) -> str:
    match = re.match(r"https?://([^/?#]+)", url)
    if not match:
        return ""
    host = match.group(1).lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def is_known_platform(url: str) -> bool:
    """True se l'URL appartiene a una delle piattaforme principali."""
    return _hostname(url) in KNOWN_PLATFORMS


def is_supported_url(url: str) -> bool:
    """True se yt-dlp ha un estrattore in grado di gestire l'URL.

    Il controllo usa solo gli *extractor* (regex), nessuna richiesta di rete.
    """
    try:
        from yt_dlp.extractor import gen_extractor_classes

        for cls in gen_extractor_classes():
            # L'extractor "generic" fa match con qualsiasi URL: va escluso,
            # altrimenti qualunque link risulterebbe "supportato".
            if getattr(cls, "IE_NAME", None) == "generic":
                continue
            if cls.suitable(url):
                return True
    except Exception:  # noqa: BLE001 - non deve mai far fallire il bot
        logger.exception("controllo yt-dlp fallito")
        return is_known_platform(url)
    return False


def _final_file_path(info: dict, workdir: Path, mode: str) -> Path | None:
    """Ricava il percorso del file finale prodotto da yt-dlp."""
    # yt-dlp espone il percorso post-elaborazione in 'requested_downloads'.
    try:
        downloaded = info["requested_downloads"][0]["filepath"]
        if downloaded and Path(downloaded).exists():
            return Path(downloaded)
    except (KeyError, IndexError, TypeError):
        pass

    # Fallback: prepara il nome dal template ed eventualmente cambia estensione.
    try:
        base = Path(info["_filename"])
    except (KeyError, TypeError):
        base = None

    if base is not None:
        candidates = [base]
        if mode == "audio":
            candidates.append(base.with_suffix(".mp3"))
        else:
            candidates.append(base.with_suffix(".mp4"))
        for candidate in candidates:
            if candidate.exists():
                return candidate

    # Ultima spiaggia: file più recente nella directory di lavoro.
    files = sorted(workdir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _download_sync(url: str, mode: str, workdir: Path) -> MediaResult:
    """Download sincrono (da eseguire in un thread)."""
    workdir.mkdir(parents=True, exist_ok=True)

    template = str(workdir / "%(title).100B [%(id)s].%(ext)s")
    options: dict = {
        "outtmpl": template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 30,
        "windowsfilenames": False,
    }

    if mode == "audio":
        options.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
            }
        )
    else:
        options.update(
            {
                "format": "bestvideo[height<=?1080]+bestaudio/best",
                "merge_output_format": "mp4",
            }
        )

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
        title = info.get("title") or url

    file_path = _final_file_path(info, workdir, mode)
    if file_path is None:
        raise RuntimeError("yt-dlp non ha prodotto alcun file.")

    return MediaResult(
        title=str(title),
        file_path=file_path,
        size_bytes=file_path.stat().st_size,
        ext=file_path.suffix.lstrip(".").lower(),
    )


async def download_media(url: str, mode: str, workdir: Path) -> MediaResult:
    """Scarica il media in un thread separato (non blocca il loop)."""
    return await asyncio.to_thread(_download_sync, url, mode, workdir)


def format_size(num: float) -> str:
    """Formatta un numero di byte in unità leggibili."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024.0:
            return f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} PB"
