# cadence-gen full gauntlet: healthz -> tts -> image -> animate (PowerShell — local curl TLS is broken)
param([string]$BaseUrl = "https://cadence-gen-pecphfeyna-uc.a.run.app")

$ErrorActionPreference = "Stop"
$token = (gcloud secrets versions access latest --secret=cadence-gen-token --project builder-ai-497610 | Out-String).Trim()
$hdr = @{ "x-gen-token" = $token; "Content-Type" = "application/json" }
$out = Join-Path $env:TEMP "gen-gauntlet"
New-Item -ItemType Directory -Force $out | Out-Null

function Step($name, $script) {
  $t0 = Get-Date
  try { & $script; $dt = [int]((Get-Date) - $t0).TotalSeconds; Write-Output ("PASS {0} ({1}s)" -f $name, $dt) }
  catch { $dt = [int]((Get-Date) - $t0).TotalSeconds; Write-Output ("FAIL {0} ({1}s): {2}" -f $name, $dt, $_.Exception.Message) }
}

Step "healthz" {
  $r = Invoke-WebRequest -Uri "$BaseUrl/healthz" -UseBasicParsing -TimeoutSec 60
  if ($r.StatusCode -ne 200) { throw "status $($r.StatusCode)" }
  Write-Output "  healthz: $($r.Content)"
}

Step "tts" {
  $body = @{ lines = @(@{ text = "CloutHook generates this voice on our own servers."; voice = "af_heart" }) } | ConvertTo-Json -Depth 4
  Invoke-WebRequest -Uri "$BaseUrl/tts" -Method Post -Headers $hdr -Body $body -OutFile "$out\tts.wav" -TimeoutSec 300
  $f = Get-Item "$out\tts.wav"; if ($f.Length -lt 10000) { throw "wav too small: $($f.Length)" }
  Write-Output "  tts.wav $($f.Length) bytes"
}

Step "image" {
  $body = @{ prompt = "a glowing computer terminal showing colorful code, cinematic lighting, vertical composition"; width = 768; height = 1344; steps = 4 } | ConvertTo-Json
  Invoke-WebRequest -Uri "$BaseUrl/image" -Method Post -Headers $hdr -Body $body -OutFile "$out\image.png" -TimeoutSec 600
  $f = Get-Item "$out\image.png"; if ($f.Length -lt 50000) { throw "png too small: $($f.Length)" }
  $magic = [System.IO.File]::ReadAllBytes("$out\image.png")[0..3] -join ","
  if ($magic -ne "137,80,78,71") { throw "not a PNG: $magic" }
  Write-Output "  image.png $($f.Length) bytes"
}

Step "animate" {
  $b64 = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes("$out\image.png"))
  $body = @{ image_b64 = $b64; prompt = "subtle camera push in, glowing characters on the screen flicker and scroll"; num_frames = 49; fps = 24; width = 704; height = 1280; steps = 3 } | ConvertTo-Json
  Invoke-WebRequest -Uri "$BaseUrl/animate" -Method Post -Headers $hdr -Body $body -OutFile "$out\animate.mp4" -TimeoutSec 900
  $f = Get-Item "$out\animate.mp4"; if ($f.Length -lt 100000) { throw "mp4 too small: $($f.Length)" }
  Write-Output "  animate.mp4 $($f.Length) bytes"
}

Write-Output "outputs: $out"
