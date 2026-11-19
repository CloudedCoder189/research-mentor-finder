import { chromium } from "playwright-core";
import { join } from "node:path";
import { mkdirSync } from "node:fs";
const require = (id) => import(id).then((m) => m.default);

// playwright-core is installed in the repo frontend
const pw = await require("playwright-core");

const FRONT = "http://127.0.0.1:3210";
const API = "http://127.0.0.1:8000";
const OUT = join(process.env.LOCALAPPDATA, "Temp", "opencode", "live");
mkdirSync(OUT, { recursive: true });

const ROUTES = [
  { name: "home", path: "/", width: 1422, height: 1000 },
  { name: "discover", path: "/discover", width: 1019, height: 1000 },
  { name: "composer", path: "/outreach/compose/747", width: 1092, height: 1200 },
  { name: "outreach", path: "/outreach", width: 1036, height: 800 },
  { name: "saved", path: "/saved", width: 1036, height: 800 },
  { name: "foryou", path: "/for-you", width: 1019, height: 900 },
  { name: "profile", path: "/researchers/747", width: 1280, height: 900 },
  { name: "onboarding", path: "/account/onboarding", width: 1019, height: 1400 },
];

async function devLogin(browser) {
  const ctx = await browser.newContext({ viewport: { width: 1100, height: 900 } });
  // auto-login on the API to obtain the session cookie
  const res = await fetch(`${API}/api/auth/dev-login`, { method: "POST" });
  const body = await res.json();
  console.log(
    "dev-login authenticated=" + body.authenticated + " user=" + (body.user?.user_id ?? "?") + " csrf=" + (body.csrf_token ? "yes" : "no")
  );
  const setCookie = res.headers.get("set-cookie") || "";
  const m = /(?:^\s*|,\s*)([^=;,]+)=([^;]+);/.exec(setCookie);
  const cookie = m ? { name: m[1], value: m[2] } : null;
  if (cookie) {
    for (const u of [FRONT + "/", API + "/"]) {
      await ctx.addCookies([
        { name: cookie.name, value: cookie.value, path: "/", url: u },
      ]);
    }
  }
  return ctx;
}

const browser = await pw.chromium.launch({ headless: true });
const ctx = await devLogin(browser);
const results = [];
for (const r of ROUTES) {
  const page = await ctx.newPage();
  await page.setViewportSize({ width: r.width, height: r.height });
  try {
    await page.goto(`${FRONT}${r.path}`, { waitUntil: "networkidle", timeout: 45000 });
    // wait for any client-side redirect / hydration / session check
    await page.waitForTimeout(2000);
    // capture full-page screenshot
    const sc = await page.screenshot({ path: `${OUT}\\live_${r.name}.png`, fullPage: true });
    // capture visible text for comparison (what a sighted reviewer relies on)
    const text = await page.evaluate(() => {
      const walk = (root) => {
        const out = [];
        const push = (el) => {
          const r = el.getBoundingClientRect();
          out.push(`${Math.round(r.top)},${Math.round(r.left)},${Math.round(r.width)} | ${el.innerText ?? ""}`);
        };
        const sel = ["h1","h2","h3","button","a","p","input","textarea","label","nav"];
        for (const s of sel) {
          for (const el of root.querySelectorAll(s)) {
            if (el.offsetParent !== null && el.innerText && el.innerText.trim()) push(el);
          }
        }
        return out;
      };
      return walk(document);
    });
    results.push({ name: r.name, path: r.path, status: "ok", text, size: sc.length });
    console.log(`OK ${r.name} ${r.path} shot=${sc.length}B`);
  } catch (e) {
    results.push({ name: r.name, path: r.path, status: "ERR " + String(e.message).split("\n")[0] });
    console.log(`ERR ${r.name} ${r.path} :: ${String(e.message).split("\n")[0]}`);
  }
  await page.close();
}
await browser.close();

const fs = await import("node:fs");
const { execFileSync } = await import("node:child_process");
for (const r of results) {
  if (r.status !== "ok") continue;
  const png = `${OUT}\\live_${r.name}.png`;
  const gridOut = `${OUT}\\livegrid_${r.name}.txt`;
  try {
    const gr = execFileSync("powershell.exe", ["-NoProfile","-ExecutionPolicy","Bypass","-File",join(process.env.LOCALAPPDATA,"Temp","opencode","astra_grid.ps1"),"-ImagePath",png], { encoding: "utf8", timeout: 60000 });
    fs.writeFileSync(gridOut, gr);
    console.log(`GRID ${r.name} -> ${gr.split("\n")[0]}`);
  } catch (e) {
    console.log(`GRIDFAIL ${r.name} :: ${String(e.stdout || e.message).split("\n")[0]}`);
  }
}
console.log("\n===== SUMMARY =====");
for (const r of results) console.log(`${r.status}`.padEnd(20) + ` ${r.name.padEnd(12)} ${r.path}`);
