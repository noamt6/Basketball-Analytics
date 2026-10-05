#!/usr/bin/env node
/**
 * build_architecture_pdf.js -- render AWS_Basketball_Architecture.pdf
 *
 * A Hebrew (RTL), study-oriented "System Architecture Document" for the
 * PlusMinus IL basketball-analytics AWS stack. Prose-heavy: every component is
 * explained in words (what it is, what it does here, why it was chosen) around
 * the reference tables. Every English term / service id / ARN is BiDi-isolated
 * so digits, hyphens and slashes never reorder inside the Hebrew text.
 *
 * Mirrors scripts/gen_og_image.js: inline styled HTML -> Playwright chromium.
 * Here we call page.pdf() instead of page.screenshot().
 *
 *   cd basketball-analytics/scripts && npm install    # once (playwright)
 *   node scripts/build_architecture_pdf.js [out.pdf]
 *
 * Default output: <workspace root>/basketball-analytics/docs/AWS_Basketball_Architecture.pdf
 */
'use strict';
const path = require('path');
const fs = require('fs');

let chromium;
try {
  ({ chromium } = require('playwright'));
} catch (e) {
  console.error('Playwright missing. Run: cd scripts && npm install');
  process.exit(2);
}

const OUT = process.argv[2]
  ? path.resolve(process.argv[2])
  : path.resolve(__dirname, '..', 'docs', 'AWS_Basketball_Architecture.pdf');

// --- BiDi helper: wrap an LTR technical token so it renders left-to-right ---
const esc = (s) => String(s).replace(/[&<>"]/g, (ch) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]
));
const c = (s) => `<code dir="ltr">${esc(s)}</code>`;             // monospace id / command
const l = (s) => `<span class="ltr" dir="ltr">${esc(s)}</span>`; // inline LTR phrase

const ARN_ACM = 'arn:aws:acm:us-east-1:402631154156:certificate/f1362ce6-9c79-41be-900d-a50e23136695';

