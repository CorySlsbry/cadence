import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { isSocialPlatform } from "@/lib/social-oauth";

// Disconnect a social account — delete the stored tokens. With an `?id=` query param
// (or a JSON body `{ connectionId }`) it removes that ONE account; without it, it removes
// every account for the platform (back-compat). Either way the delete is scoped to the
// caller's own rows — a connection id is never trusted without the user_id match.
export async function DELETE(request: Request, { params }: { params: Promise<{ platform: string }> }) {
  const { platform } = await params;
  if (!isSocialPlatform(platform)) return NextResponse.json({ error: "unknown platform" }, { status: 404 });

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  let connectionId = new URL(request.url).searchParams.get("id");
  if (!connectionId) {
    connectionId = await request
      .json()
      .then((b) => (b && typeof b.connectionId === "string" ? b.connectionId : null))
      .catch(() => null);
  }

  const admin = createAdminClient();
  let query = admin.from("social_connections").delete().eq("user_id", user.id);
  query = connectionId ? query.eq("id", connectionId) : query.eq("platform", platform);
  const { error } = await query;
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ connected: false, platform });
}
