import { NextResponse } from "next/server";
import { z } from "zod";
import { createClient } from "@/lib/supabase/server";
import { createCheckoutSessionFor, createPackCheckoutSessionFor } from "@/lib/checkout";
import { publicOrigin } from "@/lib/request-origin";

// Either a subscription plan or a one-time token pack.
const Body = z.union([
  z.object({ plan: z.enum(["base", "creator", "agency"]) }),
  z.object({ pack: z.string().min(1).max(40) }),
]);

/** Creates a Stripe Checkout Session (plan subscription or token pack) and returns its URL. */
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
    return NextResponse.json({ error: "invalid plan" }, { status: 422 });
  }

  const origin = publicOrigin(request);
  try {
    const session =
      "plan" in body
        ? await createCheckoutSessionFor(user, body.plan, origin)
        : await createPackCheckoutSessionFor(user, body.pack, origin);
    return NextResponse.json({ url: session.url });
  } catch (err) {
    const msg = err instanceof Error ? err.message : "checkout failed";
    const status = msg.endsWith("not purchasable") ? 400 : 502;
    return NextResponse.json({ error: msg }, { status });
  }
}
