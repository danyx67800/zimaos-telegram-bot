"""Caricamento e validazione della configurazione (.env / variabili d'ambiente)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Directory radice del progetto (dove vive questo file).
BASE_DIR = Path(__file__).resolve().parent

# Carica il file .env senza sovrascrivere le variabili già presenti nell'ambiente.
load_dotenv(BASE_DIR / ".env")


class ConfigError(RuntimeError):
    """Errore di configurazione non recuperabile, mostrato all'avvio."""


@dataclass(frozen=True)
class Settings:
    """Configurazione runtime del bot, validata all'avvio."""

    bot_token: str
    allowed_user_ids: frozenset[int]
    db_path: Path
    ping_timeout: float
    log_level: str
    downloads_dir: Path
    pastes_dir: Path

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise ConfigError(
                "TELEGRAM_BOT_TOKEN non impostato: aggiungilo al file .env "
                "o alle variabili d'ambiente."
            )

        raw_ids = os.getenv("ALLOWED_USER_IDS", "").strip()
        if not raw_ids:
            raise ConfigError(
                "ALLOWED_USER_IDS non impostato: indica gli ID utente autorizzati, "
                "separati da virgola (es. 123456789,987654321)."
            )

        allowed: set[int] = set()
        for part in raw_ids.split(","):
            part = part.strip()
            if not part:
                continue
            if not part.isdigit():
                raise ConfigError(
                    f"ALLOWED_USER_IDS contiene un valore non valido: {part!r}"
                )
            allowed.add(int(part))
        if not allowed:
            raise ConfigError("ALLOWED_USER_IDS non contiene alcun ID valido.")

        db_path = Path(os.getenv("DB_PATH", "/data/bot.db")).expanduser()

        # Directory per i file scaricati e per i log/paste. Nel container
        # coincidono con /app/downloads e /app/pastes (volume del compose).
        downloads_dir = Path(os.getenv("DOWNLOADS_DIR", BASE_DIR / "downloads")).expanduser()
        pastes_dir = Path(os.getenv("PASTES_DIR", BASE_DIR / "pastes")).expanduser()

        try:
            ping_timeout = float(os.getenv("PING_TIMEOUT", "5"))
        except ValueError as exc:
            raise ConfigError("PING_TIMEOUT deve essere un numero (es. 5).") from exc
        if ping_timeout <= 0:
            raise ConfigError("PING_TIMEOUT deve essere maggiore di zero.")

        log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()

        return cls(
            bot_token=token,
            allowed_user_ids=frozenset(allowed),
            db_path=db_path,
            ping_timeout=ping_timeout,
            log_level=log_level,
            downloads_dir=downloads_dir,
            pastes_dir=pastes_dir,
        )
