"use client";

import { useEffect } from "react";
import Link from "next/link";
import { Logo } from "@/components/logo";
import { UpgradeButton } from "@/components/upgrade-button";
import { PackButton } from "@/components/pack-button";

export type Tier = {
  name: string;
  price: string;
  cadence: string;
  credits: string;
  blurb: string;
  features: string[];
  plan: "base" | "creator" | "agency" | null;
  highlight: boolean;
};

export type Pack = {
  key: string;
  name: string;
  tokens: number;
  price: string;
  perToken: string;
};

const PILLARS = [
  { k: "01", t: "One raw take", d: "Talk straight through your mistakes. CloutHook keeps the takes that land and removes everything else — automatically." },
  { k: "02", t: "Word-level auto-clean", d: "Silence, filler words, and repeated takes are detected at the word and cut out, with seams feathered so nothing pops." },
  { k: "03", t: "AI b-roll that knows your words", d: "Photoreal cutaways generated from what you're actually saying — say “Claude skills” and the frame renders it." },
  { k: "04", t: "Background replacement", d: "Lift yourself off your real background and drop onto a contextual scene. No green screen, no setup." },
  { k: "05", t: "Cinematographer controls", d: "Lens, aperture, film stock, lighting, color grade, grain, cinematic letterbox — dialed like a DP, not a slider toy." },
  { k: "06", t: "Built-in teleprompter", d: "Paste a script and read it back at your exact natural pace. It scrolls while you record and rewinds every take." },
];

const STEPS = [
  { n: "Record", d: "In-browser, one take, with the teleprompter scrolling at your pace." },
  { n: "Auto-clean", d: "We strip silence, fillers, and bad takes — word-accurate." },
  { n: "Generate & style", d: "AI b-roll, background replacement, and a reference-matched grade." },
  { n: "Publish", d: "A 1080×1920 / 60fps cut, ready to post. Download and go." },
];

const FAQ = [
  { q: "Do I need editing skills?", a: "No. You record one raw take; CloutHook does the cutting, captioning, b-roll, grading, and stitching. If you can talk to a camera, you can ship." },
  { q: "What exactly is a token?", a: "One token generates one AI scene (a photoreal b-roll image or faceless scene). Clean edits — cuts, captions, zoom, color — are always unlimited and cost zero tokens. Tokens only meter AI generation." },
  { q: "Can I match a specific creator's look?", a: "Yes. Drop in a reference clip and CloutHook maps its palette, cut timing, caption zones, and pacing, then stitches your footage to match the feel." },
  { q: "Will I get a surprise bill from heavy AI use?", a: "Never. Your token balance is a hard cap, enforced server-side. When tokens run out, the render still completes as a clean edit — you are never billed past your plan." },
  { q: "Is my footage private?", a: "Every account is fully isolated at the database and storage layer. Your recordings and renders live in your own space and are never shared across accounts." },
  { q: "Can I cancel anytime?", a: "Yes — month to month, cancel in one click. Tokens stay available through the end of your billing period." },
];

