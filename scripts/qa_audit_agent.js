#!/usr/bin/env node
/**
 * qa_audit_agent.js -- one end-to-end quality gate for the dashboard.
 *
 *   node scripts/qa_audit_agent.js               # run all 4 domains, print Markdown
 *   node scripts/qa_audit_agent.js --skip-visual # A/B/C only (no Playwright)
 *   node scripts/qa_audit_agent.js --json out.json
 *
 * Domains
 *   A. Mathematical invariants   -- data.json: no NaN/Infinity, points identity
 *      PTS == 2*(FGM-FG3M) + 3*FG3M + FTM, FGA >= FG3A, GP >= 1
 *   B. Metadata completeness     -- missing jersey / missing name_he per season,
 *      referenced asset files exist on disk
 *   C. Team metrics integrity    -- team PPG*GP is internally consistent and the
 *      roster point-sum does not INFLATE past the official team total
 *   D. Visual & layout regression (Playwright) -- 8 viewports x {LTR, RTL},
 *      every tab + a player card + the search modal: 0 horizontal overflow,
 *      0 console errors, search modal opens and returns results
 *
 * Exit code 0 iff every check is green. Report uses 🟢 pass / 🟡 warn / 🔴 fail;
 * warnings (known, documented tolerances) do not fail the run.
 */
'use strict';

const path = require('path');
const fs = require('fs');
const http = require('http');

const ROOT = path.resolve(__dirname, '..');
const DATA_PATH = path.join(ROOT, 'data.json');
const DASH_PATH = path.join(ROOT, 'dashboard.html');

const args = process.argv.slice(2);
const SKIP_VISUAL = args.includes('--skip-visual');
const JSON_OUT = args.includes('--json') ? args[args.indexOf('--json') + 1] : null;

const PASS = '🟢', WARN = '🟡', FAIL = '🔴';
const num = (v) => (typeof v === 'number' ? v : Number(v));
const finite = (v) => Number.isFinite(num(v));

/* ------------------------------------------------------------------ helpers */
function loadData() {
  return JSON.parse(fs.readFileSync(DATA_PATH, 'utf8'));
}
// every (season, competition, player-row) tuple, flattened
function* eachPlayerRow(data) {
  for (const [season, s] of Object.entries(data.seasons)) {
    for (const p of s.players || []) yield { season, comp: 'regular', p };
    for (const p of (s.playoffs && s.playoffs.players) || []) yield { season, comp: 'playoffs', p };
  }
}
function* eachTeamRow(data) {
  for (const [season, s] of Object.entries(data.seasons)) {
    for (const t of s.teams || []) yield { season, comp: 'regular', t };
    for (const t of (s.playoffs && s.playoffs.teams) || []) yield { season, comp: 'playoffs', t };
  }
}

