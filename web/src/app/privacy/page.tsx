import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Privacy Policy — CloutHook",
  description: "How CloutHook collects, uses, and protects your data.",
};

const EFFECTIVE = "June 11, 2026";
const CONTACT = "cory@salisburybookkeeping.com";

function H2({ id, children }: { id?: string; children: React.ReactNode }) {
  return <h2 id={id} className="mt-10 scroll-mt-24 text-lg font-semibold text-white">{children}</h2>;
}

export default function PrivacyPage() {
  return (
    <div className="min-h-screen">
      <main className="mx-auto w-full max-w-3xl px-6 py-14">
        <Link href="/" className="text-sm text-[var(--accent)] hover:underline">← CloutHook</Link>
        <h1 className="mt-4 text-3xl font-bold text-white">Privacy Policy</h1>
        <p className="mt-2 text-sm text-white/45">Effective {EFFECTIVE}</p>

        <div className="mt-8 space-y-4 text-[15px] leading-7 text-white/70">
          <p>
            CloutHook (&quot;we&quot;, &quot;us&quot;) is a video creation service operated by Salisbury Bookkeeping
            &amp; Accounting Services LLC. This policy explains what we collect, why, and the controls you have.
            The short version: your content is yours, we collect the minimum needed to run the product, and we
            never sell your data.
          </p>

          <H2>What we collect</H2>
          <p><strong className="text-white/90">Account data.</strong> Email address, name, and a hashed password —
            or, if you sign in with Google, the email and name Google shares. We never see your Google password.</p>
          <p><strong className="text-white/90">Content you upload.</strong> Videos you record or upload, photos you
            provide for avatars, voice samples you submit for cloning, scripts, and brand assets. This content is
            stored privately, processed only to produce your videos, and never used to train AI models or shown to
            other users.</p>
          <p><strong className="text-white/90">Generated content.</strong> The videos, scenes, voiceovers, captions,
            and avatar character descriptions our pipeline produces for you.</p>
          <p><strong className="text-white/90">Billing data.</strong> Payments are processed by Stripe. We store your
            plan, token balance, and transaction records — never your card number.</p>
          <p><strong className="text-white/90">Social account tokens.</strong> If you connect a social account
            (X, Instagram, Facebook, LinkedIn, YouTube, TikTok), we store the access tokens encrypted (AES-256-GCM)
            and use them for exactly one thing: publishing the videos you explicitly tell us to post. We do not read
            your feeds, contacts, or messages.</p>
          <p><strong className="text-white/90">Usage data.</strong> Render history, feature usage, and standard
            server logs (IP address, browser type) used for security, debugging, and capacity planning.</p>

          <H2>How we use it</H2>
          <p>To run CloutHook: generate your videos, meter tokens, process payments, publish to social platforms you
            connect, provide support, and keep the service secure. If you bring your own API keys (e.g. Gemini or
            ElevenLabs), we store them encrypted and use them solely to run your generations on your accounts.</p>

          <H2>What we never do</H2>
          <p>We do not sell or rent your personal data. We do not use your uploads, likeness, or voice to train AI
            models. We do not post to your social accounts without an explicit action from you. Avatar and voice
            features are built for your own likeness and voice — see our <Link href="/terms" className="text-[var(--accent)] hover:underline">Terms</Link> for
            the consent rules.</p>

          <H2>Service providers</H2>
          <p>We rely on a small set of processors to operate: Supabase (database, authentication, storage),
            Google Cloud (hosting, AI generation), Stripe (payments), Google Gemini (script and scene generation),
            and — when you connect them — ElevenLabs and the social platforms listed above. Each receives only what
            it needs to perform its function.</p>

          <H2>Cookies</H2>
          <p>We use essential cookies only: your sign-in session and security tokens. No advertising trackers.</p>

          <H2 id="data-deletion">Data deletion</H2>
          <p>You can delete your content (projects, renders, avatars, voice samples) inside the app at any time.
            To delete your entire account and all associated data, email{" "}
            <a href={`mailto:${CONTACT}?subject=Delete my CloutHook account`} className="text-[var(--accent)] hover:underline">{CONTACT}</a>{" "}
            with the subject &quot;Delete my CloutHook account&quot; from your account email. We complete deletion
            within 30 days and confirm by email. Disconnecting a social account in Connections immediately deletes
            its stored tokens; you can also revoke CloutHook from the platform&apos;s own security settings.</p>

          <H2>Data retention &amp; security</H2>
          <p>We keep your data while your account is active. Backups age out within 30 days of deletion. Secrets and
            tokens are encrypted at rest; transport is TLS everywhere; access is least-privilege.</p>

          <H2>Your rights</H2>
          <p>Depending on where you live (including under GDPR and CCPA), you may have rights to access, correct,
            export, or delete your personal data, and to object to processing. Email{" "}
            <a href={`mailto:${CONTACT}`} className="text-[var(--accent)] hover:underline">{CONTACT}</a> and we&apos;ll
            honor them. We don&apos;t discriminate against you for exercising them.</p>

          <H2>Children</H2>
          <p>CloutHook is not directed to children under 13 (or the minimum age in your jurisdiction), and we do not
            knowingly collect their data.</p>

          <H2>Changes</H2>
          <p>If we make material changes to this policy, we&apos;ll notify you by email or in-app before they take
            effect. The current version always lives at clouthook.com/privacy.</p>

          <H2>Contact</H2>
          <p>Questions? Email <a href={`mailto:${CONTACT}`} className="text-[var(--accent)] hover:underline">{CONTACT}</a>.</p>
        </div>
      </main>
    </div>
  );
}
