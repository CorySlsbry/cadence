# Cadence — Pricing & Unit-Economics Model

> Goal: price for premium creators **and** make runaway AI/GPU cost structurally impossible.
> Core principle: **the subscription sells the transformation; credits meter the one variable
> cost that can run away (AI generation); overage credits are margin-positive.** A user can
> never spend more compute than they've paid for, because the credit balance *is* the hard cap.

## 1. Real cost drivers (grounded in the engine)

| Driver | Unit cost | Source |
|---|---|---|
| AI b-roll image (standard) | **$0.04** | `imagen-4.0-generate-001` (`imagegen/imagen.py` `_COST`) |
| AI b-roll image (fast) | $0.02 | `imagen-4.0-fast-generate-001` |
| AI b-roll image (ultra) | $0.06 | `imagen-4.0-ultra-generate-001` |
| Gemini scene distill | ~$0.0004 / render | gemini-2.5-flash, ~250 tok/scene — negligible |
| Render compute (CPU) | ~$0.02–0.03 / render | Cloud Run 4 vCPU/8 GiB, ~2–3 min wall, billed only during the request |
| ASR (whisper base.en) | $0 marginal | runs on the render CPU, model baked into image |
| Storage + egress | ~$0.02 / render | Supabase: ~40 MB output + ~100 MB raw ingest pulled by the worker |

**b-roll image count per 60 s** (from `_BROLL_CADENCE`, ~1 image / 5 s at balanced):
- `match` (punchy): clip 1.8 + gap 1.6 → ~**17** images
- `between` (balanced, default): clip 2.2 + gap 3.0 → ~**11** images
- `natural` (calm): clip 2.6 + gap 5.0 → ~**7** images

### Per-render COGS

| Render type (60 s) | AI images | AI $ | + compute/storage | **Total COGS** |
|---|---|---|---|---|
| **Clean edit** (cuts/captions/zoom, no AI) | 0 | $0.00 | ~$0.05 | **~$0.05** |
| **AI b-roll, balanced/standard** | 11 | $0.44 | ~$0.05 | **~$0.49** |
| **AI b-roll, punchy/standard** | 17 | $0.68 | ~$0.05 | **~$0.73** |
| **Background-replace** (matte, no AI bg) | 0–1 | ~$0.04 | ~$0.08 (3 passes) | **~$0.12** |

