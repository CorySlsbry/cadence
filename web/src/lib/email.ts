import type { ScoreResult } from "@/lib/score";

// Transactional email sent FROM support@neuron-HQ.com (the app's hub) via Neuron-HQ's own Google
// Workspace — NO third-party ESP. Transport is a small Workspace relay (an Apps Script or tiny
// endpoint bound to the support@ mailbox) so this file stays dependency-free. If the relay isn't
// configured yet, every send is a graceful no-op — the funnel never blocks on mail delivery.
// Phase 4 stands up the relay and sets EMAIL_RELAY_URL / EMAIL_RELAY_TOKEN.

const FROM = "CloutHook <support@neuron-HQ.com>";
const REPLY_TO = "support@neuron-HQ.com";

type Mail = { to: string; subject: string; html: string; text?: string };

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string);
}

export async function sendMail(mail: Mail): Promise<boolean> {
  const url = process.env.EMAIL_RELAY_URL;
  const token = process.env.EMAIL_RELAY_TOKEN;
  if (!url) {
    console.warn("[email] EMAIL_RELAY_URL unset — skipping send to", mail.to);
    return false;
  }
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json", ...(token ? { authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify({ from: FROM, replyTo: REPLY_TO, ...mail }),
    signal: AbortSignal.timeout(10000),
  });
  if (!res.ok) {
    throw new Error(`relay ${res.status}: ${(await res.text().catch(() => "")).slice(0, 200)}`);
  }
  return true;
}

export async function sendScoreReport(to: string, result: ScoreResult, id: string): Promise<boolean> {
  const site = process.env.NEXT_PUBLIC_SITE_URL || "https://clouthook.com";
  const rows = result.dimensions
    .map(
      (d) =>
        `<tr><td style="padding:8px 12px;border-bottom:1px solid #eee">${escapeHtml(d.label)}</td>` +
        `<td style="padding:8px 12px;border-bottom:1px solid #eee;font-weight:700">${d.score}/10</td>` +
        `<td style="padding:8px 12px;border-bottom:1px solid #eee;color:#444">${escapeHtml(d.fix)}</td></tr>`,
    )
    .join("");
  const fixes = result.topFixes.map((f) => `<li style="margin:6px 0">${escapeHtml(f)}</li>`).join("");
  const html = `<div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:640px;margin:0 auto;color:#111">
  <h1 style="font-size:22px;margin:0 0 4px">Your Viral Score: ${result.score}/10 <span style="color:#6e7bff">(${escapeHtml(result.grade)})</span></h1>
  <p style="color:#444;margin:0 0 16px">${escapeHtml(result.summary)}</p>
  <h2 style="font-size:16px;margin:20px 0 8px">Your top fixes</h2>
  <ol style="padding-left:18px;color:#222">${fixes}</ol>
  <h2 style="font-size:16px;margin:20px 0 8px">Full breakdown</h2>
  <table style="border-collapse:collapse;width:100%;font-size:14px">${rows}</table>
  <p style="margin:24px 0"><a href="${site}/signup" style="background:#6e7bff;color:#000;text-decoration:none;font-weight:700;padding:12px 20px;border-radius:10px;display:inline-block">Let CloutHook fix this video for you →</a></p>
  <p style="color:#888;font-size:12px;margin-top:24px">You got this because you ran a free Viral Score at CloutHook. <a href="${site}/unsubscribe?e=${encodeURIComponent(to)}" style="color:#888">Unsubscribe</a> · CloutHook, an app by Neuron HQ.</p>
</div>`;
  const text = `Your Viral Score: ${result.score}/10 (${result.grade})\n\n${result.summary}\n\nTop fixes:\n${result.topFixes
    .map((f, i) => `${i + 1}. ${f}`)
    .join("\n")}\n\nFix it with CloutHook: ${site}/signup\nUnsubscribe: ${site}/unsubscribe?e=${encodeURIComponent(to)}`;
  return sendMail({ to, subject: `Your Viral Score: ${result.score}/10 (${result.grade})`, html, text });
}
