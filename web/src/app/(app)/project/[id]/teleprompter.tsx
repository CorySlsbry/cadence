"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Teleprompter: paste a script and auto-scroll it while recording. The speed slider is
 * calibrated in words-per-minute — the scroll rate is derived live from the rendered
 * content height and word count, so the whole script passes in (words / wpm) minutes
 * regardless of font size. It auto-plays when recording starts (and the DOM-only effect
 * rewinds it to the top) and pauses when recording stops; manual play/restart let you
 * rehearse and dial in your pace.
 */
export function Teleprompter({ recording }: { recording: boolean }) {
  const [script, setScript] = useState("");
  const [wpm, setWpm] = useState(130);
  const [fontSize, setFontSize] = useState(30);
  const [manualPlay, setManualPlay] = useState(false);
  const [editing, setEditing] = useState(true);

  const scrollRef = useRef<HTMLDivElement>(null);
  const rafRef = useRef<number | null>(null);
  const accRef = useRef(0);
  const lastTsRef = useRef<number | null>(null);

  const wordCount = script.trim() ? script.trim().split(/\s+/).length : 0;
  const readMins = wordCount > 0 ? wordCount / wpm : 0;
  // Scroll is active when recording OR when the user pressed Play. The reading pane is
  // shown whenever scrolling (so recording always reveals it, even if mid-edit).
  const running = (recording || manualPlay) && wordCount > 0;
  const showReader = running || !editing;

  // Rewind to the top when recording begins — DOM-only side effect (no setState here).
  useEffect(() => {
    if (recording && scrollRef.current) {
      scrollRef.current.scrollTop = 0;
      accRef.current = 0;
      lastTsRef.current = null;
    }
  }, [recording]);

  // The scroll loop. setState only happens asynchronously inside the rAF callback
  // (allowed) — never synchronously in the effect body.
  useEffect(() => {
    if (!running) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      lastTsRef.current = null;
      return;
    }
    const step = (ts: number) => {
      const el = scrollRef.current;
      if (el) {
        if (lastTsRef.current === null) lastTsRef.current = ts;
        const dt = (ts - lastTsRef.current) / 1000;
        lastTsRef.current = ts;
        const scrollable = el.scrollHeight - el.clientHeight;
        // px/sec so the full script scrolls past in (wordCount / wpm) minutes.
        const pxPerSec = scrollable > 0 && wordCount > 0 ? (wpm / 60) * (scrollable / wordCount) : 0;
        accRef.current += pxPerSec * dt;
        if (accRef.current >= 1) {
          el.scrollTop += accRef.current;
          accRef.current = 0;
        }
        if (scrollable > 0 && el.scrollTop >= scrollable - 1) {
          setManualPlay(false); // reached the end (async — fine)
          return;
        }
      }
      rafRef.current = requestAnimationFrame(step);
    };
    rafRef.current = requestAnimationFrame(step);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [running, wpm, wordCount]);

  function rewind() {
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
    accRef.current = 0;
    lastTsRef.current = null;
  }

  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-medium text-white/60">Teleprompter</span>
        <div className="flex items-center gap-2 text-xs text-white/35">
          {wordCount > 0 && (
            <span>{wordCount} words · ~{readMins < 1 ? `${Math.round(readMins * 60)}s` : `${readMins.toFixed(1)}m`}</span>
          )}
          <button onClick={() => setEditing((e) => !e)} className="rounded-md px-2 py-1 text-white/55 hover:text-white">
            {showReader ? "Edit script" : "Done"}
          </button>
        </div>
      </div>

      {!showReader ? (
        <textarea
          value={script}
          onChange={(e) => setScript(e.target.value)}
          placeholder="Paste your script here…"
          rows={5}
          className="w-full resize-none rounded-xl border border-white/10 bg-black/40 p-3 text-sm text-white/85 outline-none placeholder:text-white/25 focus:border-[var(--accent)]/40"
        />
      ) : (
        <div className="relative">
          <div className="pointer-events-none absolute inset-x-0 top-0 z-10 h-10 rounded-t-xl bg-gradient-to-b from-[#0a0a0f] to-transparent" />
          <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 h-10 rounded-b-xl bg-gradient-to-t from-[#0a0a0f] to-transparent" />
          <div className="pointer-events-none absolute inset-x-0 top-1/2 z-10 h-px -translate-y-1/2 bg-[var(--accent)]/20" />
          <div ref={scrollRef} className="h-[220px] overflow-hidden rounded-xl bg-black/40 px-5">
            <p
              className="whitespace-pre-wrap py-[110px] text-center font-semibold text-white"
              style={{ fontSize: `${fontSize}px`, lineHeight: 1.5 }}
            >
              {script || "No script yet. Tap “Edit script” to paste one."}
            </p>
          </div>
        </div>
      )}

      <div className="mt-3 space-y-3">
        <div className="flex items-center gap-2">
          <button
            onClick={() => { setEditing(false); setManualPlay((p) => !p); }}
            disabled={!script.trim() || recording}
            className="flex-1 rounded-lg bg-[var(--accent)] px-3 py-2 text-sm font-medium text-black disabled:opacity-40"
          >
            {recording ? "Reading (recording)" : manualPlay ? "Pause" : "Play"}
          </button>
          <button onClick={rewind} className="rounded-lg border border-white/10 px-3 py-2 text-sm text-white/60 hover:text-white">
            Restart
          </button>
        </div>
        <div>
          <div className="flex items-center justify-between text-xs">
            <span className="text-white/45">Read speed</span>
            <span className="text-white/45">{wpm} wpm</span>
          </div>
          <input type="range" min={70} max={260} step={5} value={wpm}
            onChange={(e) => setWpm(parseInt(e.target.value, 10))} className="w-full accent-[var(--accent)]" />
        </div>
        <div>
          <div className="flex items-center justify-between text-xs">
            <span className="text-white/45">Text size</span>
            <span className="text-white/45">{fontSize}px</span>
          </div>
          <input type="range" min={18} max={56} step={2} value={fontSize}
            onChange={(e) => setFontSize(parseInt(e.target.value, 10))} className="w-full accent-[var(--accent)]" />
        </div>
      </div>
    </div>
  );
}
