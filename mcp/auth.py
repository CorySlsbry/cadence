"""Cadence MCP OAuth 2.1 authorization server (FastMCP OAuthProvider).

The MCP server is BOTH the resource server and its own AS. FastMCP wires the protocol routes
(/authorize, /token, /register, /.well-known/*) to these methods + does PKCE validation in its
token handler; we implement: client storage (DCR), authorization-code + refresh storage, user
authentication (against Supabase Auth), and audience-bound JWT access tokens whose ``sub`` is
the Cadence user id. The bearer token is validated on every tool call and NEVER forwarded
downstream (confused-deputy safe) — tools use the service-role key scoped to ``sub``.
"""

from __future__ import annotations

import hashlib
import html
import os
import secrets
import time
from datetime import datetime, timezone

import jwt
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

import db
from fastmcp.server.auth import OAuthProvider
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.server.auth.settings import ClientRegistrationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

JWT_SECRET = os.environ["CADENCE_MCP_JWT_SECRET"]
BASE_URL = os.environ["CADENCE_MCP_BASE_URL"].rstrip("/")
RESOURCE = f"{BASE_URL}/mcp"  # canonical MCP URI (one acceptable audience)
ACCESS_TTL = 3600
REFRESH_TTL = 30 * 24 * 3600
TXN_TTL = 600


