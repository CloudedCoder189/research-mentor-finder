/* Real browser against real-data isolated DB, AI disabled. Starts/stops only
 * its own servers (:13310 frontend, :18501 API). Requires a production build
 * made with NEXT_PUBLIC_API_BASE_URL=http://localhost:18501, Python .venv,
 * and PLAYWRIGHT_MODULE pointing to an installed Playwright package.
 */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { mkdirSync, createWriteStream, writeFileSync } from "node:fs";
import { dirname, resolve, join } from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as pause } from "node:timers/promises";
import net from "node:net";

const frontRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const root = resolve(frontRoot, "..");
const evidence = join(root, "evidence", "real-acceptance-2026-10-04", process.env.ACCEPTANCE_COMPOSER ? "composer" : (process.env.ACCEPTANCE_RECOVERY ? "recovery" : (process.env.ACCEPTANCE_FOCUS ? "focused" : ".")));
mkdirSync(evidence, { recursive: true });
const python = join(root, ".venv", "Scripts", "python.exe");
const db = join(root, "test-runtime", "real-acceptance-20261004.db");
const API = "http://localhost:18501";
const FRONT = "http://localhost:13310";
const env = { ...process.env, PROFESSOR_DB_PATH: db, APP_MODE: "local",
  AUTH_DEV_EMAIL: `acceptance-${Date.now()}@localhost`, OPENAI_API_KEY: "", AI_EXPLANATIONS: "0", AUTH_ALLOW_DEV_LOGIN: "true",
  AUTH_CLIENT_ID: "", AUTH_CLIENT_SECRET: "", AUTH_COOKIE_SECURE: "false",
  CORS_ORIGINS: FRONT, GMAIL_TOKEN_DIR: join(root, "test-runtime", "gmail-disabled"),
  NEXT_TELEMETRY_DISABLED: "1" };
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const results = [];
const children = [];
const logs = [];
let browser;

async function assertPortFree(port) {
  await new Promise((yes, no) => {
    const server = net.createServer();
    server.on("error", no);
    server.listen(port, "127.0.0.1", () => server.close(yes));
  });
}
function start(command, args, cwd, name) {
  const child = spawn(command, args, { cwd, env, stdio: ["ignore", "pipe", "pipe"] });
  children.push(child);
  const log = createWriteStream(join(evidence, name)); logs.push(log);
  child.stdout.pipe(log); child.stderr.pipe(log);
  return child;
}
async function waitFor(url) {
  const deadline = Date.now() + 45000;
  while (Date.now() < deadline) {
    try { if ((await fetch(url)).ok) return; } catch { /* starting */ }
    await pause(300);
  }
  throw new Error(`Server not ready: ${url}`);
}