**Takeaway:** AI image generation is **~90% of variable cost.** Clean edits are nearly free.
This is exactly the "credit usage" risk — so credits must gate **AI generation specifically**,
while clean editing stays unlimited (it's the cheap, sticky, daily-use hook).

## 2. The credit system (margin firewall)

- **1 credit = 1 AI scene** at standard quality (internal cost $0.04). `fast` = 0.5 credit, `ultra` = 1.5 credits.
- **Clean edits cost 0 credits** — unlimited on every paid plan (compute is covered by the base fee).
- **Background-replace** = 1 credit if it generates a contextual AI background, else 0 (uses your image).
- The credit balance is enforced atomically server-side (the existing `ai_spend` table + `charge_ai_spend`
  RPC generalizes to a per-user `credits` ledger). **When credits hit 0, AI generation stops** — the render
  still completes as a clean edit. There is no path to overspend. This is the "can't die by credit usage" guarantee.

## 3. Tiers

| Plan | Price | Monthly credits | AI-video-minutes* | Clean edits | Notable |
|---|---|---|---|---|---|
| **Starter** | Free | 60 one-time | ~5 min | Unlimited | 1080p, Cadence watermark |
| **Creator** | **$39/mo** | 250 | ~22 min | Unlimited | No watermark, all cinematography controls, teleprompter |
| **Pro** | **$99/mo** | 800 | ~70 min | Unlimited | Priority queue, ultra quality, brand kits, background-replace |
| **Studio** | **$299/mo** | 3,000 | ~270 min | Unlimited | 3 seats, API access, fastest queue |
| **Overage** | — | 500 / **$59** · 2,000 / **$199** | — | — | $0.10–0.118 per credit (2.5–3× cost) |

\* AI-video-minutes at balanced pacing (~11 credits/min). Fast quality ~doubles it.

### Margins (worst case = 100% credit utilization, standard quality)

| Plan | Price | Max AI COGS | + compute | Total COGS | **Gross margin** |
|---|---|---|---|---|---|
| Creator | $39 | $10.00 | ~$1.1 | ~$11.1 | **72%** |
| Pro | $99 | $32.00 | ~$3.5 | ~$35.5 | **64%** |
| Studio | $299 | $120.00 | ~$13.5 | ~$133.5 | **55%** |

At a realistic **~60% credit utilization** (most users don't exhaust their bucket), margins rise to
**~78% / ~74% / ~73%**. Overage credits sit at **60–66% margin**, so the heaviest users are the *most*
profitable — the opposite of the flat-rate death spiral.

## 4. 10,000-user blended P&L (monthly)

Distribution: 60% Free (6,000) · 25% Creator (2,500) · 12% Pro (1,200) · 3% Studio (300), 60% credit utilization.

| Line | Amount |
|---|---|
| Revenue (2,500·$39 + 1,200·$99 + 300·$299) | **$306,000** |
| Paid COGS (~$7 / ~$21 / ~$80 per user @60% util) | −$66,700 |
| Free-tier COGS (trial credits + compute) | −$6,000 |
| Fixed infra (Supabase Pro, Cloud Run baseline, AR, scheduler) | −$6,000 |
| **Gross profit** | **≈ $227,000/mo (~74%)** |

Plus overage-credit revenue (pure upside, margin-positive). **Break-even on AI cost is impossible to
breach** because every AI image is pre-paid in credits.

## 5. The "GPUs at scale" question — reframed

Rendering is **FFmpeg + faster-whisper, which are CPU-bound**; a GPU (e.g., Cloud Run L4) only speeds
throughput — per-render compute stays **<10% of COGS**. So **GPUs are not the margin risk.** The risk is
the **AI generation API (Imagen)**, which is ~90% of variable cost — and that is exactly what credits cap.

- **Now:** CPU Cloud Run, scale-to-zero, ~$0.02–0.03/render compute. Fine to ~thousands of renders/day.
- **At scale (throughput/speed):** optional Cloud Run **GPU (L4)** pool for the render + ASR step — faster
  user experience, ~$0.02–0.05/render, still dwarfed by AI image cost. Model it as a small fixed add-on,
  not a per-user variable that can explode.
- **If/when generative *video* (diffusion) is added:** that IS GPU-heavy — price it as a separate, higher
  credit multiplier (e.g., 20–50 credits/clip) so it self-funds. Never bundle it into flat pricing.

## 6. Levers to protect/expand margin

1. **Default lower tiers to `fast` quality** (0.5 credit/image) — halves AI COGS, doubles effective credits.
2. **Clean-edit-first UX** — the free, sticky daily habit; AI b-roll is the paid upgrade moment.
3. **Conservative included credits + visible overage** — never give "unlimited AI."
4. **Quality tiers gated by plan** — ultra reserved for Pro/Studio.
5. **Per-account hard cap = credit balance** (already enforced atomically) — zero runaway exposure.

## 7. Implementation hooks (already in the codebase)

- The atomic `charge_ai_spend(cost, cap)` RPC + `ai_spend` table → generalize to per-user
  `user_credits(user_id, balance, plan, refilled_at)` + `charge_credits(user_id, n)`; the worker's
  `SupabaseCostLedger` already calls a guarded RPC, so credit enforcement is a drop-in swap.
- `profiles.plan` + `monthly_render_limit` already exist; add `credit_balance` + a monthly refill job
  (Cloud Scheduler, same pattern as the worker drain).
- `broll_quality` control already maps to the three Imagen tiers → credit multiplier wiring is trivial.
- Stripe (or similar) for subscriptions + credit-pack purchases is the only new external integration.
