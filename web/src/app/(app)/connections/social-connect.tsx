"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Badge, Card } from "@/components/ui";

export type SocialStatus = {
  id: string;
  platform: string;
  username: string | null;
  label: string | null;
  expires_at: string | null;
};

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
  maxAccountsPerPlatform,
  accountLimit,
  notice,
}: {
  social: Record<string, SocialStatus[]>;
  configured: Record<string, boolean>;
  maxAccountsPerPlatform: number;
  accountLimit: boolean;
  notice: { platform: string; status: string } | null;
}) {
  return (
    <div className="space-y-3">
      <h2 className="text-lg font-semibold">Social accounts</h2>
      <p className="text-sm text-white/45">
        Connect your own accounts to publish directly — separate from Blotato, and free.
        {maxAccountsPerPlatform > 1 && ` Your plan allows up to ${maxAccountsPerPlatform} accounts per platform.`}
      </p>
      {accountLimit && (
        <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-3 text-sm text-amber-200">
          You&apos;ve reached your plan&apos;s account limit for that platform.{" "}
          <Link href="/premium" className="font-medium underline underline-offset-2">Upgrade</Link> to connect more.
        </div>
      )}
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
          <SocialCard
            key={p}
            platform={p}
            accounts={social[p] ?? []}
            configured={!!configured[p]}
            maxAccounts={maxAccountsPerPlatform}
          />
        ))}
      </div>
    </div>
  );
}

function SocialCard({
  platform,
  accounts,
  configured,
  maxAccounts,
}: {
  platform: string;
  accounts: SocialStatus[];
  configured: boolean;
  maxAccounts: number;
}) {
  const router = useRouter();
  const [busyId, setBusyId] = useState<string | null>(null);
  const meta = META[platform];
  const count = accounts.length;
  const atCap = count >= maxAccounts;

  async function disconnect(id: string) {
    setBusyId(id);
    await fetch(`/api/social/oauth/${platform}?id=${encodeURIComponent(id)}`, { method: "DELETE" });
    router.refresh();
    setBusyId(null);
  }

  return (
    <Card className="flex flex-col">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="font-semibold">{meta.label}</h3>
        {count > 0 ? (
          <Badge tone="good">{count === 1 ? "Connected" : `${count} accounts`}</Badge>
        ) : configured ? (
          <Badge tone="accent">Not connected</Badge>
        ) : (
          <Badge tone="bad">Setup needed</Badge>
        )}
      </div>
      <p className="mb-3 text-sm text-white/45">{meta.why}</p>

      {count > 0 && (
        <ul className="mb-3 space-y-1.5">
          {accounts.map((a) => (
            <li
              key={a.id}
              className="flex items-center justify-between gap-2 rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2"
            >
              <span className="min-w-0 truncate text-sm text-white/80">
                @{a.label || a.username || "connected"}
              </span>
              <button
                type="button"
                onClick={() => disconnect(a.id)}
                disabled={busyId === a.id}
                className="press shrink-0 text-xs font-medium text-white/45 transition-colors hover:text-red-400 disabled:opacity-50"
              >
                {busyId === a.id ? "…" : "Disconnect"}
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-auto">
        {!configured ? (
          <span className="text-xs text-white/35">Awaiting app credentials (admin setup).</span>
        ) : atCap ? (
          <span className="text-xs text-white/40">
            <Link href="/premium" className="text-[var(--accent)] hover:underline">
              Upgrade for more accounts
            </Link>
          </span>
        ) : (
          <a
            href={`/api/social/oauth/${platform}/start`}
            className="inline-flex items-center justify-center rounded-xl bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white hover:opacity-90"
          >
            {count > 0 ? "Add another account" : `Connect ${meta.label}`}
          </a>
        )}
      </div>
    </Card>
  );
}
