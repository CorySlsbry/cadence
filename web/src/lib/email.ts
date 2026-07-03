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
    // Token in BOTH the header (Cloud Function / Cloud Run relays) and the body (Google Apps
    // Script web apps can't read request headers — only e.postData). The relay checks whichever.
    headers: { "content-type": "application/json", ...(token ? { authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify({ from: FROM, replyTo: REPLY_TO, token, ...mail }),
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

// --- Lifecycle / funnel emails (welcome · nurture · win-back · abandoned checkout) ------------
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "https://clouthook.com";

export type FunnelTemplate =
  | "welcome"
  | "nurture_day2"
  | "nurture_day5"
  | "nurture_day12"
  | "winback"
  | "abandoned_checkout";

function funnelLayout(o: { heading: string; bodyHtml: string; ctaText: string; ctaUrl: string; to: string }): string {
  return `<div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:520px;margin:0 auto;background:#14141f;border:1px solid #ffffff14;border-radius:16px;padding:32px;color:#e8e8f2">
  <div style="font-size:18px;font-weight:800;margin-bottom:14px">Clout<span style="color:#9e96ff">Hook</span></div>
  <h1 style="font-size:21px;margin:0 0 10px;color:#fff;line-height:1.25">${escapeHtml(o.heading)}</h1>
  <p style="font-size:15px;line-height:1.6;color:#c7c7d6;margin:0 0 20px">${o.bodyHtml}</p>
  <a href="${o.ctaUrl}" style="display:inline-block;background:#6e7bff;color:#fff;text-decoration:none;font-weight:600;padding:13px 26px;border-radius:10px">${escapeHtml(o.ctaText)}</a>
  <p style="color:#6b6b7d;font-size:12px;margin-top:26px;line-height:1.5">CloutHook · an app by Neuron HQ · <a href="${SITE_URL}" style="color:#8a83e6">clouthook.com</a> · <a href="${SITE_URL}/unsubscribe?e=${encodeURIComponent(o.to)}" style="color:#6b6b7d">Unsubscribe</a></p>
</div>`;
}

function renderFunnel(tpl: FunnelTemplate, to: string, name?: string): { subject: string; html: string } {
  const hi = name ? `Hey ${escapeHtml(name)},` : "Hey there,";
  const T: Record<FunnelTemplate, { subject: string; heading: string; body: string; ctaText: string; cta: string }> = {
    welcome: {
      subject: "Welcome to CloutHook 🎬",
      heading: "You're in. Let's make your first short.",
      body: `${hi} CloutHook finds the proven video in your niche, scripts it in your voice, scrolls it on a teleprompter while you record — then cleans, captions, adds b-roll, and clips it into a studio-grade short. One loop, no editor.`,
      ctaText: "Open your studio",
      cta: "/dashboard",
    },
    nurture_day2: {
      subject: "Your first clip is ~2 minutes away",
      heading: "Record one take — we finish it",
      body: `${hi} the hardest part of short-form is deciding what to film. CloutHook picks a proven outlier in your niche and writes the script for you. Hit record, read the teleprompter, and you'll have a captioned 9:16 short ready to post.`,
      ctaText: "Make a short",
      cta: "/dashboard",
    },
    nurture_day5: {
      subject: "The part creators love most",
      heading: "It knows what to film",
      body: `${hi} CloutHook watches the channels in your niche, scores the outliers (and tells you <em>why</em> they popped), then remixes the winner into a script in your voice. Stop guessing, start shipping daily.`,
      ctaText: "See your outliers",
      cta: "/dashboard",
    },
    nurture_day12: {
      subject: "Ready to post every day?",
      heading: "Go all-in on daily shorts",
      body: `${hi} if CloutHook has earned it, a paid plan unlocks more monthly tokens for AI b-roll and scenes — enough to batch a week of content in one sitting. No per-seat tax, cancel anytime.`,
      ctaText: "See plans",
      cta: "/premium",
    },
    winback: {
      subject: "Your CloutHook plan ended — 1-click back",
      heading: "Come back and keep shipping",
      body: `${hi} your subscription wrapped up, so you're on the free plan now. Your projects and connections are all still here — whenever you're ready to batch shorts again, your plan is one click away.`,
      ctaText: "Reactivate",
      cta: "/premium",
    },
    abandoned_checkout: {
      subject: "You left your CloutHook plan in the cart",
      heading: "Finish upgrading in a click",
      body: `${hi} you started upgrading but didn't finish. No rush — your studio is ready whenever you are. Pick up right where you left off:`,
      ctaText: "Complete checkout",
      cta: "/premium",
    },
  };
  const t = T[tpl];
  return {
    subject: t.subject,
    html: funnelLayout({ heading: t.heading, bodyHtml: t.body, ctaText: t.ctaText, ctaUrl: `${SITE_URL}${t.cta}`, to }),
  };
}

/** Send one lifecycle email. No-ops (returns false) when the relay isn't configured. */
export async function sendFunnelEmail(to: string, tpl: FunnelTemplate, name?: string): Promise<boolean> {
  if (!to) return false;
  const { subject, html } = renderFunnel(tpl, to, name);
  try {
    return await sendMail({ to, subject, html });
  } catch (err) {
    console.warn("[email] funnel send failed:", tpl, err);
    return false;
  }
}
