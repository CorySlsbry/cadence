import type { Metadata } from "next";
import Link from "next/link";

const SITE = "https://clouthook.com";

export const metadata: Metadata = {
  title: "How the Viral Score works — the 6 things that decide a short's reach | CloutHook",
  description:
    "CloutHook's Viral Score rates a short-form video 0-10 across six weighted factors — hook, pacing, captions, visual variety, format, and length. Here's exactly what each one measures and why it matters.",
  alternates: { canonical: `${SITE}/how-the-viral-score-works` },
};

const DIMS = [
  {
    name: "Hook (first 3 seconds)",
    weight: "30%",
    q: "Why is the hook weighted the most?",
    a: "Short-form platforms decide how far to push a video based on what happens in the first 1-3 seconds. If viewers swipe, nothing else matters — so the hook carries the most weight in the score. We look at whether the opening makes a bold claim, opens a loop, mirrors a pain, or pattern-interrupts, versus a slow warm-up.",
  },
  {
    name: "Pacing & retention",
    weight: "20%",
    q: "What does pacing measure?",
    a: "After the hook, retention is held by energy and momentum: tight cuts, no dead air, and a clear through-line. We assess whether the video keeps moving or sags in the middle where most drop-off happens.",
  },
  {
    name: "Captions",
    weight: "15%",
    q: "Do captions really affect reach?",
    a: "Most short-form is watched on mute, and on-screen captions measurably lift watch time and accessibility. The score checks whether captions are present, readable, and well-timed — not an afterthought.",
  },
  {
    name: "Visual variety / b-roll",
    weight: "15%",
    q: "Why does visual variety matter?",
    a: "A static talking head loses attention faster than a video with cutaways, b-roll, and motion tied to what's being said. We look for visual changes that re-earn attention every few seconds.",
  },
  {
    name: "Format & framing",
    weight: "10%",
    q: "What counts as good format?",
    a: "Vertical 9:16, subject framed in the safe zones (away from each platform's UI), and clean composition. A horizontal or poorly-framed clip gets throttled regardless of content.",
  },
  {
    name: "Length",
    weight: "10%",
    q: "Is there an ideal length?",
    a: "Length should fit the idea and the platform — long enough to deliver, short enough to finish. We flag videos that overstay or feel cut off for the platform they're posted to.",
  },
];

const SCHEMA = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "HowTo",
      name: "How the CloutHook Viral Score is calculated",
      description:
        "A short-form video is scored 0-10 across six weighted factors: hook (30%), pacing (20%), captions (15%), visual variety (15%), format (10%), and length (10%).",
      step: DIMS.map((d) => ({ "@type": "HowToStep", name: d.name, text: d.a })),
    },
    {
      "@type": "FAQPage",
      mainEntity: DIMS.map((d) => ({
        "@type": "Question",
        name: d.q,
        acceptedAnswer: { "@type": "Answer", text: d.a },
      })),
    },
  ],
};

export default function HowScoreWorks() {
  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-14">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(SCHEMA) }} />
      <Link href="/" className="text-sm text-[var(--accent)] hover:underline">
        ← CloutHook
      </Link>
      <h1 className="mt-4 text-3xl font-bold text-white sm:text-4xl">How the Viral Score works</h1>
      <p className="mt-3 text-[15px] leading-7 text-white/70">
        The CloutHook <Link href="/score" className="text-[var(--accent)] hover:underline">Viral Score</Link> rates a
        short-form video from 0 to 10 across the six factors that actually decide reach. Each factor is scored 0-10 by an
        AI growth analyst, then combined with the weighting below — the hook counts most because the first three seconds
        decide whether a video gets pushed at all.
      </p>

      <div className="mt-8 overflow-hidden rounded-xl border border-white/10">
        <table className="w-full text-left text-[15px]">
          <thead>
            <tr className="border-b border-white/10 bg-white/5">
              <th className="px-4 py-3 font-semibold text-white">Factor</th>
              <th className="px-4 py-3 font-semibold text-white">Weight</th>
            </tr>
          </thead>
          <tbody>
            {DIMS.map((d) => (
              <tr key={d.name} className="border-b border-white/10 last:border-0">
                <td className="px-4 py-3 text-white/80">{d.name}</td>
                <td className="px-4 py-3 font-semibold text-[var(--accent)]">{d.weight}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {DIMS.map((d) => (
        <section key={d.name} className="mt-10">
          <h2 className="text-xl font-semibold text-white">{d.q}</h2>
          <p className="mt-3 text-[15px] leading-7 text-white/70">{d.a}</p>
        </section>
      ))}

      <section className="mt-12 rounded-2xl border border-[var(--accent)]/30 bg-[var(--accent)]/10 p-6">
        <h2 className="text-xl font-semibold text-white">Score your video, then fix it automatically</h2>
        <p className="mt-2 text-[15px] leading-7 text-white/70">
          Run a free <Link href="/score" className="text-[var(--accent)] hover:underline">Viral Score</Link>, then let{" "}
          <Link href="/" className="text-[var(--accent)] hover:underline">CloutHook</Link> apply the fixes — clean cuts,
          karaoke captions, AI b-roll, and a vertical reframe — from one raw take. See{" "}
          <Link href="/pricing" className="text-[var(--accent)] hover:underline">pricing</Link>.
        </p>
        <Link
          href="/score"
          className="mt-4 inline-flex min-h-12 items-center rounded-xl bg-[var(--accent)] px-6 font-semibold text-black transition active:scale-[0.99]"
        >
          Get my Viral Score
        </Link>
      </section>
    </main>
  );
}