def _now() -> int:
    return int(time.time())


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _iso(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _epoch(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def _mint_access(user_id: str, client_id: str, scopes: list[str], resource: str | None) -> str:
    return jwt.encode(
        {"iss": BASE_URL, "sub": user_id, "aud": resource or RESOURCE, "client_id": client_id,
         "scope": " ".join(scopes or []), "iat": _now(), "exp": _now() + ACCESS_TTL},
        JWT_SECRET, algorithm="HS256",
    )


def _verify_access(token: str) -> dict | None:
    try:  # accept either the base URL or the /mcp URI as audience (metadata-suffix tolerant)
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"], audience=[BASE_URL, RESOURCE])
    except Exception:  # noqa: BLE001
        return None


class CadenceOAuth(OAuthProvider):
    def __init__(self) -> None:
        super().__init__(
            base_url=BASE_URL,
            resource_base_url=BASE_URL,
            client_registration_options=ClientRegistrationOptions(
                enabled=True, valid_scopes=["cadence"], default_scopes=["cadence"]
            ),
        )

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        db.save_client({
            "client_id": client_info.client_id,
            "client_secret": client_info.client_secret,
            "client_name": client_info.client_name,
            "redirect_uris": [str(u) for u in client_info.redirect_uris],
            "grant_types": list(client_info.grant_types or ["authorization_code", "refresh_token"]),
        })

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        row = db.get_client(client_id)
        if not row:
            return None
        return OAuthClientInformationFull(
            client_id=row["client_id"],
            client_secret=row.get("client_secret"),
            redirect_uris=row["redirect_uris"],
            client_name=row.get("client_name"),
            grant_types=row.get("grant_types") or ["authorization_code", "refresh_token"],
            scope="cadence",  # the one scope this AS grants; without it /authorize 400s invalid_scope
            token_endpoint_auth_method="none" if not row.get("client_secret") else "client_secret_post",
        )

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        # The user isn't authenticated yet → bounce to our login page carrying a signed txn that
        # holds the (already client/redirect-validated) authorization request.
        txn = jwt.encode(
            {"client_id": client.client_id, "redirect_uri": str(params.redirect_uri),
             "code_challenge": params.code_challenge, "state": params.state,
             "scopes": params.scopes or ["cadence"], "resource": params.resource or RESOURCE,
             "exp": _now() + TXN_TTL},
            JWT_SECRET, algorithm="HS256",
        )
        return f"{BASE_URL}/login?txn={txn}"

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        row = db.get_code(authorization_code)
        if not row or row["client_id"] != client.client_id:
            return None
        return AuthorizationCode(
            code=row["code"], scopes=(row.get("scope") or "").split(),
            expires_at=_epoch(row["expires_at"]), client_id=row["client_id"],
            code_challenge=row["code_challenge"], redirect_uri=row["redirect_uri"],
            redirect_uri_provided_explicitly=True, resource=row.get("resource"),
            subject=row["user_id"],
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        db.delete_code(authorization_code.code)  # single-use
        scopes = authorization_code.scopes or ["cadence"]
        access = _mint_access(authorization_code.subject, client.client_id, scopes, authorization_code.resource)
        refresh = secrets.token_urlsafe(32)
        db.save_refresh({
            "token_hash": _hash(refresh), "client_id": client.client_id,
            "user_id": authorization_code.subject, "scope": " ".join(scopes),
            "expires_at": _iso(_now() + REFRESH_TTL),
        })
        return OAuthToken(access_token=access, token_type="Bearer", expires_in=ACCESS_TTL,
                          scope=" ".join(scopes), refresh_token=refresh)

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        row = db.get_refresh(_hash(refresh_token))
        if not row or row.get("revoked") or row["client_id"] != client.client_id:
            return None
        return RefreshToken(token=refresh_token, client_id=row["client_id"],
                            scopes=(row.get("scope") or "").split(),
                            expires_at=_epoch(row["expires_at"]), subject=row["user_id"])

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]
    ) -> OAuthToken:
        granted = scopes or refresh_token.scopes or ["cadence"]
        access = _mint_access(refresh_token.subject, client.client_id, granted, RESOURCE)
        return OAuthToken(access_token=access, token_type="Bearer", expires_in=ACCESS_TTL,
                          scope=" ".join(granted), refresh_token=refresh_token.token)

    async def load_access_token(self, token: str) -> AccessToken | None:
        return await self.verify_token(token)

    async def verify_token(self, token: str) -> AccessToken | None:
        claims = _verify_access(token)
        if not claims:
            return None
        return AccessToken(token=token, client_id=claims.get("client_id", ""),
                           scopes=(claims.get("scope") or "").split(), expires_at=claims.get("exp"),
                           resource=claims.get("aud"), subject=claims["sub"], claims=claims)

    async def revoke_token(self, token) -> None:  # noqa: ANN001 - AccessToken | RefreshToken
        raw = getattr(token, "token", None)
        if raw:
            db.revoke_refresh(_hash(raw))


def _login_page(txn: str, error: str = "") -> HTMLResponse:
    # Escape everything interpolated into this credential-entry page. txn should already be a
    # validated JWT (no HTML metacharacters), but escaping is the defense that guarantees no
    # reflected-XSS breakout even if a raw value ever reaches here.
    txn = html.escape(txn, quote=True)
    err = f'<p style="color:#f87171;font-size:13px">{html.escape(error)}</p>' if error else ""
    return HTMLResponse(f"""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Connect Cadence to Claude</title>
<style>body{{font-family:system-ui;background:#0a0a0a;color:#fff;display:grid;place-items:center;height:100vh;margin:0}}
.card{{width:340px;background:#141414;border:1px solid #ffffff1a;border-radius:16px;padding:28px}}
h1{{font-size:18px;margin:0 0 4px}}p.sub{{color:#ffffff70;font-size:13px;margin:0 0 20px}}
input{{width:100%;box-sizing:border-box;background:#0a0a0a;border:1px solid #ffffff1a;border-radius:10px;
padding:11px;color:#fff;margin-bottom:10px;font-size:14px}}
button{{width:100%;background:#6d5efc;color:#fff;border:0;border-radius:10px;padding:12px;font-weight:600;cursor:pointer}}</style>
</head><body><form class=card method=post action="/login">
<h1>Connect Cadence to Claude</h1><p class=sub>Sign in to authorize Claude to use your Cadence account.</p>
{err}<input name=email type=email placeholder="Email" required autofocus>
<input name=password type=password placeholder="Password" required>
<input type=hidden name=txn value="{txn}"><button type=submit>Authorize</button></form></body></html>""")


async def login_route(request: Request):
    """GET renders the Cadence login; POST verifies it against Supabase Auth and issues the
    authorization code, then redirects back to the OAuth client (Claude)."""
    if request.method == "GET":
        # Validate the signed txn BEFORE rendering — never reflect an unverified query param onto
        # the credential page. An invalid/tampered/expired txn gets a static error, not the form.
        txn_raw = request.query_params.get("txn", "")
        try:
            jwt.decode(txn_raw, JWT_SECRET, algorithms=["HS256"])
        except Exception:  # noqa: BLE001
            return HTMLResponse(
                "Authorization request expired — restart the connection from Claude.", status_code=400
            )
        return _login_page(txn_raw)

    form = await request.form()
    txn_raw = str(form.get("txn", ""))
    try:
        txn = jwt.decode(txn_raw, JWT_SECRET, algorithms=["HS256"])
    except Exception:  # noqa: BLE001
        return HTMLResponse("Authorization request expired — restart the connection from Claude.", status_code=400)

    user_id = db.authenticate(str(form.get("email", "")), str(form.get("password", "")))
    if not user_id:
        return _login_page(txn_raw, "Invalid email or password.")

    code = secrets.token_urlsafe(32)
    db.save_code({
        "code": code, "client_id": txn["client_id"], "user_id": user_id,
        "redirect_uri": txn["redirect_uri"], "code_challenge": txn["code_challenge"],
        "scope": " ".join(txn.get("scopes") or ["cadence"]), "resource": txn.get("resource"),
        "expires_at": _iso(_now() + 600),
    })
    return RedirectResponse(
        construct_redirect_uri(txn["redirect_uri"], code=code, state=txn.get("state")),
        status_code=302,
    )
