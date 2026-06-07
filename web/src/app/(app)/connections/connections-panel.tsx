"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Badge, Button, Card, Input } from "@/components/ui";
import { PROVIDERS, PROVIDER_META, type Provider } from "@/lib/connections";

export type ConnStatus = { provider: string; last4: string | null; status: string; validated_at: string | null };

export function ConnectionsPanel({
  statuses,
  blotatoConnected,
}: {
  statuses: Record<string, ConnStatus>;
  blotatoConnected: boolean;
}) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {PROVIDERS.map((p) => (
        <ProviderCard key={p} provider={p} status={statuses[p]} />
      ))}
      <BlotatoCard connected={blotatoConnected} />
    </div>
  );
}

function ProviderCard({ provider, status }: { provider: Provider; status?: ConnStatus }) {
  const meta = PROVIDER_META[provider];
  const router = useRouter();
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const connected = status?.status === "active";
  const invalid = status?.status === "invalid";

  async function connect() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/connections/${provider}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ apiKey: key }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || "Failed to connect");
      setKey("");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to connect");
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    setBusy(true);
    setError(null);
    try {
      await fetch(`/api/connections/${provider}`, { method: "DELETE" });
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="flex flex-col">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="font-semibold">{meta.label}</h3>
        {connected ? (
          <Badge tone="good">Connected ·{status?.last4}</Badge>
        ) : invalid ? (
          <Badge tone="bad">Key invalid</Badge>
        ) : (
          <Badge tone="accent">Using shared quota</Badge>
        )}
      </div>
      <p className="mb-3 text-sm text-white/45">{meta.why}</p>

      {connected ? (
        <div className="mt-auto flex items-center gap-3">
          <span className="text-xs text-white/35">
            Validated{status?.validated_at ? ` ${new Date(status.validated_at).toLocaleDateString()}` : ""}
          </span>
          <Button variant="outline" onClick={disconnect} disabled={busy} className="ml-auto">
            {busy ? "…" : "Disconnect"}
          </Button>
        </div>
      ) : (
        <div className="mt-auto space-y-2">
          <Input
            type="password"
            placeholder={`Paste your ${meta.label} API key`}
            value={key}
            onChange={(e) => setKey(e.target.value)}
            autoComplete="off"
          />
          <div className="flex items-center gap-3">
            <a
              href={meta.createUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-[var(--accent)] hover:underline"
            >
              Get a key: {meta.createLabel} ↗
            </a>
            <Button onClick={connect} disabled={busy || key.trim().length < 8} className="ml-auto">
              {busy ? "Validating…" : invalid ? "Reconnect" : "Connect"}
            </Button>
          </div>
          {error && <p className="text-xs text-red-300">{error}</p>}
        </div>
      )}
    </Card>
  );
}

function BlotatoCard({ connected }: { connected: boolean }) {
  return (
    <Card className="flex flex-col">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="font-semibold">Social posting (Blotato)</h3>
        {connected ? <Badge tone="good">Connected</Badge> : <Badge tone="accent">Not connected</Badge>}
      </div>
      <p className="mb-3 text-sm text-white/45">
        Auto-post finished videos to TikTok, YouTube &amp; Instagram. Blotato handles each
        platform&apos;s login — you connect your socials inside Blotato.
      </p>
      <div className="mt-auto flex items-center gap-3">
        <a
          href="https://my.blotato.com/settings"
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-[var(--accent)] hover:underline"
        >
          Connect socials in Blotato ↗
        </a>
        <span className="ml-auto text-xs text-white/35">Add your Blotato key on a project&apos;s publish panel</span>
      </div>
    </Card>
  );
}
