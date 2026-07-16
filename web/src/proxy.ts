import { NextResponse, type NextRequest } from "next/server";
import { updateSession } from "@/lib/supabase/middleware";

// Security headers set here (not next.config `headers()`, which doesn't emit reliably under
// output:"standalone" on Cloud Run). frame-ancestors 'none' + X-Frame-Options DENY stop
// clickjacking; camera/mic allowed for `self` (the in-browser recorder needs them).
const SECURITY_HEADERS: Record<string, string> = {
  "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
  "X-Frame-Options": "DENY",
  "Content-Security-Policy": "frame-ancestors 'none'",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Permissions-Policy": "camera=(self), microphone=(self), geolocation=(), browsing-topics=()",
};
function harden(res: NextResponse): NextResponse {
  for (const [k, v] of Object.entries(SECURITY_HEADERS)) res.headers.set(k, v);
  return res;
}

// Next.js 16: "Middleware" is now "Proxy" (proxy.ts, exporting `proxy`).
export async function proxy(request: NextRequest) {
  // Canonical host. The Cloud Run default domain (*.run.app) serves the whole site, and any page
  // loaded there bakes that origin into Supabase auth emails + OAuth redirectTo via
  // window.location.origin. 308 it to clouthook.com so the public origin is always canonical
  // (leaves clouthook.com and localhost dev untouched; container health probes don't carry a
  // *.run.app Host header, so they're unaffected).
  const host = request.headers.get("host") ?? "";
  if (host.endsWith(".run.app")) {
    return harden(NextResponse.redirect(
      new URL(request.nextUrl.pathname + request.nextUrl.search, "https://clouthook.com"),
      308,
    ));
  }
  return harden(await updateSession(request));
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|mp4)$).*)",
  ],
};
