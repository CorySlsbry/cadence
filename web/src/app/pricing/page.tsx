import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "CloutHook Pricing — plans & tokens",
  description:
    "CloutHook pricing: Free ($0), Base ($30/mo), and Creator ($79/mo). Token-based, no per-seat fees. See what each plan includes and how tokens work.",
};

const PLANS = [
  {
    key: "free", name: "Free", price: "$0", cadence: "/month", tokens: "25 tokens / month",
    blurb: "Make real shorts before you pay. No card required.",
    cta: "Start free", featured: false,
    includes: ["Record-once auto-editing", "Auto-captions + cleanup", "Auto-reframe 16:9 → 9:16", "1080×1920 · up to 60fps"],
  },
  {
    key: "base", name: "Base", price: "$30", cadence: "/month", tokens: "200 tokens / month",
    blurb: "For creators publishing every week.",
    cta: "Choose Base", featured: false,
    includes: ["Everything in Free", "Faceless videos (script → video)", "AI b-roll per moment", "Bring-your-own voice + cloning", "Direct posting to 6 platforms"],
  },
  {
    key: "creator", name: "Creator", price: "$79", cadence: "/month", tokens: "560 tokens / month",
    blurb: "For serious creators and affiliate marketers.",
    cta: "Choose Creator", featured: true,
    includes: ["Everything in Base", "Photoreal “clone yourself” avatar", "Up to 20 avatar videos / month", "Priority rendering", "Affiliate program — 30% recurring"],
  },
];

const ROWS: { label: string; free: string; base: string; creator: string }[] = [
  { label: "Monthly tokens", free: "25", base: "200", creator: "560" },
  { label: "Record-once auto-editing", free: "Yes", base: "Yes", creator: "Yes" },
  { label: "Auto-captions & cleanup", free: "Yes", base: "Yes", creator: "Yes" },
  { label: "Auto-reframe 16:9 → 9:16", free: "Yes", base: "Yes", creator: "Yes" },
  { label: "Auto-clip long videos", free: "Yes", base: "Yes", creator: "Yes" },
  { label: "Faceless videos", free: "—", base: "Yes", creator: "Yes" },
  { label: "AI b-roll", free: "—", base: "Yes", creator: "Yes" },
  { label: "Voice cloning (BYO key)", free: "—", base: "Yes", creator: "Yes" },
  { label: "Direct posting (X, IG, FB, LinkedIn, YouTube, TikTok)", free: "—", base: "Yes", creator: "Yes" },
  { label: "Photoreal AI avatar", free: "—", base: "—", creator: "20 / month" },
  { label: "Per-seat fees", free: "None", base: "None", creator: "None" },
];

const BILLING_FAQ = [
  { q: "How do tokens work?", a: "One token = one AI scene. An animated scene costs 3 tokens; a photoreal avatar video costs 8. Plain edits of your own footage cost nothing. Your monthly allowance refreshes each billing cycle." },
  { q: "What happens if I run out of tokens?", a: "Plain edits keep working. AI generation pauses until your allowance refreshes or you upgrade — you are never charged a surprise overage." },
  { q: "Do unused tokens roll over?", a: "Your allowance refreshes monthly and does not stack indefinitely, so plans stay simple and predictable." },
  { q: "Can I change plans anytime?", a: "Yes — upgrade or downgrade whenever you like. Changes take effect on your next cycle, and you keep access through the period you have paid for." },
  { q: "Is there a free trial?", a: "The Free plan is a permanent free tier with 25 tokens a month and no card required — so you can ship real videos before deciding to upgrade." },
  { q: "How do I cancel?", a: "Cancel anytime from billing settings; your plan stays active until the end of the current period. No long-term contract." },
];

const schema = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "CloutHook",
  applicationCategory: "MultimediaApplication",
  operatingSystem: "Web",
  description:
    "Record one raw take and CloutHook auto-edits a studio-grade 9:16 short — plus faceless videos and a photoreal AI avatar.",
  offers: PLANS.map((p) => ({
    "@type": "Offer",
    name: `${p.name} plan`,
    price: p.price.replace("$", ""),
    priceCurrency: "USD",
  })),
};

function Cell({ v }: { v: string }) {
  if (v === "—") return <td className="px-4 py-3 text-center text-white/40">—</td>;
  return <td className="px-4 py-3 text-center text-[15px] text-white/80">{v}</td>;
}

