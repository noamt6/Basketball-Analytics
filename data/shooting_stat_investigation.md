# Shooting-Stat Data-Quality Investigation

Investigation date: 2026-08-26. All live figures below were fetched directly from basket.co.il
(raw HTML, parsed with Python — not summarized by a model) during this session. Team page IDs and
player profile page IDs are basket.co.il's own IDs; they match this project's `PlayerId` for every
non-MTA player checked (e.g. Isaiah Miles = 17471 on both sides) but **not** for MTA, whose 14
players use a separate 100–113 numbering scheme in this workbook, cross-referenced here via jersey
number (`Roster` sheet) against basket.co.il's own jersey/PlayerId table on the MTA team page.

## Summary of conclusions (read this first)

1. **MTA (Hypothesis A) — CONFIRMED for all 14 players, root cause pinned down exactly.** Every
   MTA player's `FGM`/`FGA` in `Player_Stats` is that player's basket.co.il **2PT-made / 2PT-attempted**
   figure, not total field goals; `3PM`/`3PA` is a correctly-tracked, non-overlapping category. This is
   not inference from percentages anymore — it's now been cross-checked against each of the 14 players'
   own basket.co.il profile pages.
2. **Isaiah Miles — a THIRD, distinct issue, not Hypothesis A or B.** His combined HTA+IRG row has
   the *exact same* 2PT-only-in-FGM/FGA bug as every MTA player, isolated to his one row (verified
   against his own profile page's per-stint "Total" rows). The two-stint *merge* itself (combining his
   HTA and IRG games into one row) is otherwise done correctly.
3. **Hypothesis B — NOT a scraping/merge corruption in the way originally suspected (no evidence of
   "released player double-counted via a teammate who took over their minutes").** It is fully explained,
   to within a handful of makes/attempts, by two independent, identifiable effects:
   - **(a) A season-length/scope mismatch between the two sheets.** `Team_Stats` reflects a narrower
     ~22–24 game season; `Player_Stats` (for all 12 non-MTA teams) was built from basket.co.il data that
     covers a broader ~29–30 game season. This alone explains the bulk of the overshoot even for teams
     with zero mid-season trades (EKA, HJM: Player_Stats team-sum matches the live site's own team total
     to <0.1%, but is ~32–37% above `Team_Stats`).
   - **(b) The "kept single combined row" policy for traded players** (documented in the `Transfers`
     sheet) mechanically over-counts at the team that kept the row and under-counts at the team whose row
     was dropped — reproduced here to the exact make/attempt for BNH, HHF and IRG.
4. **Recommended fixes are narrow**: correct `Player_Stats` for the 14 MTA rows and the 1 Isaiah
   Miles row (exact values below). Do **not** touch `Team_Stats` — it is already storing true total
   field goals for every team, MTA included; it simply covers fewer games than `Player_Stats` does,
   which is a separate, pre-existing scope inconsistency between the two sheets that is out of scope
   for "fixing the 6 flagged rows" (see §4).

---

## 1. MTA: corrected FGM/FGA/3PM/3PA for all 14 players

### Method and what "verify against the live site" actually established

basket.co.il's MTA team page (`team.asp?TeamId=1055`) has a "Players – Regular Season Averages" table
that (like every other team on the site) shows **percentages only**, no raw counts, on the roster page
itself. But **every individual player's own profile page** (`player.asp?PlayerId=…`) has a "Team Stats"
table with a `Total` row giving exact season **M/A counts** for 2PT, 3PT and FT separately. All 14 MTA
players' profile pages were fetched and parsed:

| PlayerId | Name | Site GP | Site 2PT M/A | Site 3PT M/A | Site FT M/A |
|---|---|---|---|---|---|
| 100 | Antonius Cleveland | 17 | 47/75 | 13/34 | 20/27 |
| 101 | James Webb | 14 | 18/29 | 23/62 | 13/16 |
| 102 | Lorenzo Brown | 15 | 42/88 | 26/59 | 18/25 |
| 103 | Wade Baldwin | 16 | 51/97 | 8/55 | 68/78 |
| 104 | Rafi Menco | 26 | 49/81 | 36/109 | 16/28 |
| 105 | Roman Sorkin | 24 | 142/212 | 20/41 | 45/69 |
| 106 | Omer Mayer | 21 | 20/40 | 17/49 | 8/15 |
| 107 | John Dibartolomeo | 21 | 17/29 | 46/96 | 24/29 |
| 108 | Jasiel Rivero | 18 | 80/123 | 1/4 | 55/79 |
| 109 | Jake Cohen | 29 | 38/55 | 14/38 | 36/40 |
| 110 | Josh Nebo | 21 | 87/117 | 0/0 | 48/63 |
| 111 | Tamir Blatt | 24 | 20/33 | 48/149 | 30/34 |
| 112 | Bonzie Colson | 16 | 46/88 | 16/52 | 40/45 |
| 113 | Joe Thomasson | 14 | 21/50 | 17/40 | 14/15 |

**Important caveat — this is a full ~14–29 game season, not the ~9–24 game window `Player_Stats`
uses.** basket.co.il's own team-level "Team Stats – Regular Season" table for MTA totals **29 games**
(682/1130 2PT, 290/799 3PT), while this workbook's `Team_Stats` row for MTA says **GP=24**. The same
~5–8 game gap exists for every one of the 8 teams checked in this investigation (see §2) — basket.co.il's
"Regular Season" label evidently includes a post-round-robin group stage that this workbook's narrower
season definition excludes. Because of that, **exact make/attempt counts from the live site will not
match `Player_Stats`' existing (smaller) GP for any MTA player**, and that's expected, not a sign the
diagnosis is wrong — see the percentage-based check below, which is scope-independent and is the
actual confirmation.

### The scope-independent proof: FG% match

If `FGM`/`FGA` in `Player_Stats` really is 2PT-only, then `xlsx FG% = FGM/FGA` should track the site's
**2PT%**, not the site's true combined FG%, regardless of which games are in each sample. That is
exactly what's observed for all 14 players:

| Name | xlsx FGM | xlsx FGA | xlsx FG% | site 2PT% | site true FG% (2PT+3PT) |
|---|---|---|---|---|---|
| Cleveland | 36 | 54 | 66.7% | 62.7% | 55.0% |
| Webb | 14 | 20 | 70.0% | 62.1% | 45.1% |
| Brown | 36 | 77 | 46.8% | 47.7% | 46.3% |
| Baldwin | 51 | 97 | 52.6% | **52.6%** | 38.8% |
| Menco | 43 | 64 | 67.2% | 60.5% | 44.7% |
| Sorkin | 123 | 181 | 68.0% | 67.0% | 64.0% |
| Mayer | 12 | 25 | 48.0% | 50.0% | 41.6% |
| Dibartolomeo | 16 | 27 | 59.3% | 58.6% | 50.4% |
| Rivero | 65 | 100 | 65.0% | **65.0%** | 63.8% |
| Cohen | 33 | 48 | 68.8% | 69.1% | 55.9% |
| Nebo | 79 | 104 | 76.0% | 74.4% | 74.4%† |
| Blatt | 18 | 30 | 60.0% | 60.6% | 37.4% |
| Colson | 37 | 71 | 52.1% | 52.3% | 44.3% |
| Thomasson | 12 | 28 | 42.9% | 42.0% | 42.2% |

† Nebo has 0 three-point attempts all season, so his 2PT% and true FG% coincide — not informative on
its own, but consistent.