/* ---------------------------------------------------------------- Domain A */
function domainA(data) {
  const checks = [];
  const NUMERIC_HINT = /^(avg_|per_36_|per36_)/;
  const EXPLICIT = ['pts', 'reb', 'ast', 'tov', 'oreb', 'dreb', 'min', 'gp',
    'fgm', 'fga', 'fg3m', 'fg3a', 'ftm', 'fta', 'pir',
    'fg_pct', 'fg3_pct', 'ft_pct', 'efg_pct', 'ts_pct', 'ast_to_tov', 'efficiency'];

  // A single point off the shot-split is source rounding on season TOTALS; a
  // gap this small cannot come from a 2PT/3PT column swap (that throws the sum
  // off by the whole 3PT volume). Flag > PTS_TOL as a real defect.
  const PTS_TOL = 2;

  let nanCount = 0; const nanEx = [];
  let idExact = 0, idRound = 0, idBad = 0; const idEx = [];
  let fgaOk = 0, fgaBad = 0; const fgaEx = [];
  let gpOk = 0, gpDnp = 0, gpBad = 0; const gpEx = [];

  for (const { season, comp, p } of eachPlayerRow(data)) {
    const keys = new Set(EXPLICIT);
    for (const k of Object.keys(p)) if (NUMERIC_HINT.test(k)) keys.add(k);
    for (const k of keys) {
      if (!(k in p) || p[k] === null || p[k] === undefined) continue;
      const v = p[k];
      if (typeof v === 'number' && !Number.isFinite(v)) {
        nanCount++;
        if (nanEx.length < 8) nanEx.push(`${season}/${comp} ${p.name} .${k}=${v}`);
      }
    }
    // points identity -- skip rows flagged bad_split (source 3PT > FG, documented)
    const fgm = num(p.fgm), fg3m = num(p.fg3m), ftm = num(p.ftm), pts = num(p.pts);
    if ([fgm, fg3m, ftm, pts].every(finite) && !p.bad_split) {
      const d = Math.abs(2 * (fgm - fg3m) + 3 * fg3m + ftm - pts);
      if (d === 0) idExact++;
      else if (d <= PTS_TOL) idRound++;
      else { idBad++; if (idEx.length < 8) idEx.push(`${season}/${comp} ${p.name}: PTS=${pts}, split gives ${2 * (fgm - fg3m) + 3 * fg3m + ftm} (Δ${d})`); }
    }
    const fga = num(p.fga), fg3a = num(p.fg3a);
    if (finite(fga) && finite(fg3a)) {
      if (fga >= fg3a) fgaOk++;
      else { fgaBad++; if (fgaEx.length < 8) fgaEx.push(`${season}/${comp} ${p.name}: FGA=${fga} < FG3A=${fg3a}`); }
    }
    const gp = num(p.gp), mins = num(p.min), rowPts = num(p.pts);
    if (finite(gp)) {
      if (gp >= 1) gpOk++;
      else if (gp === 0 && (mins || 0) === 0 && (rowPts || 0) === 0) gpDnp++;     // registered, did not play
      else { gpBad++; if (gpEx.length < 8) gpEx.push(`${season}/${comp} ${p.name}: GP=${gp} but min=${mins} pts=${rowPts}`); }
    }
  }

  checks.push({ label: 'No NaN / Infinity in numeric fields', status: nanCount === 0 ? PASS : FAIL,
    detail: nanCount === 0 ? 'all counting + rate fields finite' : `${nanCount} bad value(s): ${nanEx.join('; ')}` });
  checks.push({ label: `Points identity  PTS == 2·(FGM−FG3M) + 3·FG3M + FTM  (±${PTS_TOL} source rounding)`,
    status: idBad === 0 ? PASS : FAIL,
    detail: `${idExact} exact, ${idRound} within ±${PTS_TOL} (season-total rounding)` + (idBad ? `, ${idBad} BEYOND tolerance: ${idEx.join('; ')}` : '') });
  checks.push({ label: 'FGA ≥ FG3A', status: fgaBad === 0 ? PASS : FAIL,
    detail: fgaBad === 0 ? `${fgaOk} rows` : `${fgaBad} violation(s): ${fgaEx.join('; ')}` });
  checks.push({ label: 'GP ≥ 1 (or a clean did-not-play zero row)', status: gpBad === 0 ? PASS : FAIL,
    detail: `${gpOk} rows GP≥1` + (gpDnp ? `, ${gpDnp} registered-DNP rows (GP=0, min=0, pts=0 — benign)` : '') + (gpBad ? `, ${gpBad} CONTRADICTORY: ${gpEx.join('; ')}` : '') });
  return { name: 'A. Mathematical invariants', checks };
}

