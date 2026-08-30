# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

FROM base AS builder
RUN pip install --upgrade pip
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --prefix=/install .

FROM base AS runtime
RUN useradd --system --uid 10001 --create-home flux
COPY --from=builder /install /usr/local
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
USER flux
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/livez').status==200 else 1)"
CMD ["uvicorn", "flux.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
