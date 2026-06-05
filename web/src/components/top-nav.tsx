"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { Badge } from "@/components/ui";

export function TopNav({ email, used, limit }: { email: string; used: number; limit: number }) {
  const router = useRouter();

  async function signOut() {
    await createClient().auth.signOut();
    router.push("/");
    router.refresh();
  }

  return (
    <header className="sticky top-0 z-20 border-b border-white/[0.06] bg-[var(--background)]/80 backdrop-blur">
      <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-4">
        <Link href="/dashboard" className="flex items-center gap-2">
          <span className="text-lg font-extrabold tracking-tight">Cadence</span>
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)]" />
        </Link>
        <div className="flex items-center gap-4">
          <Badge tone={used >= limit ? "bad" : "accent"}>
            {used}/{limit} renders this month
          </Badge>
          <span className="hidden text-sm text-white/40 sm:inline">{email}</span>
          <button onClick={signOut} className="text-sm text-white/60 hover:text-white">
            Sign out
          </button>
        </div>
      </div>
    </header>
  );
}
