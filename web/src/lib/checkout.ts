import type { User } from "@supabase/supabase-js";
import { createAdminClient } from "@/lib/supabase/admin";
import { getStripe } from "@/lib/stripe";
import { ensurePlanPrice, type PlanRow } from "@/lib/pricing";

/**
 * Creates a Stripe hosted Checkout Session for a paid plan.
 *
 * The price is re-verified against `plans.price_usd` on EVERY session via
 * ensurePlanPrice, so what the buyer pays always equals what the website says.
 * The buyer's user_id, plan, and referring affiliate are stamped into the
 * subscription metadata so the webhook can attribute the sub + commissions.
 */
export async function createCheckoutSessionFor(
  user: User,
  plan: "base" | "creator",
  origin: string,
): Promise<string> {
  const admin = createAdminClient();

  const { data: planRow } = await admin
    .from("plans")
    .select("key,name,price_usd,monthly_tokens,active,stripe_price_id,stripe_product_id")
    .eq("key", plan)
    .single();
  if (!planRow || !planRow.active || Number(planRow.price_usd) <= 0) {
    throw new Error("plan is not purchasable");
  }

  const stripe = getStripe();
  const { stripe_price_id: priceId } = await ensurePlanPrice(stripe, admin, planRow as PlanRow);

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

  const meta = { user_id: user.id, plan, affiliate_id: affiliateId };
  const session = await stripe.checkout.sessions.create({
    mode: "subscription",
    line_items: [{ price: priceId, quantity: 1 }],
    customer_email: user.email ?? undefined,
    client_reference_id: user.id,
    success_url: `${origin}/dashboard?upgraded=1`,
    cancel_url: `${origin}/premium?canceled=1`,
    metadata: meta,
    subscription_data: { metadata: meta },
    allow_promotion_codes: true,
  });
  if (!session.url) throw new Error("Stripe did not return a checkout URL");
  return session.url;
}
