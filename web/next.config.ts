import type { NextConfig } from "next";

// Security headers applied to every response. `frame-ancestors 'none'` + X-Frame-Options: DENY stop
// clickjacking of the app (nobody can iframe clouthook.com); this does NOT restrict what WE embed,
// so the Stripe Embedded Checkout iframe still loads. camera/microphone are allowed for `self`
// because the in-browser recorder needs them; everything else in Permissions-Policy is denied.
const SECURITY_HEADERS = [
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(self), microphone=(self), geolocation=(), browsing-topics=()" },
];

const nextConfig: NextConfig = {
  // Emit a self-contained server (.next/standalone/server.js) for a minimal Cloud Run
  // image. The Dockerfile copies public/ and .next/static/ in manually (standalone
  // does not bundle them — see next docs output.md).
  output: "standalone",
  // Pin the file-tracing root to THIS app dir. Without it, Next infers a parent dir
  // from stray lockfiles and nests server.js under .next/standalone/<abs/path>/server.js,
  // which breaks the Docker COPY. Build always runs from the web/ dir (npm here; Docker
  // WORKDIR /app), so cwd is the correct root.
  outputFileTracingRoot: process.cwd(),
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
};

export default nextConfig;
