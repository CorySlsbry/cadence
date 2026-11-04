import { NextResponse } from "next/server";
import type Stripe from "stripe";
import { createAdminClient } from "@/lib/supabase/admin";
import { getStripe, epochToIso } from "@/lib/stripe";

type Admin = ReturnType<typeof createAdminClient>;

// Stripe moved current_period_* across API versions; read them defensively.
function periodBounds(sub: Stripe.Subscription): { start: string | null; end: string | null } {
  const s = sub as unknown as { current_period_start?: number; current_period_end?: number };
  return { start: epochToIso(s.current_period_start), end: epochToIso(s.current_period_end) };
}

/**
 * Stripe webhook. Verifies the signature, then keeps our DB in sync:
 *  - checkout.session.completed  -> upsert an active subscription, set the user's plan + grant tokens
 *  - customer.subscription.updated/deleted -> sync status (canceled flips commissions off automatically,
 *    since affiliate_dashboard() sums ACTIVE subs only) + downgrade to free on final cancel
 *  - invoice.paid -> accrue the affiliate's commission once per invoice (idempotent)
 * Returns 500 on handler errors so Stripe retries.
 */
export async function POST(request: Request) {
  const sig = request.headers.get("stripe-signature");
  const secret = process.env.STRIPE_WEBHOOK_SECRET;
  if (!sig || !secret) {
    return NextResponse.json({ error: "webhook not configured" }, { status: 400 });
  }

  const stripe = getStripe();
  const raw = await request.text(); // raw body required for signature verification
  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(raw, sig, secret);
  } catch {
    return NextResponse.json({ error: "signature verification failed" }, { status: 400 });
  }

  const admin = createAdminClient();
  try {
    switch (event.type) {
      case "checkout.session.completed":
        await activateFromSession(admin, stripe, event.data.object as Stripe.Checkout.Session);
        break;
      case "customer.subscription.updated":
      case "customer.subscription.deleted":
        await syncSubscription(admin, event.data.object as Stripe.Subscription);
        break;
      case "invoice.paid":
        await accrueCommission(admin, event.data.object as Stripe.Invoice);
        break;
      case "charge.refunded":
        await reverseCommission(admin, event.data.object as Stripe.Charge);
        break;
    }
  } catch (err) {
    console.error("[stripe webhook]", event.type, err);
    return NextResponse.json({ error: "handler error" }, { status: 500 });
  }

  return NextResponse.json({ received: true });
}

async function activateFromSession(admin: Admin, stripe: Stripe, s: Stripe.Checkout.Session) {
  // One-time token pack purchases take their own path (no subscription involved).
  if (s.mode === "payment" && s.metadata?.pack) {
    await grantPackPurchase(admin, s);
    return;
  }

  const userId = s.metadata?.user_id || s.client_reference_id || undefined;
  const plan = s.metadata?.plan || undefined;
  const affiliateId = s.metadata?.affiliate_id || null;
  if (!userId || !plan) return;

  const subId = typeof s.subscription === "string" ? s.subscription : s.subscription?.id ?? null;
  const custId = typeof s.customer === "string" ? s.customer : s.customer?.id ?? null;

  const { data: planRow } = await admin
    .from("plans")
    .select("price_usd, monthly_tokens")
    .eq("key", plan)
    .single();

  let start: string | null = null;
  let end: string | null = null;
  if (subId) {
    const sub = await stripe.subscriptions.retrieve(subId);
    ({ start, end } = periodBounds(sub));
  }

  await admin.from("subscriptions").upsert(
    {
      user_id: userId,
      plan,
      status: "active",
      amount_usd: planRow?.price_usd ?? null,
      affiliate_id: affiliateId,
      stripe_subscription_id: subId,
      stripe_customer_id: custId,
      current_period_start: start,
      current_period_end: end,
      started_at: new Date().toISOString(),
      canceled_at: null,
    },
    { onConflict: "stripe_subscription_id" },
  );

  // Set plan + grant the plan's monthly tokens immediately; claim_monthly_tokens handles
  // subsequent calendar-month refreshes on page load.
  await admin
    .from("profiles")
    .update({
      plan,
      tokens: planRow?.monthly_tokens ?? 25,
      token_period_start: new Date().toISOString(),
    })
    .eq("id", userId);
}

/** Token pack paid → grant tokens exactly once (unique session id absorbs Stripe retries)
 *  and accrue the referring affiliate's commission on the one-time amount. */