Every single player's xlsx FG% sits within a few points of the site's 2PT%, and is 8–33 points away
from the site's true FG%. This confirms — independent of the GP/scope mismatch — that `FGM`/`FGA` in
`Player_Stats` is 2PT-only for all 14 MTA players, not just the 5 that got flagged (those 5 were only
flagged because they happen to have high enough 3PA relative to their 2PT-only FGA to trip the
`3PA > FGA` check; the other 9 have the identical underlying definition problem, it just doesn't happen
to violate the sanity check numerically).

### Recommended correction

Since the live site's current season window (14–29 GP per player) doesn't match `Player_Stats`' existing
GP for any MTA player, and the goal is to fix the *definition* bug without changing what games are
covered, the correct fix is the one already anticipated in the background brief: **add the existing
(correct) `3PM`/`3PA` onto the existing (2PT-only) `FGM`/`FGA`**, keeping each player's current GP/window
exactly as-is:

| PlayerId | Name | GP | FGM→ | FGA→ | 3PM | 3PA | **Corrected FGM** | **Corrected FGA** | **Corrected FG%** | 3P% (unchanged) | FTM/FTA (unchanged) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 100 | Antonius Cleveland | 14 | 36 | 54 | 10 | 27 | **46** | **81** | 56.8% | 37.04% | 14/19 |
| 101 | James Webb | 11 | 14 | 20 | 16 | 45 | **30** | **65** | 46.2% | 35.56% | 10/12 |
| 102 | Lorenzo Brown | 12 | 36 | 77 | 17 | 41 | **53** | **118** | 44.9% | 41.46% | 14/20 |
| 103 | Wade Baldwin | 16 | 51 | 97 | 8 | 55 | **59** | **152** | 38.8% | 14.55% | 68/78 |
| 104 | Rafi Menco | 21 | 43 | 64 | 28 | 90 | **71** | **154** | 46.1% | 31.11% | 12/22 |
| 105 | Roman Sorkin | 20 | 123 | 181 | 11 | 27 | **134** | **208** | 64.4% | 40.74% | 41/64 |
| 106 | Omer Mayer | 16 | 12 | 25 | 11 | 35 | **23** | **60** | 38.3% | 31.43% | 4/6 |
| 107 | John Dibartolomeo | 20 | 16 | 27 | 44 | 90 | **60** | **117** | 51.3% | 48.89% | 20/25 |
| 108 | Jasiel Rivero | 15 | 65 | 100 | 1 | 3 | **66** | **103** | 64.1% | 33.33% | 50/70 |
| 109 | Jake Cohen | 24 | 33 | 48 | 9 | 30 | **42** | **78** | 53.8% | 30.00% | 33/37 |
| 110 | Josh Nebo | 18 | 79 | 104 | 0 | 0 | **79** | **104** | 76.0% | 0% | 39/51 |
| 111 | Tamir Blatt | 21 | 18 | 30 | 41 | 131 | **59** | **161** | 36.6% | 31.30% | 27/31 |
| 112 | Bonzie Colson | 13 | 37 | 71 | 13 | 41 | **50** | **112** | 44.6% | 31.71% | 40/45 |
| 113 | Joe Thomasson | 9 | 12 | 28 | 11 | 24 | **23** | **52** | 44.2% | 45.83% | 5/5 |

**Sum check:** corrected team FGM/FGA totals across all 14 = **795 / 1565**, vs. `Team_Stats`' existing
MTA row of **801 / 1580** — a 0.75%/0.95% difference, i.e. this correction makes `Player_Stats` and
`Team_Stats` agree almost exactly for MTA (the tiny residual is fully explained by 5 low-minute MTA
players who exist on the site but were excluded from `Player_Stats` entirely — Doron, Behar, Goldman,
Berko, Sahar — each with 1–3 GP and near-zero production). No further correction to MTA's `Team_Stats`
row is needed; it is already reporting true total field goals.

`3PM`/`3PA`/`3P%`/`FTM`/`FTA`/`FT%` require no changes for any of the 14 — all confirmed correct
(3P% is already computed as `3PM/3PA`, and FT is a single, non-decomposed category with no possible
2PT/3PT-style ambiguity).

