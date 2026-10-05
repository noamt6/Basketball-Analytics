"""
bball-genai-insights -- daily serverless GenAI trends blurb for plusminus.cloud.

Reads ``data.json`` straight from the site bucket (no DB, no VPC), pulls the
salient impact rows (PIR / efficiency -- the dataset has no plus/minus), asks
Bedrock (Claude Haiku 4.5 via the EU inference profile, Converse API) for a
2-3 sentence Hebrew tactical summary, writes ``insights.json`` back next to
``data.json`` and invalidates ``/insights.json`` on CloudFront.

All configuration is via environment variables -- see ``_env`` below.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import time

import boto3

SITE_BUCKET = os.environ["SITE_BUCKET"]
DATA_KEY = os.environ.get("DATA_KEY", "data.json")
INSIGHTS_KEY = os.environ.get("INSIGHTS_KEY", "insights.json")
DISTRIBUTION_ID = os.environ["CLOUDFRONT_DISTRIBUTION_ID"]
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "eu.amazon.nova-lite-v1:0")
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "eu-central-1")

_s3 = boto3.client("s3")
_cf = boto3.client("cloudfront")
_brt = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)

MIN_GP = 10
TOP_N = 5

_PROMPT_INTRO = (
    "אתה אנליסט כדורסל. על סמך הנתונים הבאים (סיכומי עונה מלאים, "
    "מדד ההשפעה הוא PIR ויעילות – אין נתוני פלוס/מינוס) כתוב סיכום טקטי קצר "
    "של 2-3 משפטים בעברית על המגמות הבולטות בליגה: שחקנים מובילים לפי PIR ויעילות, "
    "ומצב הקבוצות בצמרת הטבלה. טקסט זורם בלבד, בלי רשימות ובלי כותרות."
)


def _env() -> dict:
    return {
        "SITE_BUCKET": SITE_BUCKET,
        "DATA_KEY": DATA_KEY,
        "INSIGHTS_KEY": INSIGHTS_KEY,
        "CLOUDFRONT_DISTRIBUTION_ID": DISTRIBUTION_ID,
        "BEDROCK_MODEL_ID": MODEL_ID,
        "BEDROCK_REGION": BEDROCK_REGION,
    }


def _player_row(p: dict, team_names: dict) -> dict:
    return {
        "name": p.get("name_he") or p.get("name"),
        "team": team_names.get(p.get("team_id"), p.get("team_id")),
        "gp": p.get("gp"),
        "avg_points": p.get("avg_points"),
        "avg_pir": p.get("avg_pir"),
        "pir": p.get("pir"),
        "efficiency": p.get("efficiency"),
        "ts_pct": p.get("ts_pct"),
    }


def _top(players: list[dict], key: str, team_names: dict, *, min_gp: int = 0) -> list[dict]:
    pool = [
        p
        for p in players
        if not p.get("bad_split")
        and p.get(key) is not None
        and (p.get("gp") or 0) >= min_gp
    ]
    pool.sort(key=lambda p: p[key], reverse=True)
    return [_player_row(p, team_names) for p in pool[:TOP_N]]


def _salient(season_blob: dict) -> dict:
    players = season_blob.get("players", [])
    teams = season_blob.get("teams", [])
    team_names = {t["id"]: t.get("label_he") or t.get("label") for t in teams}
    standings = sorted(
        (
            {
                "rank": t.get("rank"),
                "team": t.get("label_he") or t.get("label"),
                "avg_points": t.get("avg_points"),
                "avg_pir": t.get("avg_pir"),
            }
            for t in teams
        ),
        key=lambda t: (t["rank"] is None, t["rank"]),
    )
    return {
        "top_pir": _top(players, "pir", team_names),
        "top_efficiency": _top(players, "efficiency", team_names),
        "top_avg_pir": _top(players, "avg_pir", team_names, min_gp=MIN_GP),
        "scoring_leaders": _top(players, "avg_points", team_names, min_gp=MIN_GP),
        "team_standings": standings,
    }


def _summarise(season: str, highlights: dict) -> tuple[str, dict]:
    payload = json.dumps(
        {"season": season, **highlights}, ensure_ascii=False, separators=(",", ":")
    )
    resp = _brt.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": f"{_PROMPT_INTRO}\n\n{payload}"}]}],
        inferenceConfig={"maxTokens": 400, "temperature": 0.3},
    )
    text = "".join(
        block.get("text", "") for block in resp["output"]["message"]["content"]
    ).strip()
    usage = resp.get("usage", {})
    return text, {
        "input_tokens": usage.get("inputTokens"),
        "output_tokens": usage.get("outputTokens"),
    }


def handler(event, context):
    raw = _s3.get_object(Bucket=SITE_BUCKET, Key=DATA_KEY)["Body"].read()
    data = json.loads(raw)
    season = data["default_season"]
    season_blob = data["seasons"][season]

    highlights = _salient(season_blob)
    summary_he, usage = _summarise(season, highlights)

    doc = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "season": season,
        "model": MODEL_ID,
        "summary_he": summary_he,
        "highlights": highlights,
        "usage": usage,
    }
    body = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    _s3.put_object(
        Bucket=SITE_BUCKET,
        Key=INSIGHTS_KEY,
        Body=body.encode("utf-8"),
        ContentType="application/json; charset=utf-8",
        CacheControl="public,max-age=300",
    )

    inv = _cf.create_invalidation(
        DistributionId=DISTRIBUTION_ID,
        InvalidationBatch={
            "Paths": {"Quantity": 1, "Items": [f"/{INSIGHTS_KEY}"]},
            "CallerReference": str(time.time()),
        },
    )

    result = {
        "season": season,
        "chars": len(summary_he),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "invalidation_id": inv["Invalidation"]["Id"],
    }
    print(json.dumps(result))
    return result


if __name__ == "__main__":  # local smoke test (needs AWS creds + env vars)
    print(json.dumps(_env(), indent=2))
    print(handler({}, None))
