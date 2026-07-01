import type { Metadata } from "next";
import Link from "next/link";

const CANONICAL = "https://clouthook.com/blog/ai-affiliate-marketing-videos";

export const metadata: Metadata = {
  title: "How to Make Affiliate Marketing Videos With AI (Faceless, Fast, No Editor) — 2026",
  description:
    "Yes — you can produce faceless product and review shorts from a script, daily, without showing your face or touching an editor. Here's the exact AI workflow for a faceless affiliate channel, the token math, and the platforms you can auto-post to.",
  alternates: { canonical: CANONICAL },
};

function H2({ id, children }: { id?: string; children: React.ReactNode }) {
  return <h2 id={id} className="mt-12 scroll-mt-24 text-xl font-semibold text-white">{children}</h2>;
}
function P({ children }: { children: React.ReactNode }) {
  return <p className="mt-3 text-[15px] leading-7 text-white/70">{children}</p>;
}

const STEPS: { title: string; body: string }[] = [
  {
    title: "Write a 30–60 second review script",
    body: "Affiliate shorts win on one clear angle: the problem, the product as the fix, and the link. Open with the pain (\"still editing podcasts by hand?\"), name the product, give one concrete reason it works, and end with a call to grab it. Aim for 90–140 words — about 30–60 seconds, the retention sweet spot for shorts.",
  },
  {
    title: "Pick a voice (preset or your clone)",
    body: "Choose a preset AI voice for a fully anonymous channel, or your own cloned voice so the channel sounds like a real reviewer. CloutHook can clone your voice, or you can bring your own ElevenLabs voice and clones — voice quality is the line between a trusted review and obvious spam.",
  },
  {
    title: "Let AI generate the review scenes",
    body: "The tool reads the script line by line and generates a matching visual for each beat — product close-ups, before/after framing, feature callouts. In CloutHook this is 1 token per AI scene (an animated scene is 3). No stock library, no timeline, no footage to source.",
  },
  {
    title: "Add karaoke captions",
    body: "Most shorts are watched on mute, and a review only converts if the viewer reads the benefit. CloutHook lays word-by-word karaoke captions over the whole video automatically, synced to the voiceover, so the product name and the offer land even with the sound off.",
  },
  {
    title: "Render to 1080×1920 vertical",
    body: "Everything composites into one studio-grade 1080×1920 (9:16) MP4 — the native shorts frame for TikTok, Reels, and YouTube Shorts. No export settings, no resizing. What comes out is ready to publish with your affiliate link in the caption.",
  },
  {
    title: "Auto-post and drop the link",
    body: "Connect each account once and publish straight from the app to X, Instagram, Facebook, LinkedIn, YouTube, and TikTok — then paste your affiliate or bio link. One review goes to six platforms in a single pass, which is how affiliate channels post daily without a content team.",
  },
];

const WORKFLOW_ROWS: { label: string; ai: string; manual: string }[] = [
  { label: "Script → finished video", ai: "Automatic, from text", manual: "Write, film, and edit each one" },
  { label: "Voiceover", ai: "AI voice or your cloned voice", manual: "Record yourself or hire a VO" },
  { label: "Product visuals / b-roll", ai: "AI scenes generated per line", manual: "Source, license, place by hand" },
  { label: "Captions", ai: "Auto karaoke captions, synced", manual: "Type and time them manually" },
  { label: "Output format", ai: "1080×1920 9:16, ready to post", manual: "Export and resize yourself" },
  { label: "Publishing", ai: "Direct to 6 platforms", manual: "Download, then upload to each" },
  { label: "On-camera time", ai: "Zero", manual: "Filming and re-shoots" },
  { label: "Realistic cadence", ai: "Daily, solo", manual: "A few per week, at best" },
];

const blogSchema = {
  "@context": "https://schema.org",
  "@type": "BlogPosting",
  headline: "How to Make Affiliate Marketing Videos With AI (Faceless, Fast, No Editor) — 2026",
  description:
    "Yes — you can produce faceless product and review shorts from a script, daily, without showing your face or touching an editor. Here's the exact AI workflow for a faceless affiliate channel, the token math, and the platforms you can auto-post to.",
  datePublished: "2026-06-24",
  dateModified: "2026-06-24",
  author: { "@type": "Organization", name: "CloutHook" },
  publisher: { "@type": "Organization", name: "CloutHook", url: "https://clouthook.com" },
  mainEntityOfPage: { "@type": "WebPage", "@id": CANONICAL },
};

