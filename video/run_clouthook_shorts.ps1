# CloutHook - short-form cron runner (Windows Task Scheduler, twice weekly off-peak).
# Renders ONE standalone product short + posts to TikTok/IG. Kill-switch + lock + log + dry-run gate.
$ErrorActionPreference = "Continue"
$Root    = "C:\Users\Cory\Downloads\Video Analyzer"
$Claude  = "C:\Users\Cory\AppData\Roaming\npm\claude.cmd"
$Prompt  = "C:\Users\Cory\.claude\skills\geo-flywheel\references\clouthook-shorts-cycle.md"
$EnvFile = "C:\Users\Cory\Downloads\Content Engine\.env"     # ANTHROPIC_API_KEY (unattended auth)
$Model   = "claude-sonnet-5"   # claude-opus-4-8 for max reliability
$LogDir  = Join-Path $Root "video\shorts-cron-logs"
$Pause   = Join-Path $Root "video\SHORTS_CRON_PAUSED"   # create to DISABLE (kill-switch)
$GoLive  = Join-Path $Root "video\SHORTS_GO_LIVE"       # create to ARM LIVE posting (absent = render only)
$Lock    = Join-Path $LogDir ".running.lock"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$stamp = Get-Date -Format "yyyy-MM-dd_HHmm"
$Log   = Join-Path $LogDir "shorts_$stamp.log"
function W($m) { "$(Get-Date -Format 'HH:mm:ss')  $m" | Tee-Object -FilePath $Log -Append }

if (Test-Path $Pause) { W "PAUSED (kill-switch present) - skipping."; exit 0 }
if (Test-Path $Lock) {
  $age = (Get-Date) - (Get-Item $Lock).LastWriteTime
  if ($age.TotalHours -lt 3) { W "LOCKED (age $([int]$age.TotalMinutes)m) - skipping."; exit 0 }
  W "stale lock - overriding."
}
New-Item -ItemType File -Path $Lock -Force | Out-Null

if (-not (Test-Path $GoLive)) { $env:GEO_DRYRUN = "1"; W "GEO_DRYRUN=1 (no SHORTS_GO_LIVE - renders + reports, does NOT post). Create $GoLive to arm live." }
else { W "LIVE mode (SHORTS_GO_LIVE present)." }

try {
  Set-Location $Root
  W "START CloutHook shorts (model=$Model, dryrun=$($env:GEO_DRYRUN)). Root=$Root"
  if (-not (Test-Path $Claude)) { W "ERROR: claude CLI not found at $Claude"; exit 1 }
  $m = Select-String -Path $EnvFile -Pattern '^ANTHROPIC_API_KEY=(.+)$'
  if (-not $m) { W "ERROR: ANTHROPIC_API_KEY not found in $EnvFile"; exit 1 }
  $env:ANTHROPIC_API_KEY = $m.Matches[0].Groups[1].Value.Trim().Trim('"').Trim("'")
  Get-Content -Raw $Prompt | & $Claude -p --dangerously-skip-permissions --model $Model --output-format text *>> $Log
  W "DONE (claude exit $LASTEXITCODE). Log: $Log"
}
catch { W "EXCEPTION: $($_.Exception.Message)" }
finally { Remove-Item $Lock -Force -ErrorAction SilentlyContinue }
