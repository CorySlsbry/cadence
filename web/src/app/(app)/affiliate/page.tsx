import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { getStripe } from "@/lib/stripe";
import { JoinButton, LinkCard, PayoutSetupButton } from "./affiliate-client";

type Dash = {
  code: string;
  commission_rate: number;
  status: string;
  clicks: number;
  last_click_at: string | null;
  payouts_enabled: boolean;
  has_payout_account: boolean;
  referrals_total: number;
  active_subs: number;
  canceled_subs: number;
  mrr_active: number;
  monthly_commission: number;
  pending_usd: number;
  approved_usd: number;
  paid_total: number;
};
type Ref = {
  referred_user_id: string;
  plan: string;
  status: string;
  amount_usd: number;
  started_at: string;
  canceled_at: string | null;
};
type Payout = { amount_usd: number; commission_count: number; created_at: string };

const fmt = (n: unknown) => `$${(Number(n) || 0).toFixed(2)}`;

function Stat({ label, value, hint, accent }: { label: string; value: string; hint?: string; accent?: boolean }) {
  return (
    <div className="rounded-2xl border border-white/[0.07] bg-[var(--surface)] p-5">
      <div className="text-xs uppercase tracking-wide text-white/40">{label}</div>
      <div className={`mt-1 text-2xl font-bold ${accent ? "text-[var(--accent)]" : ""}`}>{value}</div>
      {hint && <div className="mt-1 text-xs text-white/35">{hint}</div>}
    </div>
  );
}

