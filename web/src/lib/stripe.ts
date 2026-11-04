import Stripe from "stripe";

/**
 * Server-only Stripe client. Reads STRIPE_SECRET_KEY (a Cloud Run secret) lazily so
 * the app still builds/boots when the key isn't set yet (checkout just 500s until it is).
 * NEVER import this from client components.
 */
export function getStripe(): Stripe {
  const key = process.env.STRIPE_SECRET_KEY;
  if (!key) throw new Error("STRIPE_SECRET_KEY is not set");
  return new Stripe(key);
}

/** Stripe deals in epoch seconds; our columns are timestamptz. */
export function epochToIso(seconds: number | null | undefined): string | null {
  return typeof seconds === "number" ? new Date(seconds * 1000).toISOString() : null;
}
