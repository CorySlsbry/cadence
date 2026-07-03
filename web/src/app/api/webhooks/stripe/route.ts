import { NextResponse } from "next/server";
import type Stripe from "stripe";
import { createAdminClient } from "@/lib/supabase/admin";
import { getStripe, epochToIso } from "@/lib/stripe";
import { notifySlack } from "@/lib/notify-slack";
import { sendFunnelEmail, type FunnelTemplate } from "@/lib/email";

type Admin = ReturnType<typeof createAdminClient>;

/** Send a lifecycle email at most once per (user, template) — email_log's unique constraint is the
 *  idempotency guard. Fetches the user's email from profiles when not supplied. No-ops if the mail
 *  relay isn't configured. */
async function sendLifecycleOnce(admin: Admin, userId: string, tpl: FunnelTemplate, emailHint?: string) {
  let email = emailHint;
  if (!email) {
    const { data } = await admin.from("profiles").select("email").eq("id", userId).maybeSingle();
    email = (data?.email as string | undefined) ?? undefined;
  }
  if (!email) return;
  const { error } = await admin.from("email_log").insert({ user_id: userId, email, template: tpl });
  if (!error) await sendFunnelEmail(email, tpl);
}
type PgResult = { error: { message: string; code?: string } | null };

// supabase-js resolves { data, error } and NEVER throws — so an unchecked DB failure would be
// silently ignored and this webhook would 200, telling Stripe "handled" when it wasn't (Stripe
// then never retries and the paid user is left without their plan/tokens). Wrap every mutation
// so a real error propagates to the outer catch → 500 → Stripe retries.
function ok<T extends PgResult>(res: T, ctx: string): T {
  if (res.error) throw new Error(`${ctx}: ${res.error.message}`);
  return res;
}

// Stripe moved current_period_* across API versions; read them defensively.
function periodBounds(sub: Stripe.Subscription): { start: string | null; end: string | null } {
  const s = sub as unknown as { current_period_start?: number; current_period_end?: number };
  return { start: epochToIso(s.current_period_start), end: epochToIso(s.current_period_end) };
}

/**
 * Stripe webhook. Verifies the signature, then keeps our DB in sync:
 *  - checkout.session.completed  -> upsert an active subscription, set the user's plan + grant tokens
 *  - customer.subscription.updated/deleted -> sync status + downgrade to free on any terminal status
 *  - invoice.paid -> accrue the affiliate's commission once per invoice (idempotent)
 *  - checkout.session.expired -> Slack ping (abandoned checkout — Stripe already has their email)
 * EVERY DB write is error-checked; a handler error returns 500 so Stripe retries.
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
      case "checkout.session.expired":
        await onCheckoutExpired(admin, event.data.object as Stripe.Checkout.Session);
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

  ok(
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
    ),
    "subscriptions.upsert",
  );

  // Set the plan (+ period anchor) — but NEVER absolutely overwrite `tokens`: that would wipe
  // purchased token-pack balances and re-grant on a duplicate webhook delivery. Grant the plan's
  // monthly tokens ADDITIVELY and exactly once, using token_topups.stripe_session_id (UNIQUE) as
  // the idempotency guard — the same mechanism the pack path uses.
  ok(
    await admin
      .from("profiles")
      .update({ plan, token_period_start: new Date().toISOString() })
      .eq("id", userId),
    "profiles.update(plan)",
  );

  const monthly = Number(planRow?.monthly_tokens ?? 0);
  if (monthly > 0 && s.id) {
    const ins = await admin.from("token_topups").insert({
      user_id: userId,
      pack_key: `plan:${plan}`, // marks this as the subscription's initial grant, not a pack sale
      tokens: monthly,
      amount_usd: null, // keep it out of pack-revenue sums
      affiliate_id: affiliateId,
      stripe_session_id: s.id,
    });
    if (ins.error) {
      if (ins.error.code !== "23505") throw new Error(`token_topups.insert(plan): ${ins.error.message}`);
      // 23505 = this checkout session already granted (Stripe retry) → don't grant again
    } else {
      ok(
        await admin.rpc("grant_extra_tokens", { p_user: userId, p_tokens: monthly, p_reason: `plan:${plan}` }),
        "grant_extra_tokens(plan)",
      );
    }
  }

  await notifySlack({
    kind: "purchase",
    title: `New subscription — ${plan}`,
    email: s.customer_details?.email ?? undefined,
    body: planRow?.price_usd ? `$${planRow.price_usd}/mo` : undefined,
  });
}

/** Token pack paid → grant tokens exactly once (unique session id absorbs Stripe retries)
 *  and accrue the referring affiliate's commission on the one-time amount. */