try {
  await assertPortFree(13310); await assertPortFree(18501);
  start(python, ["-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", "18501"], root, "browser-api.log");
  start(process.execPath, [join(frontRoot, "node_modules", "next", "dist", "bin", "next"), "start", "-H", "127.0.0.1", "-p", "13310"], frontRoot, "browser-frontend.log");
  await waitFor(`${API}/api/health`); await waitFor(FRONT);
  browser = await chromium.launch({ channel: "chrome", headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  let failWrites = false, failLogout = false, failProfileLoad = false, failExplainOnce = false;
  let delayWrites = false, putCount = 0, failResearcher = false;
  const puts = [];
  await context.route("**/*", async (route) => {
    const request = route.request(); const url = new URL(request.url());
    if (!["localhost", "127.0.0.1"].includes(url.hostname) || !["13310", "18501"].includes(url.port)) return route.abort();
    if (url.pathname === "/api/researchers/1126" && failResearcher) return route.fulfill({status:503,contentType:"application/json",body:'{"detail":"Injected profile failure"}'});
    if (url.pathname === "/api/profile") {
      if (request.method() === "PUT") {
        puts.push(request.postDataJSON()); putCount += 1;
        if (failWrites) return route.fulfill({ status: 503, contentType: "application/json", body: '{"detail":"Injected save failure"}' });
        if (delayWrites) await pause(500);
      } else if (failProfileLoad) return route.fulfill({ status: 503, contentType: "application/json", body: '{"detail":"Injected load failure"}' });
    }
    if (url.pathname === "/api/auth/logout" && failLogout) return route.fulfill({ status: 503, contentType: "application/json", body: '{"detail":"Injected logout failure"}' });
    if (url.pathname === "/api/recommendations/explain" && failExplainOnce) {
      failExplainOnce = false;
      return route.fulfill({ status: 504, contentType: "application/json", body: '{"detail":"Injected explanation failure"}' });
    }
    return route.continue();
  });
  const page = await context.newPage();
  page.setDefaultTimeout(12000);
  async function check(name, action) {
    if(process.env.ACCEPTANCE_FOCUS && !(process.env.ACCEPTANCE_RECOVERY ? /Local sign-in|Profile request|Local outreach/ : /Local sign-in|Public search|Discover filters|Footer pages|Discover pagination|320px|Profile request|Local outreach/).test(name)) return;
    try { await action(); results.push({ name, passed: true }); console.log(`PASS ${name}`); }
    catch (error) {
      results.push({ name, passed: false, error: error.message });
      console.log(`FAIL ${name}: ${error.message}`);
      await page.screenshot({ path: join(evidence, `failure-${results.length}.png`), fullPage: true }).catch(() => {});
    }
  }
  async function api(path, options = {}) {
    const me = await (await context.request.get(`${API}/api/auth/me`)).json();
    return context.request.fetch(`${API}/api${path}`, { ...options, headers: { ...(me.csrf_token ? { "X-CSRF-Token": me.csrf_token } : {}), ...(options.headers || {}) } });
  }
  async function waitSaved() { await page.getByRole("status").filter({ hasText: "Profile ready" }).waitFor(); }

  await check("Local sign-in works against isolated DB", async () => {
    await page.goto(`${FRONT}/account`);
    await page.getByRole("button", { name: "Use the local developer account" }).click();
    await page.getByRole("heading", { name: "Your account", exact: true }).waitFor();
    assert.equal((await (await api("/health")).json()).total_researchers, 2063);
  });
  await check("Required interests cannot be skipped or bypassed", async () => {
    await page.goto(`${FRONT}/account/onboarding`); await waitSaved();
    assert.equal(await page.getByRole("button", { name: "Skip this step for now" }).count(), 0);
    await page.getByRole("button", { name: "Preferences", exact: true }).click();
    await page.getByText("What are you curious about?", { exact: true }).waitFor();
    assert.equal(await page.getByRole("button", { name: "Continue", exact: true }).isEnabled(), false);
  });
  await check("Rapid profile edits persist latest text despite delayed response", async () => {
    await page.getByRole("button", { name: "Machine learning", exact: true }).click();
    await waitSaved();
    await page.getByRole("button", { name: "Skills", exact: true }).click();
    await page.getByRole("button", { name: "Python", exact: true }).click();
    await waitSaved();
    await page.getByRole("button", { name: "Interests", exact: true }).click();
    delayWrites = true;
    await page.getByLabel("Tell us more (optional)").fill("older edit");
    await page.waitForFunction(() => document.body.textContent.includes("Saving changes"));
    await pause(300);
    await page.getByLabel("Tell us more (optional)").fill("latest robotics and vision preparation");
    await waitSaved(); delayWrites = false;
    const saved = await (await api("/profile")).json();
    assert.equal(saved.interest_text, "latest robotics and vision preparation");
    assert.equal(await page.getByLabel("Tell us more (optional)").inputValue(), saved.interest_text);
  });
  await check("Failed final Save stays on onboarding and retry succeeds", async () => {
    await page.getByRole("button", { name: "Preferences", exact: true }).click();
    failWrites = true;
    await page.getByRole("button", { name: "Save profile", exact: true }).click();
    await page.getByRole("alert").filter({ hasText: "could not be saved" }).waitFor();
    assert.ok(page.url().endsWith("/account/onboarding"));
    assert.equal(await page.getByText("Profile saved", { exact: true }).count(), 0);
    failWrites = false;
    await page.getByRole("button", { name: "Save profile", exact: true }).click();
    await page.waitForURL("**/for-you");
    assert.equal((await (await api("/profile")).json()).completed, true);
  });
  await check("Profile survives refresh", async () => {
    await page.goto(`${FRONT}/account/onboarding`); await waitSaved();
    await page.getByRole("button", { name: "Interests", exact: true }).click();
    assert.equal(await page.getByLabel("Tell us more (optional)").inputValue(), "latest robotics and vision preparation");
  });
  await check("Navigating away preserves queued text edit", async () => {
    await page.getByLabel("Tell us more (optional)").fill("preserved across immediate navigation");
    await page.getByRole("navigation", { name: "Primary", exact: true }).getByRole("link", { name: "Discover", exact: true }).click();
    const deadline = Date.now() + 5000; let saved;
    do { saved = await (await api("/profile")).json(); if (saved.interest_text === "preserved across immediate navigation") break; await pause(100); } while (Date.now() < deadline);
    assert.equal(saved.interest_text, "preserved across immediate navigation");
  });
  await check("Profile load error has retry and recovers", async () => {
    failProfileLoad = true; await page.goto(`${FRONT}/for-you`);
    await page.getByRole("alert").filter({ hasText: "Could not load your research profile" }).waitFor();
    failProfileLoad = false; await page.getByRole("button", { name: "Try again", exact: true }).click();
    await page.locator("article").first().waitFor();
  });
  await check("Explanation failure keeps reasons visible and retry recovers", async () => {
    failExplainOnce = true;
    await page.getByRole("button", { name: /Why you match.*Show reasons/ }).first().click();
    await page.getByRole("alert").filter({ hasText: "AI explanation is unavailable" }).waitFor();
    assert.ok(await page.locator(".panel-aqua ul li").count() > 0);
    await page.getByRole("button", { name: "Try explanation again" }).click();
    await page.getByText("Personalizing…", { exact: true }).waitFor({ state: "hidden" });
    await page.getByRole("alert").filter({ hasText: "AI explanation is unavailable" }).waitFor({ state: "hidden" });
    await page.screenshot({ path: join(evidence, "desktop-reasons.png"), fullPage: false });
  });
  await check("Repeated reason toggles do not duplicate requests", async () => {
    let calls = 0; const observe = (request) => { if (request.url().endsWith("/api/recommendations/explain")) calls += 1; };
    page.on("request", observe);
    const toggle = page.getByRole("button", { name: /Why you match/ }).first();
    await toggle.click(); await toggle.click(); await pause(300);
    page.off("request", observe); assert.equal(calls, 0);
  });
  let savedId;
  await check("Real researchers can be saved and filtered", async () => {
    const rows = await (await api("/researchers?limit=25&offset=0")).json();
    const list = rows.results.map(row => row.researcher);
    assert.ok(list?.length > 1, JSON.stringify(Object.keys(rows)));
    savedId = list[0].id;
    assert.equal((await api(`/saved/${savedId}`, {method:"POST"})).status(), 200);
    await page.goto(`${FRONT}/saved`); await page.locator("article").first().waitFor();
    await page.getByRole("button", {name:"More filters",exact:true}).click();
    const status = list[0].verification_status;
    const alternate = ["Verified", "Review", "Failed"].find(x => x !== status);
    await page.getByLabel("Verification",{exact:true}).selectOption(alternate);
    await page.getByText("No saved researchers match these filters",{exact:true}).waitFor();
    await page.getByRole("button",{name:"Reset filters",exact:true}).first().click();
    await page.locator("article").first().waitFor();
  });
  await check("Each filter dropdown contains one Any option", async () => {
    for (const id of ["university", "field", "state", "verification", "opportunity"]) {
      const options = await page.locator(`#filter-${id} option`).allTextContents();
      assert.equal(options.filter((text) => text.startsWith("Any ")).length, 1);
    }
  });
  await check("Repeated save and unsave real record", async () => {
    await page.goto(`${FRONT}/researchers/${savedId}`);
    const unsave=page.getByRole("button",{name:"Remove from saved",exact:true}).first();
    await unsave.click();
    const save=page.getByRole("button",{name:"Save researcher",exact:true}).first();
    await save.waitFor(); await save.click(); await unsave.waitFor(); await unsave.click(); await save.waitFor();
  });
  await check("Public search baselines and 75 unique API results", async () => {
    const ids=[];
    for(const offset of [0,25,50]) {
      const response=await (await api(`/researchers?limit=25&offset=${offset}`)).json();
      ids.push(...response.results.map(row=>row.researcher.id));
    }
    assert.equal(new Set(ids).size,75);
    const baselines={};
    for(const [name,body] of [["robotics",{query:"robotics"}],["robotics_WA",{query:"robotics",state:"Washington"}]]) {
      const response=await api("/search",{method:"POST",data:body});assert.equal(response.status(),200);
      baselines[name]=(await response.json()).total;
    }
    for(const field of ["Computing","Engineering"]) {
      const response=await (await api(`/researchers?field=${field}`)).json();
      baselines[field]=response.total;assert.ok(response.total>0);
    }
    writeFileSync(join(evidence,"search-baselines.json"),JSON.stringify(baselines,null,2));
    assert.equal((await api("/search",{method:"POST",data:{query:"a".repeat(301)}})).status(),422);
    assert.equal((await api("/search",{method:"POST",data:{query:"a".repeat(300)}})).status(),200);
    assert.equal((await api("/researchers/99999999")).status(),404);
  });
  await check("Discover filters and Back retain query and scroll", async () => {
    await page.goto(`${FRONT}/discover?q=robotics&state=Washington`);
    await page.locator("article").first().waitFor();
    assert.equal(await page.getByRole("searchbox").inputValue(),"robotics");
    assert.equal(await page.getByLabel("State",{exact:true}).inputValue(),"Washington");
    await page.evaluate(()=>window.scrollTo(0,700)); await pause(150);
    const scroll=await page.evaluate(()=>window.scrollY);
    await page.locator("article").nth(2).getByRole("link",{name:"View profile"}).click();
    await page.waitForURL("**/researchers/**"); await page.goBack();
    await page.locator("article").first().waitFor(); await pause(600);
    assert.equal(await page.getByRole("searchbox").inputValue(),"robotics");
    assert.ok(Math.abs((await page.evaluate(()=>window.scrollY))-scroll)<5);
  });
  await check("Profile request failure retries successfully", async () => {
    failResearcher=true;await page.goto(`${FRONT}/researchers/1126`);
    await page.getByText(/load this profile/).first().waitFor();
    failResearcher=false;await page.getByRole("button",{name:"Try again",exact:true}).click();
    await page.getByRole("heading",{name:/Umesh Mishra/}).waitFor();
  });
  await check("Local outreach draft persists without Gmail", async () => {
    failResearcher=false; await page.goto(`${FRONT}/outreach/compose/1126`);
    await page.getByLabel("Subject",{exact:true}).waitFor();
    await page.getByLabel("Subject",{exact:true}).fill("Acceptance test draft");
    await page.getByLabel("Message",{exact:true}).fill("Synthetic acceptance message. Do not send.");
    await page.getByLabel("Private notes",{exact:true}).fill("Synthetic private note");
    assert.equal(await page.getByText(/Your draft opens|Why this draft is personalized|Used in this draft/).count(),0);
    await page.getByRole("heading",{name:"Context for your draft",exact:true}).waitFor();
    await page.getByRole("button",{name:"Save draft",exact:true}).click();
    await page.getByText(/Draft saved/).first().waitFor();
    await page.reload();
    await page.waitForFunction(()=>document.querySelector('input[id*="subject"]')?.value === "Acceptance test draft");
    assert.equal(await page.getByLabel("Message",{exact:true}).inputValue(),"Synthetic acceptance message. Do not send.");
    assert.equal(await page.getByLabel("Private notes",{exact:true}).inputValue(),"Synthetic private note");
    await page.getByRole("heading",{name:"Context for your draft",exact:true}).waitFor();
    assert.equal(await page.getByText(/Your draft opens|Why this draft is personalized|Used in this draft/).count(),0);
    await page.screenshot({path:join(evidence,"local-draft.png"),fullPage:true});
  });
  await check("Footer pages render and missing profile shows recovery", async () => {
    for(const path of ["about","privacy","terms","contact"]) {
      await page.goto(`${FRONT}/${path}`);assert.ok(await page.locator("main").innerText());
    }
    await page.goto(`${FRONT}/researchers/99999999`);
    await page.getByText(/This professor is not in the live directory yet/i).first().waitFor();
  });
  await check("Failed logout keeps signed-in state and retry actually ends session", async () => {
    failLogout = true;
    await page.getByRole("button", { name: "Sign out", exact: true }).click();
    await page.getByRole("alert").filter({ hasText: "Could not sign out" }).waitFor();
    assert.equal((await (await api("/auth/me")).json()).authenticated, true);
    assert.equal(await page.getByRole("button", { name: "Sign out", exact: true }).count(), 1);
    failLogout = false;
    await page.getByRole("button", { name: "Sign out", exact: true }).click();
    await page.getByRole("banner").getByRole("button", { name: "Sign in", exact: true }).waitFor();
    assert.equal((await (await api("/auth/me")).json()).authenticated, false);
  });
  await check("Discover pagination and query clearing work", async () => {
    await page.goto(`${FRONT}/discover`); await page.locator("article").nth(24).waitFor();
    await page.getByRole("button", { name: /Load more/i }).click();
    await page.locator("article").nth(49).waitFor();
    const names = await page.locator("article").evaluateAll((rows) => rows.map((row) => row.getAttribute("aria-label")));
    assert.equal(new Set(names).size, 50);
    await page.getByRole("searchbox").fill("unmatchedsyntheticqueryxyz");
    await page.getByRole("button", { name: "Search", exact: true }).click();
    await page.getByText("No researchers match those filters", { exact: true }).waitFor();
    await page.getByRole("button", { name: /Clear search/i }).click();
    assert.equal(await page.getByRole("searchbox").inputValue(), "");
  });
  await check("320px mobile long-query empty state has no horizontal overflow", async () => {
    await page.setViewportSize({ width: 320, height: 720 });
    await page.getByRole("searchbox").fill("a".repeat(100));
    await page.getByRole("button", { name: "Search", exact: true }).click();
    await page.getByText(/No researchers/).first().waitFor();
    await page.getByText(/No researchers/).first().scrollIntoViewIfNeeded();
    const size = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
    assert.ok(size.scroll <= size.width, JSON.stringify(size));
    await page.screenshot({ path: join(evidence, "mobile-320-empty.png"), fullPage: true });
  });
  writeFileSync(join(evidence, "browser-results.json"), JSON.stringify({ database: db, automatedAssertions: results, screenshotsRetained: true, putCount, testProfileWrites: puts.length }, null, 2));
} finally {
  if (browser) await browser.close();
  for (const child of children) { child.kill(); }
  await pause(700);
  for (const log of logs) log.end();
}
if (results.some((result) => !result.passed)) process.exitCode = 1;
