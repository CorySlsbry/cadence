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

export type PackRow = {
  key: string;
  name: string;
  tokens: number;
  price_usd: string | number;
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

/** The product for a row: reuse the stored/linked one, else create it. */
async function ensureProduct(
  stripe: Stripe,
  admin: SupabaseClient,
  table: "plans" | "token_packs",
  row: { key: string; stripe_product_id: string | null },
  productName: string,
  linkedProductId?: string,
): Promise<string> {
  const candidate = row.stripe_product_id || linkedProductId;
  if (candidate) {
    try {
      const prod = await stripe.products.retrieve(candidate);
      if (prod && !prod.deleted) {
        if (!row.stripe_product_id) {
          await admin.from(table).update({ stripe_product_id: prod.id }).eq("key", row.key);
        }
        return prod.id;
      }
    } catch {
      /* fall through to create */
    }
  }
  const created = await stripe.products.create({
    name: productName,
    metadata: { plan_key: row.key },
  });
  await admin.from(table).update({ stripe_product_id: created.id }).eq("key", row.key);
  return created.id;
}

/**
 * Core sync: returns a Stripe price id guaranteed to equal the row's current
 * price_usd. Rotates (create new + deactivate old) when they differ — Stripe
 * prices are immutable, so rotation is the only correct way to "change" one.
 */
async function ensureRowPrice(
  stripe: Stripe,
  admin: SupabaseClient,
  table: "plans" | "token_packs",
  row: { key: string; price_usd: string | number; stripe_price_id: string | null; stripe_product_id: string | null },
  productName: string,
  recurring: boolean,
): Promise<SyncResult> {
  const want = cents(row.price_usd);
  if (want <= 0) throw new Error(`${table}.${row.key} is not purchasable`);

  let current: Stripe.Price | null = null;
  if (row.stripe_price_id) {
    try {
      current = await stripe.prices.retrieve(row.stripe_price_id);
    } catch {
      current = null; // deleted/foreign id → treat as missing
    }
  }

  const intervalOk = recurring ? current?.recurring?.interval === "month" : !current?.recurring;
  if (current && current.active && current.unit_amount === want && current.currency === "usd" && intervalOk) {
    const productId = await ensureProduct(
      stripe, admin, table, row, productName,
      typeof current.product === "string" ? current.product : current.product?.id,
    );
    return { key: row.key, price_usd: want / 100, action: "match", stripe_price_id: current.id, stripe_product_id: productId };
  }

  const productId = await ensureProduct(
    stripe, admin, table, row, productName,
    current ? (typeof current.product === "string" ? current.product : current.product?.id) : undefined,
  );

  const fresh = await stripe.prices.create({
    product: productId,
    unit_amount: want,
    currency: "usd",
    ...(recurring ? { recurring: { interval: "month" as const } } : {}),
    metadata: { plan_key: row.key },
  });

  const { error } = await admin
    .from(table)
    .update({ stripe_price_id: fresh.id, stripe_product_id: productId })
    .eq("key", row.key);
  if (error) throw new Error(`price created but ${table} update failed: ${error.message}`);

  if (current?.id && current.active) {
    try {
      await stripe.prices.update(current.id, { active: false }); // retire the old price
    } catch {
      /* best-effort; a stray active price is harmless once unlinked */
    }
  }

  return {
    key: row.key,
    price_usd: want / 100,
    action: current ? "rotated" : "created",
    stripe_price_id: fresh.id,
    stripe_product_id: productId,
  };
}

export async function ensurePlanPrice(stripe: Stripe, admin: SupabaseClient, plan: PlanRow): Promise<SyncResult> {
  return ensureRowPrice(stripe, admin, "plans", plan, `CloutHook ${plan.name}`, true);
}

export async function ensurePackPrice(stripe: Stripe, admin: SupabaseClient, pack: PackRow): Promise<SyncResult> {
  return ensureRowPrice(stripe, admin, "token_packs", pack, `CloutHook Tokens — ${pack.name} (${pack.tokens})`, false);
}

/** Sync every active paid plan + token pack (or one specific key) and report. */
export async function syncPlans(
  stripe: Stripe,
  admin: SupabaseClient,
  onlyKey?: string,
): Promise<SyncResult[]> {
  const out: SyncResult[] = [];

  let pq = admin.from("plans").select("key,name,price_usd,monthly_tokens,active,stripe_price_id,stripe_product_id");
  pq = onlyKey ? pq.eq("key", onlyKey) : pq.eq("active", true).gt("price_usd", 0);
  const { data: planRows, error: pErr } = await pq;
  if (pErr) throw new Error(pErr.message);
  for (const row of planRows ?? []) {
    if (Number(row.price_usd) <= 0) continue; // free tier has no Stripe price
    out.push(await ensurePlanPrice(stripe, admin, row as PlanRow));
  }

  let kq = admin.from("token_packs").select("key,name,price_usd,tokens,active,stripe_price_id,stripe_product_id");
  kq = onlyKey ? kq.eq("key", onlyKey) : kq.eq("active", true);
  const { data: packRows, error: kErr } = await kq;
  if (kErr) throw new Error(kErr.message);
  for (const row of packRows ?? []) {
    out.push(await ensurePackPrice(stripe, admin, row as PackRow));
  }

  return out;
}
