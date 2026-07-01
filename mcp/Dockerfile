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
# MCP_APP selects which server runs: default the authenticated one; the public service sets
# MCP_APP=public_server. Keeps the public deploy durable in config (not a one-off --command flag).
CMD ["sh", "-c", "exec uvicorn ${MCP_APP:-server}:app --host 0.0.0.0 --port ${PORT:-8080}"]
