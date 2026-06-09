"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { Button, Input, Label, Card } from "@/components/ui";

export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") ?? "/dashboard";
  const supabase = createClient();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const isSignup = mode === "signup";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setInfo(null);
    setBusy(true);
    try {
      if (isSignup) {
        const { data, error } = await supabase.auth.signUp({
          email,
          password,
          options: { data: { full_name: fullName } },
        });
        if (error) throw error;
        if (data.session) {
          // Attribute a referral captured on the landing page (?ref=CODE), once.
          try {
            const code = localStorage.getItem("ch_ref");
            if (code) {
              await supabase.rpc("claim_referral", { p_code: code });
              localStorage.removeItem("ch_ref");
            }
          } catch {
            /* non-fatal */
          }
          router.push(next);
          router.refresh();
        } else {
          setInfo("Check your email to confirm your account, then sign in.");
        }
      } else {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
        router.push(next);
        router.refresh();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  async function google() {
    setError(null);
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent(next)}` },
    });
    if (error) setError(error.message);
  }

  return (
    <Card className="p-7">
      <h1 className="text-xl font-bold">{isSignup ? "Create your account" : "Welcome back"}</h1>
      <p className="mb-6 mt-1 text-sm text-white/45">
        {isSignup ? "Start making studio-grade clips." : "Sign in to your studio."}
      </p>

      <Button variant="outline" className="w-full" onClick={google} type="button">
        <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden>
          <path fill="currentColor" d="M21.35 11.1H12v2.8h5.35c-.23 1.4-1.6 4.1-5.35 4.1-3.22 0-5.85-2.66-5.85-5.95S8.78 6.1 12 6.1c1.83 0 3.06.78 3.76 1.45l2.56-2.47C16.7 3.6 14.6 2.7 12 2.7 6.92 2.7 2.8 6.82 2.8 12s4.12 9.3 9.2 9.3c5.31 0 8.82-3.73 8.82-8.98 0-.6-.07-1.06-.17-1.52z" />
        </svg>
        Continue with Google
      </Button>

      <div className="my-5 flex items-center gap-3 text-xs text-white/25">
        <span className="h-px flex-1 bg-white/10" /> or <span className="h-px flex-1 bg-white/10" />
      </div>

      <form onSubmit={submit} className="space-y-4">
        {isSignup && (
          <div>
            <Label htmlFor="name">Name</Label>
            <Input id="name" value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Alex Rivera" />
          </div>
        )}
        <div>
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@studio.com" />
        </div>
        <div>
          <Label htmlFor="password">Password</Label>
          <Input id="password" type="password" required minLength={6} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />
        </div>

        {error && <p className="text-sm text-red-400">{error}</p>}
        {info && <p className="text-sm text-emerald-400">{info}</p>}

        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? "…" : isSignup ? "Create account" : "Sign in"}
        </Button>
      </form>

      <p className="mt-5 text-center text-sm text-white/40">
        {isSignup ? (
          <>
            Already have an account?{" "}
            <Link href="/login" className="text-[var(--accent)] hover:underline">Sign in</Link>
          </>
        ) : (
          <>
            New here?{" "}
            <Link href="/signup" className="text-[var(--accent)] hover:underline">Create an account</Link>
          </>
        )}
      </p>
    </Card>
  );
}
