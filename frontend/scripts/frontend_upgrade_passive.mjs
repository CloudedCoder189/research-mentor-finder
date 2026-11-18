import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const evidence = join(root, "evidence", "frontend-upgrade-2026-10-05", "activation-browser");
mkdirSync(evidence, { recursive: true });
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const pageErrors = [];
page.on("pageerror", (error) => pageErrors.push(error.message));
await page.route("**/*", (route) => {
  const url = new URL(route.request().url());
  return ["localhost", "127.0.0.1"].includes(url.hostname) && ["13310", "18501"].includes(url.port)
    ? route.continue() : route.abort();
});
const results = [];
try {
  for (const path of ["/", "/privacy", "/for-you", "/researchers/1482"]) {
    const response = await page.goto(`http://localhost:13310${path}`);
    assert.equal(response.status(), 200);
    await page.locator("main").waitFor();
    if (path === "/privacy") await page.getByRole("heading", { name: "Keeping and removing your data" }).waitFor();
    if (path === "/for-you") await page.getByRole("button", { name: "Sign in with Google", exact: true }).waitFor();
    if (path === "/researchers/1482") await page.getByRole("heading", { name: "Anita Sarma", exact: true }).waitFor();
    results.push({ path, status: 200 });
  }
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto("http://localhost:13310/privacy");
  await page.getByRole("heading", { name: "Keeping and removing your data" }).waitFor();
  const width = await page.evaluate(() => ({ content: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  assert.equal(width.content, 320);
  assert.equal(width.scroll, 320);
  await page.screenshot({ path: join(evidence, "privacy-320-viewport.png") });
  assert.deepEqual(pageErrors, []);
  writeFileSync(join(evidence, "results.json"), JSON.stringify({ passed: true, results, width, pageErrors, externalRequestsBlocked: true }, null, 2));
  console.log("Four live routes passed; mobile width 320/320; no uncaught page errors.");
} finally {
  await browser.close();
}
