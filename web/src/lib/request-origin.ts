/**
 * The public origin for redirects built inside route handlers. On Cloud Run,
 * `new URL(request.url).origin` is the container's internal listen address
 * (https://0.0.0.0:8080) — redirecting users there is ERR_ADDRESS_INVALID.
 * Resolve from the canonical env first, then proxy headers, then the raw URL.
 */
export function publicOrigin(request: Request): string {
  const env = process.env.NEXT_PUBLIC_SITE_URL;
  if (env) return env.replace(/\/$/, "");
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
  const proto = request.headers.get("x-forwarded-proto") ?? "https";
  // A real forwarded client host (incl. localhost for dev) is trustworthy; the
  // container's internal 0.0.0.0 listen address is not.
  if (host && !/^0\.0\.0\.0/.test(host)) return `${proto}://${host}`;
  // Last resort: the canonical public site — NEVER the raw request origin, which on
  // Cloud Run is https://0.0.0.0:8080 (ERR_ADDRESS_INVALID for users, and off-brand).
  return "https://clouthook.com";
}
