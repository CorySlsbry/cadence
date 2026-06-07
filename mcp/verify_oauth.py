"""End-to-end verifier for the live Cadence MCP OAuth 2.1 + tool flow. Runs the exact dance a
Claude custom-connector performs: discover metadata -> DCR -> authorize -> login -> token ->
call a tool. Creds + base via env (MCP_BASE, MCP_EMAIL, MCP_PW). No secrets committed."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sys

import httpx

BASE = os.environ["MCP_BASE"].rstrip("/")
EMAIL, PW = os.environ["MCP_EMAIL"], os.environ["MCP_PW"]
REDIRECT = "https://claude.ai/api/mcp/auth_callback"
c = httpx.Client(follow_redirects=False, timeout=30)


def step(label, ok, extra=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {label}{(' — ' + extra) if extra else ''}", flush=True)
    if not ok:
        sys.exit(1)


# 1) discovery
pr = c.get(f"{BASE}/.well-known/oauth-protected-resource/mcp")
step("protected-resource-metadata", pr.status_code == 200, pr.text[:90])
asm = c.get(f"{BASE}/.well-known/oauth-authorization-server").json()
step("authorization-server-metadata", "authorization_endpoint" in asm)

# 2) dynamic client registration (RFC 7591)
reg = c.post(asm["registration_endpoint"], json={
    "client_name": "verifier", "redirect_uris": [REDIRECT],
    "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
    "token_endpoint_auth_method": "none",
})
client_id = reg.json().get("client_id")
step("dynamic client registration", bool(client_id), f"client_id={client_id}")

# 3) PKCE + /authorize -> 302 /login
verifier = secrets.token_urlsafe(64)
challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
az = c.get(asm["authorization_endpoint"], params={
    "response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT,
    "code_challenge": challenge, "code_challenge_method": "S256", "state": "xyz",
    "resource": f"{BASE}/mcp", "scope": "cadence",
})
loc = az.headers.get("location", "")
step("/authorize -> login redirect", az.status_code in (302, 303) and "/login" in loc, loc[:60])
txn = httpx.URL(loc).params.get("txn")

# 4) /login (verify Supabase creds) -> 302 back to client with ?code
lg = c.post(f"{BASE}/login", data={"email": EMAIL, "password": PW, "txn": txn})
cb = lg.headers.get("location", "")
step("/login -> client callback with code", lg.status_code in (302, 303) and "code=" in cb, cb[:70])
code = httpx.URL(cb).params.get("code")

# 5) /token (auth-code + PKCE)
tok = c.post(asm["token_endpoint"], data={
    "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
    "client_id": client_id, "code_verifier": verifier,
})
access = tok.json().get("access_token")
step("/token -> access token", bool(access), f"type={tok.json().get('token_type')}")

# 6) call the MCP endpoint with the bearer token
H = {"Authorization": f"Bearer {access}", "Accept": "application/json, text/event-stream",
     "Content-Type": "application/json", "MCP-Protocol-Version": "2025-06-18"}


def rpc(method, params, sid=None, notify=False):
    h = dict(H)
    if sid:
        h["Mcp-Session-Id"] = sid
    body = {"jsonrpc": "2.0", "method": method, "params": params}
    if not notify:
        body["id"] = secrets.randbelow(10000) + 1
    r = c.post(f"{BASE}/mcp", headers=h, json=body)
    return r


# unauthenticated probe -> 401 challenge
un = c.post(f"{BASE}/mcp", headers={k: v for k, v in H.items() if k != "Authorization"},
            json={"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}})
step("401 challenge when unauthenticated", un.status_code == 401 and "WWW-Authenticate" in un.headers)

init = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                          "clientInfo": {"name": "verify", "version": "1"}})
sid = init.headers.get("mcp-session-id")
step("initialize (authenticated)", init.status_code == 200, f"session={bool(sid)}")
rpc("notifications/initialized", {}, sid=sid, notify=True)

tl = rpc("tools/list", {}, sid=sid)
step("tools/list includes list_recordings", "list_recordings" in tl.text and "list_projects" in tl.text)

call = rpc("tools/call", {"name": "list_recordings", "arguments": {}}, sid=sid)
txt = call.text
ok = call.status_code == 200 and ("result" in txt or "content" in txt)
step("tools/call list_projects (scoped to user)", ok, txt[:120].replace("\n", " "))
print("\nALL OAUTH + MCP CHECKS PASSED", flush=True)