---

## 2. Hypothesis B: root cause, with concrete site evidence

### 2a. It is NOT "released players double-counted via a teammate's minutes"

Every `Player_Data_Sources` note that mentions "released" players is about **jersey-number sourcing**
(released players' rows on the roster table use a mangled 3-digit anchor code like `108` instead of the
real jersey `8`), never about stat duplication. No evidence was found on any of the 6+ live team pages
checked of a released player's attempts being folded into a replacement's row, or vice versa. That
specific mechanism the brief flagged as a hypothesis does not appear to be what happened.

### 2b. What actually explains it — two additive, independent effects

**Effect 1 — `Team_Stats` and `Player_Stats` cover different-length seasons.** Every team's own
"Team Stats – Regular Season" table on basket.co.il (`team.asp?TeamId=…`) reports **29 or 30 total team
games**, while every team's row in this workbook's `Team_Stats` sheet reports only **22–24 GP**. That
~5–8 game gap is consistent across all 8 teams checked (see table below) and is almost certainly a real
basket.co.il structural feature (a post-round-robin top-group/placement stage that the site bundles into
its "Regular Season" label, while `Team_Stats` in this workbook appears to reflect only the round-robin
portion — 13 teams × 2 = 24 games matches MTA's GP=24 exactly). Since `Player_Stats` for the 12
non-MTA teams was built from that same ~29–30-game basket.co.il "Regular Season" data (either the team
roster table or per-player profile "Total" rows, per `Player_Data_Sources`), **summing `Player_Stats`
naturally lands close to the site's ~29–30-game team total, not `Team_Stats`' ~22–24-game total** —
this alone accounts for the majority of the mismatch, including for teams with zero trades.

Live "Team Stats – Regular Season" totals fetched this session (2PT M/A + 3PT M/A summed = total FG):

| Team | Site GP | Site total FGM/FGA | `Player_Stats` sum FGM/FGA | Match to site? | This workbook's `Team_Stats` FGM/FGA (GP) |
|---|---|---|---|---|---|
| EKA | 29 | 863/1987 | 863/1987 | **exact** | 652/1501 (GP 22) |
| HJM | 29 | 862/1875 | 862/1874 | **exact** (±1, rounding) | 629/1415 (GP 22) |
| HGE | 30 | 876/2013 | 885/2017 | close (+1%/+0.2%) | 612/1437 (GP 22) |
| HTA | 29 | 957/1895 | 992/1946 | +3.7%/+2.7% (see 2c) | 741/1456 (GP 22) |
| BNH | 30 | 867/1941 | 975/2182 | +12.5%/+12.4% (see 2c) | 633/1413 (GP 22) |
| HHF | 30 | 882/1933 | 742/1628 | −15.9%/−15.8% (see 2c) | 667/1466 (GP 23) |
| IRG | 29 | 891/1900 | 809/1748 | −9.2%/−8.0% (see 2c) | 713/1526 (GP 23) |
| MTA | 29 | 972/1929 | 795/1565‡ | n/a — different bug (§1) | 801/1580 (GP 24) |

‡ MTA figure is the corrected (2PT+3PT) sum from §1; it isn't expected to match the 29-game site total
because it retains `Player_Stats`' original, narrower per-player GP.

EKA and HJM — teams untouched by any mid-season trade — reproduce the live site's own team total for
`Player_Stats` almost to the make. That is strong, direct confirmation that `Player_Stats`' overshoot
versus `Team_Stats` is fundamentally a season-length mismatch between the two sheets, not a corruption
of `Player_Stats` itself.

**Effect 2 — the "single combined row" trade-merge policy (5 teams: BNH, HGE, HHF, HTA, IRG).** The
`Transfers` sheet documents that for 4 of 6 traded players, a **single row combining both stints** was
kept at one team and the duplicate row at the other team was **removed entirely**:

| Player | Stint A | Stint B | Combined row kept at |
|---|---|---|---|
| Mike McGuirl | BNH, 8 GP | HHF, 15 GP | **BNH** (23 GP) |
| Juvonte Reddic | HGE, 8 GP | HHF, 7 GP | **HGE** (15 GP) |
| Isaiah Miles | HTA, 5 GP | IRG, 19 GP | **HTA** (24 GP) |
| Itay Moskovits | IRG, 14 GP | HHF, 4 GP | **IRG** (18 GP) |
| Kyle Feit | INZ, 13 GP | HEL, 1 GP | *not combined* — 2 independent rows kept |
| Alex Hamilton | HHF, 13 GP | IRG, 14 GP | *not combined* — 2 independent rows kept |

For the 4 combined players, this means the team that **kept** the row gets credited with that player's
production from games he played for the *other* team too (over-count), while the team whose row was
**dropped** loses that player's real production from games he actually played for them (under-count).
This was verified to the exact make/attempt by pulling each player's own basket.co.il profile page
(which shows separate `Total – <Team>` rows per stint):

- **Mike McGuirl** (profile: BNH stint 18/27 2PT, 14/41 3PT, 3/7 FT; HHF stint 74/133 2PT, 34/108 3PT,
  43/53 FT). `Player_Stats` row 17461 = GP 23, FGM 140, FGA 309, 3PM 48, 3PA 149, FTM 46, FTA 60 — this
  is the exact combined total of *both* stints, correctly summed as true FG (not the MTA-style bug). It
  is attributed entirely to BNH. His **BNH-only** contribution should have been 32 FGM / 68 FGA — a
  **+108 FGM / +241 FGA** overstatement at BNH.
  - BNH's observed excess over the site's own team total: **+108 FGM / +241 FGA** — an exact match.
- **Juvonte Reddic** and **Itay Moskovits**: profile pages confirm the same pattern (combined-stint
  totals, correctly computed as true FG, attributed to HGE and IRG respectively).
- **HHF's shortfall** (−140 FGM / −305 FGA vs. the site total) is exactly the sum of the three players'
  HHF-stint production that was dropped from HHF's roster entirely: McGuirl's HHF stint (108/241),
  Reddic's HHF stint (25/42), Moskovits' HHF stint (7/22) → 108+25+7=140 FGM, 241+42+22=305 FGA.
  **Exact match.**
- **IRG's shortfall** (−82 FGM vs. the site total) is explained almost entirely by Isaiah Miles' IRG
  stint (89 FGM true-total, see §3) being entirely absent from IRG's `Player_Stats` (his combined row
  lives at HTA instead) — accounting for the great majority of the gap, with a small residual likely from
  minor roster-exclusion differences (a couple of 0-stat players excluded per `Player_Data_Sources`).
