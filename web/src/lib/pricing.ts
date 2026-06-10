import type Stripe from "stripe";
import type { SupabaseClient } from "@supabase/supabase-js";

/**
 * Pricing sync — the `plans` table is the single source of truth.
 *
 * `ensurePlanPrice` guarantees the Stripe price a buyer checks out with matches
 * `plans.price_usd` AT THAT MOMENT: if the DB price changed (or the price is
 * missing/inactive), it rotates in a fresh monthly price on the plan's product,
 * stores the new id back on the row, and retires the old price. Checkout calls
 * this on every session, so editing the website's pricing automatically updates
 * Stripe — no manual step, no drift.
 */

export type PlanRow = {
  key: string;
  name: string;
  price_usd: string | number;
  monthly_tokens: number;
  active: boolean;
  stripe_price_id: string | null;
  stripe_product_id: string | null;
};

export type SyncResult = {
  key: string;
  price_usd: number;
  action: "match" | "created" | "rotated";
  stripe_price_id: string;
  stripe_product_id: string;
};

function cents(priceUsd: string | number): number {
  return Math.round(Number(priceUsd) * 100);
}

/** The product for a plan: reuse the stored/linked one, else create it. */
async function ensureProduct(
  stripe: Stripe,
  admin: SupabaseClient,
  plan: PlanRow,
  linkedProductId?: string,
): Promise<string> {
  const candidate = plan.stripe_product_id || linkedProductId;
  if (candidate) {
    try {
      const prod = await stripe.products.retrieve(candidate);
      if (prod && !prod.deleted) {
        if (!plan.stripe_product_id) {
          await admin.from("plans").update({ stripe_product_id: prod.id }).eq("key", plan.key);
        }
        return prod.id;
      }
    } catch {
      /* fall through to create */
    }
  }
  const created = await stripe.products.create({
    name: `CloutHook ${plan.name}`,
    metadata: { plan_key: plan.key },
  });
  await admin.from("plans").update({ stripe_product_id: created.id }).eq("key", plan.key);
  return created.id;
}

/**
 * Returns a Stripe price id guaranteed to equal the plan's current price_usd.
 * Rotates (create new + deactivate old) when they differ — Stripe prices are
 * immutable, so rotation is the only correct way to "change" a price.
 */
export async function ensurePlanPrice(
  stripe: Stripe,
  admin: SupabaseClient,
  plan: PlanRow,
): Promise<SyncResult> {
  const want = cents(plan.price_usd);
  if (want <= 0) throw new Error(`plan ${plan.key} is not purchasable`);

  let current: Stripe.Price | null = null;
  if (plan.stripe_price_id) {
    try {
      current = await stripe.prices.retrieve(plan.stripe_price_id);
    } catch {
      current = null; // deleted/foreign id → treat as missing
    }
  }

  if (
    current &&
    current.active &&
    current.unit_amount === want &&
    current.currency === "usd" &&
    current.recurring?.interval === "month"
  ) {
    const productId = await ensureProduct(
      stripe, admin, plan,
      typeof current.product === "string" ? current.product : current.product?.id,
    );
    return { key: plan.key, price_usd: want / 100, action: "match", stripe_price_id: current.id, stripe_product_id: productId };
  }

  const productId = await ensureProduct(
    stripe, admin, plan,
    current ? (typeof current.product === "string" ? current.product : current.product?.id) : undefined,
  );

  const fresh = await stripe.prices.create({
    product: productId,
    unit_amount: want,
    currency: "usd",
    recurring: { interval: "month" },
    metadata: { plan_key: plan.key },
  });

  const { error } = await admin
    .from("plans")
    .update({ stripe_price_id: fresh.id, stripe_product_id: productId })
    .eq("key", plan.key);
  if (error) throw new Error(`price created but plans update failed: ${error.message}`);

  if (current?.id && current.active) {
    try {
      await stripe.prices.update(current.id, { active: false }); // retire the old price
    } catch {
      /* best-effort; a stray active price is harmless once unlinked */
    }
  }

  return {
    key: plan.key,
    price_usd: want / 100,
    action: current ? "rotated" : "created",
    stripe_price_id: fresh.id,
    stripe_product_id: productId,
  };
}

/** Sync every active paid plan (or one specific plan key) and report what happened. */
export async function syncPlans(
  stripe: Stripe,
  admin: SupabaseClient,
  onlyKey?: string,
): Promise<SyncResult[]> {
  let q = admin.from("plans").select("key,name,price_usd,monthly_tokens,active,stripe_price_id,stripe_product_id");
  q = onlyKey ? q.eq("key", onlyKey) : q.eq("active", true).gt("price_usd", 0);
  const { data: rows, error } = await q;
  if (error) throw new Error(error.message);
  const out: SyncResult[] = [];
  for (const row of rows ?? []) {
    if (Number(row.price_usd) <= 0) continue; // free tier has no Stripe price
    out.push(await ensurePlanPrice(stripe, admin, row as PlanRow));
  }
  return out;
}