/* ---------------------------------------------------------------- Domain B */
function domainB(data) {
  const checks = [];
  const perSeasonJersey = [];
  const perSeasonNameHe = [];
  let totJerseyMiss = 0, totNameHeMiss = 0, totPlayers = 0;

  for (const [season, s] of Object.entries(data.seasons)) {
    const rows = s.players || [];
    let jm = 0, nm = 0;
    for (const p of rows) {
      totPlayers++;
      if (p.jersey === null || p.jersey === undefined || p.jersey === 0) jm++;
      if (!p.name_he || !String(p.name_he).trim()) nm++;
    }
    totJerseyMiss += jm; totNameHeMiss += nm;
    perSeasonJersey.push(`${season}: ${jm}/${rows.length}`);
    perSeasonNameHe.push(`${season}: ${nm}/${rows.length}`);
  }

  // jersey: informational -- the league source has no shirt number for a chunk
  // of stat-only appearances, so a non-zero count is expected, not a failure.
  checks.push({ label: `Jersey numbers present (${data.seasons ? Object.keys(data.seasons).length : 0} seasons)`,
    status: totJerseyMiss === 0 ? PASS : WARN,
    detail: `${totPlayers - totJerseyMiss}/${totPlayers} have a number; missing per season -> ${perSeasonJersey.join('  ')}` });
  checks.push({ label: 'Hebrew name (name_he) present', status: totNameHeMiss === 0 ? PASS : (totNameHeMiss <= 5 ? WARN : FAIL),
    detail: totNameHeMiss === 0 ? `all ${totPlayers} rows` : `${totNameHeMiss} missing -> ${perSeasonNameHe.filter((x) => !x.endsWith(' 0/' + x.split('/')[1])).join('  ')}` });

  // referenced asset files
  const dash = fs.readFileSync(DASH_PATH, 'utf8');
  const refs = new Set();
  for (const m of dash.matchAll(/(?:href|src|content)="([^"]+\.(?:png|jpe?g|svg|ico|webp|css|js))"/g)) refs.add(m[1]);
  refs.add('data.json'); // fetched at runtime
  const broken = [];
  for (const r of refs) {
    if (/^https?:\/\//i.test(r)) {
      // absolute -> check the basename exists locally (same file we deploy)
      const base = r.split('/').pop().split('?')[0];
      if (base && !fs.existsSync(path.join(ROOT, base))) broken.push(r + ' (no local ' + base + ')');
    } else if (!fs.existsSync(path.join(ROOT, r.replace(/^\.?\//, '')))) {
      broken.push(r);
    }
  }
  checks.push({ label: 'Referenced asset paths resolve', status: broken.length === 0 ? PASS : FAIL,
    detail: broken.length === 0 ? `${refs.size} refs OK (${[...refs].join(', ')})` : `broken: ${broken.join('; ')}` });
  return { name: 'B. Metadata completeness', checks };
}

/* ---------------------------------------------------------------- Domain C */
function domainC(data) {
  const checks = [];
  // roster point-sum vs official team total. A small overshoot is expected:
  // mid-season transfers mean a moved player's stint splits rarely partition
  // his season line to the pound. Treat <=5% as clean, 5-25% as documented
  // transfer-split noise (WARN), >25% as a real double-count bug (FAIL).
  const INFL_WARN = 1.05, INFL_FAIL = 1.25;
  let ppgOk = 0, ppgBad = 0; const ppgEx = [];
  let inflOk = 0, inflWarn = 0, inflFail = 0; const inflEx = []; const inflFailEx = [];

  for (const [season, s] of Object.entries(data.seasons)) {
    const teams = s.teams || [];
    const players = s.players || [];
    const byTeam = new Map();
    for (const p of players) {
      const k = String(p.team_id);
      byTeam.set(k, (byTeam.get(k) || 0) + num(p.pts || 0));
    }
    for (const t of teams) {
      const gp = num(t.gp), ppg = num(t.avg_points);
      // internal consistency: gp>=1, ppg in a sane band
      if (finite(gp) && finite(ppg) && gp >= 1 && ppg > 30 && ppg < 130) ppgOk++;
      else { ppgBad++; if (ppgEx.length < 6) ppgEx.push(`${season} ${t.label}: gp=${gp} ppg=${ppg}`); }

      // no roster-sum INFLATION past the official total (allow 5% for the
      // documented team-vs-player scope mismatch; only flag over-count)
      const teamPts = ppg * gp;
      const rosterPts = byTeam.get(String(t.id)) || 0;
      if (teamPts > 0) {
        const ratio = rosterPts / teamPts;
        const line = `${season} ${t.label}: roster Σpts=${rosterPts} vs team ${Math.round(teamPts)} (×${ratio.toFixed(2)})`;
        if (ratio <= INFL_WARN) inflOk++;
        else if (ratio <= INFL_FAIL) { inflWarn++; if (inflEx.length < 6) inflEx.push(line); }
        else { inflFail++; if (inflFailEx.length < 8) inflFailEx.push(line); }
      }
    }
  }
  checks.push({ label: 'Team PPG / GP internally consistent', status: ppgBad === 0 ? PASS : FAIL,
    detail: ppgBad === 0 ? `${ppgOk} team-seasons in range` : `${ppgBad} off: ${ppgEx.join('; ')}` });
  checks.push({ label: `No gross roster point-sum inflation vs official team total (fail > +${Math.round((INFL_FAIL - 1) * 100)}%)`,
    status: inflFail > 0 ? FAIL : (inflWarn > 0 ? WARN : PASS),
    detail: `${inflOk} team-seasons ≤ +5% (clean)`
      + (inflWarn ? `; ${inflWarn} in +5–25% band — documented mid-season-transfer split noise: ${inflEx.join('; ')}` : '')
      + (inflFail ? `; ${inflFail} FAIL > +25%: ${inflFailEx.join('; ')}` : '') });
  return { name: 'C. Team metrics integrity', checks };
}

/* ---------------------------------------------------------------- Domain D */
const VIEWPORTS = [360, 390, 414, 430, 768, 1024, 1280, 1440];
const TABS = ['overview', 'league', 'team', 'player', 'analytics'];

function startServer() {
  const MIME = { '.html': 'text/html', '.json': 'application/json', '.js': 'text/javascript',
    '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png' };
  const server = http.createServer((req, res) => {
    const rel = decodeURIComponent(req.url.split('?')[0]).replace(/^\/+/, '') || 'dashboard.html';
    const full = path.join(ROOT, rel);
    if (!full.startsWith(ROOT)) { res.writeHead(403).end(); return; }
    fs.readFile(full, (err, buf) => {
      if (err) { res.writeHead(404).end(); return; }
      res.writeHead(200, { 'content-type': MIME[path.extname(full)] || 'application/octet-stream' });
      res.end(buf);
    });
  });
  return new Promise((r) => server.listen(0, '127.0.0.1', () => r(server)));
}

async function domainD() {
  let chromium;
  try { ({ chromium } = require('playwright')); }
  catch { return { name: 'D. Visual & layout regression', checks: [{ label: 'Playwright available', status: FAIL, detail: 'cd scripts && npm install' }] }; }

  const server = await startServer();
  const base = `http://127.0.0.1:${server.address().port}/dashboard.html`;
  const browser = await chromium.launch();
  const overflow = []; const consoleErr = []; const modalErr = [];
  let sweeps = 0;

  for (const lang of ['he', 'en']) {
    for (const width of VIEWPORTS) {
      const ctx = await browser.newContext({ viewport: { width, height: 900 } });
      const page = await ctx.newPage();
      const errs = [];
      page.on('pageerror', (e) => errs.push(String(e)));
      page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text()); });
      await page.addInitScript((lg) => { try { localStorage.setItem('sls-lang', lg); localStorage.setItem('sls-competition', 'regular_season'); } catch (e) {} }, lang);
      await page.goto(base, { waitUntil: 'networkidle' });
      await page.waitForSelector('#view *', { timeout: 10000 });
      const dir = await page.evaluate(() => document.documentElement.getAttribute('dir'));
      if (dir !== (lang === 'he' ? 'rtl' : 'ltr')) modalErr.push(`${lang}/${width}: dir=${dir}`);

      for (const tab of TABS) {
        await page.evaluate((tb) => window.goTab && goTab(tb), tab);
        await page.waitForTimeout(120);
        if (tab === 'player') {
          const pid = await page.evaluate(() => {
            const ps = (window.activePlayersRaw ? activePlayersRaw() : []).slice()
              .sort((a, b) => (b.avg_points || 0) - (a.avg_points || 0));
            return ps[0] && ps[0].id;
          });
          if (pid != null) { await page.evaluate((i) => goPlayer(i), pid); await page.waitForTimeout(150); }
        }
        const of = await page.evaluate(() => Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - window.innerWidth);
        sweeps++;
        if (of > 1) overflow.push(`${lang}/${width}/${tab}: +${of}px`);
      }

      // search modal integrity
      try {
        await page.evaluate(() => window.goTab && goTab('overview'));
        await page.click('#spotlight-trigger');
        await page.waitForSelector('#sl-overlay:not([hidden])', { timeout: 3000 });
        await page.fill('#sl-input', 'a');
        await page.waitForTimeout(200);
        const n = await page.$$eval('#sl-results > *', (x) => x.length);
        if (n < 1) modalErr.push(`${lang}/${width}: search modal returned 0 results`);
        const mof = await page.evaluate(() => {
          const o = document.querySelector('#sl-overlay');
          return o ? o.getBoundingClientRect().right - window.innerWidth : 0;
        });
        if (mof > 1) modalErr.push(`${lang}/${width}: search modal overflows +${Math.round(mof)}px`);
        await page.keyboard.press('Escape');
      } catch (e) {
        modalErr.push(`${lang}/${width}: modal check threw ${String(e).split('\n')[0]}`);
      }

      if (errs.length) consoleErr.push(`${lang}/${width}: ${[...new Set(errs)].slice(0, 3).join(' | ')}`);
      await ctx.close();
    }
  }
  await browser.close(); server.close();

  const checks = [];
  checks.push({ label: `Zero horizontal overflow (${VIEWPORTS.length} widths × LTR/RTL × ${TABS.length} tabs = ${sweeps} sweeps)`,
    status: overflow.length === 0 ? PASS : FAIL, detail: overflow.length === 0 ? 'clean 360–1440px' : overflow.join('  ') });
  checks.push({ label: 'Zero console / page errors', status: consoleErr.length === 0 ? PASS : FAIL,
    detail: consoleErr.length === 0 ? 'no errors on any tab' : consoleErr.join('  ') });
  checks.push({ label: 'Search modal opens, returns results, stays in-viewport', status: modalErr.length === 0 ? PASS : FAIL,
    detail: modalErr.length === 0 ? `verified at all ${VIEWPORTS.length * 2} sizes` : modalErr.join('  ') });
  return { name: 'D. Visual & layout regression', checks };
}

