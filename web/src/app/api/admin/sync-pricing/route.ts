import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { getStripe } from "@/lib/stripe";
import { syncPlans } from "@/lib/pricing";

/**
 * Force-sync Stripe prices to the `plans` table (the website's source of truth).
 * Checkout already self-heals per-session; this gives an instant full sync +
 * report after editing pricing. Secret-gated (same secret as the payout run).
 */
export async function POST(request: Request) {
  const secret = process.env.PAYOUT_RUN_SECRET;
  if (!secret || request.headers.get("x-payout-secret") !== secret) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  let only: string | undefined;
  try {
    const body = await request.json();
    if (body && typeof body.plan === "string") only = body.plan;
  } catch {
    /* no body = sync all active paid plans */
  }

  try {
    const report = await syncPlans(getStripe(), createAdminClient(), only);
    return NextResponse.json({ report });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "sync failed" },
      { status: 502 },
    );
  }
}
