import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { TopNav } from "@/components/top-nav";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  // claim_monthly_tokens resets the grant when a new month starts and returns the current balance
  const { data: tokens } = await supabase.rpc("claim_monthly_tokens");

  return (
    <div className="flex min-h-screen flex-col">
      <TopNav email={user.email ?? ""} tokens={(tokens as number) ?? 0} />
      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">{children}</main>
    </div>
  );
}
