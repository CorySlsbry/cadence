import { createAdminClient } from "@/lib/supabase/admin";
import { PremiumClient, type Tier } from "./premium-client";

// Pricing renders straight from the `plans` table — edit the DB row and the
// website, checkout, and Stripe (via ensurePlanPrice) all follow automatically.
export const dynamic = "force-dynamic";

const BLURBS: Record<string, string> = {
  free: "Taste the studio.",
  base: "For the consistent creator.",
  creator: "For the daily publisher.",
  agency: "For teams running multiple accounts.",
};

function money(v: string | number): string {
  const n = Number(v);
  return n % 1 === 0 ? `$${n}` : `$${n.toFixed(2)}`;
}

export default async function PremiumPage() {
  const admin = createAdminClient();
  const [{ data }, { data: packRows }] = await Promise.all([
    admin
      .from("plans")
      .select("key,name,price_usd,monthly_tokens,features,sort")
      .eq("active", true)
      .order("sort"),
    admin
      .from("token_packs")
      .select("key,name,tokens,price_usd,sort")
      .eq("active", true)
      .order("sort"),
  ]);

  const tiers: Tier[] = (data ?? []).map((p) => {
    const paid = Number(p.price_usd) > 0;
    return {
      name: p.name,
      price: money(p.price_usd),
      cadence: paid ? "/ month" : "free forever",
      credits: paid ? `${p.monthly_tokens} tokens / mo` : `${p.monthly_tokens} tokens to start`,
      blurb: BLURBS[p.key] ?? "",
      features: Array.isArray(p.features) ? (p.features as string[]) : [],
      plan:
        p.key === "base" || p.key === "creator" || p.key === "agency"
          ? (p.key as "base" | "creator" | "agency")
          : null,
      highlight: p.key === "creator",
    };
  });

  const packs = (packRows ?? []).map((k) => ({
    key: k.key,
    name: k.name,
    tokens: k.tokens,
    price: money(k.price_usd),
    perToken: `$${(Number(k.price_usd) / k.tokens).toFixed(2)}/scene`,
  }));

  return <PremiumClient tiers={tiers} packs={packs} />;
}
