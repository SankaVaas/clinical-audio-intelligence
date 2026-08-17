# --- Build stage: install deps into a venv so the runtime image stays lean ---
FROM python:3.11-slim AS build

WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY backend/requirements.txt .
# torch CPU wheel + whisper are heavy; keep pip cache off to keep layer small
RUN pip install --no-cache-dir -r requirements.txt

# --- Runtime stage ---
FROM python:3.11-slim AS runtime

# ffmpeg is required by Whisper for audio decoding
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --system app && adduser --system --ingroup app app

WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY backend/ /app/

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    # Whisper model cache -- mount a volume here in k8s so pods don't
    # re-download the model on every cold start
    XDG_CACHE_HOME=/app/.cache

RUN mkdir -p /app/.cache && chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health', timeout=2)" || exit 1

# --workers 1: model objects (Whisper) are not fork-safe/cheap to duplicate.
# Scale horizontally via k8s replicas + HPA instead of uvicorn workers.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
