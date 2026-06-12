import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Terms of Service — CloutHook",
  description: "The terms that govern your use of CloutHook.",
};

const EFFECTIVE = "June 11, 2026";
const CONTACT = "support@Neuron-HQ.com";

function H2({ children }: { children: React.ReactNode }) {
  return <h2 className="mt-10 text-lg font-semibold text-white">{children}</h2>;
}

export default function TermsPage() {
  return (
    <div className="min-h-screen">
      <main className="mx-auto w-full max-w-3xl px-6 py-14">
        <Link href="/" className="text-sm text-[var(--accent)] hover:underline">← CloutHook</Link>
        <h1 className="mt-4 text-3xl font-bold text-white">Terms of Service</h1>
        <p className="mt-2 text-sm text-white/45">Effective {EFFECTIVE}</p>

        <div className="mt-8 space-y-4 text-[15px] leading-7 text-white/70">
          <p>
            These terms are an agreement between you and Salisbury Bookkeeping &amp; Accounting Services LLC
            (&quot;CloutHook&quot;, &quot;we&quot;). By creating an account or using clouthook.com, you agree to them.
          </p>

          <H2>The service</H2>
          <p>CloutHook turns recordings, scripts, and topics into finished short-form videos: editing, captions,
            AI-generated scenes and voiceovers, avatars, and direct publishing to social platforms you connect.
            Features evolve; we may add, change, or retire capabilities.</p>

          <H2>Your account</H2>
          <p>You must be at least 13 (or the minimum age where you live) and provide accurate information. You are
            responsible for activity under your account and for keeping your credentials secure.</p>

          <H2>Tokens, plans &amp; billing</H2>
          <p>Paid plans and token packs are billed through Stripe. Tokens meter AI generation (e.g. one token per AI
            scene; animated scenes cost more) and are consumed when work is performed. Monthly plan tokens refresh
            each billing cycle and do not roll over; purchased top-up packs do not expire while your account is
            active. Because tokens are consumed by real compute, completed generations are non-refundable; if a
            render fails on our side, the tokens are not charged or are restored. You can cancel anytime and keep
            access through the end of the billing period.</p>

          <H2>Your content &amp; license to us</H2>
          <p>You own what you upload and what CloutHook generates for you, to the maximum extent permitted by law.
            You grant us a limited license to host and process your content solely to operate the service — we don&apos;t
            use it to train models and we don&apos;t publish anything without your explicit action.</p>

          <H2>Likeness, voice &amp; avatars — consent rules</H2>
          <p>The avatar and voice features exist so creators can use <em>their own</em> face and voice. You may only
            upload photos, video, or voice samples of yourself, or of a person who has given you explicit, verifiable
            consent. Creating avatars, clones, or content that impersonates a real person without their consent is
            prohibited and grounds for immediate termination. You are solely responsible for the rights to any
            material you upload.</p>

          <H2>Acceptable use</H2>
          <p>Don&apos;t use CloutHook to create or distribute content that is illegal, infringing, deceptive
            (including undisclosed deepfakes of real people), harassing, hateful, sexually exploitative, or that
            violates the rules of the platforms you publish to. Don&apos;t probe, overload, scrape, or resell the
            service, and don&apos;t attempt to access other users&apos; data.</p>

          <H2>Social publishing</H2>
          <p>When you connect a social account, you authorize CloutHook to publish the specific videos you choose to
            post. Your relationship with each platform is governed by that platform&apos;s own terms, and we are not
            responsible for their moderation, reach, or availability decisions.</p>

          <H2>Bring-your-own-key services</H2>
          <p>If you connect your own API keys (e.g. Gemini, ElevenLabs), usage on those keys is billed by those
            providers under their terms, and you&apos;re responsible for complying with them.</p>

          <H2>Disclaimers</H2>
          <p>CloutHook is provided &quot;as is.&quot; AI output can be wrong, weird, or imperfect — review your videos
            before publishing. To the fullest extent permitted by law, we disclaim implied warranties and are not
            liable for indirect, incidental, or consequential damages. Our total liability for any claim is capped at
            the amount you paid us in the twelve months before the claim.</p>

          <H2>Termination</H2>
          <p>You can stop using CloutHook anytime; deleting your account removes your data per our{" "}
            <Link href="/privacy" className="text-[var(--accent)] hover:underline">Privacy Policy</Link>. We may
            suspend or terminate accounts that violate these terms, with notice where practicable.</p>

          <H2>Copyright complaints</H2>
          <p>If you believe content on CloutHook infringes your copyright, email{" "}
            <a href={`mailto:${CONTACT}?subject=DMCA notice`} className="text-[var(--accent)] hover:underline">{CONTACT}</a>{" "}
            with the work, the allegedly infringing material, your contact information, and a good-faith statement.
            We respond to valid notices, including by removing content and terminating repeat infringers.</p>

          <H2>Governing law &amp; changes</H2>
          <p>These terms are governed by the laws of the State of Utah, USA, excluding conflict-of-law rules. If we
            make material changes, we&apos;ll notify you before they take effect; continued use after that is
            acceptance. The current version always lives at clouthook.com/terms.</p>

          <H2>Contact</H2>
          <p>Questions about these terms: <a href={`mailto:${CONTACT}`} className="text-[var(--accent)] hover:underline">{CONTACT}</a>.</p>
        </div>
      </main>
    </div>
  );
}
