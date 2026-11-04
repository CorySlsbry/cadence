import { redirect } from "next/navigation";
import { cookies } from "next/headers";
import { createClient } from "@/lib/supabase/server";
import { TopNav } from "@/components/top-nav";
import { FeedbackWidget } from "@/components/feedback-widget";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  // claim_monthly_tokens resets the grant when a new month starts and returns the current balance
  const { data: tokens } = await supabase.rpc("claim_monthly_tokens");

  // Referral attribution that works on EVERY signup path (email, Google OAuth, magic link):
  // the landing page / r-link dropped a 90-day ch_ref cookie; claim it once server-side.
  // claim_referral self-guards (only-once per profile, self-referrals blocked), so this is
  // effectively free after the first successful claim.
  const ref = (await cookies()).get("ch_ref")?.value;
  if (ref) {
    try {
      await supabase.rpc("claim_referral", { p_code: ref });
    } catch {
      /* attribution must never break the app shell */
    }
  }

  return (
    <div className="flex min-h-screen flex-col">
      <TopNav email={user.email ?? ""} tokens={(tokens as number) ?? 0} />
      <main className="page-enter mx-auto w-full max-w-6xl flex-1 px-6 py-8">{children}</main>
      <FeedbackWidget />
    </div>
  );
}
