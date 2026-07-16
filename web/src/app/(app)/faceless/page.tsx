import type { Metadata } from "next";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { FacelessClient } from "./faceless-client";

export const metadata: Metadata = {
  title: "Faceless studio — CloutHook",
  description: "Topic in, finished faceless short out — AI scenes, premium narration, karaoke captions.",
};

export const dynamic = "force-dynamic";

export default async function FacelessPage() {
  // Server-resolve the plan's max video length so the client can lock lengths above it.
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  let maxLengthSec = 90;
  if (user) {
    const { data: profile } = await supabase.from("profiles").select("plan").eq("id", user.id).maybeSingle();
    const planKey = (profile?.plan as string | null) ?? "free";
    const admin = createAdminClient();
    const { data: planRow } = await admin
      .from("plans")
      .select("max_length_sec")
      .eq("key", planKey)
      .maybeSingle();
    maxLengthSec = (planRow?.max_length_sec as number | null) ?? 90;
  }

  return <FacelessClient maxLengthSec={maxLengthSec} />;
}
