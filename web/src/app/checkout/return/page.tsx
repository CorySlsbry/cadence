import { redirect } from "next/navigation";
import { getStripe } from "@/lib/stripe";

export const dynamic = "force-dynamic";

/**
 * Stripe returns here after Embedded Checkout completes (return_url). We confirm the session and
 * route the buyer onward — the actual token/plan grant is done by the checkout.session.completed
 * webhook, so this is just UX (the dashboard reflects the change once the webhook lands).
 */
export default async function CheckoutReturn({
  searchParams,
}: {
  searchParams: Promise<{ session_id?: string }>;
}) {
  const { session_id } = await searchParams;
  if (!session_id) redirect("/dashboard");

  let status = "";
  let mode = "";
  try {
    const s = await getStripe().checkout.sessions.retrieve(session_id);
    status = s.status ?? "";
    mode = s.mode ?? "";
  } catch {
    redirect("/dashboard");
  }

  if (status === "complete") {
    redirect(mode === "payment" ? "/dashboard?topup=1" : "/dashboard?upgraded=1");
  }
  if (status === "open") {
    redirect("/premium?canceled=1"); // buyer closed the form without paying
  }
  redirect("/dashboard");
}