const HTML = `<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8"><style>
  :root{
    --ink:#12213b; --muted:#5b6b83; --line:#d7deea; --accent:#1f5fa8;
    --accent-soft:#eef4fb; --band:#f4f7fb; --warn:#b4530f; --warn-soft:#fdf3e7;
    --ok:#166149; --ok-soft:#ecf6f1;
  }
  *{box-sizing:border-box;}
  html,body{margin:0;padding:0;}
  body{
    font-family:'Segoe UI', Tahoma, Arial, sans-serif;
    color:var(--ink); font-size:10.5pt; line-height:1.7;
    background:#fff;
  }
  .ltr{unicode-bidi:isolate; direction:ltr;}
  code{
    font-family:'Consolas','Courier New',monospace;
    unicode-bidi:isolate; direction:ltr; white-space:normal; word-break:break-all;
    background:#eef1f6; border:1px solid var(--line); border-radius:4px;
    padding:0 4px; font-size:9pt;
  }
  h1,h2,h3,h4{line-height:1.3; margin:0;}
  p{margin:.55em 0;}
  ul,ol{margin:.4em 0; padding-inline-start:1.4em;}
  li{margin:.32em 0;}
  strong{color:var(--accent);}
  .term{font-weight:700; color:var(--ink);}

  /* ---- title page ---- */
  .cover{
    height:247mm; display:flex; flex-direction:column; justify-content:center;
    padding:0 4mm; page-break-after:always;
  }
  .cover .kick{font-size:11pt; letter-spacing:.06em; color:var(--accent); font-weight:700;}
  .cover h1{font-size:29pt; margin:.35em 0 .15em; letter-spacing:-.01em;}
  .cover .sub{font-size:12.5pt; color:var(--muted); max-width:155mm;}
  .cover .meta{margin-top:12mm; border-top:2px solid var(--line); padding-top:6mm;
    font-size:9.5pt; color:var(--muted);}
  .cover .meta div{margin:.25em 0;}
  .cover .toc{margin-top:8mm; font-size:9.5pt; color:var(--muted);}
  .cover .toc li{margin:.15em 0;}

  /* ---- chapters ---- */
  .chapter{page-break-before:always;}
  .chapter > h2{
    font-size:16pt; color:var(--accent); border-bottom:2px solid var(--accent);
    padding-bottom:3mm; margin-bottom:4mm;
  }
  h3{font-size:11.5pt; margin:6mm 0 2mm; color:var(--ink);
    border-inline-start:4px solid var(--accent); padding-inline-start:3mm;}
  h4{font-size:10.5pt; margin:4mm 0 1mm; color:var(--accent);}

  .lead{font-size:10.8pt; color:#33445e; margin:2mm 0 3mm;}
  .tcap{font-size:8.6pt; color:var(--muted); margin:1mm 0 4mm;}

  table{width:100%; border-collapse:collapse; margin:3mm 0; font-size:9.3pt;
    break-inside:avoid;}
  th,td{border:1px solid var(--line); padding:4px 7px; text-align:right; vertical-align:top;}
  thead th{background:var(--accent); color:#fff; font-weight:600;}
  tbody tr:nth-child(even){background:var(--band);}
  td.num{text-align:left; unicode-bidi:isolate; direction:ltr; white-space:nowrap;}

  .callout{
    border:1px solid var(--line); border-inline-start:5px solid var(--accent);
    background:var(--accent-soft); border-radius:6px; padding:3mm 4mm; margin:4mm 0;
    break-inside:avoid;
  }
  .callout.warn{border-inline-start-color:var(--warn); background:var(--warn-soft);}
  .callout.ok{border-inline-start-color:var(--ok); background:var(--ok-soft);}
  .callout .lbl{font-weight:700; font-size:8.5pt; letter-spacing:.04em;
    text-transform:uppercase; color:var(--muted); display:block; margin-bottom:1mm;}

  .flow{font-size:10pt; background:var(--band); border:1px dashed var(--line);
    border-radius:6px; padding:3mm 4mm; margin:3mm 0; line-height:2;}

  .card{border:1px solid var(--line); border-radius:8px; padding:3mm 4mm;
    margin:3mm 0; break-inside:avoid;}
  .card .q{font-weight:700; color:var(--accent); font-size:10.5pt; margin-bottom:1.5mm;}
  .card .q::before{content:"?  "; color:var(--warn); font-weight:800;}
  .card .a{margin:1mm 0;}

  .principle{margin:3mm 0; break-inside:avoid;}
  .principle .tag{font-weight:700; color:var(--accent); font-size:10.8pt;}
</style></head>
<body>

<section class="cover">
  <div class="kick">PLUSMINUS IL &nbsp;·&nbsp; PRODUCTION SYSTEM ARCHITECTURE</div>
  <h1>מסמך ארכיטקטורת מערכת<br>פלטפורמת אנליטיקת הכדורסל</h1>
  <div class="sub">סיכום הנדסי מלא ומוסבר — לבחינה ולראיון עבודה. תשתית ${l('AWS')}
  מבוססת ${l('Serverless')}, מונחית-אירועים, עם ${l('FinOps')} קפדני. המסמך כולל את כל
  מזהי המשאבים האמיתיים מסביבת הייצור, ומסביר במילים כל רכיב: מה הוא, מה תפקידו כאן,
  ולמה נבחר.</div>
  <div class="meta">
    <div><strong>חשבון:</strong> ${c('402631154156')}</div>
    <div><strong>דומיין:</strong> ${c('plusminus.cloud')} · ${c('www.plusminus.cloud')}</div>
    <div><strong>אזורים:</strong> ${c('us-east-1')} (קצה / ${l('CloudFront')} / ${l('ACM')}) ·
      ${c('eu-central-1')} (${l('Lambda')} / ${l('Bedrock')})</div>
  </div>
  <div class="toc"><strong>תוכן העניינים</strong>
    <ol>
      <li>תמצית מנהלים ועקרונות תכנון — מה זה ${l('Serverless')}, ${l('Event-Driven')},
        ${l('Least-Privilege')} ו-${l('FinOps')}, ולמה הם מתאימים למערכת הזו</li>
      <li>פירוט רכיבי התשתית — ${l('Route 53')}, ${l('ACM')}, ${l('CloudFront')},
        ${l('S3')} + ${l('OAC')}, ניטור, וצינור ה-${l('GenAI')}</li>
      <li>זרימת המידע ואינטגרציית ה-${l('AI')} — מסלול הבקשה, ודפוס
        ${l('Asynchronous Batch AI Caching')}</li>
      <li>ניתוח ${l('FinOps')} — טבלת עלויות אמיתית וניתוח חלופות שנפסלו</li>
      <li>כרטיסיות שליפה לראיון — שאלות מכשילות ותשובות מלאות</li>
    </ol>
  </div>
</section>

<!-- ================= פרק 0 ================= -->
<section class="chapter">
  <h2>לפני שמתחילים — סיכום ב-60 שניות ומילון מונחים</h2>
  <div class="callout ok"><span class="lbl">הסיכום</span>
  <ul>
    <li><strong>מה זה?:</strong> אתר אנליטיקה לכדורסל ליגת העל הישראלית: 10 עונות של נתוני שחקנים וקבוצות, עם מדדים מתקדמים וגרפים.</li>
    <li><strong>איך בנוי?:</strong> האתר הוא קבצים סטטיים (דף <span class="ltr" dir="ltr">HTML</span> וקובץ נתונים אחד) ששמורים ב־<span class="ltr" dir="ltr">S3</span> ומוגשים דרך <span class="ltr" dir="ltr">CloudFront</span> בכתובת <span class="ltr" dir="ltr">plusminus.cloud.</span> אין שרת שרץ.</li>
    <li><strong>איפה המחשוב?:</strong> כל החישוב הכבד נעשה מראש, בזמן הבנייה: קוד פייתון מחשב את המדדים ומייצר את קובץ הנתונים. הדפדפן רק מציג.</li>
    <li><strong>מה עם בסיס הנתונים?:</strong> היה <span class="ltr" dir="ltr">RDS</span> (<span class="ltr" dir="ltr">PostgreSQL</span>) שהחזיק את הנתונים. מחקתי אותו כדי לא לשלם על מכונה שרצה <span class="ltr" dir="ltr">24/7</span> לחינם, ושמרתי <span class="ltr" dir="ltr">snapshot</span> לשחזור.</li>
    <li><strong>איפה ה־<span class="ltr" dir="ltr">AI</span>?:</strong> פעם ביום <span class="ltr" dir="ltr">Lambda</span> שולחת ל־<span class="ltr" dir="ltr">Bedrock</span> (מודל שפה) את הנתונים הבולטים, ומקבלת סיכום מגמות בעברית שנשמר כקובץ. עוזר האנליטיקה בצ'אט עצמו מבוסס כללים, לא מודל.</li>
    <li><strong>כמה זה עולה?:</strong> כ־<span class="ltr" dir="ltr">$1</span> בחודש (בעיקר ה־<span class="ltr" dir="ltr">DNS</span> של הדומיין). בשיא, כשה־<span class="ltr" dir="ltr">RDS</span> רץ, החיוב הגולמי היה כ־<span class="ltr" dir="ltr">$9</span> בחודש. כיסו את זה קרדיטים, אבל לא רציתי לשלם סתם.</li>
    <li><strong>איך מבטיחים איכות?:</strong> בדיקות אוטומטיות בודקות שהמתמטיקה בנתונים עקבית ושהאתר נראה תקין ב-8 גדלי מסך, בעברית ובאנגלית.</li>
    <li><strong>מה המגבלה הכנה?:</strong> יש רק סיכומי עונה. אין קואורדינטות זריקה, אין <span class="ltr" dir="ltr">play-by-play</span> ואין <span class="ltr" dir="ltr">game logs</span>, ולכן המפות אזוריות ולא נקודתיות.</li>
    <li><strong>שים לב:</strong> האתר חסום מחוץ לישראל (<span class="ltr" dir="ltr">Geo-Restriction</span>), ולכן מי שנכנס מחו"ל יקבל שגיאת 403.</li>
  </ul></div>
  <p class="tcap">איך ללמוד: קרא את הסיכום ואת המילון, ואז את פרק 5 (כרטיסיות הראיון). פרקים 1–4 הם ההסבר המלא שמאחורי התשובות.</p>
  <h3>מילון מונחים קצר</h3>
  <table>
    <thead><tr><th>מונח</th><th>בעברית פשוטה</th></tr></thead>
    <tbody>
      <tr><td class="term"><span class="ltr" dir="ltr">S3</span></td><td>אחסון קבצים של <span class="ltr" dir="ltr">AWS.</span> כאן הוא 'הכספת' שבה יושבים דף האתר וקובץ הנתונים.</td></tr>
      <tr><td class="term"><span class="ltr" dir="ltr">CloudFront</span> (<span class="ltr" dir="ltr">CDN</span>)</td><td>רשת שמעתיקה את הקבצים לשרתים קרובים לגולש, כדי שהאתר ייטען מהר. היא גם שומרת עותק (<span class="ltr" dir="ltr">cache</span>) כדי לא לפנות ל־<span class="ltr" dir="ltr">S3</span> בכל פעם.</td></tr>
      <tr><td class="term"><span class="ltr" dir="ltr">OAC</span></td><td>מנגנון שמאפשר רק ל־<span class="ltr" dir="ltr">CloudFront</span> לקרוא מה־<span class="ltr" dir="ltr">S3.</span> אי אפשר להיכנס ל־<span class="ltr" dir="ltr">S3</span> ישירות בכתובת.</td></tr>
      <tr><td class="term"><span class="ltr" dir="ltr">Cache</span> ו־<span class="ltr" dir="ltr">Invalidation</span></td><td><span class="ltr" dir="ltr">Cache</span> = עותק שמור. <span class="ltr" dir="ltr">Invalidation</span> = בקשה למחוק את העותק כדי שהגולשים יקבלו את הגרסה החדשה מיד אחרי עדכון.</td></tr>
      <tr><td class="term"><span class="ltr" dir="ltr">Lambda</span></td><td>קוד שרץ רק כשמפעילים אותו ואתה משלם רק על שניות הריצה. אין שרת שמחכה.</td></tr>
      <tr><td class="term"><span class="ltr" dir="ltr">EventBridge</span></td><td>שעון מתוזמן של <span class="ltr" dir="ltr">AWS.</span> אצלי הוא מפעיל את ה־<span class="ltr" dir="ltr">Lambda</span> כל יום ב-<span class="ltr" dir="ltr">06:00 UTC</span>.</td></tr>
      <tr><td class="term"><span class="ltr" dir="ltr">Bedrock</span></td><td>שירות של <span class="ltr" dir="ltr">AWS</span> שנותן גישה למודלי שפה (<span class="ltr" dir="ltr">AI</span>) דרך <span class="ltr" dir="ltr">API</span>, בלי לארח אותם בעצמי.</td></tr>
      <tr><td class="term"><span class="ltr" dir="ltr">RDS</span> ו־<span class="ltr" dir="ltr">Snapshot</span></td><td><span class="ltr" dir="ltr">RDS</span> = בסיס נתונים מנוהל שרץ כל הזמן ועולה כסף. <span class="ltr" dir="ltr">Snapshot</span> = צילום שלו ששורד גם אחרי שמוחקים אותו, ואפשר לשחזר ממנו.</td></tr>
      <tr><td class="term"><span class="ltr" dir="ltr">IAM</span></td><td>מערכת ההרשאות של <span class="ltr" dir="ltr">AWS.</span> עיקרון 'הרשאה מינימלית': כל רכיב מקבל רק מה שהוא באמת צריך.</td></tr>
      <tr><td class="term"><span class="ltr" dir="ltr">Serverless</span> / <span class="ltr" dir="ltr">Static</span></td><td>לא מנהלים שרתים בעצמך. באתר סטטי אין קוד שרץ בשרת בזמן הבקשה, אלא רק קבצים מוכנים.</td></tr>
      <tr><td class="term"><span class="ltr" dir="ltr">ETL</span> / <span class="ltr" dir="ltr">Upsert</span></td><td><span class="ltr" dir="ltr">ETL</span> = לקרוא נתונים, לעבד אותם ולטעון למקום חדש. <span class="ltr" dir="ltr">Upsert</span> = הוספה או עדכון, כך שאפשר להריץ שוב בלי כפילויות.</td></tr>
      <tr><td class="term"><span class="ltr" dir="ltr">VPC</span> ו־<span class="ltr" dir="ltr">NAT Gateway</span></td><td><span class="ltr" dir="ltr">VPC</span> = רשת פרטית ב־<span class="ltr" dir="ltr">AWS. NAT Gateway</span> = רכיב שנותן לרשת פרטית גישה לאינטרנט, ועולה כ־<span class="ltr" dir="ltr">$32</span> לחודש קבוע. <span class="ltr" dir="ltr">Lambda</span> שלי רצה בלי <span class="ltr" dir="ltr">VPC</span> ולכן לא צריכה אותו.</td></tr>
      <tr><td class="term"><span class="ltr" dir="ltr">PIR</span></td><td>מדד יעילות אירופי: חיוביים (נקודות, ריבאונדים, אסיסטים...) פחות שליליים (החטאות, איבודים...).</td></tr>
      <tr><td class="term"><span class="ltr" dir="ltr">TS%</span> ו־<span class="ltr" dir="ltr">eFG%</span></td><td>אחוזי קליעה מתוקנים: <span class="ltr" dir="ltr">eFG%</span> נותן משקל מלא לשלשה, ו־<span class="ltr" dir="ltr">TS%</span> מוסיף גם זריקות עונשין. שניהם אמינים יותר מאחוז קליעה גולמי.</td></tr>
    </tbody>
  </table>
</section>

<!-- ================= פרק 1 ================= -->
<section class="chapter">
  <h2>פרק 1 — תמצית מנהלים ועקרונות תכנון (Architecture Philosophy)</h2>

  <h3>1.1 &nbsp; מה המערכת עושה</h3>
  <p class="lead">הפלטפורמה היא כלי <strong>אנליטיקת ביצועי כדורסל</strong> לליגת העל
  הישראלית. היא לוקחת נתוני סיכום-עונה גולמיים (כמה נקודות, ריבאונדים, אסיסטים, איבודים
  וכו' צבר כל שחקן וכל קבוצה במהלך העונה), מחשבת מהם מדדים מתקדמים, ומציגה אותם בדף
  ${l('dashboard')} אינטראקטיבי אחד.</p>
  <p>המדד המרכזי הוא ${l('PIR')} — <span class="term">Performance Index Rating</span>,
  מדד יעילות מצרפי שמקובל בכדורסל האירופי: הוא מחבר את כל התרומות החיוביות של השחקן
  (נקודות, ריבאונדים, אסיסטים, חטיפות, חסימות, עבירות שנספגו) ומחסר מהן את השליליות
  (זריקות ומסירות שהוחמצו, איבודים, עבירות שבוצעו). לצידו מחושבים מדדי יעילות נוספים:
  ${l('TS%')} (${l('True Shooting')} — אחוז קליעה שמנרמל זריקות שדה, שלשות וזריקות עונשין
  לערך אחד), ${l('eFG%')} (${l('Effective Field Goal')} — אחוז קליעה שנותן משקל עודף
  לשלשה), ${l('AST/TOV')} (יחס אסיסטים לאיבודים), ו-${l('Per-36')} (נרמול הסטטיסטיקה
  ל-36 דקות משחק, כדי להשוות שחקנים עם זמן מגרש שונה).</p>
  <p>נקודה הנדסית קריטית: <strong>הנתונים הם קריאה בלבד</strong>. אין משתמשים מחוברים,
  אין טפסים, אין כתיבה מהקהל, והתוכן מתעדכן רק כשמריצים מחדש את צינור העיבוד. תכונה זו
  היא הסיבה שכל שאר ההחלטות בארכיטקטורה הזו הגיוניות — אין צורך במסד נתונים חי, אין
  ${l('API')} דינמי, ואפשר להגיש את הכול כקבצים סטטיים.</p>

  <h3>1.2 &nbsp; ארבעת עקרונות הברזל — מוסברים</h3>

  <div class="principle">
    <div class="tag">${l('Event-Driven')} — מונחה אירועים</div>
    <p>המערכת לא "בודקת כל הזמן אם יש עבודה" (מה שנקרא ${l('polling')}), אלא <strong>מגיבה
    לאירוע</strong> ברגע שהוא קורה. האירוע שמפעיל את החלק ה"חכם" הוא שעון מתוזמן:
    ${c('EventBridge')} יורה פעם ביום ומפעיל את צינור ה-${l('GenAI')}. בקשות הגולשים עצמן
    מוגשות כקבצים סטטיים בלי להריץ קוד. בין האירועים <strong>שום דבר לא רץ</strong> ולכן שום דבר לא עולה כסף.
    זה ההבדל מול שרת מסורתי שמאזין 24/7.</p>
  </div>

  <div class="principle">
    <div class="tag">${l('Serverless-First')} — ללא שרתים</div>
    <p>"${l('Serverless')}" לא אומר "אין שרתים" אלא <strong>"אתה לא מנהל אותם"</strong>.
    כל רכיב במערכת הוא שירות מנוהל של ${l('AWS')} שמתוחזק, מתעדכן ומתרחב אוטומטית:
    ${l('S3')} לאחסון, ${l('CloudFront')} להפצה, ${l('Lambda')} לקוד, ${l('Bedrock')}
    למודל ה-${l('AI')}. אין ${l('EC2')} (מכונה וירטואלית) לתחזק, אין ${l('OS patching')}
    (עדכוני אבטחה למערכת ההפעלה), ואין ${l('capacity planning')} (ניחוש כמה כוח מחשוב
    להקצות). הקיבולת מתאפסת לאפס כשאין שימוש, וקופצת מיידית כשצריך.</p>
  </div>

  <div class="principle">
    <div class="tag">${l('Least-Privilege IAM')} — הרשאות מינימום</div>
    <p>${l('IAM')} (${l('Identity and Access Management')}) הוא מערכת ההרשאות של
    ${l('AWS')}. העיקרון: כל רכיב מקבל <strong>בדיוק את ההרשאות שהוא צריך ולא יותר</strong>.
    ל-${l('Lambda')} שלנו יש מדיניות ${l('inline')} (מדיניות שמוצמדת ישירות לתפקיד, לא
    משותפת) עם <strong>ארבע פעולות בלבד</strong>, כל אחת ממופה למשאב יחיד ספציפי — אין
    אף ${l('wildcard')} (כוכבית שמשמעה "הכול"). כך, גם אם הקוד נפרץ, התוקף לא יכול לעשות
    יותר ממה שהפונקציה עצמה עושה.</p>
  </div>

  <div class="principle">
    <div class="tag">${l('Strict FinOps')} — משמעת עלויות</div>
    <p>${l('FinOps')} = ${l('Financial Operations')}, הדיסציפלינה של ניהול עלות הענן
    כחלק מהתכנון ההנדסי ולא כבדיעבד. כאן זה הוביל לעלות כוללת של
    <strong>כ-${l('$1')} לחודש</strong> — שהיא בעיקר עלות ה-${l('Route 53 Hosted Zone')},
    שאי אפשר להימנע ממנה. כל שאר הרכיבים נכנסים לתוך ה-${l('Free Tier')} של ${l('AWS')}
    או עולים שברירי סנט. בנוסף, ${l('Geo-Restriction')} (ראה 2.3) חוסמת מראש תעבורה
    מחוץ לישראל — גם כהגנה וגם כתקרת עלות.</p>
  </div>

  <div class="callout ok"><span class="lbl">שורה תחתונה</span>
  ארבעת העקרונות מתכנסים ל-<strong>${l('Zero-Maintenance')}</strong>: אין תור תחזוקה,
  אין ${l('scaling')} ידני, אין הפתעות בחשבון בסוף החודש. המערכת "רצה לבד" ומתעדכנת
  אוטומטית פעם ביום. זה אפשרי רק כי אופי הנתונים (קריאה בלבד, עדכון יומי) מתאים בול
  לארכיטקטורה סטטית + ${l('batch')}.</div>
</section>

<!-- ================= פרק 2 ================= -->
<section class="chapter">
  <h2>פרק 2 — פירוט רכיבי התשתית (Component Deep Dive &amp; True ARNs)</h2>
  <p class="lead">לכל רכיב: פסקת הסבר (מה זה ולמה בחרנו בו), ואז טבלת ייחוס עם המזהים
  האמיתיים.</p>

  <h3>2.1 &nbsp; DNS וניתוב קצה — Route 53</h3>
  <p>${l('DNS')} (${l('Domain Name System')}) הוא "ספר הטלפונים" של האינטרנט — הוא מתרגם
  שם קריא (${c('plusminus.cloud')}) לכתובת של שרת. ${l('Route 53')} הוא שירות ה-${l('DNS')}
  המנוהל של ${l('AWS')}. ה-<span class="term">Hosted Zone</span> הוא האוסף של כל רשומות
  ה-${l('DNS')} של הדומיין שלנו.</p>
  <p>השתמשנו ברשומות <span class="term">Alias</span> ולא ברשומות ${l('CNAME')} רגילות.
  ההבדל: ${l('Alias')} היא המצאה של ${l('AWS')} שמצביעה ישירות על משאב ${l('AWS')}
  (כאן — ה-${l('CloudFront distribution')}), נפתרת בצד השרת, <strong>עובדת גם לשם
  השורש</strong> של הדומיין (${l('apex')} — ${c('plusminus.cloud')} בלי ${l('www')},
  דבר ש-${l('CNAME')} אוסר טכנית), <strong>וחינמית</strong> — שאילתות ${l('Alias')}
  ל-${l('CloudFront')} לא מחויבות. יצרנו שתי רשומות ${l('Alias')} — לשורש ול-${l('www')}
  — כדי ששתי הצורות של הכתובת יעבדו.</p>
  <table>
    <tbody>
      <tr><th>Hosted Zone ID</th><td>${c('Z08760831K1ID5J0TLH88')} עבור ${c('plusminus.cloud')}</td></tr>
      <tr><th>רשומות</th><td>${l('Alias')} ${c('A')} + ${c('AAAA')} עבור ${c('plusminus.cloud')}
        ועבור ${c('www.plusminus.cloud')} — שתיהן מצביעות על ה-${l('CloudFront distribution')}</td></tr>
      <tr><th>רישום הדומיין</th><td>נרכש אצל רשם חיצוני (לא ב-${l('Route 53')}); ${l('Route 53')} משמש רק כשרת ${l('DNS')}</td></tr>
      <tr><th>עלות</th><td>כ-${l('$1')} לחודש על ה-${l('Hosted Zone')} (ספטמבר 2026, ${l('Cost Explorer')}); שאילתות ${l('DNS')} — פחות מסנט; רשומות ה-${l('Alias')} — חינם</td></tr>
    </tbody>
  </table>

  <h3>2.2 &nbsp; אבטחה ותעודות — ACM (SSL/TLS)</h3>
  <p>${l('TLS')} (${l('Transport Layer Security')}, היורש של ${l('SSL')}) הוא הפרוטוקול
  שמצפין את התעבורה בין הדפדפן לאתר — זה ה-"s" ב-${l('https')} והמנעול בשורת הכתובת.
  כדי להפעיל אותו צריך <span class="term">תעודה</span> דיגיטלית שמאמתת שאנחנו באמת
  הבעלים של הדומיין. ${l('ACM')} (${l('AWS Certificate Manager')}) מנפיק תעודות כאלה
  <strong>בחינם</strong> ו<strong>מחדש אותן אוטומטית</strong> לפני שהן פגות — אפס
  תחזוקה, ואפס סיכון של "האתר נפל כי התעודה פגה".</p>
  <p>שתי דקויות מקצועיות: (1) התעודה חייבת לשבת באזור ${c('us-east-1')} דווקא, כי
  ${l('CloudFront')} הוא שירות גלובלי שקורא תעודות רק משם. (2) בחרנו מדיניות אבטחה
  ${c('TLSv1.2_2021')} — היא קובעת <span class="term">פרוטוקול מינימלי</span> של
  ${l('TLS 1.2')} ומעלה, ופוסלת גרסאות ישנות (${l('TLS 1.0/1.1')}) וצפנים חלשים שכבר
  נחשבים פגיעים.</p>
  <table>
    <tbody>
      <tr><th>ARN</th><td>${c(ARN_ACM)}</td></tr>
      <tr><th>אזור</th><td>${c('us-east-1')} — חובה עבור ${l('CloudFront')}</td></tr>
      <tr><th>SANs</th><td>${c('plusminus.cloud')} + ${c('www.plusminus.cloud')}, אימות ${l('DNS-validated')}</td></tr>
      <tr><th>מדיניות</th><td>${c('TLSv1.2_2021')} — ${l('minimum protocol')} ל-${l('TLS 1.2')}+</td></tr>
      <tr><th>חידוש</th><td>${l('Managed renewal')} אוטומטי</td></tr>
    </tbody>
  </table>

  <h3>2.3 &nbsp; הפצה, מטמון וסינון — CloudFront</h3>
  <p>${l('CloudFront')} הוא ה-<span class="term">CDN</span> (${l('Content Delivery Network')})
  של ${l('AWS')} — רשת של מאות שרתי קצה (${l('POPs')} — ${l('Points of Presence')})
  פרוסים גיאוגרפית. כשגולש מבקש את הדף, הוא מקבל אותו מה-${l('POP')} הקרוב
  אליו פיזית ולא מה-${l('S3')} שיושב באזור אחד — זה מקצר משמעותית את זמן הטעינה
  (${l('latency')}).</p>
  <p><span class="term">Caching (מטמון)</span>: ה-${l('POP')} שומר עותק של התוכן לזמן
  מוגדר (${l('TTL')} — ${l('Time To Live')}) ומגיש אותו ישירות מבלי לפנות ל-${l('S3')}.
  קבענו ${l('TTL')} קצר על ${l('HTML')} ו-${c('data.json')} (כדי שהעדכון היומי יופיע
  מהר) ו-${l('TTL')} ארוך על תמונות ו-${l('SVG')} (שלא משתנים). דחיסת ${l('Gzip/Brotli')}
  פעילה כדי להקטין את גודל ההעברה.</p>
  <p><span class="term">Geo-Restriction</span>: הגדרנו ${l('whitelist')} של ישראל בלבד.
  כל בקשה ממדינה אחרת נחסמת כבר בקצה עם שגיאת ${c('403')} — היא אף פעם לא מגיעה ל-${l('S3')}.
  מכיוון שכל קהל היעד מקומי, זה משיג שתי מטרות בו-זמנית: <strong>הקטנת שטח התקיפה</strong>
  (בוטים וסורקים זרים לא נכנסים) ו<strong>תקרת עלות</strong> (תעבורה זדונית מחו"ל לא
  מייצרת חיוב).</p>
  <table>
    <tbody>
      <tr><th>Distribution ID</th><td>${c('E155IZM1SR95HY')}</td></tr>
      <tr><th>Origin</th><td>${l('S3')} דרך ${l('OAC')} (ראה 2.5), לא ${l('website endpoint')}</td></tr>
      <tr><th>Caching</th><td>${l('TTL')} קצר ל-${l('HTML/JSON')}, ${l('TTL')} ארוך לנכסים סטטיים, ${l('Gzip/Brotli')}</td></tr>
      <tr><th>Geo-Restriction</th><td>${l('whitelist')} = ישראל; כל השאר → ${c('403')} בקצה</td></tr>
      <tr><th>TLS</th><td>${c('TLSv1.2_2021')} + ${l('HTTP/2')}, ${l('redirect')} מ-${l('HTTP')} ל-${l('HTTPS')}</td></tr>
    </tbody>
  </table>

  <h3>2.4 &nbsp; ניטור (Observability) — מה קיים בפועל</h3>
  <p><span class="term">Observability</span> = היכולת לדעת מה קורה במערכת מבחוץ, דרך
  לוגים ומדדים. כרגע הניטור מינימלי ובמכוון: ה-${l('Lambda')} של ה-${l('GenAI')} כותבת לוגים
  ל-<span class="term">CloudWatch Logs</span> (דרך ${c('AWSLambdaBasicExecutionRole')}) עם
  <span class="term">retention של 14 יום</span> — הלוגים נמחקים אוטומטית אחרי שבועיים, כדי
  למנוע הצטברות עלות. כל הרצה מדפיסה שורת סיכום (עונה, אורך הטקסט, טוקנים, מזהה ${l('invalidation')}).</p>
  <div class="callout warn"><span class="lbl">מה עדיין לא קיים ברמת הפרויקט</span>
  אין ${l('CloudFront Function')} או ${l('Lambda@Edge')} שרושמים בקשות גולשים, ואין ${l('alarm')} ייעודי
  על עלות ${l('Bedrock')} ספציפית. <strong>כן קיימת</strong> רשת ביטחון ברמת כל חשבון ${l('AWS')} (לא
  ספציפית לפרויקט הזה): שני ${l('AWS Budgets')} אישיים ("${l('Emergency Kill-Switch')}" ו-"${l('Monthly Cost Budget')}", שניהם סביב ${l('$10')}) ששולחים התראה אם החיוב החודשי הכולל חוצה סף — וגם
  ${l('CloudFront standard logging')} ל-${l('S3')} כן מופעל בפועל (${l('bucket')}
  ${c('plusminus-cloudfront-logs-402631154156')}), ברמת כל התעבורה לאתר.</div>
  <table>
    <tbody>
      <tr><th>לוגי Lambda</th><td>${c('/aws/lambda/bball-genai-insights')} ב-${l('CloudWatch Logs')}</td></tr>
      <tr><th>Retention</th><td>14 יום, מחיקה אוטומטית</td></tr>
      <tr><th>בדיקת תקינות</th><td>הרצה ידנית עם ${c('scripts/deploy_genai_insights.py --invoke')} מחזירה סטטוס ותשובה</td></tr>
    </tbody>
  </table>

  <h3>2.5 &nbsp; אחסון ומקור מאובטח — S3 + OAC</h3>
  <p>${l('S3')} (${l('Simple Storage Service')}) הוא אחסון האובייקטים של ${l('AWS')} —
  כאן הוא ה-<span class="term">origin</span>, המקום שבו יושבים הקבצים האמיתיים
  (${c('dashboard.html')}, ${c('data.json')}, ${c('insights.json')}, מדיה). ה-${l('bucket')}
  קרוי ${c('bball-dashboard-402631154156')} (מספר החשבון בשם הוא מוסכמה שמבטיחה ייחודיות
  גלובלית).</p>
  <p>ה-${l('bucket')} <strong>אטום לחלוטין לאינטרנט</strong>: ${l('Block Public Access')}
  מופעל על ארבעת הדגלים, אין ${l('bucket policy')} ציבורי ואין ${l('ACL')} ציבורי.
  אז איך ${l('CloudFront')} קורא ממנו? דרך <span class="term">OAC</span>
  (${l('Origin Access Control')}) — מנגנון שבו ${l('CloudFront')} חותם כל בקשה ל-${l('S3')}
  בחתימת ${l('SigV4')}, וה-${l('bucket policy')} מתירה ${c('s3:GetObject')}
  <strong>אך ורק</strong> ל-${l('service principal')} של ${l('CloudFront')}, ורק כאשר
  הבקשה מגיעה מה-${l('distribution')} הספציפי שלנו (תנאי ${c('AWS:SourceArn')}).
  התוצאה: אי אפשר "לעקוף" את ה-${l('CDN')} ולפנות לקבצים ישירות. ${l('OAC')} הוא היורש
  המודרני של ${l('OAI')} הישן, ותומך גם בהצפנת ${l('SSE-KMS')}.</p>
  <table>
    <tbody>
      <tr><th>Bucket</th><td>${c('bball-dashboard-402631154156')}</td></tr>
      <tr><th>Block Public Access</th><td>ארבעת הדגלים ${c('true')} — אטום הרמטית</td></tr>
      <tr><th>גישה</th><td>${c('s3:GetObject')} רק ל-${l('CloudFront service principal')} + תנאי ${c('AWS:SourceArn')}</td></tr>
      <tr><th>הצפנה</th><td>${l('SSE-S3')} ${l('at rest')}</td></tr>
      <tr><th>תוכן</th><td>${c('dashboard.html')}, ${c('data.json')}, ${c('insights.json')}, מדיה</td></tr>
    </tbody>
  </table>

  <h3>2.6 &nbsp; צינור ה-GenAI האוטונומי</h3>
  <p>זה החלק ה"חכם": פעם ביום, מודל שפה מייצר סיכום מילולי של העונה הנוכחית. הצינור בנוי
  משלושה חלקים.</p>
  <p><span class="term">1. תזמון — EventBridge.</span> ${l('EventBridge')} הוא אפיק
  האירועים של ${l('AWS')}. הגדרנו ${l('Rule')} בשם ${c('bball-genai-insights-daily')} עם
  ביטוי ${c('cron(0 6 * * ? *)')} — כלומר "כל יום ב-06:00 ${l('UTC')}". ה-${l('rule')}
  הזה הוא היחיד שמפעיל את הפונקציה; אין דרך אחרת להריץ אותה.</p>
  <p><span class="term">2. חישוב — Lambda.</span> ${l('Lambda')} מריצה קוד ללא שרת, ומשלמים
  רק על זמן הריצה בפועל. הפונקציה ${c('bball-genai-insights')} כתובה ב-${c('Python 3.12')},
  רצה על ארכיטקטורת ${c('arm64')} (${l('Graviton')} — מעבדי ${l('ARM')} של ${l('AWS')},
  זולים ומהירים יותר מ-${l('x86')} לעומס הזה), עם ${c('256 MB')} זיכרון. הכי חשוב:
  <strong>הפונקציה רצה ${l('ללא VPC')}</strong>. ${l('VPC')} (${l('Virtual Private Cloud')})
  הוא רשת פרטית; ${l('Lambda')} בתוך ${l('VPC')} שצריכה לגשת לאינטרנט מחייבת
  <span class="term">NAT Gateway</span> שעולה כ-${l('$32/חודש')} קבוע. מכיוון שהפונקציה
  מדברת רק עם שירותי ${l('AWS')} ציבוריים (${l('S3')}, ${l('Bedrock')}, ${l('CloudFront')}),
  אין שום סיבה להכניס אותה ל-${l('VPC')} — וכך נחסך ה-${l('NAT')} לגמרי.</p>
  <p><span class="term">3. המודל — Bedrock.</span> ${l('Bedrock')} הוא שירות ה-${l('GenAI')}
  המנוהל של ${l('AWS')} — גישה למודלים דרך ${l('API')} אחיד, בלי לארח ${l('GPU')}. אנחנו
  קוראים ל-${l('Converse API')} (ממשק שיחה אחיד לכל המודלים) דרך
  <span class="term">Inference Profile</span> ${c('eu.amazon.nova-lite-v1:0')} —
  ${l('Nova Lite')} הוא מודל קטן וזול של ${l('Amazon')}, וה-${l('inference profile')}
  מנתב את הבקשה בין כמה אזורי ${l('EU')} לזמינות טובה יותר. הפלט נכתב כ-${c('insights.json')}
  ל-${l('S3')}, ואז הפונקציה מריצה ${l('CloudFront Invalidation')} (מחיקת המטמון) כדי
  שהתוכן החדש יופיע מיד.</p>
  <p><span class="term">IAM — ארבע פעולות בדיוק.</span> תפקיד ה-${l('Lambda')} נושא
  מדיניות ${l('inline')} מינימלית של ארבע פעולות, כל אחת ממופה למשאב ספציפי. בנוסף מוצמדת
  המדיניות המנוהלת ${c('AWSLambdaBasicExecutionRole')} שמאפשרת רק כתיבת לוגים ל-${l('CloudWatch')}.
  ההרשאה ל-${l('Bedrock')} כוללת גם את ה-${l('foundation model')} עצמו, שבו האזור ב-${l('ARN')}
  הוא ${c('*')} — כי ${l('inference profile')} מנתב בין אזורי ${l('EU')}.</p>
  <table>
    <thead><tr><th>#</th><th>פעולה</th><th>על המשאב</th><th>למה</th></tr></thead>
    <tbody>
      <tr><td class="num">1</td><td>${c('s3:GetObject')}</td><td>${c('data.json')}</td><td>לקרוא את נתוני העונה</td></tr>
      <tr><td class="num">2</td><td>${c('s3:PutObject')}</td><td>${c('insights.json')}</td><td>לכתוב את הסיכום</td></tr>
      <tr><td class="num">3</td><td>${c('cloudfront:CreateInvalidation')}</td><td>${c('E155IZM1SR95HY')}</td><td>לרענן את המטמון</td></tr>
      <tr><td class="num">4</td><td>${c('bedrock:InvokeModel')}</td><td>${c('eu.amazon.nova-lite-v1:0')}</td><td>להריץ את המודל</td></tr>
    </tbody>
  </table>
  <p class="tcap">שים לב: אין ${c('s3:*')}, אין ${c('bedrock:*')}, ואין ${c('Resource: "*"')}
  על אף פעולה — פשרה מדויקת בין תפקוד לבין נזק אפשרי במקרה פריצה.</p>
</section>

<!-- ================= פרק 3 ================= -->
<section class="chapter">
  <h2>פרק 3 — זרימת המידע ואינטגרציית ה-AI (Data Flow &amp; Hybrid AI)</h2>

  <h3>3.1 &nbsp; מסלול בקשת משתמש, שלב-אחר-שלב</h3>
  <p>נתאר מה קורה מרגע שגולש מקליד ${c('plusminus.cloud')} ועד שהדף מצויר:</p>
  <ol>
    <li><span class="term">User → Route 53.</span> הדפדפן שואל "מה הכתובת של
      ${c('plusminus.cloud')}?". ${l('Route 53')} מחזיר, דרך רשומת ${l('Alias')}, את
      כתובת ה-${l('CloudFront distribution')}.</li>
    <li><span class="term">User → CloudFront POP.</span> הדפדפן פותח חיבור ${l('HTTPS')}
      ל-${l('POP')} הקרוב. כאן נאכפים שני דברים בו-זמנית: התאמת ${l('TLS')}
      (${c('TLSv1.2_2021')}), ובדיקת ${l('Geo')} (אם לא ישראל → ${c('403')} וזהו).</li>
    <li><span class="term">Cache HIT או MISS?</span> אם ל-${l('POP')} כבר יש עותק תקף
      של הקובץ המבוקש — הוא מגיש אותו מיד, וזהו (הבקשה לא ממשיכה הלאה). אם אין
      (${l('MISS')}) — ממשיכים לשלב הבא.</li>
    <li><span class="term">CloudFront → OAC → S3.</span> ${l('CloudFront')} חותם בקשה
      פנימית ל-${l('S3')} (${l('SigV4')} דרך ${l('OAC')}), מקבל את הקובץ, שומר עותק
      במטמון להבא, ומחזיר לגולש.</li>
    <li><span class="term">הדפדפן מצייר.</span> ${c('dashboard.html')} נטען, ואז הוא
      עצמו מבצע ${c('fetch(\'./data.json\')')} ו-${c('fetch(\'./insights.json\')')} מאותו
      ${l('origin')} — עוד שתי בקשות שעוברות את אותו מסלול. אין ${l('API')} דינמי, אין
      ${l('backend')} שמריץ קוד בזמן הבקשה.</li>
  </ol>
  <div class="flow" dir="rtl">
    <span class="ltr" dir="ltr">User</span> → <span class="ltr" dir="ltr">Route 53 (Alias)</span>
    → <span class="ltr" dir="ltr">CloudFront POP</span>
    (<span class="ltr" dir="ltr">TLS · Geo=IL</span>)
    → <span class="ltr" dir="ltr">Cache HIT</span>? → מוגש מהקצה &nbsp;|&nbsp;
    <span class="ltr" dir="ltr">MISS</span> → <span class="ltr" dir="ltr">OAC</span>
    → <span class="ltr" dir="ltr">S3 origin</span>
    → <span class="ltr" dir="ltr">html + data.json + insights.json</span>
  </div>

  <h3>3.2 &nbsp; דפוס Asynchronous Batch AI Caching — למה לא AI בזמן אמת</h3>
  <p>ההחלטה המרכזית באינטגרציית ה-${l('AI')}: הסיכום של המודל מחושב
  <strong>מראש, פעם ביום, ב-${l('batch')}</strong> ונשמר כקובץ ${c('insights.json')}
  סטטי — ולא נקרא "חי" מהמודל בכל פעם שגולש נכנס. זהו דפוס
  <span class="term">Asynchronous Batch AI Caching</span>: מזיזים את החישוב היקר
  מ-<span class="term">request-time</span> (זמן הבקשה) ל-<span class="term">build-time</span>
  (זמן ההכנה).</p>
  <p>למה זה עדיף כל כך? כי זה <strong>מנתק את העלות ואת זמן ההמתנה מנפח התעבורה</strong>.
  לא משנה אם נכנס גולש אחד או מיליון — המודל רץ אותו מספר פעמים (כ-30 בחודש), והגולש
  תמיד מקבל קובץ סטטי מוכן מהמטמון, בלי להמתין למודל ובלי לייצר קריאת ${l('AI')} בתשלום.</p>
  <table>
    <thead><tr><th>שיקול</th><th>Batch יומי (נבחר)</th><th>Real-time לכל בקשה (נפסל)</th></tr></thead>
    <tbody>
      <tr><td>המתנה לגולש (${l('latency')})</td><td>0 — קובץ סטטי מהקצה</td>
        <td class="num">+300–2000 ms לכל טעינה</td></tr>
      <tr><td>עלות</td><td>~30 קריאות מודל בחודש, סנטים בודדים</td>
        <td>גדלה ליניארית עם מספר הכניסות — ללא תקרה</td></tr>
      <tr><td>חשיפה למתקפה</td><td>אין נתיב חיצוני שמפעיל מודל</td>
        <td>${l('DoS')} / ${l('cost runaway')} — כל ${l('refresh')} = הוצאה</td></tr>
      <tr><td>עמידות בתקלה</td><td>נפילת ${l('Bedrock')} לא משפיעה על הגשת הדף</td>
        <td>נפילת מודל = דף שבור לכל הגולשים</td></tr>
      <tr><td>יכולת מטמון</td><td>${l('cacheable')} מלא ב-${l('CloudFront')}</td>
        <td>תשובה ${l('per-user')} — לא ניתנת למטמון</td></tr>
    </tbody>
  </table>
  <div class="callout"><span class="lbl">העיקרון במשפט</span>
  כשהפלט לא חייב להשתנות בין גולש לגולש ולא חייב להיות עדכני לשנייה — חשב אותו פעם אחת,
  שמור, והגש מהמטמון. זה הופך עלות משתנה ומסוכנת לעלות קבועה וזניחה.</div>

  <h3>3.3 &nbsp; מודל ה-Hybrid: מתי AI ומתי חילוץ מקומי</h3>
  <p>הסוכן שמרכיב את התצוגה נוקט גישה מעורבת:</p>
  <ul>
    <li><span class="term">העונה האחרונה (ברירת המחדל, כרגע ${l('2025-2026')}):</span> מוצג הסיכום
      הנרטיבי שנוצר על ידי ${l('Bedrock')} ונשמר ב-${c('insights.json')} — טקסט "אנושי" שמסביר
      את המגמות. ה-${l('Lambda')} קוראת את העונה מהשדה ${c('default_season')} ב-${c('data.json')},
      כך שהאתר והסיכום תמיד מסונכרנים על אותה עונה. לפני שליחה למודל היא ממירה מזהי קבוצות
      לשמות בעברית, כדי שהסיכום לא יכלול קודים באנגלית.</li>
    <li><span class="term">עונות היסטוריות:</span> <strong>אין קריאת מודל בכלל</strong>.
      הסוכן מבצע חילוץ תבניתי דטרמיניסטי ישירות מ-${c('data.json')} (מי מוביל ב-${l('PIR')},
      מי הכי יעיל, מגמות עונתיות) ומרכיב את התצוגה בקוד רגיל.</li>
  </ul>
  <p>הרציונל: ${l('GenAI')} עולה כסף ומוסיף אי-ודאות, אז משתמשים בו רק היכן שהערך שלו
  ברור (ניסוח חופשי של העונה החיה), ובכל שאר המקומות נשארים עם לוגיקה צפויה, מהירה
  וללא עלות.</p>
  <p><span class="term">עוזר האנליטיקה בדשבורד.</span> ה-${l('chat widget')} בדשבורד הוא
  <strong>מבוסס כללים</strong>: תבניות קבועות בקוד שמחשבות תשובות ישירות מ-${c('data.json')}
  (מוביל בקליעה, דירוג שחקן וכו'). רק שאלות על מגמות מצטטות את סיכום ה-${l('Bedrock')} היומי.
  לכן הוא מסומן "עוזר אנליטיקה" ולא "${l('AI')}" — ה-${l('AI')} האמיתי במערכת הוא הסיכום
  היומי, ולא כל תשובה בצ'אט.</p>
</section>

<!-- ================= פרק 4 ================= -->
<section class="chapter">
  <h2>פרק 4 — ניתוח FinOps והחלטות הנדסיות (Trade-offs)</h2>
  <p class="lead">ה-${l('FinOps')} כאן הוא תוצאה של החלטות ארכיטקטורה, לא של "קימוץ"
  בדיעבד. כל בחירה בפרקים הקודמים (סטטי במקום דינמי, ${l('batch')} במקום ${l('real-time')},
  ללא ${l('VPC')}, ${l('Geo')} לישראל) מתורגמת ישירות לשורה בטבלה הזו.</p>

  <h3>4.1 &nbsp; טבלת עלות חודשית בפועל</h3>
  <table>
    <thead><tr><th>שירות</th><th>שימוש חודשי</th><th>עלות</th></tr></thead>
    <tbody>
      <tr><td>${l('Route 53 Hosted Zone')}</td><td class="num">1 zone</td><td class="num">≈ $1.00 (Cost Explorer, ספט' 2026)</td></tr>
      <tr><td>${l('S3')}</td><td class="num">&lt; 50 MB, אלפי GET</td><td class="num">≈ $0.00 (Free Tier)</td></tr>
      <tr><td>${l('CloudFront')}</td><td class="num">&lt; 1 GB, IL בלבד</td><td class="num">≈ $0.00 (1 TB Free Tier)</td></tr>
      <tr><td>${l('Lambda')}</td><td class="num">~30 הרצות, 256 MB, שניות</td><td class="num">≈ $0.00 (Free Tier)</td></tr>
      <tr><td>${l('EventBridge')}</td><td class="num">~30 אירועים</td><td class="num">$0.00</td></tr>
      <tr><td>${l('Bedrock')} (${l('Nova Lite')})</td><td class="num">~30 קריאות קצרות</td><td class="num">&lt; $0.01</td></tr>
      <tr><td>${l('CloudWatch Logs')}</td><td class="num">&lt; 100 MB, retention 14 יום</td><td class="num">≈ $0.00 (5 GB Free Tier)</td></tr>
      <tr><td>${l('ACM')}</td><td class="num">תעודה ציבורית</td><td class="num">$0.00</td></tr>
      <tr><th>סה"כ</th><th></th><th class="num" style="text-align:left">≈ $1 / חודש</th></tr>
    </tbody>
  </table>
  <p class="tcap">כל שורה מלבד ה-${l('Hosted Zone')} מתכנסת ל-${l('Free Tier')} או לשברירי
  סנט — לא בגלל מזל, אלא בגלל שהעומס עצמו זעיר (עדכון יומי, קהל מקומי, קבצים קטנים).</p>

  <h3>4.2 &nbsp; חלופות שנפסלו — והנימוק ההנדסי</h3>

  <h4>${l('EC2')} + ${l('ALB')} — כ-${l('$18+')} לחודש</h4>
  <p>הגישה הקלאסית: מכונה וירטואלית (${l('EC2')}) שמריצה ${l('web server')}, מאחורי
  ${l('Application Load Balancer')} לפיזור עומס ו-${l('TLS')}. נפסל כי ${l('ALB')} לבדו
  עולה כ-${l('$16/חודש')} <strong>קבוע</strong>, ועוד ${l('EC2')} מעל. בשביל להגיש קבצים
  סטטיים שלא משתנים — זו הוצאה מיותרת, ומעליה נטל תחזוקה: ${l('OS patching')},
  ${l('scaling groups')}, פריסה על כמה ${l('Availability Zones')}. ${l('S3')} +
  ${l('CloudFront')} עושים את אותה עבודה טוב יותר, בפחות, וללא תחזוקה.</p>

  <h4>${l('VPC')} + ${l('NAT Gateway')} — כ-${l('$32+')} לחודש</h4>
  <p>אם היינו מכניסים את ה-${l('Lambda')} לרשת פרטית (${l('VPC')}) וזו הייתה צריכה גישה
  לאינטרנט, חובה ${l('NAT Gateway')} — כ-${l('$0.045')} לשעה (${l('~$32/חודש')})
  <strong>גם באפס שימוש</strong>, ועוד תשלום per-GB על תעבורה. נמנענו מזה לחלוטין:
  ה-${l('Lambda')} רצה ${l('ללא VPC')}, ומגיעה ל-${l('S3')} / ${l('Bedrock')} /
  ${l('CloudFront')} דרך ה-${l('public endpoints')} שלהם, כשההרשאה נאכפת ב-${l('IAM')}.
  אין נכס רגיש ברשת פרטית שמצדיק ${l('VPC')} מלכתחילה.</p>

  <h4>${l('RDS')} מנוהל (${l('PostgreSQL')}) — כ-${l('$15+')} לחודש</h4>
  <p>מסד נתונים יחסי מנוהל. אפילו המכונה הקטנה (${c('db.t4g.micro')}) חיה 24/7 ומצטרפת
  אליה עלות אחסון וגיבוי. אבל הנתונים שלנו <strong>נקראים בלבד ומתעדכנים פעם ביום</strong>
  — קובץ ${c('data.json')} סטטי ב-${l('S3')} ממלא את אותו תפקיד בעלות אפס ובלי שרת
  להריץ. ${l('PostgreSQL')} עדיין קיים בפרויקט, אבל רק ככלי ${l('ETL')} מקומי / משימת
  ${l('Fargate')} חד-פעמית שרצה כשמייבאים עונה חדשה, ולא כרכיב חי בסביבת הייצור.</p>

  <div class="callout ok"><span class="lbl">כלל האצבע</span>
  אם משאב חייב לרוץ 24/7 כדי לשרת עומס שהוא ${l('bursty')} (מתפרץ) או אפסי — הוא הבחירה
  הלא נכונה. ${l('Serverless')} + נכסים סטטיים ממירים <strong>"עלות זמן"</strong> (משלמים
  על קיום) ל-<strong>"עלות שימוש"</strong> (משלמים על עבודה שבוצעה).</div>
</section>

<!-- ================= פרק 5 ================= -->
<section class="chapter">
  <h2>פרק 5 — כרטיסיות שליפה לראיון (Exam / Interview Flashcards)</h2>
  <p class="lead">ארבע שאלות שמראיין בכיר עשוי לירות, עם תשובה מלאה ומנוסחת. כל תשובה
  פותחת במשפט מפתח ואז מפרטת.</p>

  <div class="card">
    <div class="q">למה הרצת את ה-Lambda מחוץ ל-VPC?</div>
    <p class="a"><strong>משפט מפתח:</strong> כי אין שום נכס פרטי שצריך גישה אליו, וכניסה
    ל-${l('VPC')} הייתה מוסיפה רק עלות (${l('NAT')}) ו-${l('cold start')} בלי שום רווח
    אבטחתי.</p>
    <ul>
      <li>הפונקציה מדברת רק עם ${l('S3')}, ${l('CloudFront')} ו-${l('Bedrock')} — כולם
        ${l('public endpoints')} שההרשאה אליהם נאכפת ב-${l('IAM')}, לא ברשת.</li>
      <li>${l('Lambda')} ב-${l('VPC')} עם יציאה לאינטרנט מחייבת ${l('NAT Gateway')} —
        ${l('~$32/חודש')} קבוע + עלות תעבורה, גם באפס שימוש.</li>
      <li>אין ${l('RDS')} / ${l('ElastiCache')} / ${l('endpoint')} פרטי בתמונה — אין מה
        לבודד ברשת.</li>
      <li>מודל האבטחה כאן הוא <strong>identity-based</strong> (${l('IAM')}, 4 פעולות)
        ולא <strong>network-based</strong>.</li>
    </ul>
  </div>

  <div class="card">
    <div class="q">למה OAC ולא Bucket Policy ציבורי ל-S3?</div>
    <p class="a"><strong>משפט מפתח:</strong> ${l('OAC')} מאפשר להשאיר את ה-${l('bucket')}
    אטום לגמרי ולתת גישה רק ל-${l('CloudFront')} — ${l('bucket')} ציבורי היה יוצר נתיב
    שעוקף את כל שכבות ההגנה.</p>
    <ul>
      <li>עם ${l('OAC')}, ${l('Block Public Access')} נשאר מלא; ${l('CloudFront')} חותם
        כל בקשה (${l('SigV4')}) וה-${l('bucket policy')} מתירה גישה רק ל-${l('service principal')}
        שלו בתנאי ${c('AWS:SourceArn')} של ה-${l('distribution')}.</li>
      <li>${l('bucket')} ציבורי או ${l('S3 website endpoint')} חושף ${l('URL')} ישיר
        שעוקף ${l('Geo-Restriction')}, ${l('WAF')}, ${l('TLS')} מנוהל ולוגים — ופתוח
        לסריקות אינטרנט.</li>
      <li>${l('OAC')} הוא היורש של ${l('OAI')} ותומך גם בהצפנת ${l('SSE-KMS')}.</li>
    </ul>
  </div>

  <div class="card">
    <div class="q">איך אתה מנטר את המערכת, ומה חסר?</div>
    <p class="a"><strong>משפט מפתח:</strong> הניטור מינימלי בכוונה, כי אין תהליך חי שיכול ליפול —
    ואני יודע בדיוק מה הייתי מוסיף.</p>
    <ul>
      <li>ה-${l('Lambda')} כותבת ל-${l('CloudWatch Logs')} עם ${l('retention')} של 14 יום, וכל הרצה מדפיסה שורת סיכום.</li>
      <li>נפילת ${l('Bedrock')} לא שוברת את האתר: הסיכום הוא קובץ קיים מהריצה הקודמת.</li>
      <li>${l('CloudFront standard logging')} כן מופעל — כל בקשה לאתר נכתבת ל-${l('S3')}.</li>
      <li>${l('AWS Budgets')} קיימים, אבל ברמת כל חשבון ה-${l('AWS')} שלי (רשת ביטחון אישית), לא
        כרכיב ייעודי של הפרויקט — ולכן אין ${l('alarm')} ממוקד דווקא על עלות ${l('Bedrock')} או על כשל
        ב-${l('Lambda')} הזו ספציפית. זה הייתי מוסיף אם הפרויקט היה גדל.</li>
    </ul>
  </div>

  <div class="card">
    <div class="q">איך מנעת מה-AI לייצר הוצאות בלתי נשלטות (Cost Runaway)?</div>
    <p class="a"><strong>משפט מפתח:</strong> אין שום נתיב שבו בקשת גולש מפעילה מודל.
    המודל רץ רק מטיימר, במספר קריאות קבוע, על מודל זול, עם הרשאה שלא ניתנת להרחבה.</p>
    <ul>
      <li><strong>${l('Batch')} ולא ${l('real-time')}:</strong> ${c('cron(0 6 * * ? *)')}
        — כ-30 קריאות בחודש, תדירות מנותקת לחלוטין מהתעבורה.</li>
      <li><strong>אין ${l('trigger')} חיצוני:</strong> הגולש מקבל ${c('insights.json')}
        סטטי מהמטמון; ${l('Bedrock')} לא נמצא במסלול הבקשה.</li>
      <li><strong>${l('IAM')} חוסם התרחבות:</strong> ההרשאה היחידה היא
        ${c('bedrock:InvokeModel')} על ${c('eu.amazon.nova-lite-v1:0')} — אי אפשר
        "לשדרג" למודל יקר.</li>
      <li><strong>קלט חסום:</strong> ${l('Nova Lite')} (מודל קטן) + ${l('prompt')} בגודל
        ${c('data.json')} של עונה אחת, לא יותר.</li>
      <li><strong>רשת ביטחון:</strong> ${l('AWS Budgets')} / ${l('CloudWatch alarm')}
        על עלות ${l('Bedrock')}.</li>
    </ul>
  </div>
</section>

</body></html>`;

if (require.main !== module) { module.exports = { HTML }; return; }

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setContent(HTML, { waitUntil: 'load' });
  try { await page.evaluate(() => document.fonts.ready); } catch (e) {}
  await page.waitForTimeout(150);

  await page.pdf({
    path: OUT,
    format: 'A4',
    printBackground: true,
    margin: { top: '18mm', bottom: '18mm', left: '16mm', right: '16mm' },
    displayHeaderFooter: true,
    headerTemplate: '<span></span>',
    footerTemplate:
      '<div style="width:100%;font-size:8px;color:#888;text-align:center;' +
      'font-family:Segoe UI,Tahoma,Arial,sans-serif;">' +
      'PlusMinus IL · AWS System Architecture &nbsp;·&nbsp; ' +
      '<span class="pageNumber"></span> / <span class="totalPages"></span></div>',
  });

  await browser.close();
  const kb = (fs.statSync(OUT).size / 1024).toFixed(1);
  console.log('wrote ' + OUT + ' (' + kb + ' KB)');
})().catch((e) => { console.error(e); process.exit(1); });
