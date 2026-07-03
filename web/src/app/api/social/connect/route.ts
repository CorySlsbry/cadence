import { NextResponse } from "next/server";
import { z } from "zod";
import { createClient } from "@/lib/supabase/server";
import { listAccounts } from "@/lib/blotato";
import { encryptSecret } from "@/lib/crypto";

const Body = z.object({ apiKey: z.string().min(10) });

// Validate a user's Blotato API key by listing their connected accounts, then persist
// the key + account map on their profile (RLS keeps it owner-only). The key is never
// returned to the client — only the connected accounts.
export async function POST(request: Request) {
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

  let accounts;
  try {
    accounts = await listAccounts(body.apiKey);
  } catch (e) {
    return NextResponse.json(
      { error: `Could not validate Blotato key: ${e instanceof Error ? e.message : "unknown error"}` },
      { status: 400 },
    );
  }

  const { error } = await supabase
    .from("profiles")
    // Store the key AES-256-GCM encrypted (server-only master key); clear any legacy plaintext.
    .update({ blotato_api_key_enc: encryptSecret(body.apiKey), blotato_api_key: null, blotato_accounts: accounts })
    .eq("id", user.id);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  return NextResponse.json({ connected: true, accounts });
}