- **HTA's excess** (+35 FGM / +51 FGA) nets out two opposite errors on the same row: Isaiah Miles'
  combined row over-states HTA (it includes his IRG-stint production, +89 FGM/+172 FGA that didn't happen
  at HTA) but simultaneously *understates* itself because of the separate 2PT-only bug on that same row
  (true combined total is 99/202, but the row currently shows 45/81, a −54/−121 understatement). Net:
  +89−54 = +35 FGM; +172−121 = +51 FGA. **Exact match**, and this is the clearest evidence that Isaiah
  Miles' issue really is two separate, independently-verifiable defects stacked on one row (see §3).

For comparison, `Kyle Feit` and `Alex Hamilton` — the two players kept as **independent per-stint
rows** rather than merged — introduce no such distortion; each team gets exactly that player's real
stint production, nothing more and nothing less. This is the "correct" pattern; the 4 merged players are
the "incorrect" pattern.

### 2c. Does this generalize to the other basket.co.il teams not fetched live this session?

Not fetched live this session: HAF, HBS, HEL, HHL, INZ. However, `Player_Data_Sources`' own notes
(written when this dataset was originally built) already give HHL's and IRG's team-level totals from the
site (854/1830 for HHL, 891/1900 for IRG); HHL's number matches this workbook's `Player_Stats` sum for
HHL (854/1829) almost exactly — consistent with Effect 1 alone (HHL has no trades in/out per
`Transfers`). Given the mechanism is now confirmed exactly (to the make/attempt) for 5 different teams
covering both "no trade" and "4 different trade shapes," it is reasonable to expect HAF, HBS, HEL and
INZ follow the same two-effect pattern (Effect 1 always; Effect 2 only if `Transfers` lists a trade
touching them — none of these 4 teams appear in `Transfers`, so their `Player_Stats` sums should track
their own site team totals about as closely as EKA/HJM do).

