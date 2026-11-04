import { createAdminClient } from "@/lib/supabase/admin";
import PhoneRecorder from "./recorder";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
// Don't leak the capability token in a Referer header to any outbound resource.
export const metadata = { referrer: "no-referrer" as const };

// Public mobile capture page. Validates the capability token server-side (via the service role)
// BEFORE rendering the recorder, and never exposes the owning user_id to the client.
export default async function Page({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const admin = createAdminClient();
  const { data: s } = await admin
    .from("phone_link_sessions")
    .select("status, expires_at")
    .eq("token", token)
    .maybeSingle();

  const valid = !!s && s.status === "pending" && new Date(s.expires_at).getTime() > Date.now();
  if (!valid) {
    const used = s?.status === "uploaded" || s?.status === "consumed";
    return (
      <main className="min-h-dvh bg-neutral-950 text-neutral-100 flex flex-col items-center justify-center gap-3 px-6 text-center">
        <div className="text-4xl">{used ? "✓" : "⏳"}</div>
        <h1 className="text-xl font-semibold">{used ? "Already recorded" : "Link expired"}</h1>
        <p className="text-neutral-400 max-w-xs">
          {used
            ? "This recording link was already used. Head back to CloutHook on your computer to finish your avatar."
            : "Generate a fresh QR code in CloutHook on your computer, then scan it again."}
        </p>
      </main>
    );
  }

  return <PhoneRecorder token={token} />;
}
