# Factual-image assets (the guardrail's real-asset library)

When a talking point names a **real, guarded thing** ("Claude Code", "Cowork", "Skills",
or any brand/product term you add), the AI b-roll pipeline shows the **exact real
screenshot** from this folder instead of a generated (hallucinated) image. Result: the
b-roll is 100% accurate to what you're saying, and it burns **0 AI tokens** (the
generator is skipped entirely).

## How it works
- `manifest.json` maps **keywords → a real image file**. Edit it freely.
- The matcher (`cadence/synthesis/factual.py`) is case-insensitive, matches on word
  boundaries, and prefers the **longest phrase** (so `claude code` wins over a bare term).
- An entry whose PNG isn't present yet is **skipped** — the pipeline never breaks while
  the library is being built.
- The worker loads this manifest once per deploy (override the path with the
  `CADENCE_FACTUAL_MANIFEST` env var).

## Naming cadence (shared with the screenshot library)
Each image is named by its canonical **key** so a human and the AI both know which screen
maps to which talking point:

| File | Talking point it covers |
|------|--------------------------|
| `claude-skills.png` | "Claude Skills", "skills tab" |
| `claude-code.png` | "Claude Code", "code tab" |
| `claude-cowork.png` | "Claude Cowork", "cowork" |
| `claude-connectors.png` | "connectors", "add a connector" |
| `claude-mcp.png` | "MCP server", "model context protocol" |
| `claude-permission-prompt.png` | "permission prompt", "allow or deny", "guardrail" |
| `claude-model-picker.png` | "model picker", "Opus or Sonnet" |
| `claude-projects.png` | "Claude Projects" |
| `claude-artifacts.png` | "artifacts" |
| `claude-new-chat.png` | "new chat", "Claude home" |
| `claude-desktop.png` | "Claude Desktop" (generic app window) |

## Adding a new factual asset
1. Drop the screenshot here named `<key>.png` (landscape is fine — it's contain-fit into
   9:16 over a blurred fill, so the whole UI stays visible).
2. Add/extend the matching entry in `manifest.json` (`key`, `asset_path`, `aliases`,
   `variant`, `alt`).
3. Redeploy the worker (the assets ship inside the image).

The master copies of these screenshots also live in **Downloads** and **Google Drive**
(the library the AI pulls from); this folder is the subset shipped into the render worker.
