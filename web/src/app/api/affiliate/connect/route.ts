import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { getStripe } from "@/lib/stripe";
import { publicOrigin } from "@/lib/request-origin";

/**
 * Stripe Connect Express onboarding for affiliate payouts.
 * Creates (once) an Express account for the affiliate, then returns a fresh
 * onboarding link. Re-callable any time — Stripe resumes incomplete onboarding.
 */
export async function POST(request: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const admin = createAdminClient();
  const { data: aff } = await admin
    .from("affiliates")
    .select("id, stripe_account_id")
    .eq("user_id", user.id)
    .maybeSingle();
  if (!aff) return NextResponse.json({ error: "Join the affiliate program first." }, { status: 400 });

  const stripe = getStripe();
  const origin = publicOrigin(request);

  try {
    let accountId = aff.stripe_account_id as string | null;
    if (!accountId) {
      const account = await stripe.accounts.create({
        type: "express",
        capabilities: { transfers: { requested: true } },
        business_type: "individual",
        email: user.email ?? undefined,
        metadata: { affiliate_id: aff.id, user_id: user.id },
      });
      accountId = account.id;
      await admin.from("affiliates").update({ stripe_account_id: accountId }).eq("id", aff.id);
    }

    const link = await stripe.accountLinks.create({
      account: accountId,
      refresh_url: `${origin}/affiliate?connect=retry`,
      return_url: `${origin}/affiliate?connect=done`,
      type: "account_onboarding",
    });
    return NextResponse.json({ url: link.url });
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Stripe Connect error";
    // Most common cause: Connect not yet enabled on the platform account.
    return NextResponse.json({ error: msg }, { status: 502 });
  }
}