const FAQ = [
  {
    q: "Can you make affiliate marketing videos without showing your face?",
    a: "Yes. AI tools like CloutHook generate the entire review short from a script — an AI or cloned voiceover, AI scenes for each line, and karaoke captions — composited to a 1080×1920 vertical video with zero on-camera time. You run a faceless affiliate channel and drop your link in the caption.",
  },
  {
    q: "What AI workflow produces review shorts from a script automatically?",
    a: "Write a short review script, pick a voice, and the tool narrates it, generates a matching visual scene per line, syncs karaoke captions, renders to 1080×1920, and posts to your platforms. In CloutHook the pipeline is script → TTS or cloned voice → AI scenes → captions → 9:16, with one token per AI scene.",
  },
  {
    q: "How do you clone your voice for narration without re-recording?",
    a: "Clone your voice once from a short reference, then every future short narrates from text in your voice — no re-recording per video. CloutHook can clone your voice or use your own ElevenLabs voice and clones, so a faceless channel keeps a consistent, human-sounding reviewer across hundreds of videos.",
  },
  {
    q: "How many affiliate shorts can you make per month on a $30 or $79 plan?",
    a: "On CloutHook's Base plan ($30, 200 tokens) a single-scene short costs about 1 token, so roughly 200 shorts a month — comfortably enough to post daily. Creator ($79, 560 tokens) adds the photoreal clone-yourself avatar and more headroom for animated or multi-scene reviews.",
  },
  {
    q: "Which platforms can you auto-post affiliate shorts to?",
    a: "CloutHook posts directly to X, Instagram, Facebook, LinkedIn, YouTube, and TikTok from inside the app — connect each account once, no download and re-upload. One faceless review can go to all six in a single pass, then you add your affiliate link in the caption or bio.",
  },
];

const faqSchema = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: FAQ.map((x) => ({
    "@type": "Question",
    name: x.q,
    acceptedAnswer: { "@type": "Answer", text: x.a },
  })),
};

