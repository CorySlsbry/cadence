import type { NextConfig } from "next";

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
};

export default nextConfig;
