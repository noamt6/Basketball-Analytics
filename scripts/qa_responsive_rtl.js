#!/usr/bin/env node
/**
 * qa_responsive_rtl.js -- Playwright sweep of dashboard.html for responsive /
 * RTL regressions.
 *
 * For every (viewport x language x tab) it asserts:
 *   - <html dir> matches the language (rtl for he, ltr for en)
 *   - ZERO horizontal overflow: max(documentElement.scrollWidth,
 *     body.scrollWidth) <= window.innerWidth (+1px for sub-pixel rounding),
 *     checked both at the top of the page and after scrolling to the bottom
 *   - the top bar isn't clipped horizontally, and carries the position the
 *     layout intends for that width: `static` at <=640px (the mobile design
 *     deliberately un-sticks it so the wrapped 3-row bar doesn't eat the
 *     viewport), `sticky` above -- and at a desktop control width the sticky
 *     bar actually stays pinned to top:0 after a scroll.
 *
 * Playwright is NOT a repo dependency. Install it once:
 *     cd scripts && npm init -y && npm i -D playwright && npx playwright install chromium
 * (or `npm i -g playwright`). Then:
 *     node scripts/qa_responsive_rtl.js [path/to/dashboard.html]
 *
 * Exit codes: 0 all checks passed, 1 one or more failed, 2 Playwright missing.
 */
'use strict';

const path = require('path');
const fs = require('fs');
const http = require('http');

let chromium;
try {
  ({ chromium } = require('playwright'));
} catch (err) {
  console.error(
    'Playwright is not installed.\n' +
    '  cd scripts && npm init -y && npm i -D playwright && npx playwright install chromium\n' +
    'then re-run:  node scripts/qa_responsive_rtl.js',
  );
  process.exit(2);
}

const FILE = path.resolve(process.argv[2] || path.join(__dirname, '..', 'dashboard.html'));
// The dashboard now fetch()es ./data.json at runtime, which a file:// origin
// can't do — serve its directory over loopback HTTP instead (also closer to how
// S3 + CloudFront serve it in production).
const SERVE_DIR = path.dirname(FILE);
const MIME = { '.html': 'text/html', '.json': 'application/json', '.js': 'text/javascript',
  '.css': 'text/css', '.svg': 'image/svg+xml' };

function startServer() {
  const server = http.createServer((req, res) => {
    const rel = decodeURIComponent(req.url.split('?')[0]).replace(/^\/+/, '');
    const full = path.join(SERVE_DIR, rel || 'index.html');
    if (!full.startsWith(SERVE_DIR)) { res.writeHead(403).end(); return; }
    fs.readFile(full, (err, buf) => {
      if (err) { res.writeHead(404).end(); return; }
      res.writeHead(200, { 'content-type': MIME[path.extname(full)] || 'application/octet-stream' });
      res.end(buf);
    });
  });
  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => resolve(server));
  });
}

const MOBILE_VIEWPORTS = [
  { name: '360', width: 360, height: 800 },
  { name: '390', width: 390, height: 844 },
  { name: '430', width: 430, height: 932 },
];
const DESKTOP_VIEWPORT = { name: '1280', width: 1280, height: 900 };
const LANGS = [
  { code: 'he', dir: 'rtl' },
  { code: 'en', dir: 'ltr' },
];
const TABS = ['overview', 'league', 'team', 'player', 'analytics'];

