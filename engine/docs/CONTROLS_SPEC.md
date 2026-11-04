I now have full ground truth on every file all three designs reference. I have everything needed to produce the merged, de-duplicated, buildable spec. Writing it now.

---

# Cadence Customization Spec â€” Merged Implementation (v1)

Single source of truth merging the 3 expert designs against the actual engine at `C:\Users\you\Downloads\Video Analyzer\engine\cadence\`. De-duplicated, with verified field/function names. Every control maps to either a **PROMPT clause** (Imagen b-roll only â€” `imagen.py:46 generate()` takes only `prompt` + `aspect` + `style_refs` + `seed`, no optical params) or a **RENDER param** (A-roll/composite via the existing ffmpeg builders), or both.

## 0. Architecture decisions (resolve the 3 designs' conflicts)

1. **New dataclass `CinematographyConfig`** in `config.py`, plus extend `CleaningConfig` and `SynthesisConfig` with the new cut/smooth fields. One `customization` JSON deserializes into these three configs. This is Design 1's recommendation; Designs 2 & 3 agreed on the same threading points.
2. **One preset table is the single source of truth** for film-stock â†’ (prompt clause, ColorGrade override) so the AI b-roll and graded A-roll never drift (the "two cameras" tell flagged by all 3). Defined as a const `FILM_STOCKS` in `config.py`.
3. **`build_ai_prompt_scene()` / `build_ai_prompt()` (`contextual.py:76,85`) are refactored to accept a `CinematographyConfig`** and *compose* clauses, **replacing** (not appending to) the hardcoded tail `"Premium editorial photography, soft natural cinematic lighting, shallow depth of field..."`. The current literal string becomes the `Digital Clean + 50mm + f/2.8 + Soft Natural` default so existing behavior is unchanged.
4. **Two new model fields** required: `ColorGrade.grain: float = 0.0` and `ColorGrade.shadow_balance: float = 0.0` (split-tone for true Teal&Orange). Both default to identity so existing plans are unaffected.
5. **Prompt-length guardrail**: assembled cinematography modifier capped at ~3 clauses / ~2 sentences; drop redundant clauses (e.g. if Time-of-Day = Golden Hour, suppress the Golden Hour lighting clause). Implement as `CinematographyConfig.to_prompt_clauses()` returning a de-duped, length-capped list.
6. **The smooth-cut fix is the priority-zero workstream** (Design 2's diagnosis is the most load-bearing). It ships independent of the camera controls.

---

## A. CONTROL MODEL â€” new fields on the render `customization` JSON

Grouped TOGGLES / SELECTS / SLIDERS. Every name is the JSON key the Flutter client sends; the engine deserializes into the configs in section B.

### A.1 TOGGLES (boolean; default in parens)

| JSON key | Default | Notes |
|---|---|---|
| `auto_clean` | `true` | Master switch for the whole cleaning stage. Off â†’ keep full take. |
| `remove_silences` | `true` | Child of auto_clean. |
| `remove_fillers` | `true` | Existing `CleaningConfig.remove_fillers`. |
| `detect_retakes` | `true` | Existing `CleaningConfig.detect_retakes`. |
| `trim_dead_air` | `true` | Existing `CleaningConfig.trim_lead_silence`. |
| `snap_cuts_to_words` | `true` | **NEW** â€” the #1 root-cause fix (cuts land in word gaps). |
| `audio_crossfade` | `true` | **NEW** â€” feather every concat seam (`acrossfade`). |
| `cut_only_sentence_gaps` | `false` | **NEW** â€” never cut mid-phrase. Off keeps current breath-cut behavior. |
| `jl_cut` *(see SELECT note)* | â€” | Modeled as a SELECT (`off/J/L/both`), listed under A.2. |
| `smart_zoom` | `true` | Existing `SynthesisConfig.smart_zoom`. |
| `color_grade` | `true` | Existing `SynthesisConfig.color_grade_to_reference`. |
| `film_grain` | `false` | **NEW** â€” gate the `noise=` render pass independently of grade. |
| `letterbox` | `false` | **NEW** â€” gate the 2.39:1 bar/pad pass independently of `framing`. |
| `captions` | `true` | Gate caption emission in `build_generation_plan`. |
| `ai_broll` | `true` | Gate `build_ai_broll` entirely (real $ cost). |
| `broll_overlay_banner` | `false` | `build_ai_broll(overlay_text=â€¦)` â€” guaranteed-legible caption banner. |
| `watermark` | per-plan | Gate `WatermarkSpec`; respects plan-tier lock. |
| `audio_normalize` | `true` | Existing `GenerationPlan.audio_normalize`. |

### A.2 SELECTS (string enum; default in parens)

| JSON key | Options (value) | Default |
|---|---|---|
| `preset` | `cinematic` / `clean_ugc` / `documentary` / `premium_editorial` / `cinematic_film` / `gritty_doc` / `custom` | `cinematic` |
| `lens` | `24mm` / `35mm` / `50mm` / `85mm` / `100mm_macro` / `anamorphic` | `50mm` |
| `film_stock` | `digital_clean` / `portra_400` / `vision3` / `teal_orange` / `bleach_bypass` / `bw_trix` / `cross_process` | `digital_clean` |
| `lighting` | `high_key` / `soft_natural` / `golden_hour` / `low_key` / `chiaroscuro` / `neon` | `soft_natural` |
| `time_of_day` | `sunrise` / `midday` / `golden_hour` / `blue_hour` / `night` / `unset` | `unset` |
| `camera_angle` | `eye_level` / `low_angle` / `high_angle` / `overhead` / `dutch` / `ots` | `eye_level` |
| `shot_type` | `ecu` / `closeup` / `medium` / `wide` / `aerial` / `ots` | `medium` |
| `framing` | `full_916` / `letterbox_239` / `safe_45` / `punch_in_crop` | `full_916` |
| `broll_motion` | `static` / `zoom_in` / `zoom_out` / `pan_left` / `pan_right` / `pan_up` / `pan_down` | `zoom_in` |
| `broll_quality` | `fast` / `standard` / `ultra` | `standard` |
| `caption_style` | `fade` / `pop` / `karaoke` | `fade` |
| `caption_zone` | `top` / `center` / `bottom` / `auto` | `auto` |
| `jl_cut` | `off` / `j` / `l` / `both` | `off` |
| `cut_sensitivity` | `gentle` / `balanced` / `aggressive` | `balanced` |

> **De-dup note:** Design 1's `film_stock` list and Design 3's `film_look` list are merged into one `film_stock` enum (7 options â€” superset). `karaoke`/`word-by-word` from Design 2 collapse to a single `karaoke` value (word-by-word is karaoke with `max_words=1`). Aperture is a SLIDER (A.3), not duplicated as a select.

### A.3 SLIDERS (numeric; min / max / default)

| JSON key | Min | Max | Default | Engine units |
|---|---|---|---|---|
| `lead_pad_sec` | 0.00 | 0.30 | **0.08** | `CleaningConfig.lead_pad_sec` (NEW) |
| `tail_pad_sec` | 0.00 | 0.40 | **0.15** | `CleaningConfig.tail_pad_sec` (NEW, asymmetric â€” larger) |
| `crossfade_ms` | 0 | 60 | **20** | `acrossfade d=` in builder (NEW) |
| `min_kept_segment_sec` | 0.20 | 1.50 | **0.50** | `CleaningConfig.min_kept_segment_sec` (NEW) |
| `word_snap_radius_sec` | 0.00 | 0.25 | **0.12** | snap search radius (NEW) |
| `zoom_intensity` | 1.00 | 1.20 | **1.12** | `SynthesisConfig.zoom_factor` |
| `filler_aggressiveness` | 0 | 2 | **1** | 0=off,1=default,2=aggressive (`aggressive_fillers` promoted to int) |
| `retake_strictness` | 0.70 | 0.95 | **0.82** | `CleaningConfig.retake_similarity` |
| `aperture` | 1.4 | 16 | **2.8** | f-stop â†’ DOF prompt clause (snap to 1.4/2.8/5.6/11/16) |
| `film_grain_amount` | 0 | 40 | **0** | `ColorGrade.grain` (NEW) â†’ `noise=alls=` |
| `grade_intensity` | 0 | 100 | **70** | scalar on `derive_color_grade()` deltas |
| `broll_density` | 0 | 100 | **50** | windows/min in `plan_broll_windows` + `max_images` cap |
| `watermark_opacity` | 0.0 | 1.0 | **0.85** | `WatermarkSpec.opacity` |

> **De-dup note:** `jl_offset_ms` is implied by `jl_cut` (fixed 80â€“150ms, not user-exposed â€” internal constant `JL_OFFSET_SEC = 0.12`). `j_cut`/`l_cut` are not separate toggles.

---

## B. EXACT ENGINE MAPPING (per control)

### B.1 Smooth-cut / cleaning controls

- `auto_clean=false` â†’ skip steps 1â€“4 in `editor.clean_recording`; EDL = single `TimeRange(0, duration)`.
- `remove_silences` â†’ gates step 1 (`detect_silence_ranges`) + step 2 (`word_gap_silence_ranges`).
- `cut_sensitivity` â†’ bundle preset writing `CleaningConfig`: `gentle` = `silence_db=-45, min_silence_sec=0.45`; `balanced` = `-40 / 0.30`; `aggressive` = `-36 / 0.22`.
- `lead_pad_sec` / `tail_pad_sec` â†’ **replace** the single symmetric `keep_pad_sec` (`config.py:54`). `editor._shrink(r, pad)` (`editor.py:30`) becomes `_shrink_asym(r, lead, tail)`: `start = r.start + lead`, `end = r.end - tail`. (Removed-span start gets `lead`, end gets `tail`; the tail of a *kept* word is protected because the *removed* silence's leading edge is padded by `lead` and its trailing edge by `tail`.)
- `snap_cuts_to_words` â†’ **NEW pass in `editor.clean_recording` between line 110 (`merge_spans`) and line 111 (`snap_ranges`)**: for each keep-range edge, snap to nearest `transcript.words` `.start`/`.end` within `word_snap_radius_sec`, *then* `snap_ranges` frame-snaps. Requires a transcript; no-op without one.
- `cut_only_sentence_gaps` â†’ gates step 2: when on, only emit a `word_gap_silence_range` if the gap sits at an utterance boundary â€” reuse `retakes.segment_utterances(transcript, pause_gap=cfg.min_silence_sec)` and keep only gaps between utterances.
- `min_kept_segment_sec` â†’ **NEW post-process after `invert_to_keep` (editor.py:111)**: drop/merge any kept range shorter than the floor by re-absorbing it into the adjacent removed gap (merge with neighbor keep across the micro-silence).
- `remove_fillers` â†’ `CleaningConfig.remove_fillers` (gates step 3).
- `filler_aggressiveness` â†’ promote `CleaningConfig.aggressive_fillers: bool` to `int` (0/1/2). `0`=skip step 3; `1`=`DEFAULT_FILLERS`; `2`=`DEFAULT_FILLERS | AGGRESSIVE_FILLERS` (the union already wired at `editor.py:86-88`).
- `detect_retakes` â†’ `CleaningConfig.detect_retakes` (gates step 4).
- `retake_strictness` â†’ `CleaningConfig.retake_similarity` (passed to `detect_retakes`).
- `trim_dead_air` â†’ `CleaningConfig.trim_lead_silence`.

### B.2 Audio-seam controls (the "abrupt skip" fix)

- `audio_crossfade` + `crossfade_ms` â†’ **`build_cut_concat` (builder.py:18) and `_build_graph` concat (renderer.py:75-80)**: replace the bare `concat=...:a=1` audio join with pairwise `acrossfade=d=<crossfade_ms/1000>:c1=tri:c2=tri` between consecutive audio segments. Video stays hard-cut (`concat ... v=1` unchanged). When `crossfade_ms=0` or toggle off â†’ current bare concat.
  - **Critical follow-up:** `acrossfade` shortens total by `(N-1)Ã—overlap`. Recompute `output_duration` AFTER crossfades, and re-derive captions/b-roll windows from the final kept ranges, or A/V desyncs over many cuts. `remap_words_to_output` (plan.py:69) must run on the post-crossfade timeline.
- `jl_cut` â†’ **NEW in plan/renderer**: offset the audio seam from the video seam by `JL_OFFSET_SEC=0.12`. `j` = next clip's audio starts under current clip's tail; `l` = current audio runs under next clip's head; `both` = alternate. Implemented by per-clip a/v in/out divergence + the `acrossfade` on audio only.

### B.3 Motion / zoom

- `smart_zoom` â†’ `SynthesisConfig.smart_zoom`; consumed at `plan.py:132` (`zoom = cfg.zoom_factor if (cfg.smart_zoom and i > 0)`).
- `zoom_intensity` â†’ `SynthesisConfig.zoom_factor`; drives `_clip_video_chain` punch-in (renderer.py:33-37). `1.00` = effectively off.
- `broll_motion` â†’ `BrollInsert.motion` (KenBurns enum) consumed by `build_kenburns` (builder.py:129). `static` = `zoom_in` with near-zero amplitude. Override the auto-cycle in `plan_broll_windows`/`place_broll`.
- `framing=punch_in_crop` â†’ bump every `ClipSpec.zoom += 0.04` and raise the hardcoded KenBurns amplitude `0.16` (builder.py:147) to `0.22`.

### B.4 Camera / optics â€” PROMPT clauses (Imagen b-roll only)

All injected by the refactored `build_ai_prompt_scene()`/`build_ai_prompt()` (contextual.py), **replacing** the hardcoded tail. `lens` also biases `ClipSpec.zoom` as a secondary render param to match the b-roll optical crop.

- **`lens`** â†’ prompt clause + `zoom_factor` bias: `24mm`â†’`'shot on a 24mm wide-angle lens, expansive field of view, deep environmental context'` / zoom 1.06; `35mm`â†’`'35mm lens, natural reportage field of view, documentary framing'` / 1.10; `50mm`â†’`'50mm lens, natural human-eye perspective, true-to-life proportions'` / 1.12; `85mm`â†’`'85mm short-telephoto portrait lens, compressed perspective, creamy out-of-focus background, strong subject separation'` / 1.15; `100mm_macro`â†’`'100mm macro lens, extreme close detail, razor-thin focal plane'` / 1.15; `anamorphic`â†’`'vintage anamorphic lenses, 2.0x squeeze, oval bokeh, horizontal blue lens flares, cinematic widescreen'` / 1.14 + force `broll_motion âˆˆ {zoom_in, zoom_out}` (suppress pans). **Honesty constraint:** the A-roll FOV is already shot; `lens` only changes (a) b-roll FOV via prompt and (b) A-roll punch-in aggressiveness â€” it does not re-shoot the A-roll.
- **`aperture`** â†’ DOF prompt clause, appended after the lens clause: `1.4`â†’`'wide open at f/1.4, extremely shallow depth of field, creamy bokeh, dreamy subject isolation'`; `2.8`â†’`'at f/2.8, shallow depth of field, clear subject separation'`; `5.6`â†’`'at f/5.6, moderate depth of field'`; `11`â†’`'at f/11, deep depth of field, most of scene sharp'`; `16`â†’`'at f/16, deep focus, sharp front to back, subtle sunstars'`. **Replaces** the old `'shallow depth of field'` literal (must replace, not append â€” else contradictory prompts).
- **`lighting`** â†’ replaces `'soft natural cinematic lighting'`: `high_key`â†’`'bright high-key lighting, airy white background, minimal shadows'`; `soft_natural`â†’`'soft natural window light, gentle directional shadows'`; `golden_hour`â†’`'warm golden-hour sunlight, long soft shadows, glowing rim light'`; `low_key`â†’`'moody low-key lighting, deep shadows, single soft key, dark negative space'`; `chiaroscuro`â†’`'dramatic chiaroscuro, hard single-source key, Rembrandt lighting'`; `neon`â†’`'colorful neon practicals, magenta and cyan rim lights, nighttime urban glow'`. Secondary: nudge `ColorGrade.brightness/contrast` (high_key +0.06/0.95; low_key âˆ’0.06/1.15).
- **`time_of_day`** â†’ appended clause; `unset` emits nothing. Secondary: bias `ColorGrade.temperature` (sunrise/golden +0.15â€¦0.20; blue_hour/night âˆ’0.15). **Guardrail:** if `golden_hour` time AND `golden_hour` lighting both set, emit only one.
- **`camera_angle`** â†’ prompt clause only (b-roll). `low_angle`â†’`'low-angle shot looking up, heroic perspective'`; `overhead`â†’`'directly overhead top-down flat-lay, 90-degree bird-eye view'`; `dutch`â†’`'dutch angle, canted horizon, dynamic unease'`; `ots`â†’`'over-the-shoulder framing, foreground shoulder soft'`; etc.
- **`shot_type`** â†’ prepended to `{scene}`: `ecu`â†’`'extreme close-up'`; `wide`â†’`'wide establishing shot'`; `aerial`â†’`'aerial drone shot'`; etc. Pairs with `lens`.

### B.5 Film stock â€” DUAL (prompt + real ColorGrade), single source of truth

`film_stock` drives **both** a prompt clause and a `ColorGrade` override from one `FILM_STOCKS` table in `config.py`. `grade_intensity` scales the deltas.

| value | prompt clause (abbrev) | ColorGrade override |
|---|---|---|
| `digital_clean` | `'clean modern digital color, neutral color science'` | leave `derive_color_grade()` untouched |
| `portra_400` | `'Kodak Portra 400, warm skin tones, soft pastel palette, fine grain'` | bright +0.02, contrast 0.95, sat 1.05, temp +0.18 |
| `vision3` | `'Kodak Vision3 500T cinema stock, filmic latitude, rich shadows'` | contrast 1.08, sat 1.04, temp +0.06, gamma 0.97 |
| `teal_orange` | `'Hollywood teal-and-orange grade, warm skin vs cool teal shadows'` | sat 1.18, temp +0.22, **shadow_balance âˆ’0.18** (split-tone) |
| `bleach_bypass` | `'bleach bypass, desaturated, crushed blacks, metallic contrast'` | sat 0.55, contrast 1.25, bright âˆ’0.04 |
| `bw_trix` | `'black and white, Kodak Tri-X 400, deep blacks, classic grain'` | sat 0.0, contrast 1.15, gamma 0.95 |
| `cross_process` | `'cross-processed film, cyan-green shadows, yellow highlights, punchy'` | sat 1.3, temp âˆ’0.10, contrast 1.12, **shadow_balance +0.12** |

**New `ColorGrade.shadow_balance` field** â†’ extend `build_color_grade` (builder.py:89) `colorbalance` to use shadow split: add `sh=<shadow_balance>` style terms (`rs`/`bs` on shadows vs `rh`/`bh` on highlights). Without it, Teal&Orange and Cross-Process are approximations only.

### B.6 Film grain â€” DUAL (composite-wide)

- `film_grain`/`film_grain_amount` â†’ (1) PROMPT: at >0 append `'subtle 35mm film grain, organic analog texture'` (8=`'very fine grain'`, 24=`'visible grain'`, 40=`'heavy analog texture'`). (2) **RENDER: new `ColorGrade.grain` field â†’ insert `noise=alls=<amount>:allf=t+u` node in `_build_graph` AFTER all overlays + subtitles** (renderer.py, after the watermark step, before encode) so A-roll + b-roll + captions share ONE grain field. Net-new node â€” none exists today.

### B.7 Letterbox / aspect â€” RENDER composite

- `letterbox` / `framing=letterbox_239` â†’ **render-side `pad`/`drawbox` pass in `_build_graph`** (top+bottom bars ~13% height each â†’ 2.39:1 inside 1080Ã—1920). **Must be composite-time, not baked into the image** â€” `compose_broll_image` (contextual.py:95) cover-fits + center-crops to 1080Ã—1920 and would crop pre-baked bars. Also: shift caption zone `TextZone.BOTTOM.anchor_y` 0.80â†’0.74 (so captions sit above the lower bar) and reposition the watermark above the bar. Pair the `anamorphic` lens preset with this so the widescreen feel is guaranteed even when the flare doesn't render.
- `framing=safe_45` â†’ centered 4:5 safe-area guides only (no render change).
- `framing=full_916` â†’ no change.

### B.8 B-roll, captions, watermark

- `ai_broll` â†’ gates `build_ai_broll` (contextual.py:127) entirely. Off â†’ `broll=[]` (or fall back to user images via `place_broll`).
- `broll_density` â†’ `plan_broll_windows` window count/min + `max_images` cap in `build_ai_broll`. Surfaces a live cost estimate.
- `broll_quality` â†’ `ImagenGenerator` model via `CADENCE_IMAGEN_MODEL`: `fast`=`imagen-4.0-fast-generate-001` ($0.02), `standard`=`imagen-4.0-generate-001` ($0.04), `ultra`=`imagen-4.0-ultra-generate-001` ($0.06) (costs verified in `imagen.py:18-22`).
- `broll_overlay_banner` â†’ `build_ai_broll(overlay_text=â€¦)`.
- `captions` â†’ gate caption block in `build_generation_plan` (plan.py:144-149) + `.ass` burn.
- `caption_style` â†’ `SynthesisConfig.caption_default_style` â†’ `CaptionStyle` (FADE/POP; `karaoke` is a new value to add). `caption_fade_sec` (0.20) drives fade timing.
- `caption_zone` â†’ `SynthesisConfig.caption_default_zone` â†’ `Caption.zone`; `auto` keeps `_dominant_zone()` (plan.py:110).
- `color_grade` â†’ `SynthesisConfig.color_grade_to_reference` (gates `derive_color_grade`). Off â†’ identity `ColorGrade()`.
- `grade_intensity` â†’ scalar (0â€“1) multiplying `derive_color_grade` brightness/contrast/saturation/temperature **deltas from identity** before `build_color_grade`. Film-stock override applies as an additive offset ON TOP (one place, in plan).
- `watermark` / `watermark_opacity` â†’ `WatermarkSpec` attach in `build_generation_plan` + `WatermarkSpec.opacity` â†’ `build_watermark` `colorchannelmixer aa`. Plan-tier lock respected.
- `audio_normalize` â†’ `GenerationPlan.audio_normalize` (loudnorm at renderer.py:122).

---

## C. SMOOTH-CUT FIX â€” ordered checklist with param values

Diagnosis (verified in code): four concrete causes. Fix in this order; each is independently shippable and testable.

1. **Word-boundary snap (root cause of "cuts off words").** In `editor.clean_recording`, insert a new pass *between* `merge_spans` (editor.py:110) and `snap_ranges` (editor.py:111). For each keep-edge, snap to nearest `Word.start`/`Word.end` within **Â±0.12s** (`word_snap_radius_sec`). Then frame-snap as before. Gate on `snap_cuts_to_words` + transcript present. **TDD:** unit-test that a keep edge falling 0.05s inside a word relocates to that word's boundary.

2. **Asymmetric keep-pad.** Replace symmetric `keep_pad_sec=0.06` with `lead_pad_sec=0.08` / `tail_pad_sec=0.15` (tail larger â€” protects word releases/consonant decay). Refactor `_shrink` â†’ `_shrink_asym(r, lead, tail)`. **TDD:** removed-span trailing edge keeps â‰¥0.15s more of the preceding word than the leading edge does of the following word.

3. **Audio seam crossfade (root cause of "skips abruptly").** In `build_cut_concat` (builder.py) and `_build_graph` audio concat (renderer.py:75-80), replace bare `concat ... a=1` with pairwise **`acrossfade=d=0.020:c1=tri:c2=tri`** (`crossfade_ms=20` default). Video stays hard-cut. **TDD:** assert the filtergraph string contains `acrossfade=d=0.020` for an N-clip plan and that video concat is unchanged.

4. **Recompute duration + re-time captions after crossfade.** After step 3, `output_duration` shrinks by `(Nâˆ’1)Ã—0.020`. Re-run `remap_words_to_output` and `plan_broll_windows` on the post-crossfade timeline. **TDD:** caption end-time of the last chunk â‰¤ recomputed `output_duration`.

5. **Min kept-segment floor.** After `invert_to_keep` (editor.py:111), merge any kept range < **0.50s** (`min_kept_segment_sec`) into its neighbor (absorb the micro-silence). Kills strobe/stutter. **TDD:** no surviving kept range < 0.50s for a synthetic transcript that would otherwise produce a 0.2s fragment.

6. **Cut-only-on-sentence-gaps (opt-in, default off).** When `cut_only_sentence_gaps=true`, gate `word_gap_silence_ranges` to inter-utterance gaps via `segment_utterances(pause_gap=min_silence_sec)`. **TDD:** a 0.4s mid-phrase breath is NOT cut when on, but the 0.8s inter-sentence gap IS.

7. **Smart-zoom frequency cap (anti-nausea).** `plan.py:132` punches in on every clip after the first; on a run of short clips this pulses. Cap: only apply punch-in if clip duration â‰¥ 0.7s, and scale the ramp to clip duration (renderer uses `max(clip.duration, 0.5)` at renderer.py:34). **TDD:** a 0.4s clip gets `zoom=1.0`.

8. **J/L-cut (opt-in).** Offset audio seam from video seam by `JL_OFFSET_SEC=0.12` per `jl_cut` mode. Build last (depends on 3â€“4). **TDD:** for `jl_cut=l`, clip *i*'s audio out-point exceeds its video out-point by 0.12s.

9. **Encoder regression guard.** Every new node (grain `noise=`, letterbox `pad`, split-tone `colorbalance`, `acrossfade`) must survive both the nvenc smoke-test and libx264 fallback in `render_plan`/`_run_render`. A malformed node silently forces the slow software path on every render. **Verify:** run one render on each encoder path after adding nodes.

**Ship defaults:** `silence_db=-40` (gentle `-45`), `min_silence_sec=0.30`, `lead_pad=0.08`, `tail_pad=0.15`, `word_snap_radius=0.12`, `crossfade_ms=20`, `min_kept_segment=0.50`, `retake_similarity=0.82`, `zoom_factor=1.12`, `caption_fade=0.20`, `jl_offset=0.12`.

---

## D. PRESETS (name â†’ exact control values)

Each preset is a **complete bundle** that writes every dependent field (not a label). Editing any Pro control after selecting a preset flips `preset` to `custom` without resetting other edits. Smooth-cut fixes (snap, crossfade, asymmetric pad, min-segment) are ON in all presets â€” they are quality baseline, not style.

| Control | **Cinematic / Premium Editorial** | **Cinematic Film** | **Clean UGC / Clean SaaS** | **Gritty Doc** |
|---|---|---|---|---|
| `lens` | `85mm` | `anamorphic` | `35mm` | `35mm` |
| `aperture` | `2.8` | `2.8` | `5.6` | `4` (â†’5.6 snap) |
| `film_stock` | `portra_400` | `vision3` | `digital_clean` | `bleach_bypass` |
| `lighting` | `soft_natural` | `low_key` | `high_key` | `chiaroscuro` |
| `framing` | `full_916` | `letterbox_239` | `full_916` | `full_916` |
| `film_grain_amount` | `12` | `16` | `0` | `24` |
| `smart_zoom` | on | on | on | on |
| `zoom_intensity` | `1.14` | `1.12` | `1.10` | `1.12` |
| `color_grade` | on | on | off (flat) | on |
| `caption_style` | `pop` | `fade` | `pop` | `fade` |
| `caption_zone` | `bottom` | `bottom` | `bottom` | `bottom` |
| `ai_broll` | on | on | off/minimal | on |
| `broll_quality` | `standard` | `ultra` | `fast` | `standard` |
| `broll_density` | `50` | `40` | `0` | `60` |
| `broll_motion` | `zoom_in` | `zoom_in` | â€” | `pan_right` |
| `auto_clean` | on (non-aggressive) | on | on | on (aggressive) |
| `filler_aggressiveness` | `1` | `1` | `1` | `2` |
| `watermark` | on | on | on | on |

(Designs 1 and 3 proposed overlapping preset sets; merged into 4 canonical presets. `cinematic`/`premium_editorial` are the same bundle; expose 4 chips + Custom.)

---

## E. UI PLAN â€” Simple vs Pro disclosure, widget per control

**Layout (Next.js + Tailwind studio):** persistent left rail = live vertical 9:16 preview + Generate button; right rail = control surface with a Simple/Pro switch at the top.

### Simple mode (default â€” three decisions, then Generate)
1. **Preset** segmented control (`Cinematic | Clean UGC | Documentary | Gritty Doc`).
2. One row of **caption position** chips (`top / center / bottom`).
3. **AI B-Roll** on/off toggle **with a live cost estimate** (`~$0.16, 4 images`).

That is the entire Simple screen. If a first-run user sees sliders, the design failed.

### Pro mode (collapsible accordions, in pipeline order)
1. **CLEAN** â†’ `CleaningConfig`: Auto-Clean master â†’ Remove Silences (+ `cut_sensitivity` slider), Remove Fillers (+ `filler_aggressiveness` slider), Snap-to-Words toggle, Audio Crossfade (+ `crossfade_ms`), Cut-only-Sentence-Gaps toggle, J/L-Cut select, Detect Retakes (+ `retake_strictness`), Trim Dead Air, Lead/Tail Pad sliders, Min-Segment slider.
2. **MOTION** â†’ `SynthesisConfig`: Smart-Zoom toggle + Zoom Intensity slider (greyed when off).
3. **LOOK** â†’ Color Grade toggle + Grade Intensity slider, Film Stock select, Film Grain toggle + amount slider, Letterbox toggle + Framing select.
4. **CAMERA (b-roll optics)** â†’ Lens select, Aperture slider, Lighting select, Time-of-Day select, Camera Angle select, Shot Type select. **All greyed when AI B-Roll is off** (they only rewrite the Imagen prompt â€” showing them active with no b-roll is a lie).
5. **CAPTIONS** â†’ Captions toggle â†’ Style select (greyed when off), Zone select, fade timing (Pro-only).
6. **AI B-ROLL** â†’ master toggle â†’ Motion select, Density slider (+ live $), Quality select (plan-gated, price labels), Overlay Banner toggle.
7. **BRAND** â†’ Watermark toggle (plan-gated) + 5-way Anchor picker + Opacity slider.

### Widget-language rules (consistency)
- **Segmented control** for mutually-exclusive named looks: `preset`, `lens`, `film_stock`, `lighting`, `time_of_day`, `camera_angle`, `shot_type`, `framing`, `broll_motion`, `broll_quality`, `caption_style`, `caption_zone`, `jl_cut`, `cut_sensitivity`.
- **Toggle** for binary on/off: every item in A.1.
- **Slider with WORD tick-labels** (never raw numbers â€” show `Subtle / Default / Punchy`) for intensity: `zoom_intensity`, `lead_pad_sec`, `tail_pad_sec`, `crossfade_ms`, `min_kept_segment_sec`, `filler_aggressiveness`, `retake_strictness`, `aperture`, `film_grain_amount`, `grade_intensity`, `broll_density`, `watermark_opacity`.

### Mandatory UI hygiene (from the pitfalls)
- **Disabled-state discipline:** Zoom Intensity greys when Smart-Zoom off; Aggressive fillers grey when Remove Fillers off; caption style/zone grey when Captions off; ALL b-roll children (incl. Camera accordion) grey when AI B-Roll off.
- **Destructive-control review:** Auto-Clean + children DELETE footage. Always pair with a reviewable "*X spans removed (tap to restore)*" list before final render, driven by `EditDecisionList.removed` (each `RemovedSpan` carries `reason` + `detail` â€” retakes already surface "superseded by utterance #N").
- **Cost transparency:** AI B-Roll Density + Quality show a live `$` estimate BEFORE Generate (`window_count Ã— {0.02/0.04/0.06}`). Respect the `CostLedger` budget cap; surface "budget reached" gracefully (`BudgetExceeded` already stops generation and keeps prior cutaways).
- **Preset â†’ Custom:** editing any Pro control flips the chip to `custom` and preserves all other edits (never re-apply the preset on change).
- **Plan-gating reads as upgrade:** Ultra quality / watermark removal show a small "Pro" badge + tooltip, not an unexplained greyed control.

### Defaults at first run
`preset=cinematic` selected â†’ AI B-Roll on (standard/balanced), captions on (pop, bottom), Auto-Clean on (non-aggressive) with all smooth-cut fixes on, watermark on. A brand-new creator hits Generate with zero config and gets a premium, smooth result.

---

## Files to touch (build order)

| Phase | Files | Change |
|---|---|---|
| **1. Smooth-cut (P0)** | `cleaning/editor.py`, `ffmpeg/builder.py` (`build_cut_concat`), `synthesis/renderer.py` (`_build_graph` concat), `config.py` (`CleaningConfig` new fields), `synthesis/plan.py` (`remap_words_to_output` re-time) | word-snap pass, asymmetric pad, `acrossfade`, min-segment floor, duration recompute |
| **2. Config plumbing** | `config.py` (new `CinematographyConfig` + `FILM_STOCKS` const), `models.py` (`ColorGrade.grain`, `ColorGrade.shadow_balance`) | new dataclass + 2 model fields |
| **3. Camera prompt half** | `synthesis/contextual.py` (`build_ai_prompt`, `build_ai_prompt_scene`, `build_ai_broll`) | accept `CinematographyConfig`, compose+replace clauses, length guardrail |
| **4. Look render half** | `ffmpeg/builder.py` (`build_color_grade` split-tone + new `noise=`/`pad` nodes), `synthesis/renderer.py` (`_build_graph` grain + letterbox passes), `synthesis/plan.py` (`derive_color_grade` + film-stock offset + `grade_intensity`) | grain, letterbox, split-tone |
| **5. API surface** | `api/server.py` (accept the `customization` JSON â†’ deserialize into the 3 configs; thread into `clean_recording`/`build_generation_plan`/`render_plan`) | new request model |

**Confirmed facts grounding this spec:** Imagen is prompt-only (`imagen.py:46`). Current b-roll tail is hardcoded (`contextual.py:88-92`). `keep_pad_sec` is symmetric 0.06 (`config.py:54`, applied `editor.py:30`). Cuts only frame-snap, never word-snap (`editor.py:111`). Audio concat has no crossfade (`builder.py:46`, `renderer.py:77`). No min-segment floor, no grain node, no `shadow_balance` exist today. `zoom` applies when `i>0` (`plan.py:132`). Imagen costs verified (`imagen.py:18-22`). `WatermarkSpec.opacity`, `BrollInsert.motion`, `caption_default_zone/style`, `aggressive_fillers`, `retake_similarity`, `color_grade_to_reference`, `audio_normalize`, `CostLedger`/`BudgetExceeded` all exist and map 1:1.