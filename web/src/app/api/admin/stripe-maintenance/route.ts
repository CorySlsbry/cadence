import { NextResponse } from "next/server";
import { getStripe } from "@/lib/stripe";

const REQUIRED_EVENTS = [
  "checkout.session.completed",
  "customer.subscription.updated",
  "customer.subscription.deleted",
  "invoice.paid",
  "charge.refunded",
] as const;

/**
 * One-shot, idempotent Stripe wiring check (secret-gated, same header as the payout run).
 * Ensures our webhook endpoint subscribes to every event the handler implements —
 * so refund clawbacks and commission accrual can never silently miss events.
 */
export async function POST(request: Request) {
  const secret = process.env.PAYOUT_RUN_SECRET;
  if (!secret || request.headers.get("x-payout-secret") !== secret) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const stripe = getStripe();
  const endpoints = await stripe.webhookEndpoints.list({ limit: 16 });
  const target = endpoints.data.find((e) => e.url.includes("clouthook.com/api/webhooks/stripe"));
  if (!target) return NextResponse.json({ error: "webhook endpoint not found" }, { status: 404 });

  const have = new Set(target.enabled_events);
  const missing = REQUIRED_EVENTS.filter((e) => !have.has(e));
  if (missing.length === 0) {
    return NextResponse.json({ ok: true, updated: false, events: target.enabled_events });
  }

  const updated = await stripe.webhookEndpoints.update(target.id, {
    enabled_events: [...new Set([...target.enabled_events, ...missing])] as never,
  });
  return NextResponse.json({ ok: true, updated: true, added: missing, events: updated.enabled_events });
}
