#!/usr/bin/env node
/**
 * qa_audit_agent.js -- one end-to-end quality gate for the dashboard.
 *
 *   node scripts/qa_audit_agent.js               # run all 5 domains, print Markdown
 *   node scripts/qa_audit_agent.js --skip-visual # A/B/C + E data checks (no Playwright)
 *   node scripts/qa_audit_agent.js --baseline-ref <git ref>  # E: boot-size delta base (default origin/main)
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
 *   E. Game data (games/ pilot) -- schema of seasons.json / index.json /
 *      g/<id>.json / player_logs.json; per-game integrity (player points sum
 *      == score, quarters incl. OT sum == score, made <= attempted);
 *      reconciliation of summed player-game rows vs data.json season totals;
 *      and (Playwright) lazy loading: no games/ request at boot, one request
 *      per box score, zero on re-open, initial transfer size vs a baseline ref.
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

/* ---------------------------------------------------------------- Domain E */
const GAMES_DIR = path.join(ROOT, 'games');
const LOG_COLS = ['game_id', 'player_id', 'team_id', 'opp_id', 'home', 'starter', 'min', 'pts',
  'fg2m', 'fg2a', 'fg3m', 'fg3a', 'ftm', 'fta', 'oreb', 'dreb', 'ast', 'stl', 'tov', 'blk', 'pf', 'fd', 'pir', 'pm'];
// Reconciliation tolerance: share of players allowed to differ from data.json
// before it is a failure (the league source itself credits the odd rebound to
// a different player in the box score than in its season totals).
const RECON_WARN_SHARE = 0.03;

function readJSON(p) { try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (e) { return null; } }

