"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { Badge } from "@/components/ui";
import { Logo } from "@/components/logo";

export function TopNav({ email, tokens }: { email: string; tokens: number }) {
  const router = useRouter();

  async function signOut() {
    await createClient().auth.signOut();
    router.push("/");
    router.refresh();
  }

  return (
    <header className="sticky top-0 z-20 border-b border-white/[0.06] bg-[var(--background)]/80 backdrop-blur">
      <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-3 px-4 py-3 sm:px-6 sm:py-4">
        <Link href="/dashboard" className="shrink-0">
          <Logo size={22} />
        </Link>

        <div className="flex items-center gap-3 sm:gap-4">
          {/* Inline links — sm and up */}
          <Link href="/outliers" className="hidden text-sm text-white/60 hover:text-white sm:inline">
            Outliers
          </Link>
          <Link href="/blueprint" className="hidden text-sm text-white/60 hover:text-white sm:inline">
            Blueprint
          </Link>
          <Link href="/affiliate" className="hidden text-sm text-white/60 hover:text-white sm:inline">
            Affiliate
          </Link>
          <Link href="/connections" className="hidden text-sm text-white/60 hover:text-white sm:inline">
            Connections
          </Link>

          {/* Token balance — always visible */}
          <Badge tone={tokens <= 0 ? "bad" : "accent"}>{tokens} tokens</Badge>

          <span className="hidden max-w-[14ch] truncate text-sm text-white/40 lg:inline">{email}</span>
          <button
            onClick={signOut}
            className="hidden text-sm text-white/60 hover:text-white sm:inline"
          >
            Sign out
          </button>

          {/* Hamburger sheet — below sm */}
          <details className="relative sm:hidden">
            <summary className="flex h-11 w-11 list-none items-center justify-center rounded-xl border border-[var(--border)] text-white/80 [&::-webkit-details-marker]:hidden">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <line x1="4" y1="7" x2="20" y2="7" />
                <line x1="4" y1="12" x2="20" y2="12" />
                <line x1="4" y1="17" x2="20" y2="17" />
              </svg>
            </summary>
            <div className="absolute right-0 top-12 z-30 w-56 overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-1.5 shadow-2xl">
              <Link href="/outliers" className="block rounded-lg px-3 py-3 text-sm text-white/80 hover:bg-white/5">
                Outliers
              </Link>
              <Link href="/blueprint" className="block rounded-lg px-3 py-3 text-sm text-white/80 hover:bg-white/5">
                Blueprint
              </Link>
              <Link href="/affiliate" className="block rounded-lg px-3 py-3 text-sm text-white/80 hover:bg-white/5">
                Affiliate
              </Link>
              <Link href="/connections" className="block rounded-lg px-3 py-3 text-sm text-white/80 hover:bg-white/5">
                Connections
              </Link>
              <div className="truncate px-3 py-2 text-xs text-white/45">{email}</div>
              <button
                onClick={signOut}
                className="block w-full rounded-lg px-3 py-3 text-left text-sm text-white/80 hover:bg-white/5"
              >
                Sign out
              </button>
            </div>
          </details>
        </div>
      </div>
    </header>
  );
}
