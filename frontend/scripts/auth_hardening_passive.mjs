/* Anonymous UI checks on the activated prototype; never starts OAuth. */
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { dirname, resolve, join } from "node:path";
import { fileURLToPath } from "node:url";
import { mkdirSync, writeFileSync } from "node:fs";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const evidence = join(root, "evidence/auth-hardening-2026-10-05/activated-browser");
mkdirSync(evidence, { recursive: true });
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const browser = await chromium.launch({ channel: "chrome", headless: true });
const results = [], errors = [];
try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await context.route("**/*", route => {
    const u = new URL(route.request().url());
    if (!["localhost", "127.0.0.1"].includes(u.hostname) || !["13310", "18501"].includes(u.port)) return route.abort();
    return route.continue();
  });
  const page = await context.newPage();
  page.on("pageerror", error => errors.push(error.message));
  for (const [reason, text] of [
    ["state", "That sign-in attempt expired"],
    ["verification", "Google could not verify your identity"],
    ["denied", "Google sign-in was cancelled"],
    ["unavailable", "Sign-in did not complete"],
  ]) {
    await page.goto(`http://localhost:13310/account?auth=error&reason=${reason}`);
    await page.getByRole("alert").filter({ hasText: text }).waitFor();
    assert.equal(await page.getByRole("button", { name: "Sign in with Google", exact: true }).count(), 1);
    results.push({ reason, passed: true });
    if (reason === "state") await page.screenshot({ path: join(evidence, "expired-login.png"), fullPage: true });
  }
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto("http://localhost:13310/account?auth=error&reason=verification");
  await page.getByRole("alert").waitFor();
  const sizes = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  assert.ok(sizes.scroll <= sizes.width, JSON.stringify(sizes));
  await page.screenshot({ path: join(evidence, "verification-mobile-320.png"), fullPage: true });
  assert.deepEqual(errors, []);
  writeFileSync(join(evidence, "results.json"), JSON.stringify({ results, sizes, errors, anonymousOnly: true }, null, 2));
  console.log("Activated frontend: four login-error states, 320px layout, zero browser errors; no OAuth initiated.");
} finally {
  await browser.close();
}