function domainEData(data) {
  const checks = [];
  const manifest = readJSON(path.join(GAMES_DIR, 'seasons.json'));
  if (!manifest || !manifest.seasons || !Object.keys(manifest.seasons).length) {
    checks.push({ label: 'games/seasons.json present', status: FAIL, detail: 'missing or empty -- run scrape_games.py' });
    return checks;
  }
  const schemaErr = [], gameErr = [], flagged = [], noBox = [], reconDetail = [];
  let boxes = 0, logRows = 0, otGames = 0, reconStatus = PASS;
  for (const season of Object.keys(manifest.seasons)) {
    const dir = path.join(GAMES_DIR, season);
    const idx = readJSON(path.join(dir, 'index.json'));
    const logs = readJSON(path.join(dir, 'player_logs.json'));
    if (!idx || !Array.isArray(idx.games)) { schemaErr.push(`${season}: index.json missing/invalid`); continue; }
    if (!logs || JSON.stringify(logs.cols) !== JSON.stringify(LOG_COLS)) { schemaErr.push(`${season}: player_logs.json cols mismatch`); continue; }
    const badLen = logs.rows.filter((r) => r.length !== LOG_COLS.length).length;
    if (badLen) schemaErr.push(`${season}: ${badLen} log rows with wrong width`);
    logRows += logs.rows.length;
    const stageOf = new Map(idx.games.map((g) => [g.id, g.stage]));

    for (const g of idx.games) {
      for (const k of ['id', 'stage', 'date', 'status', 'home', 'away', 'box']) if (!(k in g)) schemaErr.push(`${season}/${g.id}: index entry lacks ${k}`);
      if (g.flags) flagged.push(String(g.id));
      if (g.status === 'final' && !g.box) { noBox.push(`${g.id}${g.note ? ' (' + g.note + ')' : ''}`); continue; }
      if (!g.box) continue;
      const b = readJSON(path.join(dir, 'g', `${g.id}.json`));
      if (!b || !Array.isArray(b.teams) || b.teams.length !== 2) { schemaErr.push(`${season}/${g.id}: box file missing/invalid`); continue; }
      boxes++;
      if (g.ot) otGames++;
      b.teams.forEach((t, i) => {
        const side = i === 0 ? g.home : g.away;
        // players + the site's "Team" row (rarely carries unattributed points)
        const pts = t.players.reduce((a, p) => a + p.pts, 0) + ((t.team_row && t.team_row.pts) || 0);
        if (pts !== t.pts || t.pts !== side.pts) gameErr.push(`${g.id}/${t.team_id}: players+team ${pts}, box ${t.pts}, index ${side.pts}`);
        const q = (t.q || []).reduce((a, v) => a + v, 0);
        if (q !== t.pts) gameErr.push(`${g.id}/${t.team_id}: sum(q) ${q} != ${t.pts}`);
        if ((t.q || []).length !== 4 + (g.ot || 0)) gameErr.push(`${g.id}/${t.team_id}: ${(t.q || []).length} periods for ot=${g.ot}`);
        t.players.forEach((p) => ['fg2', 'fg3', 'ft'].forEach((k) => {
          if (p[k][0] > p[k][1]) gameErr.push(`${g.id}/${p.id}: ${k} made > att`);
        }));
      });
    }

    // reconciliation: regular-season log rows summed per player vs data.json
    const dj = data.seasons[season];
    if (!dj) { reconDetail.push(`${season}: not in data.json`); reconStatus = WARN; continue; }
    const KEYS = ['gp', 'pts', 'min', 'fgm', 'fga', 'fg3m', 'fg3a', 'ftm', 'fta', 'reb', 'ast'];
    const c = Object.fromEntries(LOG_COLS.map((k, i) => [k, i]));
    const agg = new Map();
    for (const r of logs.rows) {
      if (stageOf.get(r[c.game_id]) !== 'regular') continue;
      const a = agg.get(r[c.player_id]) || Object.fromEntries(KEYS.map((k) => [k, 0]));
      a.gp += 1; a.pts += r[c.pts]; a.min += r[c.min];
      a.fgm += r[c.fg2m] + r[c.fg3m]; a.fga += r[c.fg2a] + r[c.fg3a];
      a.fg3m += r[c.fg3m]; a.fg3a += r[c.fg3a]; a.ftm += r[c.ftm]; a.fta += r[c.fta];
      a.reb += r[c.oreb] + r[c.dreb]; a.ast += r[c.ast];
      agg.set(r[c.player_id], a);
    }
    const tot = new Map();
    for (const p of dj.players) {
      const a = tot.get(Number(p.id)) || Object.fromEntries(KEYS.map((k) => [k, 0]));
      KEYS.forEach((k) => { a[k] += num(p[k]) || 0; });
      tot.set(Number(p.id), a);
    }
    let exact = 0; const diffs = [];
    for (const [pid, tt] of tot) {
      const g = agg.get(pid);
      if (!g) { if (tt.gp) diffs.push(`${pid}: no game rows`); continue; }
      const d = KEYS.filter((k) => g[k] !== tt[k]).map((k) => `${k}${g[k] - tt[k] > 0 ? '+' : ''}${g[k] - tt[k]}`);
      if (d.length) diffs.push(`${pid}: ${d.join(' ')}`); else exact++;
    }
    const extra = [...agg.keys()].filter((pid) => !tot.has(pid));
    const share = diffs.length / Math.max(1, tot.size);
    const st = diffs.length === 0 && extra.length === 0 ? PASS : (share <= RECON_WARN_SHARE ? WARN : FAIL);
    if (st === FAIL || (st === WARN && reconStatus === PASS)) reconStatus = st;
    reconDetail.push(`${season}: ${exact}/${tot.size} players exact` +
      (diffs.length ? `; differ: ${diffs.slice(0, 6).join(', ')}` : '') +
      (extra.length ? `; ${extra.length} player id(s) in game logs but absent from data.json (data.json gap): ${extra.slice(0, 8).join(', ')}` : ''));
  }

  checks.push({ label: 'Game files: schema (seasons.json, index.json, g/<id>.json, player_logs.json)',
    status: schemaErr.length ? FAIL : PASS,
    detail: schemaErr.length ? schemaErr.slice(0, 8).join('  ') : `${Object.keys(manifest.seasons).join(', ')}: ${boxes} box scores, ${logRows} player-game rows` });
  checks.push({ label: 'Per-game integrity: player (+Team-row) points == score, sum(quarters incl. OT) == score, made ≤ att',
    status: gameErr.length ? FAIL : PASS,
    detail: gameErr.length ? gameErr.slice(0, 8).join('  ') : `all ${boxes} games consistent (${otGames} overtime games)` });
  // header fields are parsed per element; a page-wide regex once swallowed
  // standings + news into "referees" -- guard length and both languages
  const hdrErr = [], hdrGap = [];
  for (const season of Object.keys(manifest.seasons)) {
    const dir = path.join(GAMES_DIR, season, 'g');
    let files = [];
    try { files = fs.readdirSync(dir).filter((f) => f.endsWith('.json')); } catch (e) { /* reported above */ }
    for (const f of files) {
      const b = readJSON(path.join(dir, f));
      if (!b) continue;
      const loc = (v) => (v && typeof v === 'object' && !Array.isArray(v) ? v : { en: v, he: null });
      const refs = loc(b.referees), venue = loc(b.venue);
      for (const lg of ['en', 'he']) {
        const r = refs[lg] || [];
        if (r.some((x) => String(x).length > 40)) hdrErr.push(`${b.id}: ${lg} referee field runs on (${String(r.find((x) => String(x).length > 40)).slice(0, 30)}…)`);
        if (venue[lg] && String(venue[lg]).length > 60) hdrErr.push(`${b.id}: ${lg} venue runs on`);
        // one language blank AT THE SOURCE: the UI falls back to the other one
        if (!r.length) hdrGap.push(`${b.id} ${lg} referees`);
        if (!venue[lg]) hdrGap.push(`${b.id} ${lg} venue`);
      }
      if (!(refs.en || []).length && !(refs.he || []).length) hdrErr.push(`${b.id}: no referees in either language`);
      if (!venue.en && !venue.he) hdrErr.push(`${b.id}: no venue in either language`);
    }
  }
  checks.push({ label: 'Game header: referees + venue in both languages, no runaway text',
    status: hdrErr.length ? FAIL : (hdrGap.length ? WARN : PASS),
    detail: hdrErr.length ? `${hdrErr.length} issue(s): ${hdrErr.slice(0, 6).join('  ')}`
      : (hdrGap.length ? `no runaway text; blank in one language at the source (UI falls back to the other): ${hdrGap.join(', ')}` : 'all box scores clean in both languages') });
  checks.push({ label: 'Source quirks surfaced, not hidden (flagged games / games without a box score)',
    status: (flagged.length || noBox.length) ? WARN : PASS,
    detail: `flagged: ${flagged.join(', ') || 'none'} · no box score: ${noBox.join(', ') || 'none'}` });
  checks.push({ label: `Reconciliation: summed game rows vs data.json season totals (warn ≤ ${RECON_WARN_SHARE * 100}% of players)`,
    status: reconStatus, detail: reconDetail.join('  ') });
  return checks;
}

