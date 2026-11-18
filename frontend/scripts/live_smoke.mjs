#!/usr/bin/env node
/*
 * Phase 6 live-integration smoke:
 *  - starts the FastAPI backend on :8000 and `next start` on :3210
 *  - signs in through the dev-login endpoint, then exercises authenticated
 *    public + protected APIs (profile, saved, outreach, recommendations)
 *  - asserts Discover + a live professor profile render from the frontend
 * Requires a successful `npm run build` first.
 */
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as sleep } from "node:timers/promises";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const repo = join(root, "..");
const FRONT_PORT = 3210;
const API_PORT = 8000;
const FRONT = `http://127.0.0.1:${FRONT_PORT}`;
const API = `http://127.0.0.1:${API_PORT}`;

const LIVE_DB = resolve(join(repo, "data", "professors.db"));
const DB_ENV = "PROFESSOR_DB_PATH";
// Set by the harness to the id of a sentinel row that exists ONLY in the
// isolated copy, proving at runtime that the backend is not on the live DB.
const SENTINEL_ENV = "SMOKE_SENTINEL_ID";
const SENTINEL_EMAIL = "smoke-sentinel@isolated.invalid";

/**
 * Refuse to run unless an isolated database copy was configured explicitly.
 * This test writes professor outreach, profiles and sessions, so it must never
 * be able to touch the live database.
 */
function resolveIsolatedDb() {
  const raw = process.env[DB_ENV];
  if (!raw || !raw.trim()) {
    throw new Error(
      `${DB_ENV} is not set. The live smoke test writes rows, so it refuses to ` +
        `run against the default database. Point ${DB_ENV} at an isolated copy first.`,
    );
  }
  const target = resolve(repo, raw);
  if (!existsSync(target)) {
    throw new Error(`${DB_ENV} points at a missing file: ${target}`);
  }
  if (target === LIVE_DB) {
    throw new Error(
      `refusing to run: ${DB_ENV} resolves to the live database (${target}). ` +
        `Use a copy instead.`,
    );
  }
  return target;
}

function pythonExe() {
  return join(repo, "venv", "Scripts", "python.exe");
}

async function waitFor(url, timeoutMs = 45000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const res = await fetch(url, { redirect: "follow" });
      if (res.status >= 200 && res.status < 500) return;
    } catch {
      /* not ready yet */
    }
    await sleep(1000);
  }
  throw new Error(`Server did not become ready in time: ${url}`);
}

async function expectJson(path, predicate) {
  const res = await fetch(`${API}${path}`);
  if (res.status !== 200) throw new Error(`${path} -> HTTP ${res.status}`);
  const body = await res.json();
  const detail = predicate(body);
  if (detail) throw new Error(`${path} -> ${detail}`);
  return body;
}

const children = [];
let isolatedDb = "";

async function startApi() {
  const child = spawn(
    pythonExe(),
    ["-m", "uvicorn", "api.main:app", "--port", String(API_PORT), "--host", "127.0.0.1"],
    {
      cwd: repo,
      stdio: ["ignore", "ignore", "ignore"],
      env: { ...process.env, [DB_ENV]: isolatedDb },
    },
  );
  children.push(child);
}

async function startFrontend() {
  const child = spawn(
    process.execPath,
    [join(root, "node_modules", "next", "dist", "bin", "next"), "start", "-p", String(FRONT_PORT)],
    { cwd: root, stdio: ["ignore", "ignore", "ignore"] },
  );
  children.push(child);
}

