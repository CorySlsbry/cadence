// Cloud Run APPENDS the real client IP to the END of X-Forwarded-For and preserves whatever the
// client sent, so the LEFTMOST entry is attacker-controlled (it can be spoofed to dodge per-IP rate
// limits). Trust only the last hop.
export function clientIp(req: Request): string {
  const xff = (req.headers.get("x-forwarded-for") || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  return xff[xff.length - 1] || req.headers.get("x-real-ip") || "unknown";
}
