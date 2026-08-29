#!/usr/bin/env node
/**
 * gen_og_image.js -- render the 1200x630 branded social-share card
 * (og-image.png) for PlusMinus IL.
 *
 * Uses the Playwright chromium that scripts/qa_responsive_rtl.js already
 * depends on (scripts/node_modules/playwright) -- no Canvas/Pillow needed,
 * and Chromium handles the mixed RTL Hebrew / LTR Latin text and web fonts
 * natively.
 *
 *   cd basketball-analytics/scripts && npm install    # once (playwright)
 *   node scripts/gen_og_image.js [out.png]
 *
 * Default output: basketball-analytics/og-image.png
 */
'use strict';
const path = require('path');

let chromium;
try {
  ({ chromium } = require('playwright'));
} catch (e) {
  console.error('Playwright missing. Run: cd scripts && npm install');
  process.exit(2);
}

const OUT = process.argv[2]
  ? path.resolve(process.argv[2])
  : path.resolve(__dirname, '..', 'og-image.png');

const HTML = `<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Rubik:wght@400;500;600;700;900&display=swap" rel="stylesheet">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { width: 1200px; height: 630px; overflow: hidden; }
  body {
    position: relative;
    background:
      radial-gradient(1200px 700px at 82% 12%, rgba(216,73,46,.16), transparent 60%),
      linear-gradient(135deg, #0B132B 0%, #0F172A 55%, #0A0E13 100%);
    font-family: 'Rubik', system-ui, sans-serif;
    color: #fff;
  }
  .court { position: absolute; inset: 0; opacity: .10; }
  .court svg { width: 100%; height: 100%; }
  .accent-edge { position: absolute; inset-inline-start: 0; top: 0; bottom: 0; width: 10px; background: #D8492E; }
  .wrap { position: absolute; inset: 0; padding: 70px 84px; display: flex; flex-direction: column; }
  .top { display: flex; align-items: center; gap: 26px; }
  .logo { width: 104px; height: 104px; flex: none; }
  .brand-lines { display: flex; flex-direction: column; gap: 8px; }
  .brand-en { font-family: 'Anton', 'Rubik', sans-serif; font-size: 40px; letter-spacing: .04em; text-transform: uppercase; line-height: 1; }
  .brand-kick { font-size: 17px; font-weight: 600; letter-spacing: .22em; text-transform: uppercase; color: #94a3b8; }
  .mid { margin-top: auto; margin-bottom: auto; }
  .title { font-size: 78px; font-weight: 900; line-height: 1.04; letter-spacing: -.01em; }
  .title .sep { color: #D8492E; font-weight: 700; margin: 0 14px; }
  .tagline { margin-top: 24px; font-size: 30px; font-weight: 500; line-height: 1.45; color: #cbd5e1; max-width: 940px; }
  .badges { display: flex; flex-wrap: wrap; gap: 14px; }
  .badge {
    font-size: 21px; font-weight: 600; padding: 11px 20px; border-radius: 999px;
    background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.14); color: #e2e8f0;
    white-space: nowrap;
  }
  .badge.accent { background: rgba(216,73,46,.18); border-color: rgba(216,73,46,.5); color: #ffd9cf; }
  .url { position: absolute; left: 84px; right: auto; bottom: 46px; font-size: 19px; font-weight: 600; letter-spacing: .04em; color: #64748b; direction: ltr; }
</style></head>
<body>
  <div class="court" aria-hidden="true">
    <svg viewBox="0 0 1200 630" fill="none" stroke="#ffffff" stroke-width="2.5">
      <circle cx="1000" cy="150" r="230"/>
      <circle cx="1000" cy="150" r="70"/>
      <path d="M1200 470 A 320 320 0 0 1 620 630"/>
      <line x1="120" y1="0" x2="120" y2="630"/>
      <circle cx="120" cy="315" r="90"/>
      <rect x="0" y="215" width="220" height="200"/>
    </svg>
  </div>
  <div class="accent-edge"></div>
  <div class="wrap">
    <div class="top">
      <svg class="logo" viewBox="0 0 64 64" aria-hidden="true">
        <rect x="1" y="1" width="62" height="62" rx="13" fill="#0A0E13" stroke="rgba(255,255,255,.14)"/>
        <circle cx="32" cy="32" r="20" fill="none" stroke="rgba(255,255,255,.18)" stroke-width="2"/>
        <line x1="32" y1="8" x2="32" y2="56" stroke="rgba(255,255,255,.18)" stroke-width="2"/>
        <g stroke-linecap="round">
          <line x1="17" y1="24" x2="31" y2="24" stroke="#D8492E" stroke-width="6.5"/>
          <line x1="24" y1="17" x2="24" y2="31" stroke="#D8492E" stroke-width="6.5"/>
          <line x1="34" y1="43" x2="48" y2="43" stroke="#ffffff" stroke-width="6.5"/>
        </g>
      </svg>
      <div class="brand-lines">
        <div class="brand-en">PlusMinus IL</div>
        <div class="brand-kick">PlusMinus.IL · אנליטיקס כדורסל ישראלי</div>
      </div>
    </div>
    <div class="mid">
      <div class="title" dir="rtl">PlusMinus IL<span class="sep">|</span>פלוס מינוס</div>
      <div class="tagline">פלטפורמת הנתונים והאנליטיקס המתקדמת של הכדורסל הישראלי</div>
    </div>
    <div class="badges">
      <span class="badge accent">10 עונות היסטוריות</span>
      <span class="badge">מדדי יעילות מתקדמים</span>
      <span class="badge">מפת חצי מגרש</span>
      <span class="badge">Four Factors</span>
    </div>
  </div>
  <div class="url">d1bmim02dszrj9.cloudfront.net</div>
</body></html>`;

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
  await page.setContent(HTML, { waitUntil: 'networkidle' });
  try { await page.evaluate(() => document.fonts.ready); } catch (e) {}
  await page.waitForTimeout(250);
  await page.screenshot({ path: OUT, clip: { x: 0, y: 0, width: 1200, height: 630 } });
  await browser.close();
  console.log('wrote ' + OUT);
})().catch((e) => { console.error(e); process.exit(1); });
