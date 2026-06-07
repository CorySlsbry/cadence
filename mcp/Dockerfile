# syntax=docker/dockerfile:1
# Cadence remote MCP server — light Python service (FastMCP + Supabase + OAuth 2.1).
# Build context: repo ROOT  ->  docker build -f mcp/Dockerfile .
FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY mcp/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt
COPY mcp/ ./
# Cloud Run injects $PORT (default 8080).
CMD ["sh", "-c", "exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-8080}"]
