
## 2026-07-03 — Multi-account posting + Agency tier + long-form faceless (new surfaces)
Focused adversarial review of the NEW authz/billing surfaces (verified in code + live). Standing full 4-lens bar unchanged (prior Wave 2, 2026-07-02).
- **Publish fan-out** (`web/src/app/api/social/publish/route.ts`): every connection loaded `.eq("id",id).eq("user_id",user.id)` BEFORE token decrypt — a client-supplied connectionId can never post to another user's account. Job read is RLS-scoped (user client). PASS.
- **Account cap** (`web/src/app/api/social/oauth/[platform]/start/route.ts`): server-side count of the caller's OWN connections vs `plans.max_accounts_per_platform`; over-cap connects redirect to `account_limit`. Not client-trusted; UI disable is advisory only. PASS.
- **Length gate** (`web/src/app/api/faceless/route.ts`): server-side `403` when `lengthSec > plans.max_length_sec`; fail-closed default 90; enforced before script/TTS spend. `plans.features` remains display-only (correctly not used for enforcement). PASS.
- **Read RPC** `my_social_connections`: SECURITY DEFINER filtered by `auth.uid()` — returns only the caller's rows (id/label; tokens never leave the server). PASS.
- **Schema**: `social_connections` RLS deny-all unchanged; unique now `(user_id,platform,platform_user_id)`. `guard_profiles_privileged_cols` trigger still blocks users editing plan/tokens/limits. PASS.
- **Per-user token budget** (`worker/cadence_worker.py`): animation metered per-user via `spend_tokens` (pre-charged before GPU spend); global `CADENCE_AI_BUDGET_USD` is a cross-user runaway guard only ($500), no longer a per-user starve. PASS.

Result: no cross-tenant, IDOR, or privilege-escalation issue found in the new surfaces. Live rev: cadence-web-00079-lvs, cadence-worker-00054-hps.
