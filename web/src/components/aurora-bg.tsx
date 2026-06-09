/**
 * Full-bleed animated aurora / mesh-gradient field in the CloutHook brand palette
 * (blue → violet → purple). Pure CSS (the `.aurora` keyframes live in globals.css),
 * $0, no deps. Fixed behind all content; pointer-events disabled. Motion is gated by
 * the global `prefers-reduced-motion` block in globals.css.
 *
 * Presentational only — safe to render on the server.
 */
export function AuroraBg() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      {/* deep base wash so the canvas reads near-black even before blobs paint */}
      <div className="absolute inset-0 bg-[var(--background)]" />

      {/* drifting colour blobs (each `.aurora` animates independently via nth offsets) */}
      <div
        className="aurora"
        style={{
          top: "-14%",
          left: "8%",
          width: "46vw",
          height: "46vw",
          background: "radial-gradient(circle at 50% 50%, rgba(92,140,255,0.55), transparent 70%)",
          animationDelay: "0s",
        }}
      />
      <div
        className="aurora"
        style={{
          top: "6%",
          right: "-6%",
          width: "42vw",
          height: "42vw",
          background: "radial-gradient(circle at 50% 50%, rgba(160,107,255,0.5), transparent 70%)",
          animationDelay: "-5s",
          animationDuration: "20s",
        }}
      />
      <div
        className="aurora"
        style={{
          bottom: "-18%",
          left: "28%",
          width: "52vw",
          height: "40vw",
          background: "radial-gradient(circle at 50% 50%, rgba(122,108,255,0.45), transparent 70%)",
          animationDelay: "-9s",
          animationDuration: "24s",
        }}
      />

      {/* faint vertical light streaks for an "app-like" depth cue */}
      <div
        className="absolute inset-0 opacity-[0.5] mix-blend-screen"
        style={{
          backgroundImage:
            "linear-gradient(90deg, transparent 0%, rgba(122,140,255,0.10) 22%, transparent 23%, transparent 60%, rgba(160,107,255,0.10) 77%, transparent 78%)",
        }}
      />

      {/* subtle film grain via fine dotted overlay — kills banding on the gradients */}
      <div
        className="absolute inset-0 opacity-[0.22]"
        style={{
          backgroundImage:
            "radial-gradient(rgba(255,255,255,0.6) 0.5px, transparent 0.5px)",
          backgroundSize: "3px 3px",
          maskImage: "radial-gradient(120% 90% at 50% 0%, #000 30%, transparent 100%)",
          WebkitMaskImage: "radial-gradient(120% 90% at 50% 0%, #000 30%, transparent 100%)",
        }}
      />

      {/* vignette so edges sink into black and content pops */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(130% 120% at 50% 12%, transparent 42%, rgba(7,6,12,0.78) 100%)",
        }}
      />
    </div>
  );
}
