import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";

export const dynamic = "force-dynamic";

type Feedback = {
  id: string;
  email: string | null;
  message: string;
  page: string | null;
  status: string;
  created_at: string;
};

export default async function AdminPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: profile } = await supabase.from("profiles").select("plan").maybeSingle();
  if (profile?.plan !== "admin") redirect("/dashboard");

  // Service role bypasses RLS to read every user's feedback (admin already verified above).
  const admin = createAdminClient();
  const { data } = await admin
    .from("feedback")
    .select("id, email, message, page, status, created_at")
    .order("created_at", { ascending: false })
    .limit(300);
  const items = (data ?? []) as Feedback[];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-[var(--foreground)]">Admin · Feedback</h1>
        <p className="mt-1 text-sm text-white/50">
          {items.length} message{items.length === 1 ? "" : "s"} from creators &amp; users.
        </p>
      </div>

      {items.length === 0 ? (
        <div className="rounded-2xl border border-white/10 p-10 text-center text-white/45">
          No feedback yet. The 💬 Feedback button on every page sends here.
        </div>
      ) : (
        <ul className="space-y-3">
          {items.map((f) => (
            <li key={f.id} className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
              <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-white/45">
                <span className="rounded-full bg-[var(--accent)]/20 px-2 py-0.5 text-[var(--accent)]">{f.status}</span>
                <span>{f.email ?? "anonymous"}</span>
                {f.page && <span className="text-white/30">· {f.page}</span>}
                <span className="ml-auto">{new Date(f.created_at).toLocaleString()}</span>
              </div>
              <p className="whitespace-pre-wrap text-sm text-[var(--foreground)]">{f.message}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
