import { NextResponse } from "next/server";
import { z } from "zod";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { getStripe } from "@/lib/stripe";

const Body = z.object({ plan: z.enum(["base", "creator"]) });

/**
 * Creates a Stripe hosted Checkout Session for a subscription plan and returns its URL.
 * The buyer's user_id, plan, and (if they were referred) the affiliate_id are stamped
 * into subscription metadata so the webhook can attribute the sub + its commissions.
 */
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

  // Service-role reads: the price + the referring affiliate (bypass RLS, server-trusted).
  const admin = createAdminClient();
  const { data: planRow } = await admin
    .from("plans")
    .select("stripe_price_id")
    .eq("key", plan)
    .single();
  if (!planRow?.stripe_price_id) {
    return NextResponse.json({ error: "plan is not purchasable" }, { status: 400 });
  }

  // referred_by holds the referrer's user_id; map it to their affiliate row (if any).
  let affiliateId = "";
  const { data: profile } = await admin
    .from("profiles")
    .select("referred_by")
    .eq("id", user.id)
    .single();
  if (profile?.referred_by) {
    const { data: aff } = await admin
      .from("affiliates")
      .select("id")
      .eq("user_id", profile.referred_by)
      .maybeSingle();
    affiliateId = aff?.id ?? "";
  }

  const origin = process.env.NEXT_PUBLIC_SITE_URL || new URL(request.url).origin;
  const meta = { user_id: user.id, plan, affiliate_id: affiliateId };

  const stripe = getStripe();
  const session = await stripe.checkout.sessions.create({
    mode: "subscription",
    line_items: [{ price: planRow.stripe_price_id, quantity: 1 }],
    customer_email: user.email ?? undefined,
    client_reference_id: user.id,
    success_url: `${origin}/dashboard?upgraded=1`,
    cancel_url: `${origin}/premium?canceled=1`,
    metadata: meta,
    subscription_data: { metadata: meta },
    allow_promotion_codes: true,
  });

  return NextResponse.json({ url: session.url });
}
