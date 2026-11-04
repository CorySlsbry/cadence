import type { Metadata } from "next";
import Link from "next/link";

const SITE = "https://clouthook.com";

type Post = { slug: string; title: string; dek: string; date: string };

// Keep this list in sync with the /blog/<slug> pages. The sequential blog workflow writes the pages;
// this index + the sitemap/llms entries point at them.
const POSTS: Post[] = [
  {
    slug: "best-opusclip-alternatives-2026",
    title: "Best OpusClip Alternatives in 2026 (for Creation, Not Just Clipping)",
    dek: "OpusClip clips existing video. The best alternatives also create — record-once, faceless, and photoreal AI avatars. An honest rundown for creators.",
    date: "2026-06-24",
  },
  {
    slug: "how-to-make-faceless-youtube-shorts-ai",
    title: "How to Make Faceless YouTube Shorts With AI (No Camera, No Editor)",
    dek: "Script to posted short with zero on-camera time. The full 2026 workflow for building a faceless channel with AI.",
    date: "2026-06-24",
  },
  {
    slug: "ai-avatar-video-clone-yourself",
    title: "AI Avatar Video: How to Clone Yourself and Stop Re-Recording",
    dek: "Speak any script in your own likeness from a single reference clip — how it works, the consent rules, and what it really costs versus HeyGen.",
    date: "2026-06-24",
  },
  {
    slug: "ai-affiliate-marketing-videos",
    title: "How to Make Affiliate Marketing Videos With AI (Faceless, Fast, No Editor)",
    dek: "Faceless product and review shorts at daily volume, no editor required. The exact AI stack for affiliate creators.",
    date: "2026-06-24",
  },
  {
    slug: "ai-short-form-video-pricing-2026",
    title: "AI Short-Form Video Pricing in 2026: Tokens vs Credits vs Seats",
    dek: "Tokens, credits, and per-seat plans compared — plus how many videos a $30 plan actually buys.",
    date: "2026-06-24",
  },
  {
    slug: "how-to-turn-long-video-into-shorts-ai",
    title: "How to Turn a Long Video Into Short Clips Automatically With AI",
    dek: "Paste a long video; AI finds the strongest moments and reframes them vertical. The full auto-clipping workflow.",
    date: "2026-06-24",
  },
  {
    slug: "how-to-auto-caption-videos-tiktok-instagram",
    title: "How to Auto-Caption Videos for TikTok and Instagram Reels",
    dek: "Frame-accurate karaoke captions burned in automatically — no manual sync — and why captions are non-negotiable for short-form.",
    date: "2026-06-24",
  },
  {
    slug: "how-to-post-to-all-social-media-at-once",
    title: "How to Post the Same Video to TikTok, Instagram, YouTube, LinkedIn, and Facebook at Once",
    dek: "Connect once, publish a short to all six platforms from one dashboard — the fastest record-to-posted workflow.",
    date: "2026-06-24",
  },
  {
    slug: "what-is-ai-b-roll",
    title: "What Is AI B-Roll and How to Generate It Automatically for Shorts",
    dek: "Generated cutaway footage matched to what you're saying — contextual, not stock. How it works and what it costs.",
    date: "2026-06-24",
  },
  {
    slug: "how-to-build-faceless-youtube-channel-ai",
    title: "How to Build a Faceless YouTube Channel With AI in 2026",
    dek: "Script, voice, scenes, captions, posting — all AI, zero on-camera time. The complete channel-starter guide.",
    date: "2026-06-24",
  },
  {
    slug: "best-opusclip-alternatives-faceless-avatar",
    title: "Best OpusClip Alternatives for Faceless Video and AI Avatars (2026)",
    dek: "The creator-facing tools for faceless creation and AI avatars versus the enterprise avatar incumbents.",
    date: "2026-06-24",
  },
];

export const metadata: Metadata = {
  title: "Blog — CloutHook",
  description:
    "Practical guides to AI short-form video: faceless YouTube Shorts, photoreal AI avatars, auto-clipping long footage, pricing breakdowns, and the best OpusClip alternatives in 2026.",
  alternates: { canonical: `${SITE}/blog` },
};

const SCHEMA = {
  "@context": "https://schema.org",
  "@type": "Blog",
  "@id": `${SITE}/blog`,
  name: "CloutHook Blog",
  url: `${SITE}/blog`,
  description:
    "Guides to AI short-form video: faceless shorts, AI avatars, auto-clipping, pricing, and OpusClip alternatives.",
  publisher: { "@type": "Organization", name: "CloutHook", url: SITE },
  blogPost: POSTS.map((p) => ({
    "@type": "BlogPosting",
    headline: p.title,
    url: `${SITE}/blog/${p.slug}`,
    datePublished: p.date,
    dateModified: p.date,
    author: { "@type": "Organization", name: "CloutHook" },
  })),
};

export default function BlogIndex() {
  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-14">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(SCHEMA) }}
      />
      <Link href="/" className="text-sm text-[var(--accent)] hover:underline">
        ← CloutHook
      </Link>
      <h1 className="mt-4 text-3xl font-bold text-white">The CloutHook Blog</h1>
      <p className="mt-3 max-w-2xl text-[15px] leading-7 text-white/70">
        Practical guides to AI short-form video — faceless shorts, photoreal avatars, auto-clipping
        long footage, honest pricing breakdowns, and how CloutHook stacks up against the tools you
        already know.
      </p>

      <div className="mt-10 space-y-4">
        {POSTS.map((p) => (
          <Link
            key={p.slug}
            href={`/blog/${p.slug}`}
            className="block rounded-xl border border-white/10 bg-white/5 p-6 transition hover:border-white/20 hover:bg-white/[0.07] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]"
          >
            <h2 className="text-lg font-semibold text-white">{p.title}</h2>
            <p className="mt-2 text-[15px] leading-7 text-white/70">{p.dek}</p>
            <span className="mt-3 inline-block text-sm text-[var(--accent)]">Read →</span>
          </Link>
        ))}
      </div>
    </main>
  );
}
