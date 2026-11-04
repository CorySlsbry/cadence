# CloutHook — Brand Kit (v1, fresh direction · 2026-06-24)

> Strategy in one line: the brand's whole job is **the hook** — the first three seconds that earn
> the scroll and compound into clout. The mark *is* a hook; the system is **editorial, not dark-SaaS**:
> warm bone, ink black, one electric vermillion. Confident and expensive — the opposite of templated
> AI-tool neon.

**Personality:** sharp, premium, fast, creator-native, a little editorial. **Avoid:** generic SaaS
gradients, purple-blue "AI glow", neon-on-black, clipart, busy mockups.

## Logo
- **Symbol** — "the hook": a bold rounded single-stroke fishhook (shank → left U-bend → point → barb),
  round caps. Reads as a hook (the name) and as "catch + lift" (capture attention → lift clout).
- **Wordmark** — `clouthook`, lowercase, Clash Display 700, tight tracking (~-3%). `hook` is set in
  **Flare**; `clout` in **Ink**. Lowercase is deliberate (modern/confident, à la Linear/Vercel).
- **Lockups:** primary (symbol tile + wordmark, horizontal), stacked, symbol-only (app icon),
  reversed (ink tile, bone wordmark, flare hook).
- **Clear space:** ≥ the hook's bend-width on all sides. **Min size:** symbol 24px; wordmark 90px wide.
- **Don'ts:** no gradient/glow/shadow on the mark; don't stretch, rotate, outline, or recolor the hook
  (Flare or Ink only); don't place the wordmark on busy imagery without an ink/bone plate.

## Color
| Token | Name | Hex | Role | Target ratio |
|---|---|---|---|---|
| `--ch-ink` | Ink | `#16130F` | Primary text, dark surfaces, the symbol tile | ~25% |
| `--ch-bone` | Bone | `#F3EFE6` | Canvas / default background | ~55% |
| `--ch-flare` | Flare | `#FF3B1E` | Single accent: one CTA / one highlight per view | **≤10%** |
| `--ch-slate` | Slate | `#2C2A26` | Secondary dark surface, footers | ~5% |
| `--ch-stone` | Stone | `#B8B2A4` | Muted text, hairlines, disabled | ~5% |
| `--ch-mist` | Mist | `#EAE4D6` | Subtle fills, track/inactive bars | as needed |

Rule: **Flare has exactly one job per screen.** Never use Flare for body text or large fills.
Text on Flare = Ink. Hairlines = `#D8D1C1` on bone.

```css
:root{
  --ch-ink:#16130F; --ch-bone:#F3EFE6; --ch-flare:#FF3B1E;
  --ch-slate:#2C2A26; --ch-stone:#B8B2A4; --ch-mist:#EAE4D6; --ch-line:#D8D1C1;
}
```

## Typography
- **Display — Clash Display** (free, Fontshare). Wordmark + headlines. Weights 600–700, tracking -1 to -3%.
- **Text/UI — Inter** (free, Google Fonts). Body, UI, captions. Weights 400 / 500. Tabular numerals.
- **Scale:** display 92 / 62 / 34; UI h1 28, h2 20, body 16/1.6, caption 13, label 11–12 (tracking +1).
- Sentence case everywhere except the lowercase wordmark.

## Imagery / art direction
- Warm, cinematic, real creators in real light — not stock "person at laptop". High-contrast crops,
  generous bone margins, one Flare element max per frame.
- Treatment: subtle film grain ok; **no** purple/teal AI gradients, no glossy 3D blobs, no neon.
- Product shots sit on bone or ink plates with hairline frames (editorial deck feel).

## Voice
Confident, plain, a little swagger. Short sentences. Show the outcome, not the feature.
- Tagline: **Record once. Hook everyone.** · Short form: **Win the hook.**
- Say: "studio-grade", "one raw take", "earn the scroll". Avoid: "cheap", "easy", "AI-powered" filler.

## Adoption note
This is a **fresh** direction — the live clouthook.com is still the prior dark/gradient look. See the
brand review for the prioritized migration list (tokens → components → marketing pages).
