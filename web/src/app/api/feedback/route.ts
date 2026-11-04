import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

// Creator/user feedback → lands in the admin dashboard (/admin). Signed-in users only;
// RLS lets each user insert only their own row (auth.uid() = user_id).
export async function POST(req: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  let body: { message?: string; page?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "bad json" }, { status: 400 });
  }

  const message = (body.message ?? "").trim();
  if (!message) return NextResponse.json({ error: "empty message" }, { status: 422 });

  const { error } = await supabase.from("feedback").insert({
    user_id: user.id,
    email: user.email ?? null,
    message: message.slice(0, 4000),
    page: (body.page ?? "").slice(0, 300) || null,
  });
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ ok: true });
}
