# =============================================================================
# Stage 1: builder — scarica/compila tutte le wheel una sola volta.
# =============================================================================
FROM python:3.11-slim AS builder

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip

COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# =============================================================================
# Stage 2: runtime — immagine finale minimale.
# =============================================================================
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

# ffmpeg: richiesto da yt-dlp per la conversione MP3 e l'unione dei flussi.
# tzdata: necessario per il fuso orario del container (TZ).
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY . .

# Directory dati (database SQLite, download e paste).
RUN mkdir -p /data /app/downloads /app/pastes

# Il bot viene eseguito come root per poter leggere /var/run/docker.sock (ro).
# Per un profilo più restrittivo vedere le note nel README.
CMD ["python", "main.py"]
