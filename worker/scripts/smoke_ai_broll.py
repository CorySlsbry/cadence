"""Verify AI contextual b-roll end-to-end through the worker (stub generator, $0).

Uses the real-speech speech.mp4 so the transcript drives topic-aware cutaways, runs
the worker's _process in-process with broll_mode='ai', and extracts a cutaway frame.
"""

from __future__ import annotations

import os
import sys
import uuid

ENV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
for line in open(ENV, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v)
os.environ.pop("IDEOGRAM_API_KEY", None)  # force the free stub for this test

from supabase import create_client

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cadence_worker import Worker  # noqa: E402
from cadence.ffmpeg.runner import FFmpeg  # noqa: E402

URL, KEY = os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"]
ENGINE_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "engine", "output")
SPEECH = os.path.join(ENGINE_OUT, "speech_skills.mp4")  # ~21s of real speech about Claude skills
admin = create_client(URL, KEY)
ff = FFmpeg()


def main() -> int:
    if not os.path.isfile(SPEECH):
        print(f"FAIL: {SPEECH} missing (run engine/scripts/verify_asr.py first)")
        return 1
    email = f"aibroll_{uuid.uuid4().hex[:8]}@test.dev"
    uid = admin.auth.admin.create_user({"email": email, "password": "Password123!", "email_confirm": True}).user.id
    try:
        rec_key = f"{uid}/ai/recording.mp4"
        with open(SPEECH, "rb") as fh:
            admin.storage.from_("uploads").upload(rec_key, fh.read(), {"content-type": "video/mp4", "upsert": "true"})
        proj = admin.table("projects").insert({"user_id": uid, "name": "AI"}).execute().data[0]
        job = admin.table("render_jobs").insert({
            "user_id": uid, "project_id": proj["id"], "recording_path": rec_key,
            "customization": {"broll_mode": "ai", "pacing": "match", "broll_caption": True},
            "status": "queued",
        }).execute().data[0]
        print(f"[ai] job {job['id']} queued; processing with stub generator…")
        w = Worker()
        w._process(w._claim())
        final = admin.table("render_jobs").select("*").eq("id", job["id"]).single().execute().data
        assert final["status"] == "done", f"status={final['status']} err={final.get('error')}"
        assert final["result"]["width"] == 1080
        out = os.path.join("diag", "ai_broll_out.mp4")
        os.makedirs("diag", exist_ok=True)
        open(out, "wb").write(admin.storage.from_("outputs").download(final["output_path"]))
        ff.run(["-y", "-ss", "2.0", "-i", out, "-frames:v", "1", "diag/ai_broll_frame.png"], timeout=60)
        print(f"[ai] OK -> {final['output_path']} ({final['result']['width']}x{final['result']['height']}); frame at 2.0s saved")
        print("\nAI B-ROLL SMOKE: PASS")
        return 0
    finally:
        admin.auth.admin.delete_user(uid)


if __name__ == "__main__":
    raise SystemExit(main())
