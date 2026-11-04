// Best-effort wake of the render worker so a freshly-queued job starts in seconds instead of
// waiting up to ~60s for the every-minute drain scheduler. The worker is a PRIVATE Cloud Run
// service (IAM-invoker only), so we mint an OIDC identity token for it from the metadata server
// (the web SA has run.invoker on the worker) — mirroring how the scheduler authenticates.
//
// Safe + idempotent: /process just drains the queue (claims are atomic via FOR UPDATE SKIP
// LOCKED), so a duplicate or failed poke is harmless — the Cloud Scheduler tick is the fallback.
export async function pokeWorker(): Promise<void> {
  const base = (
    process.env.CADENCE_WORKER_URL || "https://cadence-worker-840472456279.us-west1.run.app"
  ).replace(/\/$/, "");
  try {
    let authHeader: Record<string, string> = {};
    try {
      // Cloud Run / GCE metadata server: identity token with audience = the worker's URL.
      const tok = await fetch(
        `http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=${encodeURIComponent(base)}`,
        { headers: { "Metadata-Flavor": "Google" }, signal: AbortSignal.timeout(1500) },
      );
      if (tok.ok) authHeader = { Authorization: `Bearer ${(await tok.text()).trim()}` };
    } catch {
      /* no metadata server (local/dev) — fall through to an unauthenticated attempt */
    }
    await fetch(`${base}/process`, {
      method: "POST",
      headers: authHeader,
      signal: AbortSignal.timeout(3500),
    });
  } catch {
    /* the every-minute scheduler picks it up regardless */
  }
}
