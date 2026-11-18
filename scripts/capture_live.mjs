import { chromium } from "playwright-core";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const FRONT = "http://127.0.0.1:3210";
const API = "http://127.0.0.1:8000";
const OUT = join(process.env.TEMP, "opencode", "live");
mkdirSync(OUT, { recursive: true });

const ROUTES = [
  { name: "discover", path: "/discover", width: 1346, rows: 18 },
  { name: "composer", path: "/outreach/compose/747", width: 1272, rows: 18 },
  { name: "outreach", path: "/outreach", width: 1036, rows: 18 },
  { name: "saved", path: "/saved", width: 1036, rows: 18 },
  { name: "foryou", path: "/for-you", width: 1019, rows: 18 },
  { name: "onboarding", path: "/account/onboarding", width: 1092, rows: 18 },
  { name: "home", path: "/", width: 1092, rows: 18 },
  { name: "profile", path: "/researchers/747", width: 1272, rows: 18 },
];

async function main() {
  const execPath = join(process.env.LOCALAPPDATA, "ms-playwright", "chromium-1234", "chrome-win64", "chrome.exe");
  const browser = await chromium.launch({ executablePath: execPath, headless: true });

  // dev-login to get session cookie (writes it into the API origin)
  const login = await fetch(`${API}/api/auth/dev-login`, { method: "POST" });
  const loginBody = await login.json();
  const sessionCookie = (login.headers.get("set-cookie") || "").split(";")[0];
  const csrf = loginBody.csrf_token;
  console.log("dev-login authenticated=" + !!loginBody.authenticated + " user=" + (loginBody.user?.user_id ?? "?") + " csrf=" + !!csrf + " session=" + (sessionCookie ? sessionCookie.split("=")[0] : "NONE"));

  const ctx = await browser.newContext({ viewport: { width: 1422, height: 1300 } });

  // dev-login also returned a csrf_token; the smoke set the cookie via context.
  // We seed the session cookie for the frontend origin too (astro pages were
  // captured logged-in for shielded pages).
  if (sessionCookie) {
    const [name, value] = sessionCookie.split("=");
    await ctx.addCookies([
      { name: name.trim(), value: value.trim(), url: FRONT },
      { name: name.trim(), value: value.trim(), url: API },
    ]);
  }

  for (const r of ROUTES) {
    const page = await ctx.newPage();
    await page.setViewportSize({ width: r.width, height: 900 });
    try {
      await page.goto(FRONT + r.path, { waitUntil: "networkidle", timeout: 60000 });
      await page.waitForTimeout(2500); // let hydration + CSS finish
      const shot = await page.screenshot({ path: `${OUT}\\live_${r.name}.png`, fullPage: true });
      // text tokens (what a viewer would read), top-anchored like the templates
      const tokens = await page.evaluate(() => {
        const out = [];
        const isVis = (el) => {
          const r = el.getBoundingClientRect();
          return r.width > 0 && r.height > 0;
        };
        const grab = (el) => {
          for (const ch of el.childNodes) {
            if (ch.nodeType === 3 && ch.textContent && ch.textContent.trim()) {
              out.push(el.tagName + ":" + Math.round(el.getBoundingClientRect().top) + ":" + ch.textContent.trim().slice(0, 50));
            }
          }
          for (const c of el.children) grab(c);
        };
        grab(document.body);
        return out;
      });
      const size = await page.evaluate(() => document.documentElement.scrollHeight);
      writeFileSync(`${OUT}\\ocr_live_${r.name}.txt`, "IMGSIZE=" + r.width + "x" + size + "\n" + tokens.join("\n"), "utf8");
      console.log("CAPTURED " + r.name + " bytes=" + shot.length);
    } catch (e) {
      console.log("CAPFAIL " + r.name + " :: " + String(e.message || e).split("\n")[0]);
    }
    await page.close();
  }
  await browser.close();
}

main().catch((e) => { console.error("FATAL " + String(e.message || e).split("\n")[0]); process.exit(1); });
