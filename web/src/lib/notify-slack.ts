// One Slack channel for all growth/ops alerts. SERVER-ONLY (never import in a client component).
// Fire-and-forget: never throws, never blocks the caller. If SLACK_WEBHOOK_URL is unset it no-ops.

export type SlackEventKind =
  | "signup"
  | "bug"
  | "feature"
  | "question"
  | "feedback"
  | "purchase"
  | "lead"
  | "abandoned_checkout";

const EMOJI: Record<SlackEventKind, string> = {
  signup: "🎉",
  purchase: "💰",
  bug: "🐛",
  feature: "💡",
  question: "❓",
  feedback: "💬",
  lead: "🧲",
  abandoned_checkout: "🛒",
};

export async function notifySlack(event: {
  kind: SlackEventKind;
  title: string;
  body?: string;
  email?: string;
  page?: string;
  url?: string;
}): Promise<void> {
  const webhook = process.env.SLACK_WEBHOOK_URL;
  if (!webhook) return; // no-op when unconfigured

  const emoji = EMOJI[event.kind] ?? "🔔";

  // Context fields: email / page / url shown as compact mrkdwn lines when present.
  const contextEls: { type: "mrkdwn"; text: string }[] = [];
  if (event.email) contextEls.push({ type: "mrkdwn", text: `*Email:* ${event.email}` });
  if (event.page) contextEls.push({ type: "mrkdwn", text: `*Page:* ${event.page}` });
  if (event.url) contextEls.push({ type: "mrkdwn", text: `*URL:* ${event.url}` });

  const blocks: unknown[] = [
    {
      type: "header",
      text: { type: "plain_text", text: `${emoji} ${event.title}`, emoji: true },
    },
  ];
  if (event.body) {
    blocks.push({
      type: "section",
      text: { type: "mrkdwn", text: event.body.slice(0, 2900) },
    });
  }
  if (contextEls.length) {
    blocks.push({ type: "context", elements: contextEls });
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 3000);
  try {
    await fetch(webhook, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: `${emoji} ${event.title}`, blocks }),
      signal: controller.signal,
    });
  } catch (err) {
    // Swallow everything — a Slack outage must never break the caller.
    console.warn("notifySlack failed:", err);
  } finally {
    clearTimeout(timeout);
  }
}
