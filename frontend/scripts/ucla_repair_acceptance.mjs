/* Real browser/API checks over a disposable copy of the repaired dataset.
 * Owns only :18502 API and :13312 frontend; paid AI and OAuth/Gmail disabled.
 */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { mkdirSync, readFileSync, writeFileSync, createWriteStream } from "node:fs";
import { dirname, resolve, join } from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as pause } from "node:timers/promises";
import net from "node:net";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const front = join(root, "test-runtime", "ucla-review-frontend");
const evidence = join(root, "evidence", "ucla-expanded-repair-2026-10-05", "browser");
const logs = join(root, "test-runtime", "ucla-browser-logs");
mkdirSync(evidence, { recursive: true }); mkdirSync(logs, { recursive: true });
const API = "http://localhost:18502", FRONT = "http://localhost:13312";
const env = { ...process.env, PROFESSOR_DB_PATH: join(root, "test-runtime", "ucla-expanded-browser-20261005.db"),
  OPENAI_API_KEY: "", AI_EXPLANATIONS: "0", APP_MODE: "local", AUTH_ALLOW_DEV_LOGIN: "true",
  AUTH_DEV_EMAIL: `ucla-repair-${Date.now()}@localhost`, AUTH_CLIENT_ID: "", AUTH_CLIENT_SECRET: "",
  AUTH_COOKIE_SECURE: "false", CORS_ORIGINS: FRONT, GMAIL_CLIENT_ID: "", GMAIL_CLIENT_SECRET: "",
  GMAIL_TOKEN_DIR: join(root, "test-runtime", "ucla-gmail-disabled"), NEXT_TELEMETRY_DISABLED: "1" };
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const results = [], children = [], errors = [];
let browser;

