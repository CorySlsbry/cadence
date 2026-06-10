import { createAdminClient } from "@/lib/supabase/admin";
import { PremiumClient, type Tier } from "./premium-client";

// Pricing renders straight from the `plans` table — edit the DB row and the
// website, checkout, and Stripe (via ensurePlanPrice) all follow automatically.
export const dynamic = "force-dynamic";

const BLURBS: Record<string, string> = {
  free: "Taste the studio.",
  base: "For the consistent creator.",
  creator: "For the daily publisher.",
};

function money(v: string | number): string {
  const n = Number(v);
  return n % 1 === 0 ? `$${n}` : `$${n.toFixed(2)}`;
}

export default async function PremiumPage() {
  const admin = createAdminClient();
  const { data } = await admin
    .from("plans")
    .select("key,name,price_usd,monthly_tokens,features,sort")
    .eq("active", true)
    .order("sort");

  const tiers: Tier[] = (data ?? []).map((p) => {
    const paid = Number(p.price_usd) > 0;
    return {
      name: p.name,
      price: money(p.price_usd),
      cadence: paid ? "/ month" : "free forever",
      credits: paid ? `${p.monthly_tokens} tokens / mo` : `${p.monthly_tokens} tokens to start`,
      blurb: BLURBS[p.key] ?? "",
      features: Array.isArray(p.features) ? (p.features as string[]) : [],
      plan: p.key === "base" || p.key === "creator" ? (p.key as "base" | "creator") : null,
      highlight: p.key === "creator",
    };
  });

  return <PremiumClient tiers={tiers} />;
}
