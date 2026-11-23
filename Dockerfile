FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first so Docker can cache this layer.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY agent.py db_schema.py voice_app.py ./
COPY web/ ./web/

# Run as an unprivileged user.
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# $PORT is supplied by Render; fall back to 8000 for local Docker runs.
CMD ["sh", "-c", "uvicorn voice_app:app --host 0.0.0.0 --port ${PORT:-8000}"]
