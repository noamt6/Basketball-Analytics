"""
Generate Hebrew team names for every historical team id in data.json and merge
them into data/hebrew_names.json under "teams".

basket.co.il issues a fresh numeric team id per season, so one franchise owns
many ids across the decade (Maccabi Tel-Aviv alone has ~9). The dashboard looks
up name_he / city_he / label_he by the team id string, so this expands a small
english-name -> Hebrew map to a full {id: {...}} table.
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_JSON = ROOT / "data.json"
HE_JSON = ROOT / "data" / "hebrew_names.json"

# english name (as it appears in data.json) -> (name_he, city_he)
NAME_HE = {
    "Maccabi Tel-Aviv": ("מכבי", "תל אביב"),
    "M. Tel-Aviv": ("מכבי", "תל אביב"),
    "Hapoel Tel-Aviv": ("הפועל", "תל אביב"),
    "Hapoel TA": ("הפועל", "תל אביב"),
    "Hapoel Jerusalem": ("הפועל", "ירושלים"),
    "Hapoel J-M": ("הפועל", "ירושלים"),
    "Hapoel Holon": ("הפועל", "חולון"),
    "UNET Holon": ("הפועל", "חולון"),
    "U-NET Holon": ("הפועל", "חולון"),
    "Hapoel Haifa": ("הפועל", "חיפה"),
    "M. Haifa": ("מכבי", "חיפה"),
    "Hapoel Eilat": ("הפועל", "אילת"),
    "Hapoel Yossi Avrahami Eilat": ("הפועל", "אילת"),
    "Bnei Herzliya": ("בני", "הרצליה"),
    "Bnei Herzeliya": ("בני", "הרצליה"),
    "Herzliya": ("בני", "הרצליה"),
    "Ness Ziona": ("עירוני", "נס ציונה"),
    "Nes Ziona": ("עירוני", "נס ציונה"),
    "Gilboa Galil": ("הפועל", "גלבוע גליל"),
    "Galil Elion": ("הפועל", "גליל עליון"),
    "Hapoel Galil Elion": ("הפועל", "גליל עליון"),
    "Hapoel Afula": ("הפועל", "עפולה"),
    "Hapoel Haemek": ("הפועל", "העמק"),
    "Be'er Sheva": ("הפועל", "באר שבע"),
    "Be'er Sheva/Dimona": ("הפועל", "באר שבע/דימונה"),
    "Beer Sheva/Dimona": ("הפועל", "באר שבע/דימונה"),
    "Ashdod": ("מכבי", "אשדוד"),
    "Maccabi Ashdod": ("מכבי", "אשדוד"),
    "Elitzur Netanya": ("אליצור", "נתניה"),
    "Ironi Kiryat Ata": ("עירוני", "קריית אתא"),
    "Kiryat Ata": ("עירוני", "קריית אתא"),
    "Maccabi Ramat Gan": ("מכבי עירוני", "רמת גן"),
    "Nahariya": ("עירוני", "נהריה"),
    "M. Rishon": ("מכבי", "ראשון לציון"),
    "M. Kiryat Gat": ("מכבי", "קריית גת"),
    "M. Ra'ananna": ("מכבי", "רעננה"),
}


def main() -> int:
    dj = json.loads(DATA_JSON.read_text(encoding="utf-8"))
    he = json.loads(HE_JSON.read_text(encoding="utf-8"))
    teams = he.setdefault("teams", {})

    seen, unknown, added = {}, set(), 0
    for season, blob in dj["seasons"].items():
        if season == "2023-2024":            # curated codes already in the file
            continue
        for t in blob["teams"] + blob.get("playoffs", {}).get("teams", []):
            tid, name = t["id"], t["name"]
            if tid in seen:
                continue
            seen[tid] = name
            m = NAME_HE.get(name)
            if not m:
                unknown.add(name)
                continue
            name_he, city_he = m
            teams[tid] = {
                "name_he": name_he,
                "city_he": city_he,
                "label_he": f"{name_he} {city_he}".strip(),
            }
            added += 1

    HE_JSON.write_text(json.dumps(he, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"teams: {len(seen)} historical ids, {added} mapped, {len(teams)} total entries in file")
    if unknown:
        print("UNMAPPED english names (add to NAME_HE):")
        for n in sorted(unknown):
            print(f"  {n!r}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
