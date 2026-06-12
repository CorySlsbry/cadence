"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Badge, Button, Card } from "@/components/ui";

export type SocialStatus = { platform: string; username: string | null; expires_at: string | null };

const META: Record<string, { label: string; why: string }> = {
  x: { label: "X", why: "Post your videos straight to X." },
  youtube: { label: "YouTube", why: "Publish Shorts straight to your channel." },
  instagram: { label: "Instagram", why: "Publish Reels to your Instagram business account." },
  facebook: { label: "Facebook", why: "Post videos to a Facebook Page you manage." },
  linkedin: { label: "LinkedIn", why: "Share videos to your LinkedIn feed." },
  tiktok: { label: "TikTok", why: "Post videos directly to your TikTok." },
};
const ORDER = ["x", "youtube", "instagram", "facebook", "linkedin", "tiktok"];

export function SocialConnect({
  social,
  configured,
  notice,
}: {
  social: Record<string, SocialStatus>;
  configured: Record<string, boolean>;
  notice: { platform: string; status: string } | null;
}) {
  return (
    <div className="space-y-3">
      <h2 className="text-lg font-semibold">Social accounts</h2>
      <p className="text-sm text-white/45">
        Connect your own accounts to publish directly — separate from Blotato, and free.
      </p>
      {notice && (
        <div
          className={`rounded-xl border p-3 text-sm ${
            notice.status === "connected"
              ? "border-green-500/20 bg-green-500/5 text-green-300"
              : "border-amber-500/20 bg-amber-500/5 text-amber-200"
          }`}
        >
          {notice.status === "connected"
            ? `${META[notice.platform]?.label ?? notice.platform} connected.`
            : `${META[notice.platform]?.label ?? notice.platform}: ${notice.status.replace(/_/g, " ")}`}
        </div>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        {ORDER.map((p) => (
          <SocialCard key={p} platform={p} status={social[p]} configured={!!configured[p]} />
        ))}
      </div>
    </div>
  );
}

function SocialCard({ platform, status, configured }: { platform: string; status?: SocialStatus; configured: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const meta = META[platform];
  const connected = !!status;

  async function disconnect() {
    setBusy(true);
    await fetch(`/api/social/oauth/${platform}`, { method: "DELETE" });
    router.refresh();
    setBusy(false);
  }

  return (
    <Card className="flex flex-col">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="font-semibold">{meta.label}</h3>
        {connected ? (
          <Badge tone="good">@{status?.username || "connected"}</Badge>
        ) : configured ? (
          <Badge tone="accent">Not connected</Badge>
        ) : (
          <Badge tone="bad">Setup needed</Badge>
        )}
      </div>
      <p className="mb-3 text-sm text-white/45">{meta.why}</p>
      <div className="mt-auto">
        {connected ? (
          <Button variant="outline" onClick={disconnect} disabled={busy}>
            {busy ? "…" : "Disconnect"}
          </Button>
        ) : configured ? (
          <a
            href={`/api/social/oauth/${platform}/start`}
            className="inline-flex items-center justify-center rounded-xl bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white hover:opacity-90"
          >
            Connect {meta.label}
          </a>
        ) : (
          <span className="text-xs text-white/35">Awaiting app credentials (admin setup).</span>
        )}
      </div>
    </Card>
  );
}
