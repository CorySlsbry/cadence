import { notFound } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { Studio } from "./studio";
import type { BrandBoard, Project } from "@/lib/types";

export default async function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  const { data: project } = await supabase.from("projects").select("*").eq("id", id).single();
  if (!project || !user) notFound();
  const { data: boards } = await supabase
    .from("brand_boards")
    .select("id, name, caption_primary, caption_outline")
    .order("created_at");

  return <Studio project={project as Project} boards={(boards ?? []) as BrandBoard[]} userId={user.id} />;
}
