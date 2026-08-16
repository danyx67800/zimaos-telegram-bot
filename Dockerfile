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

COPY . .

# Directory per il database SQLite (montata come volume dal compose).
RUN mkdir -p /data

# Il bot viene eseguito come root per poter leggere /var/run/docker.sock (ro).
# Per un profilo più restrittivo vedere le note nel README.
CMD ["python", "main.py"]
