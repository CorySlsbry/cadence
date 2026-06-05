import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { TopNav } from "@/components/top-nav";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: profile } = await supabase
    .from("profiles")
    .select("monthly_render_limit")
    .eq("id", user.id)
    .single();
  const { data: used } = await supabase.rpc("renders_used_this_month", { uid: user.id });

  return (
    <div className="flex min-h-screen flex-col">
      <TopNav
        email={user.email ?? ""}
        used={(used as number) ?? 0}
        limit={profile?.monthly_render_limit ?? 10}
      />
      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">{children}</main>
    </div>
  );
}
