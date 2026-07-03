import { redirect } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { createCheckoutSessionFor, createPackCheckoutSessionFor } from "@/lib/checkout";
import { EmbeddedCheckoutPanel } from "@/components/embedded-checkout-panel";

export const dynamic = "force-dynamic";

const SITE = process.env.NEXT_PUBLIC_SITE_URL || "https://clouthook.com";

/**
 * On-site checkout. Renders Stripe Embedded Checkout inline (branded CloutHook shell). When the
 * publishable key isn't configured yet it transparently falls back to Stripe's hosted page, so
 * live payments never break during the migration.
 */
export default async function CheckoutPage({
  searchParams,
}: {
  searchParams: Promise<{ plan?: string; pack?: string }>;
}) {
  const sp = await searchParams;
  const plan = sp.plan === "base" || sp.plan === "creator" ? sp.plan : null;
  const pack = sp.pack || null;
  if (!plan && !pack) redirect("/premium#pricing");

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect(`/signup${plan ? `?plan=${plan}` : ""}`);

  const pk = process.env.STRIPE_PUBLISHABLE_KEY;
  const embedded = !!pk;

  let session: Awaited<ReturnType<typeof createCheckoutSessionFor>>;
  try {
    session = plan
      ? await createCheckoutSessionFor(user, plan, SITE, embedded)
      : await createPackCheckoutSessionFor(user, pack!, SITE, embedded);
  } catch {
    redirect("/premium?checkout_error=1");
  }

  // No publishable key yet → hosted fallback (payments keep working).
  if (!embedded) {
    redirect(session.url ?? "/premium?checkout_error=1");
  }

  const label = plan ? `${plan[0].toUpperCase()}${plan.slice(1)} plan` : "Token pack";

  return (
    <main className="min-h-screen bg-[#0a0a12] text-white">
      <div className="mx-auto max-w-2xl px-5 py-10">
        <Link href="/premium#pricing" className="text-sm text-white/50 transition hover:text-white">
          ← Back to plans
        </Link>
        <div className="mt-6 flex items-baseline gap-2">
          <span className="text-xl font-extrabold">
            Clout<span className="text-[#9e96ff]">Hook</span>
          </span>
          <span className="text-xs font-medium text-white/40">by Neuron</span>
          <span className="text-white/30">·</span>
          <span className="text-sm text-white/70">{label}</span>
        </div>
        <div className="mt-6 rounded-2xl border border-white/10 bg-white p-1 shadow-2xl">
          <EmbeddedCheckoutPanel pk={pk!} clientSecret={session.client_secret!} />
        </div>
        <p className="mt-4 text-center text-xs text-white/40">Secured by Stripe · cancel anytime</p>
      </div>
    </main>
  );
}
