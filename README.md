# 🤖 ZimaOS Telegram Bot

Bot Telegram **privato** per monitorare e gestire un server ZimaOS da chat.
Scritto in Python con [aiogram 3.x](https://aiogram.dev/), pensato per girare
in un container Docker.

## ✨ Funzionalità

- **Controllo accessi**: solo gli utenti in `ALLOWED_USER_IDS` possono usare il
  bot (middleware globale, blocca gli update prima di ogni handler).
- `/start` e `/help` — benvenuto interattivo con tastiera in-line.
- `/stats` — CPU, RAM, dischi, uptime di sistema e del container (via `psutil`).
- `/notes` — CRUD di note rapide e link su SQLite:
  - `/notes` → elenco
  - `/notes add <testo o link>` → salva
  - `/notes del <id>` → elimina
- `/ping <host o URL>` — latenza e disponibilità (TCP connect).
- `/docker` — stato dei container dell'host (richiede il socket Docker).

## 📁 Struttura del progetto

```
├── main.py                 # entry point
├── config.py               # caricamento/validazione .env
├── requirements.txt
├── Dockerfile              # multi-stage
├── docker-compose.yml      # pronto per ZimaOS
├── middlewares/
│   └── access.py           # autenticazione ID utente
├── handlers/
│   ├── general.py          # /start, /help
│   ├── sysinfo.py          # /stats
│   ├── notes.py            # /notes
│   ├── ping.py             # /ping
│   └── docker_handler.py   # /docker
└── utils/
    ├── db.py               # SQLite
    ├── sysinfo.py          # psutil
    ├── network.py          # ping TCP
    └── docker_stats.py     # API socket Docker
```

## ⚙️ Configurazione

Copia `.env.example` in `.env` e compila:

```bash
cp .env.example .env
```

| Variabile            | Descrizione                                        |
| -------------------- | -------------------------------------------------- |
| `TELEGRAM_BOT_TOKEN` | Token del bot (da @BotFather)                      |
| `ALLOWED_USER_IDS`   | ID utente autorizzati, separati da virgola         |
| `DB_PATH`            | Percorso DB SQLite (default `/data/bot.db`)        |
| `PING_TIMEOUT`       | Timeout `/ping` in secondi (default `5`)           |
| `LOG_LEVEL`          | `DEBUG`, `INFO`, `WARNING`, `ERROR`                |

Il tuo ID Telegram lo trovi scrivendo a [@userinfobot](https://t.me/userinfobot).

## 🐳 Avvio con Docker Compose (ZimaOS)

Il `docker-compose.yml` monta:

- `./data:/data` — persistenza del database SQLite;
- `/var/run/docker.sock:/var/run/docker.sock:ro` — accesso in sola lettura a
  Docker per il comando `/docker`.

```bash
cp .env.example .env   # compila token e ID utente
docker compose pull
docker compose up -d
```

> **Nota sul socket Docker**: per leggere `/var/run/docker.sock` il container
> viene eseguito come `root` (default). Per un profilo più restrittivo esegui il
> container con un utente che appartenga al gruppo `docker` dell'host, ad es.
> aggiungendo al servizio `user: "1000:1000"` e verificando che il GID 1000
> corrisponda al gruppo `docker`.

## 🛍 Installazione dallo store ZimaOS

Il repository è già predisposto come app dello store ZimaOS/CasaOS: include il
file `.env` (default mostrati nel form di installazione), il blocco `x-casaos`
nel `docker-compose.yml` e l'icona `logo.png`.

1. Nello store ZimaOS usa **Install customized app** e importa il repo
   `https://github.com/danyx67800/zimaos-telegram-bot`.
2. Nel form di installazione compila **obbligatoriamente**:
   - `TELEGRAM_BOT_TOKEN` — il token del bot (da @BotFather);
   - `ALLOWED_USER_IDS` — i tuoi ID Telegram, separati da virgola.
3. Avvia l'app.

> ⚠️ Il file `.env` nel repo contiene solo **valori di default** ed è tracciato
> perché lo store lo richiede all'installazione. Non committare mai il token
> reale: inseriscilo solo dal form di ZimaOS oppure nel `.env` locale senza
> fare push.

## 📦 Pubblicazione su GitHub Container Registry (GHCR)

Il workflow
[`.github/workflows/docker-publish.yml`](.github/workflows/docker-publish.yml)
compila l'immagine (multi-arch `linux/amd64` + `linux/arm64`) e la pubblica su
GHCR a ogni push sul branch `main`.

Pubblicazione manuale in locale:

```bash
# 1. Autenticarsi a GHCR (una sola volta)
echo "$CR_PAT" | docker login ghcr.io -u <TUO-UTENTE> --password-stdin

# 2. Compilare l'immagine
docker build -t ghcr.io/<TUO-UTENTE>/zimaos-telegram-bot:latest .

# 3. Push
docker push ghcr.io/<TUO-UTENTE>/zimaos-telegram-bot:latest
```

> Se usi il GitHub CLI, assicurati che il token includa gli scope packages:
> `gh auth refresh -s write:packages -s read:packages`.

## 🧪 Esecuzione locale (senza Docker)

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## 🔒 Sicurezza

- Il token e la lista degli utenti autorizzati vanno inseriti **solo in
  locale** (form di ZimaOS o `.env` locale): il `.env` presente nel repo
  contiene esclusivamente default segnaposto per lo store.
- Il middleware di accesso rifiuta ogni update non autorizzato **prima** che
  venga eseguito qualsiasi filtro o handler, restituendo un messaggio d'errore.
- Il socket Docker è montato **in sola lettura**.
