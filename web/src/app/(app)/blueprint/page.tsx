import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { BlueprintClient } from "./blueprint-client";

// The Ikigai brand blueprint — the personalization backbone. Four questions in;
// ICP + content pillars + voice out. Scripts, hooks and captions are then written
// as THIS creator, for THIS audience ("authentic, not original").

export default async function BlueprintPage() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: blueprint } = await supabase
    .from("brand_blueprints").select("*").eq("user_id", user.id).maybeSingle();

  return (
    <div className="mx-auto w-full max-w-4xl px-6 py-10">
      <span className="text-grad text-sm font-semibold">Brand blueprint</span>
      <h1 className="mt-2 text-3xl font-extrabold leading-tight tracking-tight sm:text-4xl">
        Your voice, engineered into <span className="text-[var(--accent)]">every script.</span>
      </h1>
      <p className="mt-3 max-w-2xl text-white/55">
        Four questions — the Ikigai method. We turn your answers into your ideal-viewer profile,
        3–5 content pillars, and a voice fingerprint. Every script, hook and caption CloutHook
        writes for you is personalized with it: <strong className="text-white/80">authentic, never a copy.</strong>
      </p>
      <BlueprintClient initial={blueprint} />
    </div>
  );
}
