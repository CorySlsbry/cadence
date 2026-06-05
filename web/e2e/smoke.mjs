// End-to-end browser test: signup -> create project -> upload reference + footage
// -> generate -> worker renders -> result video appears. Exercises the whole SaaS.
import { chromium } from "playwright";
import path from "node:path";

const BASE = process.env.BASE_URL || "http://localhost:3000";
const ROOT = path.resolve(process.cwd(), "..");
const REF = path.join(ROOT, "engine", "output", "_reference.mp4");
const REC = path.join(ROOT, "engine", "output", "_aroll.mp4");
const BROLL = path.join(ROOT, "engine", "output", "broll_1.png");
const email = `e2e_${Date.now()}@test.dev`;

function log(...a) { console.log("[e2e]", ...a); }

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: 1280, height: 1000 } });
const page = await ctx.newPage();
page.on("console", (m) => { if (m.type() === "error") console.log("[browser-error]", m.text()); });

let ok = false;
try {
  // 1) Signup
  await page.goto(`${BASE}/signup`, { waitUntil: "networkidle" });
  await page.getByLabel("Name").fill("E2E Tester");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("Password123!");
  await page.getByRole("button", { name: "Create account" }).click();
  await page.waitForURL("**/dashboard", { timeout: 20000 });
  log("signed up + on dashboard:", email);

  // 2) New project
  await page.getByRole("button", { name: /New project|Create your first project/ }).first().click();
  await page.waitForURL("**/project/**", { timeout: 20000 });
  log("project created:", page.url());

  // 3) Upload reference (first video input)
  await page.locator('input[type=file][accept="video/*"]').first().setInputFiles(REF);
  await page.getByText("Reference ready").waitFor({ timeout: 30000 });
  log("reference uploaded");

  // 4) Switch footage to Upload tab, upload the raw clip (last video input)
  await page.getByRole("button", { name: "Upload", exact: true }).click();
  await page.locator('input[type=file][accept="video/*"]').last().setInputFiles(REC);
  // The Generate button only enables once the recording path is set.
  await page.getByRole("button", { name: "Generate premium video" }).waitFor({ state: "visible", timeout: 30000 });
  await page.waitForFunction(() => {
    const b = [...document.querySelectorAll("button")].find((x) => x.textContent?.includes("Generate premium video"));
    return b && !b.disabled;
  }, { timeout: 30000 });
  log("footage uploaded");

  // 4b) Add a b-roll image (animated cutaway)
  await page.locator('input[type=file][accept="image/*"]').setInputFiles(BROLL);
  await page.getByRole("button", { name: /added/ }).waitFor({ timeout: 30000 });
  log("b-roll image added");

  // 5) Generate
  await page.getByRole("button", { name: "Generate premium video" }).click();
  log("render requested; waiting for worker…");

  // 6) Wait for the result (Download link appears when the signed URL is ready)
  await page.getByRole("link", { name: "Download" }).waitFor({ timeout: 180000 });
  const videoSrc = await page.locator("video").last().getAttribute("src");
  if (!videoSrc || !videoSrc.includes("/storage/")) throw new Error(`unexpected result src: ${videoSrc}`);
  log("RESULT READY:", videoSrc.slice(0, 80) + "…");

  await page.screenshot({ path: "e2e/result.png" });
  ok = true;
  console.log("\nE2E SMOKE: PASS");
} catch (err) {
  console.error("\nE2E SMOKE: FAIL —", err.message);
  await page.screenshot({ path: "e2e/failure.png" }).catch(() => {});
} finally {
  await browser.close();
  process.exit(ok ? 0 : 1);
}