export default function PricingPage() {
  return (
    <div className="min-h-screen">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }} />
      <main className="mx-auto w-full max-w-4xl px-6 py-14">
        <Link href="/" className="text-sm text-[var(--accent)] hover:underline">← CloutHook</Link>
        <h1 className="mt-4 text-3xl font-bold text-white">Simple, token-based pricing</h1>
        <p className="mt-2 max-w-2xl text-[15px] leading-7 text-white/70">
          Pay for the AI you use — not per seat. Every plan records once and renders studio-grade
          1080×1920 shorts. Start free, upgrade when you are ready.
        </p>

        <section className="mt-10 grid grid-cols-1 gap-4 md:grid-cols-3">
          {PLANS.map((p) => (
            <div
              key={p.key}
              className={`relative flex flex-col rounded-2xl border bg-white/5 p-6 ${p.featured ? "border-[var(--accent)]" : "border-white/10"}`}
            >
              {p.featured && (
                <span className="absolute -top-3 left-6 rounded-full bg-[var(--accent)] px-3 py-1 text-xs font-bold text-black">
                  Most popular
                </span>
              )}
              <h2 className="text-lg font-semibold text-white">{p.name}</h2>
              <div className="mt-2 flex items-baseline gap-1">
                <span className="text-3xl font-extrabold text-white">{p.price}</span>
                <span className="text-sm text-white/55">{p.cadence}</span>
              </div>
              <p className="mt-1 text-sm font-medium text-[var(--accent)]">{p.tokens}</p>
              <p className="mt-3 text-[15px] leading-6 text-white/70">{p.blurb}</p>
              <ul className="mt-5 space-y-2 text-[15px] text-white/75">
                {p.includes.map((f) => (
                  <li key={f} className="flex gap-2">
                    <span aria-hidden className="text-[var(--accent)]">✓</span>
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
              <Link
                href="/signup"
                className={`press mt-6 inline-flex min-h-11 items-center justify-center rounded-xl px-5 text-sm font-bold transition ${p.featured ? "bg-[var(--accent)] text-black hover:brightness-110" : "border border-white/15 text-white hover:bg-white/5"}`}
              >
                {p.cta}
              </Link>
            </div>
          ))}
        </section>

        <section className="mt-16">
          <h2 className="text-xl font-semibold text-white">Compare plans</h2>
          <div className="mt-4 overflow-x-auto rounded-xl border border-white/10">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-white/10 bg-white/5">
                  <th className="px-4 py-3 text-sm font-semibold text-white">Feature</th>
                  <th className="px-4 py-3 text-center text-sm font-semibold text-white">Free</th>
                  <th className="px-4 py-3 text-center text-sm font-semibold text-white">Base</th>
                  <th className="px-4 py-3 text-center text-sm font-semibold text-white">Creator</th>
                </tr>
              </thead>
              <tbody>
                {ROWS.map((r, i) => (
                  <tr key={r.label} className={i % 2 ? "bg-white/[0.02]" : ""}>
                    <td className="px-4 py-3 text-[15px] text-white/80">{r.label}</td>
                    <Cell v={r.free} /><Cell v={r.base} /><Cell v={r.creator} />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="mt-16">
          <h2 className="text-xl font-semibold text-white">How tokens work</h2>
          <p className="mt-3 text-[15px] leading-7 text-white/70">
            Tokens meter AI generation so you only pay for what you create. <strong className="text-white/90">One token = one AI scene.</strong>{" "}
            An animated scene costs 3 tokens, and a photoreal avatar video costs 8 (Creator plan, up
            to 20 a month). Editing your own footage — cleanup, captions, reframing, clipping — costs
            no tokens. There are no per-seat fees, ever.
          </p>
        </section>

        <section className="mt-16">
          <h2 className="text-xl font-semibold text-white">Billing questions</h2>
          {BILLING_FAQ.map((f) => (
            <div key={f.q} className="mt-6">
              <h3 className="text-base font-semibold text-white">{f.q}</h3>
              <p className="mt-2 text-[15px] leading-7 text-white/70">{f.a}</p>
            </div>
          ))}
          <p className="mt-6 text-[15px] text-white/70">
            More questions? See the <Link href="/faq" className="text-[var(--accent)] hover:underline">FAQ</Link> or{" "}
            <a href="mailto:support@Neuron-HQ.com" className="text-[var(--accent)] hover:underline">email us</a>.
          </p>
        </section>

        <div className="mt-14 flex flex-col items-center gap-3 rounded-2xl border border-white/10 bg-white/5 p-8 text-center">
          <h2 className="text-2xl font-bold text-white">Record once. Post something studio-grade today.</h2>
          <Link
            href="/signup"
            className="press inline-flex min-h-12 items-center rounded-xl bg-[var(--accent)] px-7 text-sm font-bold text-black transition hover:brightness-110"
          >
            Start free
          </Link>
        </div>
      </main>
    </div>
  );
}
