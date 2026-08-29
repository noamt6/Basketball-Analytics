/**
 * Smoke test for the dashboard Season Selector.
 * Serves the dashboard.html dir over loopback, then for every season option:
 *   - selects it, waits for re-render
 *   - visits all five tabs
 *   - fails on any page error / console error, empty standings, or a thrown render
 * Also checks ?season= deep-link and localStorage persistence across reload.
 *
 *   cd basketball-analytics && node scripts/qa_season_selector.js [path/to/dashboard.html]
 * exit 0 = pass, 1 = failures, 2 = Playwright missing
 */
const http = require('http');
const fs = require('fs');
const path = require('path');

let chromium;
try { ({ chromium } = require('playwright')); }
catch { console.error('Playwright not installed (cd scripts && npm install)'); process.exit(2); }

const target = path.resolve(process.argv[2] || path.join(__dirname, '..', 'dashboard.html'));
const rootDir = path.dirname(target);
const TABS = ['overview', 'league', 'team', 'player', 'analytics'];
const MIME = { '.html': 'text/html', '.json': 'application/json', '.js': 'text/javascript', '.css': 'text/css' };

const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(req.url.split('?')[0]);
  const file = path.join(rootDir, rel === '/' ? 'dashboard.html' : rel);
  if (!file.startsWith(rootDir) || !fs.existsSync(file)) { res.writeHead(404); return res.end('nope'); }
  res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'application/octet-stream' });
  fs.createReadStream(file).pipe(res);
});

const fails = [];
(async () => {
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const base = `http://127.0.0.1:${server.address().port}/dashboard.html`;
  const browser = await chromium.launch();

  const newPage = async () => {
    const page = await browser.newPage();
    page.on('pageerror', (e) => fails.push(`pageerror: ${e.message}`));
    page.on('console', (m) => { if (m.type() === 'error') fails.push(`console.error: ${m.text()}`); });
    return page;
  };

  const page = await newPage();
  await page.goto(base, { waitUntil: 'networkidle' });
  await page.waitForSelector('#season-select');

  const seasons = await page.$$eval('#season-select option', (o) => o.map((x) => x.value));
  const sortedDesc = [...seasons].sort().reverse().join(',');
  if (seasons.join(',') !== sortedDesc) fails.push(`options not newest-first: ${seasons.join(',')}`);
  console.log(`seasons in dropdown: ${seasons.join(', ')}`);

  for (const s of seasons) {
    await page.selectOption('#season-select', s);
    await page.waitForFunction((sv) => document.getElementById('season-chip').textContent.startsWith(sv), s, { timeout: 4000 })
      .catch(() => fails.push(`${s}: season-chip did not update`));
    const url = new URL(page.url());
    if (url.searchParams.get('season') !== s) fails.push(`${s}: ?season= not synced (${url.searchParams.get('season')})`);

    // playoffs toggle: disabled + click is inert when the season has no playoff data
    const po = await page.$eval('#comp-switch button[data-comp="playoffs"]', (b) => ({ disabled: b.disabled, title: b.title }));
    const hasPO = await page.evaluate(() => !!(DATA && DATA.playoffs && DATA.playoffs.teams && DATA.playoffs.teams.length));
    if (!hasPO && !po.disabled) fails.push(`${s}: playoffs toggle not disabled despite no playoff data`);
    if (!hasPO && !po.title) fails.push(`${s}: disabled playoffs toggle has no tooltip`);
    if (!hasPO) {
      await page.click('#comp-switch button[data-comp="playoffs"]', { force: true }).catch(() => {});
      await page.waitForTimeout(80);
      const comp = await page.evaluate(() => state.competition);
      if (comp !== 'regular_season') fails.push(`${s}: forced playoffs click switched competition to ${comp}`);
    }
    // every team on the league tab must carry a real rank (never #0 / blank)
    const ranks = await page.evaluate(() => activeTeams().map((tm) => tm.rank));
    if (ranks.some((r) => !r || r < 1)) fails.push(`${s}: team rank missing/zero -> ${JSON.stringify(ranks)}`);

    // Hebrew mode: no Latin player/team names should leak through
    const heGaps = await page.evaluate(() => {
      // 2+ lowercase Latin letters = an un-translated English name; a bare
      // Roman-numeral / initial suffix ("III", "T.J.") is fine in a Hebrew name.
      const latin = (x) => x && /[a-z]{2,}/.test(x);
      const pl = activePlayersRaw().filter((p) => latin(playerName(p))).length;
      const tm = activeTeams().filter((t) => latin(teamName(t)) || latin(teamLabel(t))).length;
      return { pl, tm };
    });
    if (heGaps.pl || heGaps.tm) fails.push(`${s}: he-mode Latin leak — ${heGaps.pl} players, ${heGaps.tm} teams`);

    for (const tab of TABS) {
      await page.click(`#tabs button:nth-child(${TABS.indexOf(tab) + 1})`);
      await page.waitForTimeout(120);
      const viewLen = await page.$eval('#view', (v) => v.textContent.trim().length).catch(() => 0);
      if (!viewLen) fails.push(`${s}/${tab}: #view rendered empty`);
    }

    // Key Insights card: present with 2-4 bullets on team + player views
    await page.click('#tabs button:nth-child(3)'); // team
    await page.waitForTimeout(150);
    let ins = await page.$$eval('#view .insights-list .insight-item', (n) => n.length).catch(() => 0);
    if (ins < 2 || ins > 4) fails.push(`${s}/team: insights bullets = ${ins} (want 2-4)`);
    await page.click('#tabs button:nth-child(4)'); // player list
    await page.waitForTimeout(120);
    await page.$eval('#view .grid-row, #view [role="row"]', (r) => r.click()).catch(() => {});
    await page.waitForTimeout(150);
    ins = await page.$$eval('#view .insights-list .insight-item', (n) => n.length).catch(() => 0);
    if (ins < 2 || ins > 4) fails.push(`${s}/player: insights bullets = ${ins} (want 2-4)`);
    const advGone = await page.$$eval('#view .panel-title', (n) => n.map((x) => x.textContent).join('|')).catch(() => '');
    if (/Advanced metrics|מדדים מתקדמים/.test(advGone)) fails.push(`${s}/player: old advanced-metrics panel still present`);
    // standings table should have rows on the league tab
    await page.click(`#tabs button:nth-child(2)`);
    await page.waitForTimeout(120);
    const rows = await page.$$eval('#view [class*="league"] [role="row"], #view table tr, #view [class*="row"]', (n) => n.length).catch(() => 0);
    if (rows < 3) fails.push(`${s}: league view has <3 rows (${rows})`);
  }

  // deep-link + persistence
  const pick = seasons[seasons.length - 1]; // oldest
  const p2 = await newPage();
  await p2.goto(`${base}?season=${pick}`, { waitUntil: 'networkidle' });
  await p2.waitForSelector('#season-select');
  if (await p2.$eval('#season-select', (e) => e.value) !== pick) fails.push(`deep-link ?season=${pick} not honoured`);
  await p2.reload({ waitUntil: 'networkidle' });
  if (await p2.$eval('#season-select', (e) => e.value) !== pick) fails.push(`season not persisted across reload`);

  await browser.close();
  server.close();

  if (fails.length) { console.error(`\nFAIL (${fails.length}):`); fails.forEach((f) => console.error('  - ' + f)); process.exit(1); }
  console.log('\nPASS — season selector switches all tabs cleanly, deep-link + persistence OK');
})();
