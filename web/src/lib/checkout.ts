import type { User } from "@supabase/supabase-js";
import type Stripe from "stripe";
import { createAdminClient } from "@/lib/supabase/admin";
import { getStripe } from "@/lib/stripe";
import { ensurePlanPrice, ensurePackPrice, type PlanRow, type PackRow } from "@/lib/pricing";

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
  plan: "base" | "creator" | "agency",
  origin: string,
  embedded = false,
): Promise<Stripe.Checkout.Session> {
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
  return stripe.checkout.sessions.create({
    mode: "subscription",
    line_items: [{ price: priceId, quantity: 1 }],
    customer_email: user.email ?? undefined,
    client_reference_id: user.id,
    metadata: meta,
    subscription_data: { metadata: meta },
    allow_promotion_codes: true,
    // Embedded (ui_mode) renders the payment form inline on clouthook.com and returns to
    // /checkout/return; hosted keeps the classic success/cancel redirect (the fallback).
    ...(embedded
      ? { ui_mode: "embedded_page", return_url: `${origin}/checkout/return?session_id={CHECKOUT_SESSION_ID}` }
      : { success_url: `${origin}/dashboard?upgraded=1`, cancel_url: `${origin}/premium?canceled=1` }),
  });
}

/** One-time token pack purchase — price re-verified against token_packs per session. */
export async function createPackCheckoutSessionFor(
  user: User,
  packKey: string,
  origin: string,
  embedded = false,
): Promise<Stripe.Checkout.Session> {
  const admin = createAdminClient();

  const { data: pack } = await admin
    .from("token_packs")
    .select("key,name,tokens,price_usd,active,stripe_price_id,stripe_product_id")
    .eq("key", packKey)
    .maybeSingle();
  if (!pack || !pack.active) throw new Error("pack is not purchasable");

  const stripe = getStripe();
  const { stripe_price_id: priceId } = await ensurePackPrice(stripe, admin, pack as PackRow);

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

  return stripe.checkout.sessions.create({
    mode: "payment",
    line_items: [{ price: priceId, quantity: 1 }],
    customer_email: user.email ?? undefined,
    client_reference_id: user.id,
    metadata: {
      user_id: user.id,
      pack: pack.key,
      tokens: String(pack.tokens),
      affiliate_id: affiliateId,
    },
    allow_promotion_codes: true,
    ...(embedded
      ? { ui_mode: "embedded_page", return_url: `${origin}/checkout/return?session_id={CHECKOUT_SESSION_ID}` }
      : { success_url: `${origin}/dashboard?topup=1`, cancel_url: `${origin}/premium?canceled=1#topup` }),
  });
}
