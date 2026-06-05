"""Cross-tenant isolation test — the safety gate for opening signups.

Proves that with the public anon key + a user's JWT (i.e. how the browser talks to
Supabase), user B cannot read, write, impersonate, or download user A's data. RLS
must enforce this at the database/storage layer, not just the UI.
"""

from __future__ import annotations

import os
import uuid

ENV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
for line in open(ENV, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v)

from supabase import create_client

URL = os.environ["SUPABASE_URL"]
SERVICE = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
ANON = os.environ.get(
    "SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9.CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0",
)
admin = create_client(URL, SERVICE)

passed, failed = 0, 0


def check(name: str, cond: bool) -> None:
    global passed, failed
    print(("  PASS " if cond else "  FAIL ") + name)
    if cond:
        passed += 1
    else:
        failed += 1


def make_user(tag: str):
    email = f"rls_{tag}_{uuid.uuid4().hex[:6]}@test.dev"
    u = admin.auth.admin.create_user({"email": email, "password": "Password123!", "email_confirm": True})
    cli = create_client(URL, ANON)
    cli.auth.sign_in_with_password({"email": email, "password": "Password123!"})
    return u.user.id, cli


def main() -> int:
    a_id, A = make_user("a")
    b_id, B = make_user("b")
    print(f"user A={a_id}\nuser B={b_id}")

    # A creates private data (RLS insert: user_id must equal auth.uid()).
    proj = A.table("projects").insert({"user_id": a_id, "name": "A secret project"}).execute().data[0]
    print(f"A created project {proj['id']}")

    # 1) B cannot read A's project by id.
    res = B.table("projects").select("*").eq("id", proj["id"]).execute()
    check("B cannot read A's project by id", len(res.data) == 0)

    # 2) B's project list is empty (sees only own rows).
    check("B sees none of A's projects in a list query", len(B.table("projects").select("*").execute().data) == 0)

    # 3) B cannot update A's project.
    upd = B.table("projects").update({"name": "hacked"}).eq("id", proj["id"]).execute()
    still = admin.table("projects").select("name").eq("id", proj["id"]).single().execute().data
    check("B cannot rename A's project", len(upd.data) == 0 and still["name"] == "A secret project")

    # 4) B cannot impersonate A on insert (user_id = A while authed as B).
    try:
        B.table("projects").insert({"user_id": a_id, "name": "impersonation"}).execute()
        check("B cannot insert a row owned by A", False)
    except Exception:
        check("B cannot insert a row owned by A", True)

    # 5) Storage isolation: A uploads to A's folder; B cannot download it.
    key = f"{a_id}/rls/secret.txt"
    A.storage.from_("uploads").upload(key, b"top secret", {"content-type": "text/plain", "upsert": "true"})
    try:
        B.storage.from_("uploads").download(key)
        check("B cannot download A's upload", False)
    except Exception:
        check("B cannot download A's upload", True)

    # 6) B cannot write into A's folder.
    try:
        B.storage.from_("uploads").upload(f"{a_id}/rls/intrusion.txt", b"x", {"upsert": "true"})
        check("B cannot write into A's folder", False)
    except Exception:
        check("B cannot write into A's folder", True)

    admin.auth.admin.delete_user(a_id)
    admin.auth.admin.delete_user(b_id)

    print(f"\nRLS ISOLATION: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