async function domainENetwork() {
  const checks = [];
  let chromium;
  try { ({ chromium } = require('playwright')); } catch { return checks; }
  const server = await startServer();
  const base = `http://127.0.0.1:${server.address().port}/dashboard.html`;
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  const games = []; const bytes = {};
  page.on('request', (r) => { const u = r.url(); if (u.includes('/games/')) games.push(u.split('/games/')[1].split('?')[0]); });
  page.on('response', async (r) => {
    try {
      const b = await r.body();
      const k = new URL(r.url()).pathname.split('/').pop() || '/';
      bytes[k] = (bytes[k] || 0) + b.length;
    } catch (e) { /* redirects / aborted */ }
  });
  await page.addInitScript(() => { try { localStorage.clear(); } catch (e) {} });
  await page.goto(base, { waitUntil: 'networkidle' });
  await page.waitForTimeout(300);
  const bootGames = games.length;
  const bootBytes = { ...bytes };

  await page.evaluate(() => goTab('league'));
  await page.waitForSelector('.games-results .gm-row:not([aria-disabled])', { timeout: 8000 });
  const boxReqs = () => games.filter((g) => g.includes('/g/')).length;
  const n0 = boxReqs();
  await page.click('.games-results .gm-row:not([aria-disabled])');
  await page.waitForSelector('#bx-overlay:not([hidden]) .bx-table', { timeout: 8000 });
  const firstOpen = boxReqs() - n0;
  await page.keyboard.press('Escape');
  const before = games.length;
  await page.click('.games-results .gm-row:not([aria-disabled])');
  await page.waitForSelector('#bx-overlay:not([hidden]) .bx-table', { timeout: 8000 });
  const reopen = games.length - before;
  await page.keyboard.press('Escape');
  const pid = await page.evaluate(() => [...DATA.players].sort((a, b) => b.pir - a.pir)[0].id);
  await page.evaluate((i) => goPlayer(i), pid);
  await page.waitForSelector('.game-log svg', { timeout: 8000 });
  await page.evaluate(() => goTab('overview'));
  await page.evaluate((i) => goPlayer(i), pid);
  await page.waitForSelector('.game-log svg', { timeout: 8000 });
  const logFetches = games.filter((g) => g.endsWith('player_logs.json')).length;
  await browser.close(); server.close();

  checks.push({ label: 'Lazy loading: zero games/ requests on initial page load',
    status: bootGames === 0 ? PASS : FAIL,
    detail: bootGames === 0 ? 'boot fetches only dashboard.html + data.json (+ optional insights.json)' : `boot requested: ${games.slice(0, bootGames).join(', ')}` });
  checks.push({ label: 'Box score: exactly one request on first open, zero on re-open (in-memory cache)',
    status: firstOpen === 1 && reopen === 0 ? PASS : FAIL, detail: `first open ${firstOpen}, re-open ${reopen}` });
  checks.push({ label: 'Game log: player_logs.json fetched once across repeated player-card visits',
    status: logFetches === 1 ? PASS : FAIL, detail: `${logFetches} fetch(es)` });

  // boot transfer: games/ must add nothing; report dashboard.html growth vs a baseline ref
  let baseline = null;
  try {
    const ref = args.includes('--baseline-ref') ? args[args.indexOf('--baseline-ref') + 1] : 'origin/main';
    const size = require('child_process').execSync(`git show ${ref}:dashboard.html`, { cwd: ROOT, maxBuffer: 64 * 1024 * 1024 }).length;
    baseline = { ref, size };
  } catch (e) { /* no git / unknown ref: absolute sizes only */ }
  const kb = (n) => (n / 1024).toFixed(1) + ' KB';
  const dash = bootBytes['dashboard.html'] || 0;
  const dj = bootBytes['data.json'] || 0;
  const delta = baseline ? dash - baseline.size : null;
  checks.push({ label: 'Initial load size: game data adds nothing to boot (only dashboard.html code growth)',
    status: bootGames === 0 ? PASS : FAIL,
    detail: `dashboard.html ${kb(dash)}${baseline ? ` (${delta >= 0 ? '+' : ''}${kb(delta)} vs ${baseline.ref})` : ''}, data.json ${kb(dj)}, games/ 0 KB` });
  return checks;
}

/* ------------------------------------------------------------------- main */
(async () => {
  const data = loadData();
  const domains = [domainA(data), domainB(data), domainC(data)];
  if (!SKIP_VISUAL) domains.push(await domainD());
  const eChecks = domainEData(data);
  if (!SKIP_VISUAL) eChecks.push(...await domainENetwork());
  domains.push({ name: 'E. Game data (games/ pilot)', checks: eChecks });

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
