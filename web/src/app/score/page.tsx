import type { Metadata } from "next";
import Link from "next/link";
import { ScoreClient } from "./score-client";

const SITE = "https://clouthook.com";

export const metadata: Metadata = {
  title: "Free Viral Score — rate your short-form video with AI | CloutHook",
  description:
    "Paste a TikTok, Reels, or YouTube Short and get an instant AI Viral Score (0-10) on your hook, pacing, captions, visuals, format, and length — plus the exact fixes. Free, no signup to see your score.",
  alternates: { canonical: `${SITE}/score` },
};

const SCHEMA = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "WebApplication",
      "@id": `${SITE}/score#app`,
      name: "CloutHook Viral Score",
      url: `${SITE}/score`,
      applicationCategory: "MultimediaApplication",
      operatingSystem: "Web",
      offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
      description:
        "Free AI tool that scores a short-form video 0-10 on hook, pacing, captions, visual variety, format, and length, and returns specific fixes.",
      publisher: { "@type": "Organization", name: "CloutHook", url: SITE },
    },
    {
      "@type": "HowTo",
      name: "How to score your short-form video for free",
      step: [
        { "@type": "HowToStep", name: "Paste your video", text: "Paste a TikTok, Reels, or YouTube Short link, or describe the video's topic and hook." },
        { "@type": "HowToStep", name: "Get your Viral Score", text: "An AI analyst rates the hook, pacing, captions, visuals, format, and length 0-10 in about 15 seconds." },
        { "@type": "HowToStep", name: "Apply the fixes", text: "Get the prioritized fixes for that exact video, then let CloutHook apply them automatically." },
      ],
    },
  ],
};

export default function ScorePage() {
  return (
    <main className="mx-auto w-full max-w-2xl px-6 py-14">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(SCHEMA) }} />
      <Link href="/" className="text-sm text-[var(--accent)] hover:underline">
        ← CloutHook
      </Link>
      <h1 className="mt-4 text-3xl font-bold text-white sm:text-4xl">What&apos;s your video&apos;s Viral Score?</h1>
      <p className="mt-3 text-[15px] leading-7 text-white/70">
        Paste a TikTok, Reels, or YouTube Short and get an instant <strong className="text-white">0-10 Viral Score</strong> — an
        honest read on your hook, pacing, captions, visuals, format, and length, with the exact fixes for that video. Free,
        and you see your score before any signup.
      </p>

      <ScoreClient />

      <section className="mt-14">
        <h2 className="text-xl font-semibold text-white">What the Viral Score measures</h2>
        <p className="mt-3 text-[15px] leading-7 text-white/70">
          Short-form reach is decided in the first three seconds, then held by pacing and clarity. The Viral Score grades the
          six levers that decide whether a short gets pushed: the <strong className="text-white">hook</strong> (weighted
          heaviest), <strong className="text-white">pacing &amp; retention</strong>, <strong className="text-white">captions</strong>,{" "}
          <strong className="text-white">visual variety</strong>, <strong className="text-white">format &amp; framing</strong>, and{" "}
          <strong className="text-white">length</strong>. Each comes back with a score, a one-line verdict, and a concrete fix.
        </p>
        <p className="mt-3 text-[15px] leading-7 text-white/70">
          Once you know what&apos;s holding a video back, <Link href="/" className="text-[var(--accent)] hover:underline">CloutHook</Link>{" "}
          can apply the fixes for you — clean cuts, karaoke captions, AI b-roll, and a vertical reframe — from one raw take.
          See <Link href="/pricing" className="text-[var(--accent)] hover:underline">pricing</Link> or the{" "}
          <Link href="/faq" className="text-[var(--accent)] hover:underline">FAQ</Link>.
        </p>
      </section>
    </main>
  );
}
