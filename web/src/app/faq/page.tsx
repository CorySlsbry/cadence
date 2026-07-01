import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "CloutHook FAQ — AI short-form video, avatars, pricing",
  description:
    "Answers about CloutHook: how record-once editing works, faceless videos, the photoreal AI avatar, the token system, pricing, publishing, and privacy.",
};

const FAQ: { section: string; qa: { q: string; a: string }[] }[] = [
  {
    section: "Getting started",
    qa: [
      { q: "What is CloutHook?", a: "CloutHook is a premium AI studio for short-form video. You record one raw take and it auto-edits a studio-grade 1080×1920 vertical short — cleaning the audio, cutting filler, adding captions and AI b-roll, and stitching it to match a reference's style. It also makes faceless videos and photoreal AI avatars." },
      { q: "How is CloutHook different from OpusClip?", a: "OpusClip is built mainly to slice a long video into short clips. CloutHook does that too, but it also turns a single fresh recording into a finished short, generates faceless videos from a script, and can render a photoreal avatar of you. It is priced by tokens with no per-seat fee. See our full CloutHook vs OpusClip comparison." },
      { q: "Do I need any editing experience?", a: "No. The whole point is that you record once and CloutHook handles the edit — silence and filler removal, captions, b-roll, reframing, and stitching. There is no timeline to scrub. If you can hit record, you can ship a polished short." },
      { q: "Is there a free plan?", a: "Yes. The Free plan includes 25 tokens a month at no cost and no credit card to start, so you can make real videos before paying. Paid plans (Base and Creator) add more monthly tokens and unlock premium features like the photoreal avatar. See the pricing page for details." },
    ],
  },
  {
    section: "Features",
    qa: [
      { q: "How does record-once editing work?", a: "You talk straight through your mistakes. CloutHook strips silence, removes filler words and bad takes, adds frame-accurate captions, drops in AI b-roll on the beat, and renders a clean vertical cut — no manual editing. You get a studio-grade short in minutes instead of hours." },
      { q: "Can CloutHook make faceless videos?", a: "Yes. Give it a script or topic and CloutHook generates a faceless video end to end: a voiceover (TTS or your cloned voice), AI-generated scenes that match your topic, and karaoke-style captions. You never have to appear on camera." },
      { q: "What is the AI b-roll feature?", a: "AI b-roll is on-topic cutaway footage generated from what you are talking about and dropped in at the right moments. Instead of hunting for stock clips, CloutHook creates relevant scenes automatically so the video stays visually engaging while you speak." },
      { q: "Does it auto-reframe horizontal video to vertical?", a: "Yes. Upload a 16:9 source — a webcam recording, podcast, or screen capture — and CloutHook tracks the speaker's face and reframes to 9:16 so they stay centered, instead of a blind center crop. It only applies to landscape footage." },
      { q: "Can it clip a long video into shorts?", a: "Yes. Upload a long video — a podcast, stream, or webinar — and CloutHook finds the strongest moments, scores them, and renders each as a ready-to-post short, best clips first. You pick the keepers." },
      { q: "What formats does CloutHook output?", a: "CloutHook renders 1080×1920 (9:16) vertical video at up to 60fps — the format every short-form platform wants. Videos are produced in the cloud and ready to download or publish in minutes." },
    ],
  },
  {
    section: "Avatars & voice",
    qa: [
      { q: "Can CloutHook make an AI avatar video of me?", a: "Yes. The photoreal avatar clones you from a short recording (or a photo) and can speak any script in your likeness — for full talking-head shorts or as a presenter inside faceless videos. Avatars are a Creator-plan feature and only ever recreate your own face and voice, with on-camera consent required." },
      { q: "Can I record my avatar on my phone?", a: "Yes. In the avatar studio, choose “Phone,” scan the QR code with your phone, and record your reference clip at full phone-camera quality. It uploads straight to your account over a secure, single-use link. Phone footage gives a noticeably sharper avatar than a laptop webcam." },
      { q: "Can I clone my voice?", a: "Yes. You can bring your own ElevenLabs key and clone your voice from a short sample, then narrate any video in it — including faceless videos and avatar renders. You can also use built-in preset voices if you prefer not to clone." },
      { q: "Will you use my face or voice to train AI?", a: "Never. Your uploads, likeness, and voice are used only to produce your videos — never to train AI models and never shown to other users. Avatar and voice features are built strictly for your own likeness, with consent rules spelled out in our Terms." },
    ],
  },
  {
    section: "Pricing & tokens",
    qa: [
      { q: "How does the token system work?", a: "Tokens meter AI generation. One token equals one AI scene; an animated scene costs three; a photoreal avatar video costs eight (Creator plan, up to 20 a month). Plain edits of your own footage cost nothing. Each plan includes a monthly token allowance — see the pricing page." },
      { q: "What does an avatar video cost?", a: "A photoreal avatar video costs 8 tokens and is available on the Creator plan, with a fair-use limit of 20 avatar videos per month. At Creator pricing that is well under the cost of a comparable HeyGen-style render, and you are not paying per seat." },
      { q: "Are there per-seat fees?", a: "No. CloutHook charges by token usage, not by user seat. You pay for the AI generation you actually use, which keeps the cost predictable for solo creators and small teams alike." },
      { q: "How do I cancel?", a: "You can cancel anytime from your account billing settings; your plan stays active until the end of the current period. There is no long-term contract. Affiliate commissions, if you are in the program, follow the terms on the affiliate page." },
    ],
  },
  {
    section: "Publishing & privacy",
    qa: [
      { q: "Does CloutHook post directly to TikTok and other platforms?", a: "Yes. You can connect X, Instagram, Facebook, LinkedIn, YouTube, and TikTok and publish a finished video with its caption straight from CloutHook. We use those connections only to post what you explicitly tell us to — we never read your feeds, contacts, or messages." },
      { q: "How long does a render take?", a: "Most shorts render in a few minutes. A photoreal avatar render takes longer on its first run while the model warms up. You can leave the page — the video keeps rendering in the cloud and lands in your Library when it is done." },
      { q: "What AI models does CloutHook use?", a: "CloutHook runs its own GPU generation stack for images, motion, and voice, with Google Gemini for scripting and scene planning, and optional ElevenLabs for voice. If you bring your own keys, your generations run on your accounts. Details are in our Privacy Policy." },
      { q: "Is my data private?", a: "Yes. Your content is stored privately, processed only to make your videos, and never sold or used to train AI. You can delete your content in the app anytime, and request full account deletion by email. See the Privacy Policy for the specifics, including GDPR and CCPA rights." },
    ],
  },
];

