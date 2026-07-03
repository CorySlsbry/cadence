"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";

// Floating "Feedback" button shown on every signed-in page. Submissions go to the
// admin dashboard (/admin). Sits above the studio's sticky action bar on mobile.
type Category = "bug" | "feature" | "question";

const CATEGORIES: { value: Category; label: string; emoji: string }[] = [
  { value: "bug", label: "Bug", emoji: "🐛" },
  { value: "feature", label: "Feature", emoji: "💡" },
  { value: "question", label: "Question", emoji: "❓" },
];

export function FeedbackWidget() {
  const [open, setOpen] = useState(false);
  const [msg, setMsg] = useState("");
  const [category, setCategory] = useState<Category>("question");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const pathname = usePathname();

  async function submit() {
    if (!msg.trim() || busy) return;
    setBusy(true);
    try {
      const res = await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg, page: pathname, category }),
      });
      if (res.ok) {
        setSent(true);
        setMsg("");
        setTimeout(() => {
          setOpen(false);
          setSent(false);
        }, 1600);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {!open && (
        <button
          onClick={() => setOpen(true)}
          aria-label="Send feedback"
          className="fixed bottom-24 right-4 z-40 flex items-center gap-2 rounded-full bg-[var(--accent)] px-4 py-3 text-sm font-semibold text-black shadow-[0_8px_30px_rgba(0,0,0,0.45)] transition hover:opacity-90 sm:bottom-6 sm:right-6"
        >
          <span aria-hidden>💬</span> Feedback
        </button>
      )}

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-end bg-black/40 p-4 sm:p-6"
          onClick={() => setOpen(false)}
        >
          <div
            className="w-full max-w-sm rounded-2xl border border-white/12 bg-[var(--surface)] p-5 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-[var(--foreground)]">Send feedback</h3>
              <button
                onClick={() => setOpen(false)}
                aria-label="Close"
                className="text-white/45 hover:text-white"
              >
                ✕
              </button>
            </div>

            {sent ? (
              <p className="py-6 text-center text-sm text-[var(--foreground)]">Thanks — got it! 🙌</p>
            ) : (
              <>
                <div className="mb-3 flex gap-2" role="radiogroup" aria-label="Feedback type">
                  {CATEGORIES.map((c) => (
                    <button
                      key={c.value}
                      type="button"
                      role="radio"
                      aria-checked={category === c.value}
                      onClick={() => setCategory(c.value)}
                      className={`flex flex-1 items-center justify-center gap-1 rounded-xl border px-2 py-2 text-xs font-medium transition ${
                        category === c.value
                          ? "border-[var(--accent)] bg-[var(--accent)]/15 text-[var(--foreground)]"
                          : "border-white/12 bg-white/[0.04] text-white/60 hover:text-white"
                      }`}
                    >
                      <span aria-hidden>{c.emoji}</span> {c.label}
                    </button>
                  ))}
                </div>
                <textarea
                  value={msg}
                  onChange={(e) => setMsg(e.target.value)}
                  rows={4}
                  autoFocus
                  placeholder="What's working, what's broken, what you'd love to see…"
                  className="min-h-11 w-full resize-y rounded-xl border border-white/12 bg-white/[0.04] px-4 py-3 text-sm text-[var(--foreground)] placeholder:text-white/40 focus:border-[var(--accent)] focus:outline-none"
                />
                <button
                  onClick={submit}
                  disabled={busy || !msg.trim()}
                  className="mt-3 min-h-11 w-full rounded-xl bg-[var(--accent)] px-4 py-2.5 text-sm font-semibold text-black transition hover:opacity-90 disabled:opacity-40"
                >
                  {busy ? "Sending…" : "Send to the team"}
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}
