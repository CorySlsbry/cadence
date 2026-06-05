"""End-to-end backend smoke test: user -> storage upload -> job -> worker -> output.

Validates the full SaaS render path against the running local Supabase, without
the browser. Creates a throwaway user, uploads fixture videos, enqueues a render,
runs the worker in-process, and asserts a real output landed in the outputs bucket.
"""

from __future__ import annotations

import os
import sys
import time
import uuid

# Load worker/.env
ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
for line in open(ENV_PATH, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v)

from supabase import create_client

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cadence_worker import Worker  # noqa: E402

URL = os.environ["SUPABASE_URL"]
KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
ENGINE_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "engine", "output")
REF = os.path.join(ENGINE_OUT, "_reference.mp4")
REC = os.path.join(ENGINE_OUT, "_aroll.mp4")

admin = create_client(URL, KEY)


def main() -> int:
    for f in (REF, REC):
        if not os.path.isfile(f):
            print(f"FAIL: fixture missing {f} (run engine/scripts/demo_pipeline.py first)")
            return 1

    email = f"smoke_{uuid.uuid4().hex[:8]}@test.dev"
    user = admin.auth.admin.create_user({"email": email, "password": "Password123!", "email_confirm": True})
    uid = user.user.id
    print(f"[smoke] created user {email} ({uid})")

    try:
        ref_key = f"{uid}/smoke/reference.mp4"
        rec_key = f"{uid}/smoke/recording.mp4"
        for key, path in ((ref_key, REF), (rec_key, REC)):
            with open(path, "rb") as fh:
                admin.storage.from_("uploads").upload(key, fh.read(), {"content-type": "video/mp4", "upsert": "true"})
        print("[smoke] uploaded reference + recording")

        project = admin.table("projects").insert({"user_id": uid, "name": "Smoke"}).execute().data[0]
        job = admin.table("render_jobs").insert({
            "user_id": uid,
            "project_id": project["id"],
            "recording_path": rec_key,
            "reference_path": ref_key,
            "customization": {"caption_zone": "bottom", "caption_style": "pop", "zoom": 1.1, "saturation": 1.15},
            "status": "queued",
        }).execute().data[0]
        print(f"[smoke] enqueued job {job['id']}")

        # Run the worker in-process: claim + process exactly as the daemon would.
        worker = Worker()
        claimed = worker._claim()
        assert claimed and claimed["id"] == job["id"], f"claim returned {claimed}"
        print("[smoke] worker claimed job; processing (this runs the full engine)…")
        t0 = time.time()
        worker._process(claimed)
        print(f"[smoke] processed in {time.time() - t0:.1f}s")

        final = admin.table("render_jobs").select("*").eq("id", job["id"]).single().execute().data
        assert final["status"] == "done", f"status={final['status']} error={final.get('error')}"
        assert final["output_path"], "no output_path"
        assert final["result"]["width"] == 1080 and final["result"]["height"] == 1920, final["result"]
        out_bytes = admin.storage.from_("outputs").download(final["output_path"])
        assert len(out_bytes) > 10000, f"output too small: {len(out_bytes)} bytes"
        print(f"[smoke] OK -> output {final['output_path']} ({len(out_bytes)} bytes), "
              f"{final['result']['width']}x{final['result']['height']}@{final['result']['fps']}fps")
        print("\nBACKEND SMOKE: PASS")
        return 0
    finally:
        admin.auth.admin.delete_user(uid)
        print("[smoke] cleaned up test user")


if __name__ == "__main__":
    raise SystemExit(main())
