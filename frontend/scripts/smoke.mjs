#!/usr/bin/env node
/* Route smoke test: starts `next start`, fetches every core route, and asserts SSR content. */
import { spawn } from "node:child_process";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as sleep } from "node:timers/promises";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const PORT = 3210;
const BASE = `http://127.0.0.1:${PORT}`;

const CHECKS = [
  { path: "/", needle: "Your next research chapter starts here" },
  { path: "/discover", needle: "Discover researchers" },
  { path: "/researchers/maria-chen", needle: "Back to Discover" },
  // The routes below are behind the auth guard: anonymous SSR renders the
  // session check, and a real sign-in state only appears after hydration.
  { path: "/account", needle: "Checking your session…" },
  { path: "/account/onboarding", needle: "Checking your session…" },
  { path: "/for-you", needle: "Checking your session…" },
  { path: "/saved", needle: "Checking your session…" },
  { path: "/outreach", needle: "Checking your session…" },
  { path: "/outreach/compose/747", needle: "Checking your session…" },
  { path: "/researchers/does-not-exist", needle: "Back to Discover" },
  // Footer destinations must be real routes, not dead fragments.
  { path: "/about", needle: "About" },
  { path: "/contact", needle: "Contact" },
  { path: "/privacy", needle: "Privacy" },
  { path: "/terms", needle: "Terms" },
];

async function waitForServer(timeoutMs = 60000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const res = await fetch(`${BASE}/`, { redirect: "follow" });
      if (res.status >= 200 && res.status < 500) return;
    } catch {
      /* not ready yet */
    }
    await sleep(1000);
  }
  throw new Error("Server did not become ready in time");
}

const child = spawn(
  process.execPath,
  [join(root, "node_modules", "next", "dist", "bin", "next"), "start", "-p", String(PORT)],
  { cwd: root, stdio: ["ignore", "pipe", "pipe"] },
);
child.stdout.on("data", () => {});
child.stderr.on("data", () => {});

let failed = false;
try {
  await waitForServer();
  for (const check of CHECKS) {
    try {
      const res = await fetch(`${BASE}${check.path}`, { redirect: "manual" });
      let ok = true;
      let detail = `status ${res.status}`;
      if (typeof check.expectStatus === "number") {
        ok = res.status === check.expectStatus;
        detail += ` (expected ${check.expectStatus})`;
      } else {
        ok = res.status === 200;
        if (ok && check.needle) {
          const html = await res.text();
          const found = html.includes(check.needle);
          ok = found;
          detail += found ? " + content match" : " + MISSING expected content";
        }
      }
      if (!ok) failed = true;
      console.log(`${ok ? "PASS" : "FAIL"}  ${check.path}  ${detail}`);
    } catch (error) {
      failed = true;
      console.log(`FAIL  ${check.path}  fetch error: ${String(error)}`);
    }
  }
} finally {
  child.kill();
}

if (failed) {
  console.error("\nSmoke test failed.");
  process.exit(1);
}
console.log("\nSmoke test passed.");