let failed = false;
try {
  // Refuse before spawning anything if no isolated database was configured.
  isolatedDb = resolveIsolatedDb();
  console.log(`isolated database: ${isolatedDb}`);
  console.log(`live database (must be untouched): ${LIVE_DB}`);

  await startApi();
  await waitFor(`${API}/api/health`);

  await expectJson("/api/health", (b) =>
    b.status !== "ok" ? "unexpected health payload" : null,
  );

  // Prove at runtime that the serving process really reads the isolated copy.
  const sentinelId = Number(process.env[SENTINEL_ENV] || "");
  if (!sentinelId) {
    throw new Error(
      `${SENTINEL_ENV} is not set; cannot prove the backend is on the isolated copy.`,
    );
  }
  await expectJson(`/api/researchers/${sentinelId}`, (b) =>
    b.researcher?.email !== SENTINEL_EMAIL
      ? `sentinel row missing (got ${b.researcher?.email}); backend is not on the isolated database`
      : null,
  );
  console.log(`sentinel confirmed: backend serves the isolated copy`);

  // Sign in via the local developer account.
  const loginRes = await fetch(`${API}/api/auth/dev-login`, { method: "POST" });
  if (loginRes.status !== 200) throw new Error("/api/auth/dev-login -> HTTP " + loginRes.status);
  const loginBody = await loginRes.json();
  if (!loginBody.authenticated || !loginBody.user?.user_id) {
    throw new Error("dev-login did not return an authenticated user");
  }
  if (!loginBody.csrf_token) throw new Error("dev-login did not return a csrf token");
  const csrf = loginBody.csrf_token;
  let cookie = "";
  const setCookieHeaders = loginRes.headers.getSetCookie?.() ?? [];
  if (setCookieHeaders.length) {
    cookie = setCookieHeaders[0].split(";")[0];
  } else {
    const raw = loginRes.headers.get("set-cookie") ?? "";
    cookie = raw.split(";")[0];
  }
  if (!cookie) throw new Error("dev-login did not set a session cookie");

  const authed = (path, { method = "GET", body } = {}) =>
    fetch(`${API}${path}`, {
      method,
      headers: {
        Cookie: cookie,
        ...(method === "GET" ? {} : { "X-CSRF-Token": csrf }),
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });

  const me = await (await authed("/api/auth/me")).json();
  if (me.authenticated !== true) throw new Error("/api/auth/me reported not authenticated");

  // Authenticated student profile round-trip.
  const profilePayload = {
    interests: ["Machine learning"],
    interest_text: "applied deep learning for visual recognition",
    skills: ["Python"],
    experience: [],
    coursework: [],
    education_level: "university",
    preferences: { locations: [], university_types: [], support_level: "", remote_ok: false },
    completed: true,
  };
  const putProfile = await authed("/api/profile", { method: "PUT", body: profilePayload });
  if (putProfile.status !== 200) throw new Error("/api/profile PUT -> HTTP " + putProfile.status);
  const putProfileBody = await putProfile.json();
  if (putProfileBody.education_level !== "university") {
    throw new Error("profile PUT did not persist education level");
  }
  const getProfileBody = await (await authed("/api/profile")).json();
  if (!getProfileBody.interests.includes("Machine learning") || getProfileBody.completed !== true) {
    throw new Error("profile GET did not round-trip the saved profile");
  }

  // Gmail status is a protected endpoint now.
  const gmail = await (await authed("/api/gmail/status")).json();
  if (typeof gmail.connected !== "boolean" || typeof gmail.account_email !== "string") {
    throw new Error("unexpected Gmail status payload");
  }

  const options = await expectJson("/api/meta/options", (b) =>
    !Array.isArray(b.universities) || b.universities.length === 0
      ? "no university options returned"
      : null,
  );
  if (!options.total_researchers || options.total_researchers < 1000) {
    throw new Error(`unexpected researcher count ${options?.total_researchers}`);
  }

  const resBrowse = await fetch(`${API}/api/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (resBrowse.status !== 200) throw new Error("/api/search browse -> HTTP " + resBrowse.status);
  const search = await resBrowse.json();
  if (search.total < 1 || search.results.length < 1) {
    throw new Error("browse search returned no results");
  }

  const res = await fetch(`${API}/api/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query: "machine learning", limit: 1 }),
  });
  if (res.status !== 200) throw new Error("/api/search POST -> HTTP " + res.status);
  const ranked = await res.json();
  if (!ranked.total || !ranked.results[0]?.match) {
    throw new Error("ranked search returned no match detail");
  }

  const firstId = search.results[0].researcher.id;
  await expectJson(`/api/researchers/${firstId}`, (b) =>
    b.researcher?.id !== firstId ? "profile id mismatch" : null,
  );

  let res404 = await fetch(`${API}/api/researchers/999999999`);
  if (res404.status !== 404) throw new Error("missing professor did not return 404");

  // Anonymous access to protected state must be rejected.
  const anonSaved = await fetch(`${API}/api/saved`);
  if (anonSaved.status !== 401) throw new Error("anonymous /api/saved did not return 401");

  const resSaved = await authed("/api/saved");
  if (resSaved.status !== 200) throw new Error("/api/saved GET -> HTTP " + resSaved.status);
  const savedBody = await resSaved.json();
  if (!Array.isArray(savedBody.results)) throw new Error("/api/saved did not return a results array");

  const resSave = await authed(`/api/saved/${firstId}`, { method: "POST" });
  if (resSave.status !== 200) throw new Error("/api/saved POST -> HTTP " + resSave.status);
  const saveBody = await resSave.json();
  if (saveBody.saved !== true) throw new Error("/api/saved POST did not report saved=true");

  const savedAfter = await (await authed("/api/saved")).json();
  if (!savedAfter.results.some((row) => row.researcher.id === firstId)) {
    throw new Error("saved list does not include the just-saved researcher");
  }

  const outreachAfterSave = await (await authed("/api/outreach")).json();
  if (!outreachAfterSave.results.some((row) => row.researcher.id === firstId)) {
    throw new Error("outreach list does not include the just-saved researcher");
  }

  const patchRes = await authed(`/api/outreach/${firstId}`, {
    method: "PATCH",
    body: { outreach_status: "Drafted", notes: "live smoke draft" },
  });
  if (patchRes.status !== 200) throw new Error("/api/outreach PATCH -> HTTP " + patchRes.status);
  const patched = await patchRes.json();
  if (patched.outreach.status !== "Drafted") {
    throw new Error(`unexpected status after PATCH: ${patched.outreach.status}`);
  }

  const one = await (await authed(`/api/outreach/${firstId}`)).json();
  if (one.outreach.notes !== "live smoke draft") {
    throw new Error("outreach detail did not persist notes");
  }

  // Phase 7: sync + follow-up drafting guard-rails are hermetic (no live Gmail).
  const syncOne = await authed(`/api/outreach/${firstId}/gmail-sync`, { method: "POST" });
  if (syncOne.status !== 200) throw new Error("/api/outreach gmail-sync -> HTTP " + syncOne.status);
  const syncOneBody = await syncOne.json();
  if (syncOneBody.professor_id !== firstId || typeof syncOneBody.checked_at !== "string") {
    throw new Error("unexpected gmail-sync payload");
  }
  if (syncOneBody.linked !== false) {
    throw new Error("expected unlinked gmail-sync for a row with no Gmail thread");
  }
  if (syncOneBody.outreach?.outreach?.status !== "Drafted") {
    throw new Error("gmail-sync unexpectedly changed the row");
  }

  const syncAll = await authed("/api/outreach/gmail-sync", { method: "POST" });
  if (syncAll.status !== 200) {
    throw new Error("/api/outreach gmail-sync all -> HTTP " + syncAll.status);
  }
  const syncAllBody = await syncAll.json();
  if (
    typeof syncAllBody.checked !== "number" ||
    !Array.isArray(syncAllBody.errors) ||
    !Array.isArray(syncAllBody.results)
  ) {
    throw new Error("unexpected gmail-sync-all payload");
  }

  const followUp = await authed(`/api/outreach/${firstId}/follow-up-draft`, {
    method: "POST",
  });
  if (followUp.status !== 422) {
    throw new Error("follow-up-draft for an unsent row should be 422, got HTTP " + followUp.status);
  }
  const followUpBody = await followUp.json();
  if (!String(followUpBody.detail ?? "").toLowerCase().includes("there is no record")) {
    throw new Error("follow-up-draft did not explain why it is unavailable");
  }

  const undoStatus = await authed(`/api/outreach/${firstId}`, {
    method: "PATCH",
    body: {
      outreach_status: "Not contacted",
      notes: "",
      email_to: "",
      email_subject: "",
      email_body: "",
    },
  });
  if (undoStatus.status !== 200) throw new Error("/api/outreach cleanup PATCH -> HTTP " + undoStatus.status);

  const unsaveRes = await authed(`/api/saved/${firstId}`, { method: "DELETE" });
  if (unsaveRes.status !== 200) throw new Error("/api/saved DELETE -> HTTP " + unsaveRes.status);

  const unsaved = await unsaveRes.json();
  if (unsaved.saved !== false) throw new Error("/api/saved DELETE did not report saved=false");

  const recProfile = {
    interests: ["Machine learning"],
    interest_text: "applied deep learning for visual recognition",
    skills: ["Python"],
    experience: [],
    coursework: [],
  };
  const recRes = await fetch(`${API}/api/recommendations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile: recProfile, limit: 5 }),
  });
  if (recRes.status !== 200) throw new Error("/api/recommendations -> HTTP " + recRes.status);
  const recBody = await recRes.json();
  if (!recBody.total || !recBody.results.length) {
    throw new Error("recommendations returned no matches");
  }
  for (const row of recBody.results) {
    const label = row.match.label;
    if (!["Strong research match", "Good research match", "Potential match"].includes(label)) {
      throw new Error(`unexpected recommendation label ${label}`);
    }
    if (typeof row.match.research_fit_score !== "number") {
      throw new Error("recommendation missing research_fit_score");
    }
  }

  const recExplain = await fetch(`${API}/api/recommendations/explain`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile: recProfile, researcher_id: firstId }),
  });
  if (recExplain.status !== 200) {
    throw new Error("/api/recommendations/explain -> HTTP " + recExplain.status);
  }
  const explainBody = await recExplain.json();
  if (explainBody.total === 1 && explainBody.results[0].researcher.id !== firstId) {
    throw new Error("explain returned the wrong researcher");
  }

  // Clean up the test session.
  const logoutRes = await authed("/api/auth/logout", { method: "POST" });
  if (logoutRes.status !== 200) throw new Error("/api/auth/logout -> HTTP " + logoutRes.status);

  await startFrontend();
  await waitFor(`${FRONT}/`);

  // Public routes render their real content server-side; protected routes
  // render the auth guard (the client hydrates into real content afterward).
  for (const [path, needle] of [
    ["/discover", "Discover researchers"],
    [`/researchers/${firstId}`, "Back to Discover"],
    ["/account", "Checking your session…"],
    ["/saved", "Checking your session…"],
    ["/outreach", "Checking your session…"],
    ["/outreach/compose/747", "Checking your session…"],
  ]) {
    const page = await fetch(`${FRONT}${path}`, { redirect: "manual" });
    const ok = page.status === 200;
    const html = ok ? await page.text() : "";
    const found = html.includes(needle);
    if (!ok || !found) {
      failed = true;
      console.log(`FAIL  ${path}  ${ok ? "missing expected content" : `HTTP ${page.status}`}`);
    } else {
      console.log(`PASS  ${path}  live backend render`);
    }
  }

  if (!failed) {
    console.log("all frontend renders matched expected content");
  }
} catch (error) {
  failed = true;
  console.error(`FAIL  ${String(error)}`);
} finally {
  for (const child of children) child.kill();
}

if (failed) {
  console.error("\nLive integration smoke failed.");
  process.exit(1);
}
console.log("\nLive integration smoke passed.");