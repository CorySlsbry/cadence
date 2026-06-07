"""In-process full OAuth+MCP flow test via Starlette TestClient (no deploy). Same dance as
verify_oauth.py. Env: SUPABASE_*, CADENCE_MCP_*, MCP_EMAIL, MCP_PW."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import sys

sys.path.insert(0, "mcp")
import server  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

EMAIL, PW = os.environ["MCP_EMAIL"], os.environ["MCP_PW"]
REDIRECT = "https://claude.ai/api/mcp/auth_callback"
BASE = os.environ["CADENCE_MCP_BASE_URL"].rstrip("/")


def step(label, ok, extra=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {label}{(' — ' + extra) if extra else ''}", flush=True)
    if not ok:
        sys.exit(1)


# `with` runs the app lifespan -> initializes FastMCP's streamable-HTTP session manager.
_cm = TestClient(server.app, follow_redirects=False)
c = _cm.__enter__()
asm = c.get("/.well-known/oauth-authorization-server").json()
reg = c.post("/register", json={"client_name": "local", "redirect_uris": [REDIRECT],
             "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
             "token_endpoint_auth_method": "none"}).json()
cid = reg["client_id"]
step("DCR", bool(cid), cid)

verifier = secrets.token_urlsafe(64)
challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
az = c.get("/authorize", params={"response_type": "code", "client_id": cid, "redirect_uri": REDIRECT,
           "code_challenge": challenge, "code_challenge_method": "S256", "state": "xyz",
           "resource": f"{BASE}/mcp", "scope": "cadence"})
loc = az.headers.get("location", "")
step("/authorize -> /login", az.status_code in (302, 303) and "/login" in loc, loc[:50])
import httpx  # noqa: E402
txn = httpx.URL(loc).params.get("txn")

lg = c.post("/login", data={"email": EMAIL, "password": PW, "txn": txn})
cb = lg.headers.get("location", "")
step("/login -> code", lg.status_code in (302, 303) and "code=" in cb, cb[:60])
code = httpx.URL(cb).params.get("code")

tok = c.post("/token", data={"grant_type": "authorization_code", "code": code,
             "redirect_uri": REDIRECT, "client_id": cid, "code_verifier": verifier}).json()
access = tok.get("access_token")
step("/token", bool(access))

H = {"Authorization": f"Bearer {access}", "Accept": "application/json, text/event-stream",
     "Content-Type": "application/json", "MCP-Protocol-Version": "2025-06-18"}
init = c.post("/mcp", headers=H, json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}})
sid = init.headers.get("mcp-session-id")
step("initialize", init.status_code == 200, f"session={bool(sid)}")
h2 = dict(H, **({"Mcp-Session-Id": sid} if sid else {}))
c.post("/mcp", headers=h2, json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
call = c.post("/mcp", headers=h2, json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "list_projects", "arguments": {}}})
step("tools/call list_projects", call.status_code == 200 and '"result"' in call.text and "Error calling tool" not in call.text,
     call.text[:140].replace("\n", " "))
_cm.__exit__(None, None, None)
print("\nLOCAL OAUTH+MCP FLOW PASSED", flush=True)
