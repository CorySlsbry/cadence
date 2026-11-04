import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

// "Studio" = production: one click from the nav into a camera-ready session.
// Reuse the newest untouched project (still "Untitled project") so repeat clicks
// don't litter the dashboard; otherwise start a fresh one.
export default async function StudioPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: existing } = await supabase
    .from("projects")
    .select("id")
    .eq("name", "Untitled project")
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (existing) redirect(`/project/${existing.id}`);

  const { data: fresh, error } = await supabase
    .from("projects")
    .insert({ user_id: user.id, name: "Untitled project" })
    .select("id")
    .single();
  if (error || !fresh) redirect("/dashboard");
  redirect(`/project/${fresh.id}`);
}
