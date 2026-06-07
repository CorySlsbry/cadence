"""Data layer for the Cadence MCP service — Supabase access (service-role for everything the
MCP does on the user's behalf) + the OAuth 2.1 AS state (clients/codes/refresh tokens) + the
tool queries. Every tool query is scoped to the validated ``user_id`` (the bearer token's
subject), which is the per-tenant isolation since we use the service-role key.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from supabase import Client, create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]


@lru_cache(maxsize=1)
def admin() -> Client:
    """Service-role client — bypasses RLS. Used for OAuth state + per-user tool queries."""
    return create_client(SUPABASE_URL, os.environ["SUPABASE_SERVICE_ROLE_KEY"])


def authenticate(email: str, password: str) -> str | None:
    """Verify a Cadence (Supabase Auth) login and return the user id, or None. Uses a throwaway
    anon client so the password is checked by GoTrue exactly as the web app does."""
    try:
        anon = create_client(SUPABASE_URL, os.environ["SUPABASE_ANON_KEY"])
        res = anon.auth.sign_in_with_password({"email": email, "password": password})
        return res.user.id if res and res.user else None
    except Exception:  # noqa: BLE001 - any failure = bad credentials
        return None


# --- OAuth client registry (RFC 7591 DCR) ------------------------------------------------
def save_client(row: dict[str, Any]) -> None:
    admin().table("oauth_clients").upsert(row, on_conflict="client_id").execute()


def get_client(client_id: str) -> dict[str, Any] | None:
    r = admin().table("oauth_clients").select("*").eq("client_id", client_id).limit(1).execute()
    return r.data[0] if r.data else None


# --- authorization codes (single-use) ----------------------------------------------------
def save_code(row: dict[str, Any]) -> None:
    admin().table("oauth_codes").insert(row).execute()


def get_code(code: str) -> dict[str, Any] | None:
    r = admin().table("oauth_codes").select("*").eq("code", code).limit(1).execute()
    return r.data[0] if r.data else None


def delete_code(code: str) -> None:
    admin().table("oauth_codes").delete().eq("code", code).execute()


# --- refresh tokens (stored hashed) ------------------------------------------------------
def save_refresh(row: dict[str, Any]) -> None:
    admin().table("oauth_refresh_tokens").insert(row).execute()


def get_refresh(token_hash: str) -> dict[str, Any] | None:
    r = admin().table("oauth_refresh_tokens").select("*").eq("token_hash", token_hash).limit(1).execute()
    return r.data[0] if r.data else None


def revoke_refresh(token_hash: str) -> None:
    admin().table("oauth_refresh_tokens").update({"revoked": True}).eq("token_hash", token_hash).execute()


# --- tool queries (all scoped to user_id) ------------------------------------------------
def list_projects(user_id: str) -> list[dict[str, Any]]:
    r = (admin().table("projects").select("id,name,created_at")
         .eq("user_id", user_id).order("created_at", desc=True).limit(50).execute())
    return r.data or []


def create_project(user_id: str, name: str) -> dict[str, Any]:
    r = admin().table("projects").insert({"user_id": user_id, "name": name}).execute()
    return r.data[0]


def list_clips(user_id: str, project_id: str | None = None) -> list[dict[str, Any]]:
    q = (admin().table("render_jobs")
         .select("id,project_id,status,progress,output_path,clips,hooks,created_at")
         .eq("user_id", user_id))
    if project_id:
        q = q.eq("project_id", project_id)
    return (q.order("created_at", desc=True).limit(50).execute()).data or []


def get_job(user_id: str, job_id: str) -> dict[str, Any] | None:
    r = (admin().table("render_jobs")
         .select("id,status,progress,output_path,result,clips,hooks,repurpose,error")
         .eq("user_id", user_id).eq("id", job_id).limit(1).execute())
    return r.data[0] if r.data else None


def start_render(user_id: str, recording_path: str, project_id: str | None,
                 customization: dict[str, Any] | None) -> dict[str, Any]:
    row = {"user_id": user_id, "recording_path": recording_path, "status": "queued",
           "customization": customization or {}}
    if project_id:
        row["project_id"] = project_id
    return admin().table("render_jobs").insert(row).execute().data[0]


def renders_used(user_id: str) -> int:
    r = admin().rpc("renders_used_this_month", {"uid": user_id}).execute()
    return int(r.data or 0)


def monthly_limit(user_id: str) -> int:
    r = admin().table("profiles").select("monthly_render_limit").eq("id", user_id).limit(1).execute()
    return int((r.data[0]["monthly_render_limit"] if r.data else 0) or 0)


def signed_output_url(output_path: str, expires: int = 3600) -> str | None:
    try:
        res = admin().storage.from_("outputs").create_signed_url(output_path, expires)
        return res.get("signedURL") or res.get("signedUrl")
    except Exception:  # noqa: BLE001
        return None
