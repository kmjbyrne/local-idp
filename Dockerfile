# syntax=docker/dockerfile:1

# Keep this in step with .python-version and requires-python in pyproject.toml.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /usr/src/app

# git is here for uv, not for the source: oidcutils resolves from a git URL, and
# python:*-slim ships without a git binary for it to clone with. Dropping it
# fails the dependency layer with "Git executable not found", which reads like a
# uv problem rather than a missing package.
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates git && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd --system app && \
    useradd --system --gid app --home-dir /usr/src/app --no-create-home app

COPY --from=ghcr.io/astral-sh/uv:0.9.9 /uv /usr/local/bin/uv

# Dependencies resolve in their own layer so app edits do not invalidate them.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev

COPY . .
RUN uv sync --frozen --no-dev && \
    mkdir -p instance && \
    chown app:app instance

USER app

EXPOSE 9001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9001"]
