import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { getStripe } from "@/lib/stripe";

const MATURE_DAYS = 30; // refund-protection hold before a commission is payable
const MIN_PAYOUT_USD = 10;

/**
 * Automated monthly payout run (Cloud Scheduler -> POST with x-payout-secret).
 *  1. Mature: pending commissions older than 30 days -> approved.
 *  2. For each payout-enabled affiliate with >= $10 approved: one Stripe transfer
 *     (idempotency-keyed), then mark those commissions paid + record the payout.
 * Failures on one affiliate never block the others; everything is reported.
 */
export async function POST(request: Request) {
  const secret = process.env.PAYOUT_RUN_SECRET;
  if (!secret || request.headers.get("x-payout-secret") !== secret) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const admin = createAdminClient();
  const stripe = getStripe();

  // 1) Mature pending -> approved after the hold window.
  const cutoff = new Date(Date.now() - MATURE_DAYS * 86400_000).toISOString();
  const { data: matured } = await admin
    .from("commissions")
    .update({ status: "approved" })
    .eq("status", "pending")
    .lt("created_at", cutoff)
    .select("id");

  // 2) Collect payable commissions grouped by affiliate.
  const { data: approved } = await admin
    .from("commissions")
    .select("id, affiliate_id, amount_usd")
    .eq("status", "approved");

  const byAffiliate = new Map<string, { ids: string[]; total: number }>();
  for (const c of approved ?? []) {
    const slot = byAffiliate.get(c.affiliate_id) ?? { ids: [], total: 0 };
    slot.ids.push(c.id);
    slot.total += Number(c.amount_usd) || 0;
    byAffiliate.set(c.affiliate_id, slot);
  }

  const paid: { affiliate_id: string; amount: number; transfer: string }[] = [];
  const skipped: { affiliate_id: string; reason: string }[] = [];

  for (const [affiliateId, slot] of byAffiliate) {
    const amount = Math.round(slot.total * 100) / 100;
    if (amount < MIN_PAYOUT_USD) {
      skipped.push({ affiliate_id: affiliateId, reason: `below $${MIN_PAYOUT_USD} minimum ($${amount})` });
      continue;
    }
    const { data: aff } = await admin
      .from("affiliates")
      .select("stripe_account_id, payouts_enabled")
      .eq("id", affiliateId)
      .single();
    if (!aff?.stripe_account_id || !aff.payouts_enabled) {
      skipped.push({ affiliate_id: affiliateId, reason: "payout account not ready" });
      continue;
    }

    try {
      // Idempotency: same commission set -> same key -> Stripe dedupes on retry.
      const key = `aff-payout-${affiliateId}-${slot.ids.slice().sort().join("-")}`.slice(0, 255);
      const transfer = await stripe.transfers.create(
        {
          amount: Math.round(amount * 100),
          currency: "usd",
          destination: aff.stripe_account_id,
          description: "CloutHook affiliate commission",
        },
        { idempotencyKey: key },
      );

      const { data: payout } = await admin
        .from("payouts")
        .insert({
          affiliate_id: affiliateId,
          amount_usd: amount,
          commission_count: slot.ids.length,
          stripe_transfer_id: transfer.id,
        })
        .select("id")
        .single();

      await admin
        .from("commissions")
        .update({ status: "paid", payout_id: payout?.id ?? null })
        .in("id", slot.ids);

      paid.push({ affiliate_id: affiliateId, amount, transfer: transfer.id });
    } catch (err) {
      // Insufficient platform balance / Connect issues: commissions stay approved, retried next run.
      skipped.push({ affiliate_id: affiliateId, reason: err instanceof Error ? err.message : "transfer failed" });
    }
  }

  return NextResponse.json({ matured: matured?.length ?? 0, paid, skipped });
}
