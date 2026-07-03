"use client";

import { useMemo } from "react";
import { loadStripe } from "@stripe/stripe-js";
import { EmbeddedCheckoutProvider, EmbeddedCheckout } from "@stripe/react-stripe-js";

/** Renders Stripe Embedded Checkout inline (the payment form lives on clouthook.com). The visual
 *  branding inside the form (logo, accent) comes from the Stripe Dashboard → Branding settings. */
export function EmbeddedCheckoutPanel({ pk, clientSecret }: { pk: string; clientSecret: string }) {
  const stripePromise = useMemo(() => loadStripe(pk), [pk]);
  return (
    <div className="overflow-hidden rounded-xl">
      <EmbeddedCheckoutProvider stripe={stripePromise} options={{ clientSecret }}>
        <EmbeddedCheckout />
      </EmbeddedCheckoutProvider>
    </div>
  );
}
