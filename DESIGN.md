# Design

Captured from the live system (`web/src/app/globals.css`, `web/src/components/ui.tsx`, `web/src/components/logo.tsx`). Identity is locked — extend, don't reinvent.

## Theme

Dark only (`color-scheme: dark`). Deep indigo-black field with three fixed radial brand glows (blue top-right, violet left, indigo bottom). App surfaces are elevated indigo panels, not gray.

## Color

- `--background` #0b0a14 (indigo-black body)
- `--surface` #1a1826 · `--surface-2` #232032 · `--surface-3` #2b2840 (elevation ramp)
- `--foreground` #f6f5fb (~16:1) · `--text-secondary` #c8c5d6 (~9:1) · `--text-muted` #9d99b0 (AA-large)
- `--border` rgba(255,255,255,.12) · `--border-strong` rgba(255,255,255,.18)
- Accent: `--accent` #6e7bff (blue-violet) · `--accent-2` #a06bff (violet)
- Brand gradient `--brand-grad`: 105deg #6f97ff → #897cff 45% → #ad7eff
- Semantic: emerald-500/15 + emerald-300 (good) · red-500/15 + red-300 (bad) · amber for warnings
- Strategy: Restrained. Accent only on primary actions, selection, scores, status. Tailwind `text-white/N`, `border-white/N`, `bg-white/N` utilities are globally re-brightened for AA — keep using them, the overrides handle legibility.

## Typography

- Sans: Geist Sans (`--font-geist-sans`), system-ui fallback. Mono: Geist Mono for stats/timecodes.
- One family everywhere; weight does the hierarchy (semibold headings, medium labels, regular body).
- Product scale is fixed rem (text-xs labels · text-sm body/controls · text-base/lg section titles). Landing hero uses large display sizes + `.hero-grad` (allowed on the brand register surface only).

## Components (`web/src/components/ui.tsx`)

- `Button` variants: primary (accent bg, black text, glow via global `[class*="bg-[var(--accent)]"]` shadow), ghost, outline. min-h-11, rounded-xl, semibold sm.
- `Input`: rounded-xl, `bg-white/[0.03]`, border-white/10, focus → accent/60 border. min-h-11.
- `Card`: rounded-2xl, `--surface`, border-white/[0.07], p-4/6.
- `Badge` tones: neutral / accent / good / bad — rounded-full pills.
- Toggles/segmented controls live in studio.tsx; same vocabulary (rounded-xl, white/5 hover, accent selection).

## Motion

- Hover lift `.lift` (translateY(-4px), cubic-bezier(.2,.7,.2,1) ~300ms); scroll reveal `.reveal/.in` (IntersectionObserver island); aurora/floaty/marquee/sheen/gradpan reserved for the landing.
- Product motion: 150–250ms, exponential ease-out, state-conveying only. Press feedback on interactive controls.
- Every animation has a `prefers-reduced-motion: reduce` alternative in the global block — additions must extend that block.

## Layout

- App shell: sticky translucent top-nav (backdrop-blur) + max-w-6xl content columns; landing uses full-bleed sections.
- Radii: rounded-xl controls, rounded-2xl panels, rounded-full pills. Spacing rhythm: space-y-3/4 in panels, gap-4 grids, generous py on sections.
- Z-scale (semantic): base content < sticky nav < dropdown < modal-backdrop < modal < toast.

## Voice

Labels are calm and specific ("Auto-clip a long video", "Why it popped", "Script my version"). Hints explain the win, not the mechanism. No exclamation marks in product chrome.
