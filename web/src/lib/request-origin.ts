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
  if (host && !/^(0\.0\.0\.0|localhost|127\.)/.test(host)) return `${proto}://${host}`;
  return new URL(request.url).origin;
}
