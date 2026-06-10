import { NextResponse } from "next/server";
import { z } from "zod";
import { createClient } from "@/lib/supabase/server";
import { createCheckoutSessionFor } from "@/lib/checkout";

const Body = z.object({ plan: z.enum(["base", "creator"]) });

/** Creates a Stripe Checkout Session for a subscription plan and returns its URL. */
export async function POST(request: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  let plan: "base" | "creator";
  try {
    plan = Body.parse(await request.json()).plan;
  } catch {
    return NextResponse.json({ error: "invalid plan" }, { status: 422 });
  }

  const origin = process.env.NEXT_PUBLIC_SITE_URL || new URL(request.url).origin;
  try {
    const url = await createCheckoutSessionFor(user, plan, origin);
    return NextResponse.json({ url });
  } catch (err) {
    const msg = err instanceof Error ? err.message : "checkout failed";
    const status = msg === "plan is not purchasable" ? 400 : 502;
    return NextResponse.json({ error: msg }, { status });
  }
}
