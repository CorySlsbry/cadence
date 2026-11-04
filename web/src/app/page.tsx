import Link from "next/link";
import {
  ArrowRight,
  Clapperboard,
  Scissors,
  Captions,
  Wand2,
  Layers,
  Gauge,
} from "lucide-react";
import { createClient } from "@/lib/supabase/server";
import { Logo } from "@/components/logo";
import { RefCapture } from "@/components/ref-capture";
import { AuroraBg } from "@/components/aurora-bg";
import { RevealOnScroll } from "@/components/reveal-on-scroll";
import { HeroCommandBar } from "@/components/hero-command-bar";
import { ShowcaseGallery } from "@/components/showcase-gallery";
import { ScoreClient } from "@/app/score/score-client";

const STEPS = [
  { n: "01", t: "Analyze a reference", d: "Drop in a TikTok-style clip. CloutHook maps its palette, exact cut timing, caption zones and pacing." },
  { n: "02", t: "Record once", d: "Talk straight through your mistakes. We strip silence, filler words, and bad takes automatically." },
  { n: "03", t: "Apply your brand", d: "Persistent logos, colors, fonts and caption styling — applied to every render." },
  { n: "04", t: "Get a premium cut", d: "A 1080×1920 / 60fps vertical video, stitched to match the reference's feel. Download and post." },
];

const FEATURES = [
  { icon: Clapperboard, t: "Reference-matched edits", d: "We decode a viral clip's rhythm and rebuild your footage to feel just as tight." },
  { icon: Scissors, t: "Silence & filler removal", d: "Dead air, “ums”, and fumbled takes are cut automatically — no scrubbing the timeline." },
  { icon: Captions, t: "Auto-captions that pop", d: "Frame-accurate captions styled to your brand, placed in the safe zones that convert." },
  { icon: Wand2, t: "AI b-roll per moment", d: "Fresh, on-topic cutaways generated from your talking points and dropped on the beat." },
  { icon: Layers, t: "Replace the background", d: "Matte the speaker and swap the room for a clean set — or a dynamic AI scene." },
  { icon: Gauge, t: "1080×1920 · 60fps", d: "Studio-grade vertical output, rendered in the cloud and ready to post in minutes." },
];

const STATS = [
  { k: "1080×1920", v: "60fps vertical render" },
  { k: "Minutes", v: "raw take → posted cut" },
  { k: "$0", v: "per-seat tax, ever" },
  { k: "1 take", v: "is all it takes" },
];

const SITE = "https://clouthook.com";
const HOME_SCHEMA = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": `${SITE}/#org`,
      name: "CloutHook",
      url: SITE,
      description: "Premium AI short-form video studio.",
      sameAs: ["https://neuron-hq.com"],
      parentOrganization: {
        "@type": "Organization",
        name: "Neuron HQ",
        url: "https://neuron-hq.com",
        sameAs: ["https://neuron-hq.com"],
      },
    },
    { "@type": "WebSite", "@id": `${SITE}/#site`, name: "CloutHook", url: SITE, publisher: { "@id": `${SITE}/#org` } },
    {
      "@type": "SoftwareApplication",
      name: "CloutHook",
      applicationCategory: "MultimediaApplication",
      operatingSystem: "Web",
      url: SITE,
      publisher: { "@id": `${SITE}/#org` },
      description:
        "Record one raw take and CloutHook auto-edits a studio-grade 9:16 short — plus faceless videos and a photoreal AI avatar.",
      offers: [
        { "@type": "Offer", name: "Free", price: "0", priceCurrency: "USD" },
        { "@type": "Offer", name: "Base", price: "30", priceCurrency: "USD" },
        { "@type": "Offer", name: "Creator", price: "79", priceCurrency: "USD" },
      ],
    },
  ],
};

