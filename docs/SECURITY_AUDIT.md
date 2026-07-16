
## 2026-07-03 — Multi-account posting + Agency tier + long-form faceless (new surfaces)
Focused adversarial review of the NEW authz/billing surfaces (verified in code + live). Standing full 4-lens bar unchanged (prior Wave 2, 2026-07-02).
- **Publish fan-out** (`web/src/app/api/social/publish/route.ts`): every connection loaded `.eq("id",id).eq("user_id",user.id)` BEFORE token decrypt — a client-supplied connectionId can never post to another user's account. Job read is RLS-scoped (user client). PASS.
- **Account cap** (`web/src/app/api/social/oauth/[platform]/start/route.ts`): server-side count of the caller's OWN connections vs `plans.max_accounts_per_platform`; over-cap connects redirect to `account_limit`. Not client-trusted; UI disable is advisory only. PASS.
- **Length gate** (`web/src/app/api/faceless/route.ts`): server-side `403` when `lengthSec > plans.max_length_sec`; fail-closed default 90; enforced before script/TTS spend. `plans.features` remains display-only (correctly not used for enforcement). PASS.
- **Read RPC** `my_social_connections`: SECURITY DEFINER filtered by `auth.uid()` — returns only the caller's rows (id/label; tokens never leave the server). PASS.
- **Schema**: `social_connections` RLS deny-all unchanged; unique now `(user_id,platform,platform_user_id)`. `guard_profiles_privileged_cols` trigger still blocks users editing plan/tokens/limits. PASS.
- **Per-user token budget** (`worker/cadence_worker.py`): animation metered per-user via `spend_tokens` (pre-charged before GPU spend); global `CADENCE_AI_BUDGET_USD` is a cross-user runaway guard only ($500), no longer a per-user starve. PASS.

Result: no cross-tenant, IDOR, or privilege-escalation issue found in the new surfaces. Live rev: cadence-web-00079-lvs, cadence-worker-00054-hps.

## 2026-07-03 (cont.) — Full auth/edge audit + 24h sessions + 2FA + linter hardening
Ran enterprise-security-audit (Supabase linter + live black-box probes + code review). Focus: session lifetime + 2FA.
**LIVE + verified:**
- **24h session time-box** — Supabase Auth → Sessions set to 24h (was 0/never). Users must re-auth daily.
- **TOTP MFA enabled** — Auth → Multi-Factor: TOTP (App Authenticator) = Enabled (users can enroll an authenticator app).
- **Leaked-password protection** — enabled + FUNCTIONALLY verified: signup with `Password123` → `422 weak_password {reasons:["pwned"]}` (HaveIBeenPwned check active).
- **RPC surface locked** (linter 0011/0028/0029) — revoked EXECUTE on notify_signup (trigger fn), rl_bump/my_*(anon); pinned guard_profiles_privileged_cols search_path. Migration `20260703010000` (applied + committed).
- **Data-plane authz** — all `/api/*` data routes 401 unauth; `/admin` 307-redirects unauth; RLS deny-all/fail-closed on all credential/system tables (linter's 10 "RLS no policy" notices are the intended service-role-only vaults).
**Built, NOT yet live (bonus):**
- **SPA security headers** (HSTS/XFO DENY/CSP frame-ancestors/nosniff/Referrer/Permissions) — in `next.config.ts` + `proxy.ts` (committed). The header revision (cadence-web-00081/00082) 500s on boot (env identical to good rev → a code/runtime boot issue, undiagnosed); deferred to a safe follow-up. Site remains healthy on cadence-web-00079-lvs.
**⚠️ Operational trap found:** cadence-web **traffic is PINNED to 00079-lvs** (from the earlier outage rollback). `gcloud run deploy` creates new revisions at 0% traffic — future web deploys must EXPLICITLY route traffic to the new (verified-good) revision, or they silently don't go live. (Routing --to-latest 500'd on the broken header rev → rolled back.)
**Remaining for full 2FA (the chosen scope):** app-side TOTP enrollment UI + aal2 requirement on /admin — a focused build (not done this session).

### 2026-07-16 (cont.) — audit findings FIXED + DEPLOYED
- 🔴 cross-tenant likeness access (avatar) → owner-scoped character + consent (worker `_render_avatar`). LIVE cadence-worker-00055-jgw.
- 🟠 cross-tenant audio via `music_path` → owner-folder guard (worker `_process`). LIVE.
- 🟡 SSRF on gemini `imageUrl` → private/metadata-IP rejection, https+443, no redirects (`lib/gemini.ts`). LIVE cadence-web-00085-vr6.
- 🟡 open redirect (`?next=`) → same-origin guard (`auth-form.tsx`). LIVE.
- Session 24h + MFA + leaked-password: confirmed live (2026-07-03). Commits 9fbbbc1 + follow-ups. Tracked lower-pri (docs above): timing-safe operator compares, rate-limit outliers/analyze+blueprint, affiliate-payout retry edge.