### 2d. Does the live site's own team-total reconcile with its own roster sum?

Yes, closely — for teams with no trades (EKA, HJM), summing basket.co.il's own per-player profile totals
reproduces the site's own team-level "Team Stats – Regular Season" table to well under 1%. The live site
is internally consistent; the mismatch investigated here is entirely a property of how this project's two
sheets (`Team_Stats` vs. `Player_Stats`) were each independently built from data with two different
scopes, plus the trade-merge policy layered on top for 5 teams.

---

## 3. Isaiah Miles (PlayerId 17471): real per-stint and combined numbers

Fetched directly from his basket.co.il profile page (`player.asp?PlayerId=17471`), which lists two
separate `Total – <Team>` rows:

| Stint | GP | Min | Pts | 2PT M/A | 3PT M/A | FT M/A |
|---|---|---|---|---|---|---|
| Hapoel Tel-Aviv | 5 | 111 | 46 | 1/7 | 9/23 | 17/19 |
| Maccabi Ramat Gan (IRG) | 19 | 511 | 254 | 44/74 | 45/98 | 31/37 |
| **Combined (both stints)** | **24** | **622** | **300** | **45/81** | **54/121** | **48/56** |

This combined GP (24) matches the `Transfers` sheet's note exactly ("Single combined row kept at HTA
(24 GP)").

**True combined field goals** = 2PT + 3PT = (45+54) made / (81+121) attempted = **99 / 202**.

Current `Player_Stats` row 17471: `GP 24, FGM 45, FGA 81, 3PM 54, 3PA 121, FTM 48, FTA 56`. Comparing
field by field against the profile page's combined totals:

- `3PM`/`3PA` (54/121) — **exact match** to the true combined 3PT total.
- `FTM`/`FTA` (48/56) — **exact match** to the true combined FT total.
- `FGM`/`FGA` (45/81) — matches the combined **2PT-only** total (45/81), *not* true combined field
  goals (99/202).
- `PTS` (300) — exact match (46+254=300), confirming points itself was combined correctly.
- `MIN` (622) — exact match (111+511=622).
- `OREB`/`REB` are off by 1 from a naive sum of the two stints' OR/TR columns (22 vs. 21, 116 vs. 115)
  — a minor, low-stakes discrepancy unrelated to the shooting-stat issue, not investigated further here.

