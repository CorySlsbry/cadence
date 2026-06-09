// Server-side Gemini JSON calls (plain fetch — no SDK dependency). Used by the
// "front half" features: brand blueprint, outlier analysis, script generation.
// GEMINI_API_KEY is mounted from Secret Manager (same secret the worker uses).

const API_BASE = "https://generativelanguage.googleapis.com/v1beta/models";

type GeminiOpts = {
  model?: string;
  prompt: string;
  /** Optional image to include (e.g. an outlier thumbnail) for multimodal analysis. */
  imageUrl?: string;
  temperature?: number;
};

function extractJson(text: string): unknown {
  // Gemini with responseMimeType json usually returns clean JSON; strip fences defensively.
  const cleaned = text.trim().replace(/^```(?:json)?\s*/i, "").replace(/```\s*$/, "");
  const start = cleaned.search(/[[{]/);
  if (start === -1) throw new Error("no JSON in model response");
  return JSON.parse(cleaned.slice(start));
}

export async function geminiJson<T>(opts: GeminiOpts): Promise<T> {
  const key = process.env.GEMINI_API_KEY;
  if (!key) throw new Error("GEMINI_API_KEY not configured");
  const model = opts.model ?? "gemini-2.5-flash";

  const parts: Record<string, unknown>[] = [];
  if (opts.imageUrl) {
    try {
      const img = await fetch(opts.imageUrl);
      if (img.ok) {
        const buf = Buffer.from(await img.arrayBuffer());
        if (buf.length > 0 && buf.length < 4_000_000) {
          parts.push({
            inline_data: {
              mime_type: img.headers.get("content-type")?.split(";")[0] || "image/jpeg",
              data: buf.toString("base64"),
            },
          });
        }
      }
    } catch {
      // Image fetch is best-effort — analysis proceeds text-only.
    }
  }
  parts.push({ text: opts.prompt });

  const res = await fetch(`${API_BASE}/${model}:generateContent`, {
    method: "POST",
    headers: { "content-type": "application/json", "x-goog-api-key": key },
    body: JSON.stringify({
      contents: [{ role: "user", parts }],
      generationConfig: {
        temperature: opts.temperature ?? 0.7,
        responseMimeType: "application/json",
        maxOutputTokens: 8192,
      },
    }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`gemini ${model} ${res.status}: ${detail.slice(0, 300)}`);
  }
  const data = (await res.json()) as {
    candidates?: { content?: { parts?: { text?: string }[] } }[];
  };
  const text = data.candidates?.[0]?.content?.parts?.map((p) => p.text ?? "").join("") ?? "";
  if (!text) throw new Error("empty gemini response");
  return extractJson(text) as T;
}