async function free(port) {
  await new Promise((yes, no) => { const server = net.createServer(); server.on("error", no);
    server.listen(port, "127.0.0.1", () => server.close(yes)); });
}
function start(command, args, cwd, name) {
  const child = spawn(command, args, { cwd, env, windowsHide: true, stdio: ["ignore", "pipe", "pipe"] });
  children.push(child); const log = createWriteStream(join(logs, name));
  child.stdout.pipe(log); child.stderr.pipe(log); return child;
}
async function ready(url) {
  for (let attempt = 0; attempt < 100; attempt++) {
    try { if ((await fetch(url)).ok) return; } catch { /* starting */ }
    await pause(300);
  }
  throw new Error(`Test server unavailable: ${url}`);
}
try {
  await free(18502); await free(13312);
  start(join(root, ".venv/Scripts/python.exe"), ["-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", "18502", "--no-access-log"], root, "api.log");
  start(process.execPath, [join(front, "node_modules/next/dist/bin/next"), "start", "-H", "127.0.0.1", "-p", "13312"], front, "frontend.log");
  await ready(`${API}/api/health`); await ready(FRONT);
  browser = await chromium.launch({ channel: "chrome", headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage(); page.setDefaultTimeout(15000);
  page.on("pageerror", error => errors.push(error.message));
  let failProfile = false;
  await context.route("**/*", async route => {
    const url = new URL(route.request().url());
    if (!["localhost", "127.0.0.1"].includes(url.hostname)) return route.abort();
    if (failProfile && url.pathname === "/api/researchers/129") return route.fulfill({ status: 503, contentType: "application/json", body: '{"detail":"Injected profile failure"}' });
    return route.continue();
  });
  async function check(name, action) {
    try { await action(); results.push({ name, passed: true }); console.log(`PASS ${name}`); }
    catch (error) { results.push({ name, passed: false, error: error.message }); console.log(`FAIL ${name}: ${error.message}`);
      await page.screenshot({ path: join(evidence, `failure-${results.length}.png`), fullPage: true }).catch(() => {}); }
  }
  async function api(path, options = {}) {
    const me = await (await context.request.get(`${API}/api/auth/me`)).json();
    return context.request.fetch(`${API}/api${path}`, { ...options, headers: { ...(me.csrf_token ? { "X-CSRF-Token": me.csrf_token } : {}) } });
  }
  const university = "University of California, Los Angeles";
  const sourceReviews = JSON.parse(readFileSync(join(root, "evidence/ucla-expanded-repair-2026-10-05/expanded-staging.json"))).source_reviews;
  await check("All 50 corrected profiles match the reviewed names, titles and departments", async () => {
    for (const expected of sourceReviews) {
      const response = await api(`/researchers/${expected.id}`); assert.equal(response.status(), 200);
      const { researcher } = await response.json(); assert.equal(researcher.name, expected.name);
      assert.equal(researcher.title, expected.title); assert.equal(researcher.department, expected.departments.join("; "));
      assert.ok(researcher.ai_summary.length > 0);
    }
  });
  await check("Joint appointments remain in both broad and concrete API filters", async () => {
    for (const field of ["Computing", "Engineering", "Computer Science", "Electrical and Computer Engineering"]) {
      const response = await api(`/researchers?university=${encodeURIComponent(university)}&field=${encodeURIComponent(field)}&limit=100`);
      assert.equal(response.status(), 200); const data = await response.json();
      assert.ok(data.results.some(row => row.researcher.id === 129), field);
    }
  });
  await check("Pagination and recommendation results contain unique IDs", async () => {
    const ids = [];
    for (const offset of [0, 25, 50]) { const data = await (await api(`/researchers?offset=${offset}&limit=25`)).json(); ids.push(...data.results.map(row => row.researcher.id)); }
    assert.equal(new Set(ids).size, 75);
    const response = await api("/recommendations", { method: "POST", data: { profile: { interests: ["Machine learning"], skills: ["Python"] }, filters: { university }, limit: 50 } });
    assert.equal(response.status(), 200); const data = await response.json();
    assert.ok(data.results.length > 0); assert.equal(new Set(data.results.map(row => row.researcher.id)).size, data.results.length);
  });
  await check("Desktop profile displays both documented appointments", async () => {
    await page.goto(`${FRONT}/researchers/129`); await page.getByRole("heading", { name: "Jonathan Kao", exact: true }).waitFor();
    assert.ok((await page.locator("body").innerText()).includes("Electrical and Computer Engineering; Computer Science"));
    await page.screenshot({ path: join(evidence, "desktop-joint-profile.png"), fullPage: true });
  });
  await check("Future appointment qualifier remains visible", async () => {
    await page.goto(`${FRONT}/researchers/141`); await page.getByRole("heading", { name: "Hanrui Wang", exact: true }).waitFor();
    await page.getByText("Assistant Professor (Starting November 1, 2027)", { exact: true }).waitFor();
    assert.equal((await (await api("/researchers/141")).json()).researcher.verification_status, "Review");
    await page.getByText("In review", { exact: true }).waitFor();
    await page.screenshot({ path: join(evidence, "future-appointment.png"), fullPage: false });
  });
  await check("Local sign-in and synthetic student profile work", async () => {
    await page.goto(`${FRONT}/account`); await page.getByRole("button", { name: "Use the local developer account" }).click();
    await page.getByRole("heading", { name: "Your account", exact: true }).waitFor();
    assert.equal((await api("/profile", { method: "PUT", data: { education_level: "college", interests: ["Machine learning"], skills: ["Python"], completed: true } })).status(), 200);
  });
  await check("Saved joint profile survives both offered department filters", async () => {
    assert.equal((await api("/saved/129", { method: "POST" })).status(), 200);
    await page.goto(`${FRONT}/saved`); await page.getByRole("article", { name: "Jonathan Kao" }).waitFor();
    await page.getByRole("button", { name: "More filters", exact: true }).click();
    for (const field of ["Computer Science", "Electrical and Computer Engineering"]) {
      await page.getByLabel("Field", { exact: true }).selectOption(field);
      await page.getByRole("article", { name: "Jonathan Kao" }).waitFor();
    }
    await page.screenshot({ path: join(evidence, "saved-joint-filter.png"), fullPage: true });
  });
  await check("Recommendations and repeated Show Reasons work with paid AI disabled", async () => {
    await page.goto(`${FRONT}/for-you`); await page.locator("article").first().waitFor();
    const toggle = page.getByRole("button", { name: /Why you match/ }).first();
    await toggle.click(); await page.getByText("Personalizing…", { exact: true }).waitFor({ state: "hidden" });
    assert.ok(await page.locator(".panel-aqua li").count() > 0);
    let calls = 0; const observe = request => { if (request.url().includes("/api/recommendations/explain")) calls++; };
    page.on("request", observe); await toggle.click(); await toggle.click(); await pause(300); page.off("request", observe);
    assert.equal(calls, 0);
    await page.screenshot({ path: join(evidence, "recommendation-reasons.png"), fullPage: false });
  });
  await check("Injected profile error can recover", async () => {
    failProfile = true; await page.goto(`${FRONT}/researchers/129`); await page.getByText(/load this profile/).first().waitFor();
    failProfile = false; await page.getByRole("button", { name: "Try again", exact: true }).click();
    await page.getByRole("heading", { name: "Jonathan Kao", exact: true }).waitFor();
  });
  await check("320px joint profile has no horizontal overflow", async () => {
    await page.setViewportSize({ width: 320, height: 844 }); await page.goto(`${FRONT}/researchers/129`);
    await page.getByRole("heading", { name: "Jonathan Kao", exact: true }).waitFor();
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth));
    await page.screenshot({ path: join(evidence, "mobile-joint-profile.png"), fullPage: true });
  });
  await check("320px original 100-character Discover query has no overflow", async () => {
    await page.goto(`${FRONT}/discover?q=${"x".repeat(100)}`);
    await page.getByText(/No researchers found|No researchers match/).first().waitFor();
    await page.getByText(/No researchers found|No researchers match/).first().scrollIntoViewIfNeeded();
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth));
    await page.screenshot({ path: join(evidence, "mobile-discover-edge.png"), fullPage: true });
  });
  assert.deepEqual(errors, []);
  writeFileSync(join(evidence, "results.json"), JSON.stringify({ results, browser_errors: errors, paid_ai_calls: 0, database_scope: "Disposable repaired browser-test copy", screenshots: "Captured for separate visual inspection" }, null, 2));
  if (results.some(result => !result.passed)) process.exitCode = 1;
} finally {
  await browser?.close(); for (const child of children.reverse()) child.kill();
}
