import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE);
const evidence = path.resolve('../evidence/retention-2026-10-06/passive');
fs.mkdirSync(evidence, {recursive: true});
const browser = await chromium.launch({headless: true});
try {
  const page = await browser.newPage();
  await page.route('**/*', route => new URL(route.request().url()).hostname === 'localhost' ? route.continue() : route.abort());
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const health = await (await page.request.get('http://localhost:18501/api/health')).json();
  assert.equal(health.retention.status, 'ok');
  assert.equal(health.total_researchers, 2063);
  await page.goto('http://localhost:13310/privacy');
  const text = await page.locator('main').innerText();
  for (const phrase of ['encrypted', '30 days', 'hourly', 'Historical manual backups', 'independent deletion ledger']) assert.ok(text.includes(phrase), phrase);
  await page.screenshot({path: path.join(evidence, 'privacy-desktop.png'), fullPage: true});
  await page.setViewportSize({width: 320, height: 844});
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({path: path.join(evidence, 'privacy-mobile-320.png'), fullPage: true});
  assert.deepEqual(errors, []);
  fs.writeFileSync(path.join(evidence, 'results.json'), JSON.stringify({health, privacyDisclosure: true, mobile320NoOverflow: true, pageErrors: errors, anonymous: true}, null, 2));
} finally {await browser.close();}
