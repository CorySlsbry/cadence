import { NextResponse } from "next/server";
import { z } from "zod";
import { createClient } from "@/lib/supabase/server";
import { notifySlack } from "@/lib/notify-slack";

// Creator/user feedback → lands in the admin dashboard (/admin). Signed-in users only;
// RLS lets each user insert only their own row (auth.uid() = user_id).
const FeedbackSchema = z.object({
  message: z.string(),
  page: z.string().optional(),
  category: z.enum(["bug", "feature", "question", "other"]).optional().default("other"),
});

export async function POST(req: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  let parsed;
  try {
    parsed = FeedbackSchema.parse(await req.json());
  } catch {
    return NextResponse.json({ error: "bad request" }, { status: 400 });
  }

  const message = parsed.message.trim();
  if (!message) return NextResponse.json({ error: "empty message" }, { status: 422 });

  const category = parsed.category;
  const page = (parsed.page ?? "").slice(0, 300) || null;

  const { error } = await supabase.from("feedback").insert({
    user_id: user.id,
    email: user.email ?? null,
    message: message.slice(0, 4000),
    page,
    category,
  });
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  // Fire-and-forget Slack alert (never throws / blocks).
  await notifySlack({
    kind:
      category === "bug"
        ? "bug"
        : category === "feature"
          ? "feature"
          : category === "question"
            ? "question"
            : "feedback",
    title:
      category === "bug"
        ? "Bug report"
        : category === "feature"
          ? "Feature request"
          : category === "question"
            ? "Question"
            : "New feedback",
    body: message,
    email: user.email ?? undefined,
    page: page ?? undefined,
  });

  return NextResponse.json({ ok: true });
}