/* ------------------------------------------------------------------- main */
(async () => {
  const data = loadData();
  const domains = [domainA(data), domainB(data), domainC(data)];
  if (!SKIP_VISUAL) domains.push(await domainD());

  const rank = { [FAIL]: 0, [WARN]: 1, [PASS]: 2 };
  const worst = (cs) => cs.reduce((w, c) => (rank[c.status] < rank[w] ? c.status : w), PASS);
  const anyFail = domains.some((d) => d.checks.some((c) => c.status === FAIL));

  const lines = [];
  lines.push('# QA Audit Report');
  lines.push('');
  lines.push(`_${new Date().toISOString()}_ · \`data.json\` + \`dashboard.html\``);
  lines.push('');
  lines.push('| Domain | Result |');
  lines.push('|---|---|');
  for (const d of domains) lines.push(`| ${d.name} | ${worst(d.checks)} |`);
  lines.push('');
  lines.push(`## Overall: ${anyFail ? FAIL + ' FAIL' : PASS + ' PASS'}`);
  for (const d of domains) {
    lines.push('');
    lines.push(`### ${d.name}`);
    lines.push('');
    for (const c of d.checks) {
      lines.push(`- ${c.status} **${c.label}**`);
      if (c.detail) lines.push(`  - ${c.detail}`);
    }
  }
  const report = lines.join('\n') + '\n';
  process.stdout.write(report);
  if (JSON_OUT) fs.writeFileSync(JSON_OUT, JSON.stringify({ anyFail, domains }, null, 2));
  process.exit(anyFail ? 1 : 0);
})();