const results = [];
function record(ok, scope, msg) {
  results.push({ ok, scope, msg });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${scope.padEnd(26)}  ${msg}`);
}

async function setLang(page, code) {
  await page.evaluate((c) => {
    const btn = document.querySelector(`.lang-switch button[data-lang="${c}"]`);
    if (btn) btn.click();
  }, code);
  await page.waitForTimeout(80);
}

async function gotoTab(page, tab) {
  await page.evaluate((t) => {
    const order = ['overview', 'league', 'team', 'player', 'analytics'];
    const btns = document.querySelectorAll('nav.tabs button');
    const btn = btns[order.indexOf(t)];
    if (btn) btn.click();
  }, tab);
  await page.waitForTimeout(70);
}

async function checkNoOverflow(page, scope) {
  const m = await page.evaluate(() => ({
    docScroll: document.documentElement.scrollWidth,
    bodyScroll: document.body.scrollWidth,
    inner: window.innerWidth,
  }));
  const widest = Math.max(m.docScroll, m.bodyScroll);
  const overshoot = widest - m.inner;
  record(overshoot <= 1, scope, `h-overflow ${overshoot}px (widest ${widest} vs innerWidth ${m.inner})`);
}

/** On the Team tab, walk every option of the team <select> and assert the
 * roster table renders at least one row -- guards against a per-team render
 * crash (e.g. an i18n-helper name shadowed by a local variable) that only
 * bites teams matching some condition. */
async function checkEveryTeamRoster(page, scope) {
  const ids = await page.$$eval('.player-picker select option', (os) => os.map((o) => o.value));
  const empties = [];
  for (const id of ids) {
    await page.selectOption('.player-picker select', id);
    await page.waitForTimeout(50);
    const n = await page.evaluate(() => document.querySelectorAll('.grid-row').length);
    if (n === 0) empties.push(id);
  }
  record(empties.length === 0, scope, `all ${ids.length} teams render a roster${empties.length ? ' (empty: ' + empties.join(',') + ')' : ''}`);
}

async function checkTopbar(page, scope, width) {
  const r = await page.evaluate(() => {
    const bar = document.querySelector('.topbar');
    if (!bar) return null;
    const rect = bar.getBoundingClientRect();
    return {
      position: getComputedStyle(bar).position,
      rightOvershoot: Math.round(rect.right - window.innerWidth),
      leftClip: Math.round(rect.left),
    };
  });
  if (!r) { record(false, scope, 'no .topbar element'); return; }
  record(r.rightOvershoot <= 1 && r.leftClip >= -1, scope,
    `topbar box in viewport (right +${r.rightOvershoot}px, left ${r.leftClip}px)`);
  const expected = width <= 640 ? 'static' : 'sticky';
  record(r.position === expected, scope, `topbar position ${r.position} (expected ${expected} @ ${width}px)`);
}

async function checkStickyPinned(page, scope) {
  await page.evaluate(() => window.scrollTo(0, 600));
  await page.waitForTimeout(60);
  const top = await page.evaluate(() =>
    Math.round(document.querySelector('.topbar').getBoundingClientRect().top));
  record(Math.abs(top) <= 1, scope, `sticky topbar pinned after scroll (top ${top}px)`);
  await page.evaluate(() => window.scrollTo(0, 0));
}

(async () => {
  const server = await startServer();
  const port = server.address().port;
  const TARGET_URL = `http://127.0.0.1:${port}/${path.basename(FILE)}`;
  console.log(`sweeping ${TARGET_URL}  (serving ${SERVE_DIR})\n`);
  const browser = await chromium.launch();

  for (const lang of LANGS) {
    for (const vp of [...MOBILE_VIEWPORTS, DESKTOP_VIEWPORT]) {
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        locale: lang.code === 'he' ? 'he-IL' : 'en-US',
        deviceScaleFactor: 2,
      });
      const page = await context.newPage();
      await page.goto(TARGET_URL, { waitUntil: 'load' });
      // boot() fetches ./data.json before it can render the chrome/tabs.
      await page.waitForSelector('nav.tabs button', { timeout: 5000 });
      await page.waitForTimeout(100);
      await setLang(page, lang.code);

      const dir = await page.evaluate(() => document.documentElement.getAttribute('dir'));
      record(dir === lang.dir, `${lang.code}/${vp.name}`, `<html dir> = ${dir}`);

      for (const tab of TABS) {
        await gotoTab(page, tab);
        const scope = `${lang.code}/${vp.name}/${tab}`;

        await checkNoOverflow(page, `${scope} [top]`);
        await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
        await page.waitForTimeout(60);
        await checkNoOverflow(page, `${scope} [bottom]`);
        await page.evaluate(() => window.scrollTo(0, 0));

        await checkTopbar(page, scope, vp.width);
        if (vp.width > 640) await checkStickyPinned(page, scope);
        if (tab === 'team') await checkEveryTeamRoster(page, scope);
      }

      await context.close();
    }
  }

  await browser.close();
  server.close();

  const failed = results.filter((r) => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} checks passed.`);
  if (failed.length) {
    console.log('\nFailures:');
    failed.forEach((f) => console.log(`  ${f.scope}  --  ${f.msg}`));
    process.exit(1);
  }
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
