import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { createClient } from "@/lib/supabase/server";
import { publicOrigin } from "@/lib/request-origin";

/**
 * The signup→pay bridge. /signup?plan=X funnels here after auth; we claim any
 * pending referral cookie (so the commission attributes even when the buyer pays
 * before ever visiting the app shell), then 303 straight into Stripe Checkout.
 * Logged-out visitors bounce back to signup with the plan preserved.
 */
export async function GET(request: Request) {
  const url = new URL(request.url);
  const origin = publicOrigin(request);
  const plan = url.searchParams.get("plan");
  if (plan !== "base" && plan !== "creator") {
    return NextResponse.redirect(`${origin}/premium`);
  }

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.redirect(`${origin}/signup?plan=${plan}`);
  }

  // Referral attribution before the session is created — the checkout metadata
  // reads profiles.referred_by, so the claim must land first.
  const ref = (await cookies()).get("ch_ref")?.value;
  if (ref) {
    try {
      await supabase.rpc("claim_referral", { p_code: ref });
    } catch {
      /* attribution must never block checkout */
    }
  }

  // Referral claimed above → hand off to the on-site embedded checkout page.
  return NextResponse.redirect(`${origin}/checkout?plan=${plan}`, { status: 303 });
}
