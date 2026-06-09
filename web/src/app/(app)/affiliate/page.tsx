import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { AffiliateActions } from "./affiliate-client";

const REF_BASE = "https://clouthook.com/?ref=";

type Dash = {
  code: string;
  commission_rate: number;
  status: string;
  referrals_total: number;
  active_subs: number;
  canceled_subs: number;
  mrr_active: number;
  monthly_commission: number;
  earned_pending: number;
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

  const { data: dash } = await supabase.rpc("affiliate_dashboard");

  // Not an affiliate yet → opt-in screen
  if (!dash) {
    return (
      <div className="mx-auto w-full max-w-3xl px-6 py-16">
        <span className="text-grad text-sm font-semibold">Affiliate program</span>
        <h1 className="mt-2 text-4xl font-extrabold leading-tight tracking-tight">
          Earn <span className="text-[var(--accent)]">30%</span> — recurring.
        </h1>
        <p className="mt-4 max-w-xl text-white/55">
          Share CloutHook and earn 30% of every subscription you refer — <strong className="text-white/80">every month they stay subscribed.</strong> Track
          your referrals, the MRR you drive, and your commission, live, right here.
        </p>
        <ul className="mt-6 space-y-2 text-sm text-white/60">
          <li>• 30% recurring commission on every plan</li>
          <li>• 60-day referral window</li>
          <li>• Live dashboard — your sales + commission</li>
          <li>• Paid out monthly</li>
        </ul>
        <AffiliateActions mode="join" />
      </div>
    );
  }

  const d = dash as Dash;
  const { data: refsRaw } = await supabase.rpc("affiliate_referrals");
  const refs = (refsRaw as Ref[] | null) ?? [];
  const rate = Math.round((d.commission_rate ?? 0.3) * 100);
  const link = REF_BASE + d.code;

  return (
    <div className="mx-auto w-full max-w-5xl px-6 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-extrabold tracking-tight">Affiliate</h1>
        <span className="rounded-full border border-white/10 px-3 py-1 text-xs text-white/60">{rate}% recurring</span>
      </div>

      <div className="mt-5 rounded-2xl border border-white/[0.07] bg-[var(--surface)] p-5">
        <div className="text-xs uppercase tracking-wide text-white/40">Your referral link</div>
        <AffiliateActions mode="link" link={link} />
      </div>

      <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Monthly commission" value={fmt(d.monthly_commission)} hint="from active subscriptions" accent />
        <Stat label="Active referrals" value={String(d.active_subs ?? 0)} hint={`${d.canceled_subs ?? 0} canceled`} />
        <Stat label="MRR you drive" value={fmt(d.mrr_active)} hint={`${d.referrals_total ?? 0} total signups`} />
        <Stat label="Pending payout" value={fmt(d.earned_pending)} hint={`${fmt(d.paid_total)} paid out`} />
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
                    No referrals yet — share your link to start earning.
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
        <p className="mt-3 text-xs text-white/35">Your cut stops automatically when a referral cancels.</p>
      </div>
    </div>
  );
}
