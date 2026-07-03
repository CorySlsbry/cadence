import { createClient } from "@/lib/supabase/server";
import { SOCIAL, SOCIAL_PLATFORMS } from "@/lib/social-oauth";
import { ConnectionsPanel, type ConnStatus } from "./connections-panel";
import { SocialConnect, type SocialStatus } from "./social-connect";

// "Bring your own key" hub. Connecting a provider means each render bills to the user's own
// account — which is what keeps Cadence's costs flat as it scales. Status is read via the
// my_connections() / my_social_connections() RPCs (no secret ever leaves the server).
export default async function ConnectionsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const supabase = await createClient();
  const { data: rows } = await supabase.rpc("my_connections");
  const { data: socialRows } = await supabase.rpc("my_social_connections");
  const { data: profile } = await supabase.from("profiles").select("blotato_api_key_enc").maybeSingle();

  const statuses: Record<string, ConnStatus> = {};
  for (const r of (rows ?? []) as ConnStatus[]) statuses[r.provider] = r;
  const social: Record<string, SocialStatus> = {};
  for (const r of (socialRows ?? []) as SocialStatus[]) social[r.platform] = r;
  const configured = Object.fromEntries(SOCIAL_PLATFORMS.map((p) => [p, SOCIAL[p].configured()]));
  const noticePlatform = typeof sp.social === "string" ? sp.social : null;
  const noticeStatus = typeof sp.status === "string" ? sp.status : null;

  return (
    <div className="space-y-10">
      <div>
        <h1 className="text-2xl font-bold">Connections</h1>
        <p className="mt-1 max-w-2xl text-sm text-white/45">
          Connect your own provider accounts so AI generation runs on <em>your</em> credits, not a
          shared pool. Keys are validated, encrypted, and never shown again. Leave a provider
          unconnected to use CloutHook&apos;s included quota.
        </p>
      </div>
      <ConnectionsPanel statuses={statuses} blotatoConnected={!!profile?.blotato_api_key_enc} />
      <SocialConnect
        social={social}
        configured={configured}
        notice={noticePlatform && noticeStatus ? { platform: noticePlatform, status: noticeStatus } : null}
      />
    </div>
  );
}
