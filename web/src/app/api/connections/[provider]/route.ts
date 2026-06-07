import { NextResponse } from "next/server";
import { z } from "zod";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { encryptSecret } from "@/lib/crypto";
import { isProvider, validateKey } from "@/lib/connections";

const Body = z.object({ apiKey: z.string().min(8) });

// Connect a provider (BYOK): validate the pasted key with a free provider call, encrypt it
// (AES-256-GCM), and upsert into the service-role-only user_connections vault. The raw key is
// NEVER returned to the client and NEVER logged — only the last-4 + status.
export async function POST(request: Request, { params }: { params: Promise<{ provider: string }> }) {
  const { provider } = await params;
  if (!isProvider(provider)) return NextResponse.json({ error: "unknown provider" }, { status: 404 });

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  let body: z.infer<typeof Body>;
  try {
    body = Body.parse(await request.json());
  } catch {
    return NextResponse.json({ error: "invalid request body" }, { status: 422 });
  }

  const result = await validateKey(provider, body.apiKey);
  if (!result.ok) return NextResponse.json({ error: result.error }, { status: 400 });

  const admin = createAdminClient();
  const { error } = await admin.from("user_connections").upsert(
    {
      user_id: user.id,
      provider,
      secret_enc: encryptSecret(body.apiKey.trim()),
      last4: result.last4,
      status: "active",
      validated_at: new Date().toISOString(),
    },
    { onConflict: "user_id,provider" },
  );
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  return NextResponse.json({ connected: true, provider, last4: result.last4 });
}

// Disconnect a provider — hard-delete the stored key.
export async function DELETE(_request: Request, { params }: { params: Promise<{ provider: string }> }) {
  const { provider } = await params;
  if (!isProvider(provider)) return NextResponse.json({ error: "unknown provider" }, { status: 404 });

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const admin = createAdminClient();
  const { error } = await admin
    .from("user_connections")
    .delete()
    .eq("user_id", user.id)
    .eq("provider", provider);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  return NextResponse.json({ connected: false, provider });
}