const faqSchema = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: FAQ.flatMap((s) =>
    s.qa.map((item) => ({
      "@type": "Question",
      name: item.q,
      acceptedAnswer: { "@type": "Answer", text: item.a },
    })),
  ),
};

export default function FaqPage() {
  return (
    <div className="min-h-screen">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(faqSchema) }} />
      <main className="mx-auto w-full max-w-3xl px-6 py-14">
        <Link href="/" className="text-sm text-[var(--accent)] hover:underline">← CloutHook</Link>
        <h1 className="mt-4 text-3xl font-bold text-white">Frequently asked questions</h1>
        <p className="mt-2 text-[15px] leading-7 text-white/70">
          How CloutHook turns one raw take into a studio-grade short — features, avatars, tokens,
          publishing, and privacy. Still stuck?{" "}
          <a href="mailto:support@Neuron-HQ.com" className="text-[var(--accent)] hover:underline">Email us</a>.
        </p>

        {FAQ.map((s) => (
          <section key={s.section} className="mt-12">
            <h2 className="text-xs font-semibold uppercase tracking-[0.18em] text-white/55">{s.section}</h2>
            {s.qa.map((item) => (
              <div key={item.q} className="mt-7">
                <h3 className="text-base font-semibold text-white">{item.q}</h3>
                <p className="mt-2 text-[15px] leading-7 text-white/70">{item.a}</p>
              </div>
            ))}
          </section>
        ))}

        <div className="mt-14 rounded-xl border border-white/10 bg-white/5 p-6">
          <p className="text-[15px] text-white/80">Ready to make your first short?</p>
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
