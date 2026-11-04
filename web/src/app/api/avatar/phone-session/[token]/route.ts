import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

export const runtime = "nodejs";

// Desktop owner polls their session for the phone upload. RLS restricts rows to the owner;
// the explicit user_id check is belt-and-suspenders. Never returns another user's session.
export async function GET(_req: Request, { params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { data: s } = await supabase
    .from("phone_link_sessions")
    .select("status, recording_path, user_id, expires_at")
    .eq("token", token)
    .maybeSingle();
  if (!s || s.user_id !== user.id) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }
  return NextResponse.json({
    status: s.status,
    recording_path: s.recording_path,
    expires_at: s.expires_at,
  });
}
