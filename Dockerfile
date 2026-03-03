FROM ghcr.io/astral-sh/uv:python3.11-bookworm

WORKDIR /app

COPY pyproject.toml ./

RUN uv sync

COPY . .

EXPOSE 8000

CMD ["sleep", "infinity"]