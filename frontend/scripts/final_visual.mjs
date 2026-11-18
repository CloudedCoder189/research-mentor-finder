/* Final screenshots against existing prototype. No server changes or sign-in. */
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {mkdirSync, writeFileSync} from 'node:fs';
import {resolve, dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const output = join(root, 'evidence/final-visual-2026-10-04');
mkdirSync(output, {recursive:true});
const require = createRequire(import.meta.url);
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({channel:'chrome',headless:true});
const context = await browser.newContext({viewport:{width:1280,height:900}});
const checks = [], errors = [];
await context.route('**/*', route => {
  const u = new URL(route.request().url());
  if (!['localhost','127.0.0.1'].includes(u.hostname) || !['13310','18501'].includes(u.port)) return route.abort();
  return route.continue();
});
const page = await context.newPage();
page.on('pageerror', error => errors.push(error.name));
async function capture(name, fullPage = true) {
  const size = await page.evaluate(() => ({width:document.documentElement.clientWidth, scroll:document.documentElement.scrollWidth}));
  assert.ok(size.scroll <= size.width, JSON.stringify(size));
  await page.screenshot({path:join(output,`${name}.png`),fullPage});
  checks.push({name,passed:true,viewport:page.viewportSize(),document:size});
}
try {
  await page.goto('http://localhost:13310/');
  await page.getByRole('heading').first().waitFor();
  await capture('desktop-home');
  await page.goto('http://localhost:13310/discover?q=robotics');
  await page.locator('article').first().waitFor();
  await capture('desktop-discover');
  await capture('desktop-discover-viewport', false);
  await page.goto('http://localhost:13310/researchers/1126');
  await page.getByRole('heading', {name:/Umesh Mishra/}).waitFor();
  await capture('desktop-profile');
  await page.setViewportSize({width:320,height:720});
  await capture('mobile-320-profile');
  await page.locator('summary').filter({hasText:'Source details'}).click();
  await page.getByText('Source type',{exact:true}).waitFor();
  await page.locator('details[open]').scrollIntoViewIfNeeded();
  await capture('mobile-320-source-details', false);
  await page.goto('http://localhost:13310/discover');
  await page.locator('article').first().waitFor();
  await page.getByRole('searchbox').fill('a'.repeat(100));
  await page.getByRole('button',{name:'Search',exact:true}).click();
  await page.getByText('No researchers match those filters',{exact:true}).waitFor();
  await page.getByText('No researchers match those filters',{exact:true}).scrollIntoViewIfNeeded();
  await capture('mobile-320-long-query-empty');
  await capture('mobile-320-empty-viewport', false);
  await page.goto('http://localhost:13310/account');
  await page.getByRole('heading',{name:'Sign in to continue'}).waitFor();
  await capture('mobile-320-sign-in');
  await page.getByRole('button',{name:'Open menu',exact:true}).click();
  await page.getByRole('navigation',{name:'Mobile',exact:true}).waitFor();
  await capture('mobile-320-menu', false);
  await page.getByRole('button',{name:'Close menu',exact:true}).click();
  assert.equal(await page.getByRole('navigation',{name:'Mobile',exact:true}).count(),0);
  assert.equal(errors.length,0);
  checks.push({name:'no_uncaught_browser_errors',passed:true});
} finally {
  writeFileSync(join(output,'results.json'),JSON.stringify({checks,errors,visualReview:'Pending separate screenshot inspection',paidCalls:0,externalRequestsBlocked:true},null,2));
  await browser.close();
}
console.log(JSON.stringify({passed:checks.length,screenshots:checks.filter(c=>c.viewport).length}));