async function grantPackPurchase(admin: Admin, s: Stripe.Checkout.Session) {
  const userId = s.metadata?.user_id || s.client_reference_id || undefined;
  const tokens = Number(s.metadata?.tokens ?? 0);
  const packKey = s.metadata?.pack ?? "";
  if (!userId || !tokens || !s.id) return;

  const amountUsd = Math.round(s.amount_total ?? 0) / 100;
  const ins = await admin.from("token_topups").insert({
    user_id: userId,
    pack_key: packKey,
    tokens,
    amount_usd: amountUsd,
    affiliate_id: s.metadata?.affiliate_id || null,
    stripe_session_id: s.id,
  });
  if (ins.error) {
    // ONLY a duplicate session id means "already granted"; any other error must retry (throw),
    // otherwise a transient failure would permanently eat the customer's paid token pack.
    if (ins.error.code === "23505") return;
    throw new Error(`token_topups.insert: ${ins.error.message}`);
  }

  ok(
    await admin.rpc("grant_extra_tokens", {
      p_user: userId,
      p_tokens: tokens,
      p_reason: `topup:${packKey}`,
    }),
    "grant_extra_tokens(pack)",
  );

  const affiliateId = s.metadata?.affiliate_id || null;
  if (affiliateId && amountUsd > 0) {
    const { data: aff } = await admin
      .from("affiliates")
      .select("commission_rate")
      .eq("id", affiliateId)
      .maybeSingle();
    const rate = Number(aff?.commission_rate ?? 0.3);
    const commission = {
      affiliate_id: affiliateId,
      subscription_id: null,
      referred_user_id: userId,
      amount_usd: Math.round(amountUsd * rate * 100) / 100,
      rate,
      status: "pending",
      stripe_invoice_id: s.id, // unique idx → idempotent for pack sessions too
    };
    const cins = await admin.from("commissions").insert(commission);
    // A duplicate commission (retry) is fine; any other error should retry.
    if (cins.error && cins.error.code !== "23505") {
      throw new Error(`commissions.insert(pack): ${cins.error.message}`);
    }
  }

  await notifySlack({
    kind: "purchase",
    title: `Token pack — ${packKey}`,
    email: s.customer_details?.email ?? undefined,
    body: amountUsd > 0 ? `$${amountUsd} · ${tokens} tokens` : undefined,
  });
}

async function onCheckoutExpired(admin: Admin, s: Stripe.Checkout.Session) {
  // Stripe already collected the email on the Checkout page — highest-intent lead capture.
  const email = s.customer_details?.email ?? undefined;
  const userId = s.metadata?.user_id || s.client_reference_id || undefined;
  const what = s.metadata?.plan ? `plan ${s.metadata.plan}` : s.metadata?.pack ? `pack ${s.metadata.pack}` : "checkout";
  await notifySlack({ kind: "abandoned_checkout", title: "Abandoned checkout", email, body: what });
  if (userId) await sendLifecycleOnce(admin, userId, "abandoned_checkout", email);
}

async function syncSubscription(admin: Admin, sub: Stripe.Subscription) {
  const status =
    sub.status === "active" || sub.status === "trialing"
      ? "active"
      : sub.status === "past_due"
        ? "past_due"
        : "canceled";

  const { start, end } = periodBounds(sub);
  ok(
    await admin
      .from("subscriptions")
      .update({
        status,
        current_period_start: start,
        current_period_end: end,
        canceled_at: status === "canceled" ? new Date().toISOString() : null,
      })
      .eq("stripe_subscription_id", sub.id),
    "subscriptions.update",
  );

  // Downgrade the profile to free on ANY terminal status (canceled / unpaid / paused /
  // incomplete_expired — all map to local 'canceled'), not just Stripe's exact 'canceled'.
  // NEVER overwrite `tokens` here: a canceling user keeps whatever balance they have (they
  // paid through the period, and clobbering would destroy purchased pack tokens). Their monthly
  // refresh simply follows the free plan from here on.
  if (status === "canceled") {
    const { data: row } = await admin
      .from("subscriptions")
      .select("user_id")
      .eq("stripe_subscription_id", sub.id)
      .maybeSingle();
    if (row?.user_id) {
      ok(
        await admin.from("profiles").update({ plan: "free" }).eq("id", row.user_id),
        "profiles.update(downgrade)",
      );
      await sendLifecycleOnce(admin, row.user_id, "winback");
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

  const cins = await admin.from("commissions").insert({
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
  if (cins.error && cins.error.code !== "23505") {
    throw new Error(`commissions.insert: ${cins.error.message}`);
  }
}

/** A refunded charge claws back its commission — unless it was already paid out
 *  (the 30-day maturation hold makes that the rare case, not the norm). */
async function reverseCommission(admin: Admin, charge: Stripe.Charge) {
  const invField = (charge as unknown as { invoice?: string | { id: string } }).invoice;
  const invId = typeof invField === "string" ? invField : invField?.id ?? null;
  if (!invId) return;
  ok(
    await admin
      .from("commissions")
      .update({ status: "reversed" })
      .eq("stripe_invoice_id", invId)
      .in("status", ["pending", "approved"]),
    "commissions.update(reverse)",
  );
}
