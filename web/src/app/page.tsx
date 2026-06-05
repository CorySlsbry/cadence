import Link from "next/link";
import { createClient } from "@/lib/supabase/server";

const STEPS = [
  { n: "01", t: "Analyze a reference", d: "Drop in a TikTok-style clip. Cadence maps its palette, exact cut timing, caption zones and pacing." },
  { n: "02", t: "Record once", d: "Talk straight through your mistakes. We strip silence, filler words, and bad takes automatically." },
  { n: "03", t: "Apply your brand", d: "Persistent logos, colors, fonts and caption styling — applied to every render." },
  { n: "04", t: "Get a premium cut", d: "A 1080×1920 / 60fps vertical video, stitched to match the reference's feel. Download and post." },
];

export default async function Landing() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  return (
    <div className="flex min-h-screen flex-col">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-6">
        <div className="flex items-center gap-2">
          <span className="text-xl font-extrabold tracking-tight">Cadence</span>
          <span className="h-2 w-2 rounded-full bg-[var(--accent)]" />
        </div>
        <nav className="flex items-center gap-2">
          {user ? (
            <Link href="/dashboard" className="rounded-xl bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-black">
              Open studio
            </Link>
          ) : (
            <>
              <Link href="/login" className="rounded-xl px-4 py-2 text-sm font-medium text-white/70 hover:text-white">
                Sign in
              </Link>
              <Link href="/signup" className="rounded-xl bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-black">
                Start free
              </Link>
            </>
          )}
        </nav>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-6">
        <section className="py-20 text-center md:py-28">
          <p className="mx-auto mb-5 inline-flex items-center gap-2 rounded-full border border-white/10 px-4 py-1.5 text-xs text-white/50">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)] animate-pulse-dot" />
            Premium rendering · record in-browser · no seat tax
          </p>
          <h1 className="mx-auto max-w-3xl text-5xl font-extrabold leading-[1.05] tracking-tight md:text-6xl">
            Studio-grade short-form,
            <br />
            <span className="text-[var(--accent)]">from one raw take.</span>
          </h1>
          <p className="mx-auto mt-6 max-w-xl text-lg text-white/55">
            Stop editing for hours. Cadence analyzes a reference, cleans your raw footage, and stitches a
            premium vertical video that matches its style — automatically.
          </p>
          <div className="mt-9 flex items-center justify-center gap-3">
            <Link href={user ? "/dashboard" : "/signup"} className="rounded-xl bg-[var(--accent)] px-7 py-4 text-sm font-bold text-black transition hover:brightness-95">
              {user ? "Open your studio" : "Create your first video — free"}
            </Link>
            <Link href="#how" className="rounded-xl border border-white/15 px-7 py-4 text-sm font-semibold text-white/80 hover:bg-white/5">
              See how it works
            </Link>
          </div>
        </section>

        <section id="how" className="grid gap-4 pb-24 md:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((s) => (
            <div key={s.n} className="rounded-2xl border border-white/[0.07] bg-[var(--surface)] p-6">
              <div className="mb-4 font-mono text-sm text-[var(--accent)]">{s.n}</div>
              <h3 className="text-lg font-semibold">{s.t}</h3>
              <p className="mt-2 text-sm leading-relaxed text-white/50">{s.d}</p>
            </div>
          ))}
        </section>
      </main>

      <footer className="border-t border-white/5 py-8 text-center text-xs text-white/30">
        Cadence · Studio-grade short-form video automation
      </footer>
    </div>
  );
}