export default async function Landing() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  const primaryHref = user ? "/dashboard" : "/signup";
  const primaryCta = user ? "Open your studio" : "Start free";

  return (
    <div className="relative flex min-h-screen flex-col">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(HOME_SCHEMA) }} />
      <RefCapture />
      <AuroraBg />
      <RevealOnScroll />

      {/* ---------- glassy pill header ---------- */}
      <div className="sticky top-0 z-40 px-3 pt-3 sm:px-6 sm:pt-5">
        <header className="mx-auto flex w-full max-w-6xl items-center justify-between gap-3 rounded-2xl border border-white/12 bg-white/[0.04] px-4 py-3 shadow-[0_10px_40px_-18px_rgba(0,0,0,0.8)] backdrop-blur-xl sm:px-6">
          <Link href="/" aria-label="CloutHook home" className="shrink-0">
            <Logo size={24} />
          </Link>
          <nav className="flex items-center gap-1.5 sm:gap-2">
            <Link
              href="#how"
              className="hidden min-h-11 items-center rounded-xl px-3 py-2 text-sm font-medium text-white/60 transition hover:text-white md:inline-flex"
            >
              How it works
            </Link>
            <Link
              href="/pricing"
              className="hidden min-h-11 items-center rounded-xl px-3 py-2 text-sm font-medium text-white/60 transition hover:text-white sm:inline-flex"
            >
              Pricing
            </Link>
            <Link
              href="/blog"
              className="hidden min-h-11 items-center rounded-xl px-3 py-2 text-sm font-medium text-white/60 transition hover:text-white sm:inline-flex"
            >
              Blog
            </Link>
            <Link
              href="/score"
              className="hidden min-h-11 items-center rounded-xl px-3 py-2 text-sm font-medium text-white/60 transition hover:text-white sm:inline-flex"
            >
              Free Score
            </Link>
            <Link
              href={user ? "/affiliate" : "/login?next=/affiliate"}
              className="hidden min-h-11 items-center rounded-xl px-3 py-2 text-sm font-medium text-white/60 transition hover:text-white sm:inline-flex"
            >
              Affiliates
            </Link>
            {user ? (
              <Link
                href="/dashboard"
                className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-[var(--accent)] px-4 py-2 text-sm font-bold text-black transition hover:brightness-110"
              >
                Open studio <ArrowRight size={15} aria-hidden />
              </Link>
            ) : (
              <>
                <Link
                  href="/login"
                  className="inline-flex min-h-11 items-center rounded-xl px-3 py-2 text-sm font-medium text-white/75 transition hover:text-white"
                >
                  Log in
                </Link>
                <Link
                  href="/signup"
                  className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-[var(--accent)] px-4 py-2 text-sm font-bold text-black transition hover:brightness-110"
                >
                  Start free <ArrowRight size={15} aria-hidden />
                </Link>
              </>
            )}
          </nav>
        </header>
      </div>

      <main className="mx-auto w-full max-w-6xl flex-1 px-5 sm:px-6">
        {/* ---------- hero ---------- */}
        <section className="flex flex-col items-center pt-16 text-center sm:pt-24">
          <p className="reveal mb-6 inline-flex items-center gap-2 rounded-full border border-white/12 bg-white/[0.04] px-4 py-1.5 text-xs text-white/60 backdrop-blur-sm">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)] animate-pulse-dot" />
            Premium rendering · record in-browser · no seat tax
          </p>

          <h1 className="reveal mx-auto max-w-4xl text-[2.6rem] font-extrabold leading-[1.04] tracking-tight sm:text-6xl md:text-7xl">
            <span className="text-[var(--foreground)]">The studio that knows what to film —</span>
            <br />
            <span className="hero-grad">and finishes it.</span>
          </h1>

          <p className="reveal mx-auto mt-6 max-w-2xl text-base text-white/65 sm:text-lg">
            CloutHook finds the proven video in your niche, scripts it in your voice, scrolls it on
            the teleprompter while you record — then cleans, captions, b-rolls and clips it into a
            studio-grade short. One loop. No editor.
          </p>

          <div className="reveal mx-auto mt-7 flex max-w-3xl flex-wrap items-center justify-center gap-2 text-[13px] font-medium">
            <span className="rounded-full border border-white/10 bg-white/[0.04] px-3.5 py-1.5 text-white/75">1 · Find the outlier</span>
            <span className="text-white/25">→</span>
            <span className="rounded-full border border-white/10 bg-white/[0.04] px-3.5 py-1.5 text-white/75">2 · Script it in your voice</span>
            <span className="text-white/25">→</span>
            <span className="rounded-full border border-white/10 bg-white/[0.04] px-3.5 py-1.5 text-white/75">3 · Record on teleprompter</span>
            <span className="text-white/25">→</span>
            <span className="rounded-full border border-[var(--accent)]/30 bg-[var(--accent)]/10 px-3.5 py-1.5 text-[var(--accent)]">4 · We finish it</span>
          </div>

          <div className="reveal mt-9 w-full">
            <HeroCommandBar href={primaryHref} cta={primaryCta} />
          </div>

          <p className="reveal mt-4 text-sm text-white/60">
            Not ready to sign up?{" "}
            <Link href="/score" className="font-medium text-[var(--accent)] hover:underline">
              Score your last video free →
            </Link>
          </p>

          <div className="reveal mt-5 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-xs text-white/45">
            <span>No credit card to start</span>
            <span className="hidden h-1 w-1 rounded-full bg-white/25 sm:inline-block" />
            <span>Bring your own AI keys</span>
            <span className="hidden h-1 w-1 rounded-full bg-white/25 sm:inline-block" />
            <span>Cancel anytime</span>
          </div>
        </section>

        {/* ---------- showcase gallery ---------- */}
        <section className="reveal mt-20 sm:mt-28">
          <div className="mb-6 flex items-end justify-between px-1">
            <h2 className="text-sm font-semibold uppercase tracking-[0.18em] text-white/45">
              Built for every format
            </h2>
            <span className="text-xs text-white/35">9:16 · ready to post</span>
          </div>
          <ShowcaseGallery />
        </section>

        {/* ---------- free viral score (interactive lead-magnet centerpiece) ---------- */}
        <section id="score" className="mt-24 sm:mt-32">
          <div className="reveal mx-auto mb-8 max-w-2xl text-center">
            <p className="mb-3 inline-flex items-center gap-2 rounded-full border border-[var(--accent)]/30 bg-[var(--accent)]/10 px-4 py-1.5 text-xs font-medium text-[var(--accent)]">
              Free · no signup to see your score
            </p>
            <h2 className="text-3xl font-extrabold tracking-tight sm:text-4xl">
              Score your last video — <span className="brand-grad-text">free</span>
            </h2>
            <p className="mt-3 text-white/60">
              Paste a TikTok, Reel, or Short and get an honest 0-10 Viral Score on your hook, pacing,
              captions, visuals, format, and length — with the exact fixes for that video.
            </p>
          </div>
          <div className="reveal mx-auto max-w-2xl">
            <ScoreClient headingLevel="h3" />
          </div>
        </section>

        {/* ---------- how it works ---------- */}
        <section id="how" className="mt-24 sm:mt-32">
          <div className="reveal mx-auto mb-12 max-w-2xl text-center">
            <h2 className="text-3xl font-extrabold tracking-tight sm:text-4xl">
              From messy take to <span className="brand-grad-text">finished cut</span>
            </h2>
            <p className="mt-3 text-white/60">Four steps. No timeline. No seat tax.</p>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((s, i) => (
              <div
                key={s.n}
                className="reveal lift group relative overflow-hidden rounded-2xl border border-white/12 bg-[var(--surface)]/70 p-6 backdrop-blur-sm hover:border-white/20"
                style={{ transitionDelay: `${i * 70}ms` }}
              >
                <div
                  aria-hidden
                  className="absolute -right-6 -top-6 select-none text-7xl font-black text-white/[0.04]"
                >
                  {s.n}
                </div>
                <div className="mb-4 inline-flex h-9 items-center rounded-lg bg-[var(--accent)]/15 px-2.5 font-mono text-sm font-semibold text-[var(--accent)]">
                  {s.n}
                </div>
                <h3 className="text-lg font-semibold">{s.t}</h3>
                <p className="mt-2 text-sm leading-relaxed text-white/55">{s.d}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ---------- feature grid ---------- */}
        <section className="mt-24 sm:mt-32">
          <div className="reveal mx-auto mb-12 max-w-2xl text-center">
            <h2 className="text-3xl font-extrabold tracking-tight sm:text-4xl">
              Everything an editor does, <span className="brand-grad-text">automated</span>
            </h2>
            <p className="mt-3 text-white/60">
              The tedious parts of short-form, handled — so you just hit record.
            </p>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f, i) => {
              const Icon = f.icon;
              return (
                <div
                  key={f.t}
                  className="reveal lift group rounded-2xl border border-white/12 bg-[var(--surface)]/60 p-6 backdrop-blur-sm hover:border-[var(--accent)]/40"
                  style={{ transitionDelay: `${(i % 3) * 70}ms` }}
                >
                  <span className="mb-4 inline-flex h-11 w-11 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] text-[var(--accent)] transition-colors group-hover:border-[var(--accent)]/40">
                    <Icon size={20} aria-hidden />
                  </span>
                  <h3 className="text-base font-semibold">{f.t}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-white/55">{f.d}</p>
                </div>
              );
            })}
          </div>
        </section>

        {/* ---------- stats band ---------- */}
        <section className="reveal mt-24 sm:mt-32">
          <div className="relative overflow-hidden rounded-3xl border border-white/12 bg-white/[0.03] p-8 backdrop-blur-sm sm:p-10">
            <div
              aria-hidden
              className="pointer-events-none absolute inset-0 opacity-60"
              style={{
                background:
                  "radial-gradient(60% 120% at 50% -20%, rgba(122,108,255,0.18), transparent 70%)",
              }}
            />
            <div className="relative grid grid-cols-2 gap-6 text-center md:grid-cols-4">
              {STATS.map((s) => (
                <div key={s.k}>
                  <div className="text-2xl font-extrabold tracking-tight text-[var(--foreground)] sm:text-3xl">
                    {s.k}
                  </div>
                  <div className="mt-1 text-xs text-white/55 sm:text-sm">{s.v}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ---------- final CTA ---------- */}
        <section className="reveal mt-24 mb-28 sm:mt-32">
          <div className="relative mx-auto max-w-3xl overflow-hidden rounded-[28px] border border-white/12 p-[1px]">
            <div
              aria-hidden
              className="absolute inset-0 opacity-80 blur-[1px]"
              style={{ background: "var(--brand-grad)" }}
            />
            <div className="relative rounded-[27px] bg-[#0c0a18]/90 px-6 py-12 text-center backdrop-blur-xl sm:px-12 sm:py-14">
              <h2 className="mx-auto max-w-xl text-3xl font-extrabold leading-tight tracking-tight sm:text-4xl">
                Your next viral cut is <span className="hero-grad">one take away.</span>
              </h2>
              <p className="mx-auto mt-4 max-w-md text-white/60">
                Record once. Let CloutHook do the editing. Post something studio-grade today.
              </p>
              <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
                <Link
                  href={primaryHref}
                  className="inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-[var(--accent)] px-7 text-sm font-bold text-black transition hover:brightness-110 sm:w-auto"
                >
                  {user ? "Open your studio" : "Create your first video — free"}
                  <ArrowRight size={16} aria-hidden />
                </Link>
                <Link
                  href="#how"
                  className="inline-flex min-h-12 w-full items-center justify-center rounded-xl border border-white/15 px-7 text-sm font-semibold text-white/85 transition hover:bg-white/5 sm:w-auto"
                >
                  See how it works
                </Link>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-white/10 px-6 py-10">
        <div className="mx-auto flex max-w-6xl flex-col items-center gap-6 text-center">
          <div>
            <Logo size={22} />
            <p className="mt-2 text-xs text-white/45">Studio-grade short-form video automation</p>
          </div>

          <nav aria-label="Footer" className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs text-white/50">
            <Link href="#how" className="transition-colors hover:text-white/80">How it works</Link>
            <a href="/pricing" className="transition-colors hover:text-white/80">Pricing</a>
            <a href="/faq" className="transition-colors hover:text-white/80">FAQ</a>
            <a href="/clouthook-vs-opusclip" className="transition-colors hover:text-white/80">vs OpusClip</a>
            <a href="/blog" className="transition-colors hover:text-white/80">Blog</a>
            <a href="/score" className="transition-colors hover:text-white/80">Free Viral Score</a>
            <Link href={user ? "/affiliate" : "/login?next=/affiliate"} className="transition-colors hover:text-white/80">Affiliates</Link>
            <Link href="/signup" className="transition-colors hover:text-white/80">Start free</Link>
            <a href="/privacy" className="transition-colors hover:text-white/80">Privacy Policy</a>
            <a href="/terms" className="transition-colors hover:text-white/80">Terms of Service</a>
            <a href="/privacy#data-deletion" className="transition-colors hover:text-white/80">Data deletion</a>
          </nav>

          <div className="text-xs text-white/45">
            <p>
              Support &amp; contact:{" "}
              <a href="mailto:support@Neuron-HQ.com" className="text-white/70 transition-colors hover:text-white">
                support@Neuron-HQ.com
              </a>
            </p>
            <p className="mt-2 text-white/35">
              © {new Date().getFullYear()} CloutHook — an app by{" "}
              <a
                href="https://neuron-hq.com"
                target="_blank"
                rel="noreferrer"
                className="text-white/55 transition-colors hover:text-white"
              >
                Neuron HQ
              </a>
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