async function grantPackPurchase(admin: Admin, s: Stripe.Checkout.Session) {
  const userId = s.metadata?.user_id || s.client_reference_id || undefined;
  const tokens = Number(s.metadata?.tokens ?? 0);
  const packKey = s.metadata?.pack ?? "";
  if (!userId || !tokens || !s.id) return;

  const amountUsd = Math.round((s.amount_total ?? 0)) / 100;
  const { error: insErr } = await admin.from("token_topups").insert({
    user_id: userId,
    pack_key: packKey,
    tokens,
    amount_usd: amountUsd,
    affiliate_id: s.metadata?.affiliate_id || null,
    stripe_session_id: s.id,
  });
  if (insErr) return; // duplicate session id = already granted (retry) → do nothing

  await admin.rpc("grant_extra_tokens", {
    p_user: userId,
    p_tokens: tokens,
    p_reason: `topup:${packKey}`,
  });

  const affiliateId = s.metadata?.affiliate_id || null;
  if (affiliateId && amountUsd > 0) {
    const { data: aff } = await admin
      .from("affiliates")
      .select("commission_rate")
      .eq("id", affiliateId)
      .maybeSingle();
    const rate = Number(aff?.commission_rate ?? 0.3);
    await admin.from("commissions").insert({
      affiliate_id: affiliateId,
      subscription_id: null,
      referred_user_id: userId,
      amount_usd: Math.round(amountUsd * rate * 100) / 100,
      rate,
      status: "pending",
      stripe_invoice_id: s.id, // unique idx → idempotent for pack sessions too
    });
  }
}

async function syncSubscription(admin: Admin, sub: Stripe.Subscription) {
  const status =
    sub.status === "active" || sub.status === "trialing"
      ? "active"
      : sub.status === "past_due"
        ? "past_due"
        : "canceled";

  const { start, end } = periodBounds(sub);
  await admin
    .from("subscriptions")
    .update({
      status,
      current_period_start: start,
      current_period_end: end,
      canceled_at: status === "canceled" ? new Date().toISOString() : null,
    })
    .eq("stripe_subscription_id", sub.id);

  // Final cancellation -> downgrade the profile to free. (Commission already drops the
  // instant status != 'active' because affiliate_dashboard() sums active subs only.)
  if (sub.status === "canceled") {
    const { data: row } = await admin
      .from("subscriptions")
      .select("user_id")
      .eq("stripe_subscription_id", sub.id)
      .maybeSingle();
    if (row?.user_id) {
      const { data: free } = await admin
        .from("plans")
        .select("monthly_tokens")
        .eq("key", "free")
        .single();
      await admin
        .from("profiles")
        .update({ plan: "free", tokens: free?.monthly_tokens ?? 25 })
        .eq("id", row.user_id);
    }
  }
}

async function accrueCommission(admin: Admin, inv: Stripe.Invoice) {
  const subField = (inv as unknown as { subscription?: string | { id: string } }).subscription;
  const subId = typeof subField === "string" ? subField : subField?.id ?? null;
  if (!subId || (inv.amount_paid ?? 0) <= 0 || !inv.id) return;

  // Idempotent: Stripe retries webhooks, so never double-accrue the same invoice.
  const { data: dupe } = await admin
    .from("commissions")
    .select("id")
    .eq("stripe_invoice_id", inv.id)
    .maybeSingle();
  if (dupe) return;

  const { data: subRow } = await admin
    .from("subscriptions")
    .select("id, user_id, affiliate_id")
    .eq("stripe_subscription_id", subId)
    .maybeSingle();
  if (!subRow?.affiliate_id) return; // not a referred subscription -> no commission

  const { data: aff } = await admin
    .from("affiliates")
    .select("commission_rate")
    .eq("id", subRow.affiliate_id)
    .single();
  const rate = Number(aff?.commission_rate ?? 0.3);
  const amount = Math.round(((inv.amount_paid ?? 0) / 100) * rate * 100) / 100;

  await admin.from("commissions").insert({
    affiliate_id: subRow.affiliate_id,
    subscription_id: subRow.id,
    referred_user_id: subRow.user_id,
    amount_usd: amount,
    rate,
    period_start: epochToIso(inv.period_start),
    period_end: epochToIso(inv.period_end),
    status: "pending",
    stripe_invoice_id: inv.id,
  });
}

/** A refunded charge claws back its commission — unless it was already paid out
 *  (the 30-day maturation hold makes that the rare case, not the norm). */
async function reverseCommission(admin: Admin, charge: Stripe.Charge) {
  const invField = (charge as unknown as { invoice?: string | { id: string } }).invoice;
  const invId = typeof invField === "string" ? invField : invField?.id ?? null;
  if (!invId) return;
  await admin
    .from("commissions")
    .update({ status: "reversed" })
    .eq("stripe_invoice_id", invId)
    .in("status", ["pending", "approved"]);
}
