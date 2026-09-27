# syntax=docker/dockerfile:1.7

FROM python:3.12-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for better layer caching, then the project itself.
COPY pyproject.toml ./
COPY src ./src
RUN python -m venv /app/.venv \
  && /app/.venv/bin/pip install .


FROM python:3.12-slim-bookworm AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    COVOIT_DATABASE_URL="sqlite:////data/covoit.db"

RUN useradd --create-home --uid 10001 appuser \
  && mkdir -p /data && chown appuser:appuser /data

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv

USER appuser
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=6 \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["uvicorn", "covoit.main:app", "--host", "0.0.0.0", "--port", "8000"]