export default function AiAffiliateMarketingVideosPage() {
  return (
    <div className="min-h-screen">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(blogSchema) }} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(faqSchema) }} />
      <main className="mx-auto w-full max-w-3xl px-6 py-14">
        <Link href="/" className="text-sm text-[var(--accent)] hover:underline">← CloutHook</Link>
        <h1 className="mt-4 text-3xl font-bold leading-tight text-white">
          How to Make Affiliate Marketing Videos With AI (Faceless, Fast, No Editor)
        </h1>
        <p className="mt-2 text-xs text-white/55">By the CloutHook team · June 24, 2026</p>

        <p className="mt-4 text-[15px] leading-7 text-white/70">
          <strong className="text-white/90">Yes — you can run a faceless affiliate channel that produces product and
          review shorts from a script, daily, without ever showing your face or opening an editor.</strong>{" "}
          You write a short review script, pick a voice, and AI does the rest: a voiceover, AI-generated scenes that match
          each line, and karaoke captions, all composited into a 1080×1920 vertical short — then auto-posted to your
          platforms with your affiliate link in the caption. The workflow below is the exact path from a blank page to a
          posted review, the token math on a $30 plan (enough for daily), and the six platforms you can publish to in one
          pass. It is a format worth building: short-form keeps winning attention, and recent surveys (HubSpot, 2026)
          report roughly 73% of consumers prefer short-form video to learn about a product or service — which is exactly
          what an affiliate review is.
        </p>

        <H2 id="no-face">Can you make affiliate marketing videos without showing your face?</H2>
        <P>
          <strong className="text-white/90">Yes — a faceless affiliate channel never needs you on camera.</strong> The
          value of a review short comes from the angle, the voiceover, the on-screen visuals, and the captions, not from a
          presenter&apos;s face. With an AI generator you give it a script and it builds the whole video: it narrates the
          text, generates a matching scene for each line, syncs word-by-word captions, and renders the 1080×1920 frame
          shorts platforms expect — all without a single second of filming.
        </P>
        <P>
          Faceless is the right default for affiliate marketing for a practical reason:{" "}
          <strong className="text-white/90">it scales</strong>. You can run several niche channels — one for software,
          one for kitchen gear, one for fitness — without your face tying you to any of them, and you never burn out on
          re-shoots. In{" "}
          <Link href="/" className="text-[var(--accent)] hover:underline">CloutHook</Link>, the pipeline is{" "}
          <strong className="text-white/90">script → TTS or cloned voice → AI scenes → karaoke captions → 1080×1920</strong>,
          with zero on-camera time, so the only real work left is writing a sharp script and choosing the right product.
        </P>

        <H2 id="workflow">What AI workflow produces review shorts from a script automatically?</H2>
        <P>
          <strong className="text-white/90">The whole loop is: write a script, pick a voice, let AI generate the scenes
          and captions, then auto-post.</strong> With a faceless generator like CloutHook the only manual step is the
          first one — the script — and everything after it is generated and composited for you. Here is the full path
          from blank page to a posted affiliate review.
        </P>
        <ol className="mt-4 space-y-4">
          {STEPS.map((s, i) => (
            <li key={s.title} className="rounded-xl border border-white/10 bg-white/[0.02] p-5">
              <p className="text-[15px] font-semibold text-white">
                <span className="text-[var(--accent)]">{i + 1}.</span> {s.title}
              </p>
              <p className="mt-2 text-[15px] leading-7 text-white/70">{s.body}</p>
            </li>
          ))}
        </ol>
        <P>
          A quick way to judge any affiliate-video tool is to count the manual steps it removes. The table below maps the
          AI-generated path against doing each step by hand — the gap is the time you get back, and time is the only thing
          that caps how many reviews you can post.
        </P>
        <div className="mt-4 overflow-x-auto rounded-xl border border-white/10">
          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="border-b border-white/10 bg-white/5">
                <th className="px-4 py-3 text-sm font-semibold text-white">Step</th>
                <th className="px-4 py-3 text-sm font-semibold text-white">AI (CloutHook)</th>
                <th className="px-4 py-3 text-sm font-semibold text-white">Manual / DIY</th>
              </tr>
            </thead>
            <tbody>
              {WORKFLOW_ROWS.map((r, i) => (
                <tr key={r.label} className={i % 2 ? "bg-white/[0.02]" : ""}>
                  <td className="px-4 py-3 text-[15px] text-white/80">{r.label}</td>
                  <td className="px-4 py-3 text-[15px] text-white/80">{r.ai}</td>
                  <td className="px-4 py-3 text-[15px] text-white/60">{r.manual}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs text-white/55">
          CloutHook columns reflect current product capabilities. Other AI video tools price and feature differently —
          compare current capabilities on each tool&apos;s own site. See also{" "}
          <Link href="/clouthook-vs-opusclip" className="text-[var(--accent)] hover:underline">CloutHook vs OpusClip</Link>{" "}
          and{" "}
          <Link href="/blog/best-opusclip-alternatives-2026" className="text-[var(--accent)] hover:underline">
            the best OpusClip alternatives
          </Link>.
        </p>

        <H2 id="clone-voice">How do you clone your voice for narration without re-recording?</H2>
        <P>
          <strong className="text-white/90">Clone your voice once, then narrate every future short from text.</strong>{" "}
          Instead of recording a voiceover per video, you record a short reference clip one time, and the tool reads any
          script in your voice from then on. That is what makes a faceless channel sustainable at daily volume — the
          narration step drops from minutes of recording and cleanup to zero.
        </P>
        <P>
          CloutHook can clone your voice, and it also lets you{" "}
          <strong className="text-white/90">bring your own ElevenLabs voice and clones</strong> if you already have one
          you like. Voice quality matters more in affiliate content than anywhere else: a natural, well-paced read of a
          tight script reads as a trustworthy reviewer, while a flat robotic read reads as spam — and a viewer who
          doesn&apos;t trust the voice will never tap the link. Generate a line, listen, and tune the script for flow
          before you batch out a week of reviews. Prefer a fully anonymous channel? Use a preset AI voice instead and
          skip cloning entirely.
        </P>

        <H2 id="how-many">How many shorts can you make per month on a $30 or $79 plan?</H2>
        <P>
          <strong className="text-white/90">On the Base plan ($30, 200 tokens) you can make roughly 200 single-scene
          shorts a month — enough to post every day with room to spare.</strong> CloutHook pricing is token-based with no
          per-seat fee: one token is one AI scene, an animated scene is 3, and{" "}
          <strong className="text-white/90">editing your own footage costs 0 tokens</strong>. A typical affiliate review
          built from one strong scene is about a token, so the math works out to roughly 200 reviews — well past a daily
          cadence.
        </P>
        <P>
          The three tiers, by their current published pricing:
        </P>
        <div className="mt-4 overflow-x-auto rounded-xl border border-white/10">
          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="border-b border-white/10 bg-white/5">
                <th className="px-4 py-3 text-sm font-semibold text-white">Plan</th>
                <th className="px-4 py-3 text-sm font-semibold text-white">Price</th>
                <th className="px-4 py-3 text-sm font-semibold text-white">Tokens / mo</th>
                <th className="px-4 py-3 text-sm font-semibold text-white">Best for</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="px-4 py-3 text-[15px] text-white/80">Free</td>
                <td className="px-4 py-3 text-[15px] text-white/80">$0</td>
                <td className="px-4 py-3 text-[15px] text-white/80">25</td>
                <td className="px-4 py-3 text-[15px] text-white/60">Test it, no card</td>
              </tr>
              <tr className="bg-white/[0.02]">
                <td className="px-4 py-3 text-[15px] text-white/80">Base</td>
                <td className="px-4 py-3 text-[15px] text-white/80">$30/mo</td>
                <td className="px-4 py-3 text-[15px] text-white/80">200</td>
                <td className="px-4 py-3 text-[15px] text-white/60">Daily faceless reviews</td>
              </tr>
              <tr>
                <td className="px-4 py-3 text-[15px] text-white/80">Creator</td>
                <td className="px-4 py-3 text-[15px] text-white/80">$79/mo</td>
                <td className="px-4 py-3 text-[15px] text-white/80">560</td>
                <td className="px-4 py-3 text-[15px] text-white/60">Volume + photoreal avatar</td>
              </tr>
            </tbody>
          </table>
        </div>
        <P>
          Step up to <strong className="text-white/90">Creator ($79, 560 tokens)</strong> when you want headroom for
          animated or multi-scene reviews, or when you want the photoreal clone-yourself avatar — a presenter in your own
          likeness, recorded once on your phone, that can deliver a scripted review for you. Avatars are a Creator-plan
          feature (8 tokens per video, up to 20 a month) and only ever recreate your own face and voice. For the full
          breakdown see the <Link href="/pricing" className="text-[var(--accent)] hover:underline">pricing</Link> page and
          the token details in the <Link href="/faq" className="text-[var(--accent)] hover:underline">FAQ</Link>.
        </P>

        <H2 id="platforms">Which platforms can you auto-post affiliate shorts to?</H2>
        <P>
          <strong className="text-white/90">CloutHook posts directly to six platforms: X, Instagram, Facebook, LinkedIn,
          YouTube, and TikTok.</strong> Connect each account once and publish the finished short straight from the app —
          no downloading the MP4, no re-uploading, no juggling files. One faceless review can be distributed to all six in
          a single pass, then you add your affiliate or bio link in the caption.
        </P>
        <P>
          For affiliate marketing this is the step that actually moves revenue. Distribution is the whole game — the same
          review in front of six audiences instead of one, posted consistently, is what compounds clicks into commissions.
          Removing the download-and-reupload tax is the difference between a channel that posts daily and one that stalls
          after a week. And when you are ready to earn on the tool itself, <strong className="text-white/90">CloutHook&apos;s
          own affiliate program pays 30% recurring</strong> — so a creator who reviews their stack can monetize the stack,
          too.
        </P>

        <div className="mt-12 rounded-xl border border-white/10 bg-white/5 p-6">
          <p className="text-[15px] text-white/80">
            Make your first faceless review short from a script — free. 25 tokens, no card, no camera.
          </p>
          <Link
            href="/signup"
            className="press mt-3 inline-flex min-h-11 items-center rounded-xl bg-[var(--accent)] px-5 text-sm font-bold text-black transition hover:brightness-110"
          >
            Start free
          </Link>
        </div>
      </main>
    </div>
  );
}