function CheckIcon() {
  return (
    <svg viewBox="0 0 20 20" className="mt-0.5 h-4 w-4 shrink-0 text-[var(--accent)]" fill="none" stroke="currentColor" strokeWidth="2.4">
      <path d="M4 10.5l4 4 8-9" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function PremiumClient({ tiers, packs }: { tiers: Tier[]; packs: Pack[] }) {
  // One IntersectionObserver drives every .reveal element on the page (no deps).
  useEffect(() => {
    const els = Array.from(document.querySelectorAll<HTMLElement>(".reveal"));
    const io = new IntersectionObserver(
      (entries) => entries.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }),
      { threshold: 0.12, rootMargin: "0px 0px -8% 0px" },
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);

  return (
    <div className="relative min-h-screen overflow-clip">
      {/* ambient aurora */}
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10">
        <div className="aurora left-[8%] top-[-6%] h-[520px] w-[520px]" style={{ background: "radial-gradient(circle, rgba(94,140,255,0.32), transparent 60%)" }} />
        <div className="aurora right-[2%] top-[10%] h-[460px] w-[460px]" style={{ background: "radial-gradient(circle, rgba(160,107,255,0.28), transparent 60%)", animationDelay: "-6s" }} />
        <div className="aurora left-[30%] top-[120%] h-[560px] w-[560px]" style={{ background: "radial-gradient(circle, rgba(122,108,255,0.18), transparent 60%)", animationDelay: "-3s" }} />
      </div>

      {/* nav */}
      <header className="sticky top-0 z-50 border-b border-white/[0.06] bg-[var(--background)]/70 backdrop-blur-xl">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-4">
          <Link href="/">
            <Logo size={26} />
          </Link>
          <nav className="hidden items-center gap-7 text-sm text-white/55 md:flex">
            <a href="#features" className="hover:text-white">Features</a>
            <a href="#how" className="hover:text-white">How it works</a>
            <a href="#pricing" className="hover:text-white">Pricing</a>
            <a href="#faq" className="hover:text-white">FAQ</a>
          </nav>
          <div className="flex items-center gap-2">
            <Link href="/login" className="rounded-xl px-4 py-2 text-sm font-medium text-white/70 hover:text-white">Sign in</Link>
            <Link href="/signup" className="rounded-xl bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-black transition hover:brightness-95">Start free</Link>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl px-6">
        {/* hero */}
        <section className="grid items-center gap-12 py-20 md:grid-cols-[1.15fr_0.85fr] md:py-28">
          <div>
            <p className="mb-6 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-4 py-1.5 text-xs text-white/60">
              <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)] animate-pulse-dot" />
              The editing layer, removed entirely
            </p>
            <h1 className="text-5xl font-extrabold leading-[1.02] tracking-tight md:text-[4.4rem]">
              Studio-grade video,
              <br />
              <span className="text-grad">from one raw take.</span>
            </h1>
            <p className="mt-7 max-w-xl text-lg leading-relaxed text-white/60">
              Record once. CloutHook removes the silence, fillers, and bad takes, generates photoreal b-roll
              from what you say, replaces your background, and grades it like a cinematographer — automatically.
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-3">
              <Link href="/signup" className="rounded-xl bg-[var(--accent)] px-7 py-4 text-sm font-bold text-black transition hover:brightness-95">
                Create your first video — free
              </Link>
              <a href="#pricing" className="rounded-xl border border-white/15 px-7 py-4 text-sm font-semibold text-white/85 transition hover:bg-white/5">
                See pricing
              </a>
            </div>
            <p className="mt-5 text-xs text-white/35">No card required · unlimited clean edits on every plan</p>
          </div>

          {/* phone mockup with a live teleprompter scroll */}
          <div className="relative mx-auto w-full max-w-[300px] animate-floaty">
            <div className="absolute -inset-6 -z-10 rounded-[2.5rem] bg-[var(--accent)]/10 blur-2xl" />
            <div className="relative aspect-[9/16] overflow-hidden rounded-[2rem] border border-white/12 bg-black shadow-2xl">
              <div className="absolute inset-0 bg-gradient-to-b from-[#1a1d2b] via-[#0d0f17] to-black" />
              {/* REC pill */}
              <div className="absolute left-3 top-3 z-20 flex items-center gap-1.5 rounded-full bg-black/55 px-2.5 py-1 text-[10px] text-white/80">
                <span className="h-1.5 w-1.5 rounded-full bg-red-500 animate-pulse-dot" /> 0:14
              </div>
              {/* teleprompter band */}
              <div className="absolute inset-x-0 top-1/2 z-10 h-px -translate-y-1/2 bg-[var(--accent)]/25" />
              <div className="pointer-events-none absolute inset-x-0 top-0 z-10 h-16 bg-gradient-to-b from-black to-transparent" />
              <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 h-24 bg-gradient-to-t from-black to-transparent" />
              <div className="absolute inset-0 flex flex-col justify-center overflow-hidden px-5">
                <div className="animate-scrollscript space-y-4 text-center text-[15px] font-semibold leading-snug text-white/90">
                  <p>Here&apos;s the thing nobody tells you about short-form…</p>
                  <p>You don&apos;t need an editor. You need one good take.</p>
                  <p>CloutHook cuts the dead air, the “ums,” the restarts —</p>
                  <p>then drops in b-roll that matches what you&apos;re saying.</p>
                  <p>Here&apos;s the thing nobody tells you about short-form…</p>
                  <p>You don&apos;t need an editor. You need one good take.</p>
                  <p>CloutHook cuts the dead air, the “ums,” the restarts —</p>
                  <p>then drops in b-roll that matches what you&apos;re saying.</p>
                </div>
              </div>
              {/* caption */}
              <div className="absolute inset-x-0 bottom-7 z-20 text-center">
                <span className="rounded-md bg-black/45 px-2 py-1 text-sm font-extrabold tracking-tight text-white" style={{ WebkitTextStroke: "0.5px rgba(0,0,0,0.6)" }}>
                  ONE <span className="text-[var(--accent)]">GOOD TAKE</span>
                </span>
              </div>
            </div>
            <div className="absolute -right-3 top-10 rotate-3 rounded-xl border border-white/10 bg-[var(--surface)] px-3 py-2 text-[11px] text-white/70 shadow-xl">
              ✦ AI b-roll generated
            </div>
            <div className="absolute -left-4 bottom-16 -rotate-3 rounded-xl border border-white/10 bg-[var(--surface)] px-3 py-2 text-[11px] text-white/70 shadow-xl">
              ⤺ 11 filler words cut
            </div>
          </div>
        </section>

        {/* marquee */}
        <section className="reveal relative overflow-hidden border-y border-white/[0.06] py-5">
          <div className="flex w-max animate-marquee gap-10 whitespace-nowrap text-sm font-medium text-white/35">
            {[...Array(2)].map((_, i) => (
              <span key={i} className="flex gap-10">
                <span>Record once</span><span className="text-[var(--accent)]/50">✦</span>
                <span>Word-level cleanup</span><span className="text-[var(--accent)]/50">✦</span>
                <span>AI contextual b-roll</span><span className="text-[var(--accent)]/50">✦</span>
                <span>Background replacement</span><span className="text-[var(--accent)]/50">✦</span>
                <span>Cinematographer controls</span><span className="text-[var(--accent)]/50">✦</span>
                <span>Built-in teleprompter</span><span className="text-[var(--accent)]/50">✦</span>
              </span>
            ))}
          </div>
        </section>

        {/* features */}
        <section id="features" className="py-24">
          <div className="reveal mx-auto mb-14 max-w-2xl text-center">
            <h2 className="text-3xl font-extrabold tracking-tight md:text-4xl">Everything an editor does. None of the hours.</h2>
            <p className="mt-4 text-white/55">Six things that used to take a timeline, a plugin, and an afternoon — now they happen on render.</p>
          </div>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {PILLARS.map((p, i) => (
              <div key={p.k} className="reveal group rounded-2xl border border-white/[0.07] bg-[var(--surface)]/60 p-6 transition duration-300 hover:-translate-y-1 hover:border-[var(--accent)]/30 hover:bg-[var(--surface)]" style={{ transitionDelay: `${(i % 3) * 60}ms` }}>
                <div className="mb-4 font-mono text-sm text-[var(--accent)]">{p.k}</div>
                <h3 className="text-lg font-semibold">{p.t}</h3>
                <p className="mt-2 text-sm leading-relaxed text-white/55">{p.d}</p>
              </div>
            ))}
          </div>
        </section>

        {/* how it works */}
        <section id="how" className="py-12 pb-24">
          <div className="reveal mb-12 text-center">
            <h2 className="text-3xl font-extrabold tracking-tight md:text-4xl">From talking head to finished cut</h2>
            <p className="mt-4 text-white/55">Four steps. The last three are automatic.</p>
          </div>
          <div className="grid gap-4 md:grid-cols-4">
            {STEPS.map((s, i) => (
              <div key={s.n} className="reveal relative rounded-2xl border border-white/[0.07] bg-[var(--surface)]/40 p-6" style={{ transitionDelay: `${i * 70}ms` }}>
                <div className="mb-3 flex h-8 w-8 items-center justify-center rounded-full bg-[var(--accent)] text-sm font-bold text-black">{i + 1}</div>
                <h3 className="font-semibold">{s.n}</h3>
                <p className="mt-2 text-sm leading-relaxed text-white/50">{s.d}</p>
              </div>
            ))}
          </div>
        </section>

        {/* pricing — rendered from the plans table (single source of truth) */}
        <section id="pricing" className="py-12 pb-8">
          <div className="reveal mx-auto mb-14 max-w-2xl text-center">
            <h2 className="text-3xl font-extrabold tracking-tight md:text-4xl">Pricing that scales with your output</h2>
            <p className="mt-4 text-white/55">Every plan includes <span className="text-white/80">unlimited clean edits</span>. Tokens power AI generation — and your balance is a hard cap, so there are no surprises.</p>
          </div>
          <div className="grid gap-4 lg:grid-cols-3">
            {tiers.map((t, i) => (
              <div
                key={t.name}
                className={`reveal relative flex flex-col rounded-2xl border p-6 ${t.highlight ? "border-[var(--accent)]/60 bg-[var(--surface)]" : "border-white/[0.08] bg-[var(--surface)]/50"}`}
                style={{ transitionDelay: `${i * 60}ms` }}
              >
                {t.highlight && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-[var(--accent)] px-3 py-1 text-[11px] font-bold text-black">Most popular</span>
                )}
                <h3 className="text-lg font-semibold">{t.name}</h3>
                <p className="mt-1 text-sm text-white/45">{t.blurb}</p>
                <div className="mt-5 flex items-baseline gap-1">
                  <span className="text-4xl font-extrabold tracking-tight">{t.price}</span>
                  <span className="text-sm text-white/40">{t.cadence}</span>
                </div>
                <p className="mt-3 inline-flex w-fit rounded-md bg-[var(--accent)]/10 px-2.5 py-1 text-xs font-medium text-[var(--accent)]">{t.credits}</p>
                <ul className="mt-6 flex-1 space-y-2.5 text-sm text-white/65">
                  {t.features.map((f) => (
                    <li key={f} className="flex gap-2"><CheckIcon /> <span>{f}</span></li>
                  ))}
                </ul>
                {t.plan ? (
                  <UpgradeButton
                    plan={t.plan}
                    className={`mt-7 w-full rounded-xl px-4 py-3 text-center text-sm font-semibold transition press ${t.highlight ? "bg-[var(--accent)] text-black hover:brightness-95" : "border border-white/15 text-white/85 hover:bg-white/5"}`}
                  >
                    Go {t.name}
                  </UpgradeButton>
                ) : (
                  <Link
                    href="/signup"
                    className="mt-7 rounded-xl border border-white/15 px-4 py-3 text-center text-sm font-semibold text-white/85 transition press hover:bg-white/5"
                  >
                    Start free
                  </Link>
                )}
              </div>
            ))}
          </div>
          <p className="reveal mt-6 text-center text-sm text-white/40">
            Prices update everywhere the moment we change them — the page, checkout, and Stripe always agree.
          </p>
        </section>

        {/* token top-ups — for heavy weeks, without changing plans */}
        {packs.length > 0 && (
          <section id="topup" className="py-12">
            <div className="reveal mx-auto mb-10 max-w-2xl text-center">
              <h2 className="text-3xl font-extrabold tracking-tight md:text-4xl">Out of tokens mid-streak?</h2>
              <p className="mt-4 text-white/55">
                Top up instantly — one-time purchase, tokens land the moment payment clears, and they
                stack on top of your monthly grant.
              </p>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              {packs.map((p, i) => (
                <div key={p.key} className="reveal flex flex-col rounded-2xl border border-white/[0.08] bg-[var(--surface)]/50 p-6" style={{ transitionDelay: `${i * 60}ms` }}>
                  <div className="flex items-baseline justify-between">
                    <h3 className="text-lg font-semibold">{p.name}</h3>
                    <span className="text-xs text-white/40">{p.perToken}</span>
                  </div>
                  <div className="mt-4 flex items-baseline gap-2">
                    <span className="text-4xl font-extrabold tracking-tight">{p.tokens}</span>
                    <span className="text-sm text-white/45">tokens</span>
                  </div>
                  <p className="mt-2 text-sm text-white/50">≈ {p.tokens} AI scenes, whenever you need them.</p>
                  <PackButton
                    pack={p.key}
                    className="press mt-6 w-full rounded-xl border border-[var(--accent)]/40 bg-[var(--accent)]/10 px-4 py-3 text-center text-sm font-semibold text-[var(--accent)] transition hover:bg-[var(--accent)]/15"
                  >
                    Add {p.tokens} for {p.price}
                  </PackButton>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* tokens / no-runaway certainty band */}
        <section className="reveal my-12 overflow-hidden rounded-3xl border border-white/[0.08] bg-gradient-to-br from-[var(--surface)] to-[var(--background)] p-8 md:p-12">
          <div className="grid gap-8 md:grid-cols-3">
            <div>
              <div className="text-3xl font-extrabold text-[var(--accent)]">1 token</div>
              <p className="mt-2 text-sm text-white/55">= one AI scene. Clean cuts, captions, and grading never cost a token.</p>
            </div>
            <div>
              <div className="text-3xl font-extrabold text-[var(--accent)]">Hard cap</div>
              <p className="mt-2 text-sm text-white/55">Your balance is enforced server-side. Out of tokens? The render still finishes as a clean edit.</p>
            </div>
            <div>
              <div className="text-3xl font-extrabold text-[var(--accent)]">$0 surprises</div>
              <p className="mt-2 text-sm text-white/55">You can never be billed for a runaway render. What you buy is the ceiling — by design.</p>
            </div>
          </div>
        </section>

        {/* faq */}
        <section id="faq" className="py-20">
          <h2 className="reveal mb-10 text-center text-3xl font-extrabold tracking-tight md:text-4xl">Questions, answered</h2>
          <div className="mx-auto max-w-3xl divide-y divide-white/[0.07]">
            {FAQ.map((f) => (
              <div key={f.q} className="reveal py-5">
                <h3 className="font-semibold text-white/90">{f.q}</h3>
                <p className="mt-2 text-sm leading-relaxed text-white/55">{f.a}</p>
              </div>
            ))}
          </div>
        </section>

        {/* final CTA */}
        <section className="reveal relative my-12 overflow-hidden rounded-3xl border border-[var(--accent)]/20 p-10 text-center md:p-16">
          <div className="pointer-events-none absolute inset-0 -z-10 opacity-60" style={{ background: "radial-gradient(700px 300px at 50% 0%, rgba(110,123,255,0.14), transparent 60%)" }} />
          <h2 className="mx-auto max-w-2xl text-4xl font-extrabold leading-tight tracking-tight md:text-5xl">
            Your next post, <span className="text-grad">without the edit.</span>
          </h2>
          <p className="mx-auto mt-5 max-w-lg text-white/55">Record one take today. Watch CloutHook turn it into a finished, premium vertical video.</p>
          <Link href="/signup" className="mt-8 inline-block rounded-xl bg-[var(--accent)] px-8 py-4 text-sm font-bold text-black transition press hover:brightness-95">
            Start free — 25 tokens on us
          </Link>
        </section>
      </main>

      <footer className="border-t border-white/[0.06] py-10">
        <div className="mx-auto flex w-full max-w-6xl flex-col items-center justify-between gap-4 px-6 text-sm text-white/35 md:flex-row">
          <div className="flex items-center gap-2">
            <span className="font-bold text-white/60">CloutHook</span>
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)]" />
            <span>Studio-grade short-form, automated.</span>
          </div>
          <div className="flex gap-6">
            <a href="#features" className="hover:text-white/70">Features</a>
            <a href="#pricing" className="hover:text-white/70">Pricing</a>
            <Link href="/signup" className="hover:text-white/70">Get started</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
