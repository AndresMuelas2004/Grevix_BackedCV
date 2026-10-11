# Stage 1: build the React frontend into static files.
FROM node:24-slim AS frontend

WORKDIR /app/frontend

# Dependencies first, so code changes do not reinstall them.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend ./
RUN npm run build

# Stage 2: the Python app, which also serves the built frontend.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app/backend

# Dependencies first, so code changes do not reinstall them.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY backend/src ./src
COPY backend/samples ./samples
RUN uv sync --locked --no-dev

COPY --from=frontend /app/frontend/dist /app/frontend/dist

RUN useradd --create-home app && mkdir -p /app/data && chown app /app/data
USER app

ENV PATH="/app/backend/.venv/bin:$PATH" \
    BACKEDCV_DATA_DIR=/app/data \
    BACKEDCV_FRONTEND_DIST=/app/frontend/dist \
    BACKEDCV_SAMPLES_DIR=/app/backend/samples

EXPOSE 8000
CMD ["uvicorn", "backedcv.main:app", "--host", "0.0.0.0", "--port", "8000"]