export default async function AffiliatePage() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: dashRaw } = await supabase.rpc("affiliate_dashboard");

  // Not an affiliate yet → opt-in screen
  if (!dashRaw) {
    return (
      <div className="mx-auto w-full max-w-3xl px-6 py-16">
        <span className="text-grad text-sm font-semibold">Affiliate program</span>
        <h1 className="mt-2 text-4xl font-extrabold leading-tight tracking-tight">
          Earn <span className="text-[var(--accent)]">30%</span> — recurring.
        </h1>
        <p className="mt-4 max-w-xl text-white/55">
          Share CloutHook and earn 30% of every subscription you refer — <strong className="text-white/80">every month they stay subscribed.</strong> Your
          link, your clicks, your signups, your commission: tracked live, paid out automatically.
        </p>
        <ul className="mt-6 space-y-2 text-sm text-white/60">
          <li>• 30% recurring commission on every plan</li>
          <li>• A link you customize — say it on camera: clouthook.com/r/you</li>
          <li>• 90-day attribution window, tracked end-to-end</li>
          <li>• Automatic monthly payouts, straight to your bank via Stripe</li>
        </ul>
        <JoinButton />
      </div>
    );
  }

  const d = dashRaw as Dash;

  // If onboarding was started but not yet confirmed, refresh the account status live.
  if (d.has_payout_account && !d.payouts_enabled) {
    try {
      const admin = createAdminClient();
      const { data: aff } = await admin
        .from("affiliates")
        .select("id, stripe_account_id")
        .eq("user_id", user.id)
        .single();
      if (aff?.stripe_account_id) {
        const acct = await getStripe().accounts.retrieve(aff.stripe_account_id);
        if (acct.payouts_enabled) {
          await admin.from("affiliates").update({ payouts_enabled: true }).eq("id", aff.id);
          d.payouts_enabled = true;
        }
      }
    } catch {
      /* status refresh is best-effort */
    }
  }

  const { data: refsRaw } = await supabase.rpc("affiliate_referrals");
  const refs = (refsRaw as Ref[] | null) ?? [];
  const { data: payoutsRaw } = await supabase
    .from("payouts")
    .select("amount_usd, commission_count, created_at")
    .order("created_at", { ascending: false })
    .limit(12);
  const payouts = (payoutsRaw as Payout[] | null) ?? [];
  const rate = Math.round((d.commission_rate ?? 0.3) * 100);

  return (
    <div className="mx-auto w-full max-w-5xl px-6 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-extrabold tracking-tight">Affiliate</h1>
        <span className="rounded-full border border-white/10 px-3 py-1 text-xs text-white/60">{rate}% recurring</span>
      </div>

      <div className="mt-5">
        <LinkCard code={d.code} />
      </div>

      <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Monthly commission" value={fmt(d.monthly_commission)} hint="from active subscriptions" accent />
        <Stat label="Link clicks" value={String(d.clicks ?? 0)} hint={d.last_click_at ? `last ${new Date(d.last_click_at).toLocaleDateString()}` : "share it to start"} />
        <Stat label="Active referrals" value={String(d.active_subs ?? 0)} hint={`${d.referrals_total ?? 0} signups · ${d.canceled_subs ?? 0} canceled`} />
        <Stat label="MRR you drive" value={fmt(d.mrr_active)} hint={`your cut: ${rate}%`} />
      </div>

      {/* Payouts — the money rail */}
      <div className="mt-5 rounded-2xl border border-white/[0.07] bg-[var(--surface)] p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-wide text-white/40">Payouts</div>
            <div className="mt-2 flex items-center gap-6 text-sm">
              <div>
                <span className="text-white/45">Maturing</span>{" "}
                <span className="font-semibold">{fmt(d.pending_usd)}</span>
              </div>
              <div>
                <span className="text-white/45">Ready to pay</span>{" "}
                <span className="font-semibold text-[var(--accent)]">{fmt(d.approved_usd)}</span>
              </div>
              <div>
                <span className="text-white/45">Paid out</span>{" "}
                <span className="font-semibold">{fmt(d.paid_total)}</span>
              </div>
            </div>
            <p className="mt-2 max-w-lg text-xs text-white/35">
              Commissions unlock 30 days after each payment (refund protection), then pay out automatically
              every month — $10 minimum — straight to your bank via Stripe.
            </p>
          </div>
          <div className="shrink-0">
            {d.payouts_enabled ? (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--accent)]/15 px-3 py-1.5 text-xs font-semibold text-[var(--accent)]">
                ✓ Bank connected — payouts are automatic
              </span>
            ) : (
              <PayoutSetupButton label={d.has_payout_account ? "Finish payout setup" : "Set up payouts"} />
            )}
          </div>
        </div>

        {payouts.length > 0 && (
          <div className="mt-4 border-t border-white/[0.06] pt-3">
            <div className="mb-2 text-xs text-white/40">Payout history</div>
            <div className="space-y-1.5">
              {payouts.map((p, i) => (
                <div key={i} className="flex items-center justify-between text-sm">
                  <span className="text-white/55">{new Date(p.created_at).toLocaleDateString()} · {p.commission_count} commissions</span>
                  <span className="font-medium">{fmt(p.amount_usd)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="mt-8">
        <div className="mb-3 text-sm font-semibold text-white/70">Referrals</div>
        <div className="overflow-hidden rounded-2xl border border-white/[0.07] bg-[var(--surface)]">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-white/40">
              <tr className="border-b border-white/[0.06]">
                <th className="px-4 py-3 font-medium">Plan</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Their price</th>
                <th className="px-4 py-3 font-medium">Your cut</th>
                <th className="px-4 py-3 font-medium">Started</th>
              </tr>
            </thead>
            <tbody>
              {refs.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-10 text-center text-white/40">
                    No referrals yet — drop your link in a video description to start earning.
                  </td>
                </tr>
              )}
              {refs.map((r, i) => {
                const active = r.status === "active";
                return (
                  <tr key={i} className="border-b border-white/[0.04]">
                    <td className="px-4 py-3 capitalize">{r.plan}</td>
                    <td className="px-4 py-3">
                      <span className={`rounded-full px-2 py-0.5 text-xs ${active ? "bg-[var(--accent)]/15 text-[var(--accent)]" : "bg-white/5 text-white/40"}`}>
                        {r.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-white/70">{fmt(r.amount_usd)}/mo</td>
                    <td className={`px-4 py-3 ${active ? "font-medium text-white" : "text-white/30 line-through"}`}>
                      {fmt(Number(r.amount_usd) * (d.commission_rate ?? 0.3))}/mo
                    </td>
                    <td className="px-4 py-3 text-white/50">{new Date(r.started_at).toLocaleDateString()}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs text-white/35">Your cut stops automatically when a referral cancels — and every payment is tracked the moment Stripe confirms it.</p>
      </div>
    </div>
  );
}