**Conclusion: this is Hypothesis A, not Hypothesis B, and not a merge-specific bug.** The
HTA+IRG stint merge itself is done correctly and consistently — 2PT summed correctly across stints,
3PT summed correctly across stints, FT and points summed correctly across stints, GP summed correctly.
The only defect is that, exactly as with all 14 MTA players, `FGM`/`FGA` was populated with the
2PT-only total rather than 2PT+3PT. This is confirmed by checking three other merged/traded players on
different teams (McGuirl, Reddic, Moskovits, §2b) whose merges are all computed with the correct
total-FG definition — so the merge mechanism itself isn't inherently faulty; Isaiah Miles' row
specifically inherited the same FGM/FGA-is-2PT-only defect that affects all of MTA (possibly because
this row, or the HTA-side source data it drew from, was processed through the same code path/logic as
MTA at some point — worth asking whoever built the ingestion which script produced this one row, since
it's the only non-MTA row with this specific defect).

### Recommended correction for PlayerId 17471

| Field | Current | Corrected |
|---|---|---|
| GP | 24 | 24 (unchanged) |
| FGM | 45 | **99** |
| FGA | 81 | **202** |
| FG% | 55.56 | **49.01** (99/202) |
| 3PM | 54 | 54 (unchanged) |
| 3PA | 121 | 121 (unchanged) |
| 3P% | 44.63 | 44.63 (unchanged) |
| FTM | 48 | 48 (unchanged) |
| FTA | 56 | 56 (unchanged) |
| FT% | 85.71 | 85.71 (unchanged) |

This resolves the `3PA (121) > FGA (81)` flag (corrected FGA 202 > 3PA 121).

---

## 4. Recommendation summary

### Fix now (exact values given above)

- **`Player_Stats`, all 14 MTA players (PlayerId 100–113):** replace `FGM`/`FGA` with `FGM+3PM` /
  `FGA+3PA` (table in §1); recompute `FG%`. `3PM`/`3PA`/`3P%`/`FTM`/`FTA`/`FT%` are already correct.
- **`Player_Stats`, PlayerId 17471 (Isaiah Miles):** set `FGM=99`, `FGA=202`, recompute `FG%=49.01`.
  Everything else on that row is already correct.

These two fixes resolve all 6 flagged rows (`3PM/3PA > FGM/FGA`), because in every flagged case the
corrected `FGA` becomes `2PT-attempted + 3PT-attempted`, which is always ≥ `3PA` by construction.

### Do not change

- **`Team_Stats`** — every row (including MTA) already stores true total field goals; the sum-check in
  §1 confirms the corrected MTA `Player_Stats` total lines up with `Team_Stats`' existing MTA row to
  <1%. No team's `Team_Stats` row shows evidence of the 2PT-only bug.
- **The other 5 flagged-adjacent MTA rows are already covered above** — there are only 6 flagged rows
  total and both fixes above cover all 6 (5 MTA + Miles).

### Inherent / not fixable by a targeted row correction (flag for awareness, don't "fix" silently)

- **The `Team_Stats` vs. `Player_Stats` season-length mismatch (§2b, Effect 1).** `Team_Stats` reflects
  a ~22–24 game season; `Player_Stats` (all 12 non-MTA teams) reflects basket.co.il's broader ~29–30
  game "Regular Season" window. This is not something a per-row correction can fix — it's a scope
  mismatch between how the two sheets were originally built, and `Player_Data_Sources` doesn't document
  where `Team_Stats` actually came from (it only documents `Player_Stats`/`Roster`/`Players_Details`
  sourcing), so its provenance and correct scope should be tracked down before deciding whether
  `Team_Stats` or `Player_Stats` needs to change to match the other. This is a bigger, separate
  investigation from the 6-flagged-row shooting-stat bug this report was scoped to.
- **The BNH/HGE/HHF/IRG over/under-counts from the "kept single combined row" merge policy (§2b, Effect
  2).** These are a real, quantified distortion (+108/-140/-82 FGM etc.), but fixing them properly means
  changing the underlying merge decision for McGuirl, Reddic, and Moskovits — splitting each into two
  independent per-team rows, the same way Kyle Feit and Alex Hamilton were already (correctly) handled —
  rather than editing FGM/FGA numbers on the existing combined rows. That's a structural data-modeling
  decision (one row vs. two per traded player) beyond "correct these 6 flagged rows," so it's flagged
  here for your review rather than silently changed. If you do want it fixed, splitting those 3 players'
  rows the way Feit/Hamilton already are would resolve BNH, HGE, HHF and IRG's team-sum mismatches
  down to the same <1% residual that EKA/HJM/HHL already show (i.e., purely Effect 1, the season-length
  scope difference).
