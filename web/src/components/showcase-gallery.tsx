/**
 * Horizontal auto-scrolling showcase of rounded 9:16 "video" cards. Uses tasteful
 * brand-gradient placeholders (no real renders shipped yet). Pure CSS marquee
 * (`.animate-marquee` from globals.css, gated by prefers-reduced-motion); pauses on hover.
 *
 * Presentational only — safe on the server.
 */

type Sample = {
  label: string;
  tag: string;
  grad: string;
};

const SAMPLES: Sample[] = [
  { label: "Founder hot take", tag: "Talking head", grad: "linear-gradient(160deg,#5c8cff,#7a6cff 55%,#a06bff)" },
  { label: "Product teardown", tag: "AI b-roll", grad: "linear-gradient(160deg,#7a6cff,#a06bff 60%,#5c8cff)" },
  { label: "Day-in-the-life", tag: "Replace BG", grad: "linear-gradient(160deg,#3f6dff,#7a6cff 50%,#b07bff)" },
  { label: "Hook + payoff", tag: "Auto-captioned", grad: "linear-gradient(160deg,#6e7bff,#a06bff)" },
  { label: "Listicle / tips", tag: "Cut to beat", grad: "linear-gradient(160deg,#8a6cff,#5c8cff 60%,#a06bff)" },
  { label: "Case study", tag: "Brand kit", grad: "linear-gradient(160deg,#5c8cff,#a06bff 70%,#7a6cff)" },
];

function PlayGlyph() {
  return (
    <span className="flex h-12 w-12 items-center justify-center rounded-full border border-white/30 bg-black/25 backdrop-blur-sm transition-transform duration-300 group-hover:scale-110">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="#fff" aria-hidden>
        <path d="M8 5v14l11-7z" />
      </svg>
    </span>
  );
}

function ShowcaseCard({ s }: { s: Sample }) {
  return (
    <div className="group relative aspect-[9/16] w-[180px] shrink-0 overflow-hidden rounded-2xl border border-white/12 shadow-[0_18px_50px_-22px_rgba(0,0,0,0.9)] transition-transform duration-300 hover:-translate-y-1.5 sm:w-[210px]">
      {/* gradient "thumbnail" */}
      <div className="absolute inset-0" style={{ background: s.grad }} />
      {/* glossy highlight + darkening for legibility */}
      <div className="absolute inset-0 bg-[radial-gradient(120%_80%_at_50%_-10%,rgba(255,255,255,0.35),transparent_55%)]" />
      <div className="absolute inset-0 bg-gradient-to-t from-black/65 via-transparent to-black/10" />
      {/* sheen sweep on hover */}
      <div className="absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100">
        <div className="sheen absolute inset-0" />
      </div>

      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <PlayGlyph />
      </div>

      <div className="absolute inset-x-0 bottom-0 p-3.5">
        <span className="inline-flex rounded-full bg-white/15 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-white/90 backdrop-blur-sm">
          {s.tag}
        </span>
        <p className="mt-2 text-sm font-semibold text-white drop-shadow">{s.label}</p>
      </div>
    </div>
  );
}

export function ShowcaseGallery() {
  // Render the set twice so the -50% marquee translate loops seamlessly.
  const loop = [...SAMPLES, ...SAMPLES];
  return (
    <div className="group/marquee relative w-full overflow-hidden">
      {/* edge fades so cards dissolve instead of hard-cutting at the viewport */}
      <div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-16 bg-gradient-to-r from-[var(--background)] to-transparent sm:w-28" />
      <div className="pointer-events-none absolute inset-y-0 right-0 z-10 w-16 bg-gradient-to-l from-[var(--background)] to-transparent sm:w-28" />

      <div className="animate-marquee flex w-max gap-4 [animation-duration:46s] group-hover/marquee:[animation-play-state:paused] sm:gap-5">
        {loop.map((s, i) => (
          <ShowcaseCard key={`${s.label}-${i}`} s={s} />
        ))}
      </div>
    </div>
  );
}
