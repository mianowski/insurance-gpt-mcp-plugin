FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_DEV=1

WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-install-project

COPY src ./src
COPY knowledge ./knowledge
RUN uv sync --frozen

ENV IGPT_HOST=0.0.0.0 IGPT_PORT=8000
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "insurance-gpt"]
