import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { OutliersClient } from "./outliers-client";

// Outlier discovery: watch up to 10 channels, surface the videos that beat each
// channel's own baseline, deconstruct WHY they popped, and script a personalized
// version — straight onto the teleprompter.

export default async function OutliersPage() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const [{ data: channels }, { data: outliers }, { data: blueprint }] = await Promise.all([
    supabase.from("watched_channels").select("*").eq("user_id", user.id).order("created_at"),
    supabase.from("outlier_videos").select("*").eq("user_id", user.id).order("outlier_score", { ascending: false }).limit(60),
    supabase.from("brand_blueprints").select("user_id").eq("user_id", user.id).maybeSingle(),
  ]);

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-10">
      <span className="text-grad text-sm font-semibold">Outlier intelligence</span>
      <h1 className="mt-2 text-3xl font-extrabold leading-tight tracking-tight sm:text-4xl">
        Film what&apos;s <span className="text-[var(--accent)]">already proven.</span>
      </h1>
      <p className="mt-3 max-w-2xl text-white/55">
        Watch the channels in your niche. We score every upload against that channel&apos;s own baseline —
        anything way above 100 is an <strong className="text-white/80">outlier: proven demand.</strong> Deconstruct
        why it popped, then script your own version in your voice and read it straight off the teleprompter.
      </p>
      <OutliersClient
        initialChannels={channels ?? []}
        initialOutliers={outliers ?? []}
        hasBlueprint={!!blueprint}
      />
    </div>
  );
}
