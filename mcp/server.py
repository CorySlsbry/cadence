"""Cadence remote MCP server — lets a user drive Cadence from Claude (list projects, start
renders, fetch finished clips) over Streamable HTTP with OAuth 2.1. Light service: no engine /
ffmpeg / whisper deps — it only talks to Supabase (queue + reads) as the authenticated user.

Run: uvicorn server:app --host 0.0.0.0 --port $PORT
"""

from __future__ import annotations

import os

from starlette.responses import JSONResponse

import db
from auth import CadenceOAuth, login_route
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_access_token

mcp = FastMCP(
    "Cadence",
    instructions=(
        "Cadence turns recordings into premium short-form videos. Use these tools to list the "
        "user's projects, queue renders, check render status, and fetch finished clips. Every "
        "action is scoped to the signed-in Cadence user."
    ),
    auth=CadenceOAuth(),
)


def _uid() -> str:
    """The authenticated Cadence user id (the bearer token's subject)."""
    tok = get_access_token()
    uid = getattr(tok, "subject", None) or (getattr(tok, "claims", None) or {}).get("sub")
    if not uid:
        raise ValueError("no authenticated user on this request")
    return uid


@mcp.tool
def list_projects() -> list[dict]:
    """List your Cadence projects (id, name, created_at), newest first."""
    return db.list_projects(_uid())


@mcp.tool
def create_project(name: str) -> dict:
    """Create a new Cadence project. Returns the created project."""
    return db.create_project(_uid(), (name or "Untitled project").strip())


@mcp.tool
def list_clips(project_id: str | None = None) -> list[dict]:
    """List your renders/clips with status, progress, output_path and any multi-clip array.
    Optionally filter to one project_id."""
    return db.list_clips(_uid(), project_id)


@mcp.tool
def get_status(job_id: str) -> dict:
    """Get a render job's status, progress, result, clips, hooks and repurpose assets by id."""
    return db.get_job(_uid(), job_id) or {"error": "job not found"}


@mcp.tool
def start_render(recording_path: str, project_id: str | None = None,
                 customization: dict | None = None) -> dict:
    """Queue a render of an already-uploaded recording (recording_path is its Storage key, e.g.
    '<user-id>/<file>.mp4', obtained when the recording was uploaded in Cadence). customization
    may include {"multiclip": {"count": 3}, "captions": true, "broll_mode": "ai|none|background",
    "broll_quality": "fast|standard|ultra"}. Counts against your monthly render quota. Returns
    the queued job (poll get_status for progress)."""
    uid = _uid()
    used, limit = db.renders_used(uid), db.monthly_limit(uid)
    if limit and used >= limit:
        return {"error": f"monthly render limit reached ({used}/{limit})"}
    return db.start_render(uid, recording_path, project_id, customization)


@mcp.tool
def get_download_url(job_id: str) -> dict:
    """Get a short-lived (1h) signed download URL for a finished render's output video."""
    job = db.get_job(_uid(), job_id)
    if not job or not job.get("output_path"):
        return {"error": "that job has no finished output yet"}
    url = db.signed_output_url(job["output_path"])
    return {"url": url} if url else {"error": "could not sign a download url"}


# OAuth login page (GET form / POST verify) used by the authorization-code flow.
mcp.custom_route("/login", methods=["GET", "POST"])(login_route)


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_request):  # noqa: ANN001
    return JSONResponse({"ok": True})


app = mcp.http_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
