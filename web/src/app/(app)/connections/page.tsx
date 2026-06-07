import { createClient } from "@/lib/supabase/server";
import { ConnectionsPanel, type ConnStatus } from "./connections-panel";

// "Bring your own key" hub. Connecting a provider means each render bills to the user's own
// account — which is what keeps Cadence's costs flat as it scales. Status is read via the
// my_connections() RPC (status/last4 only; the encrypted key never leaves the server).
export default async function ConnectionsPage() {
  const supabase = await createClient();
  const { data: rows } = await supabase.rpc("my_connections");
  const { data: profile } = await supabase
    .from("profiles")
    .select("blotato_api_key")
    .maybeSingle();

  const statuses: Record<string, ConnStatus> = {};
  for (const r of (rows ?? []) as ConnStatus[]) statuses[r.provider] = r;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Connections</h1>
        <p className="mt-1 max-w-2xl text-sm text-white/45">
          Connect your own provider accounts so AI generation runs on <em>your</em> credits, not a
          shared pool. Keys are validated, encrypted, and never shown again. Leave a provider
          unconnected to use Cadence&apos;s included quota.
        </p>
      </div>
      <ConnectionsPanel statuses={statuses} blotatoConnected={!!profile?.blotato_api_key} />
    </div>
  );
}
