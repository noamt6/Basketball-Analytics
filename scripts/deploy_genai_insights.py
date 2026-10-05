#!/usr/bin/env python3
"""
Provision the ``bball-genai-insights`` serverless pipeline (idempotent).

Creates / updates, all in eu-central-1 (CloudFront is global):
  * IAM role ``bball-genai-insights-role`` + least-privilege inline policy
  * Lambda ``bball-genai-insights`` (python3.12, arm64, 256 MB, 60 s, no VPC)
  * Log group ``/aws/lambda/bball-genai-insights`` with 14-day retention
  * EventBridge rule ``bball-genai-insights-daily`` -> the Lambda (cron 06:00 UTC)

Run again any time to push new handler code / config. The local AWS CLI is a
2020 build, so this uses boto3 directly (same reason as deploy_cf_function.py).

    python scripts/deploy_genai_insights.py            # provision / update
    python scripts/deploy_genai_insights.py --dry-run  # print planned actions
    python scripts/deploy_genai_insights.py --invoke   # provision then test-invoke
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
import zipfile
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

REGION = "eu-central-1"
ACCOUNT = "402631154156"

FN_NAME = "bball-genai-insights"
ROLE_NAME = "bball-genai-insights-role"
POLICY_NAME = "bball-genai-insights"
RULE_NAME = "bball-genai-insights-daily"
LOG_GROUP = f"/aws/lambda/{FN_NAME}"
SCHEDULE = "cron(0 6 * * ? *)"  # 06:00 UTC daily

SITE_BUCKET = "bball-dashboard-402631154156"
DISTRIBUTION_ID = "E155IZM1SR95HY"
MODEL_ID = "eu.amazon.nova-lite-v1:0"
# Claude Haiku 4.5 (eu.anthropic.claude-haiku-4-5-20251001-v1:0) is preferred but
# needs the account's Anthropic "use case details" form submitted in the Bedrock
# console first; swap MODEL_ID + the bedrock Resource ARNs below once that clears.

HANDLER_SRC = Path(__file__).resolve().parents[1] / "lambda" / "genai_insights" / "lambda_function.py"

ENV_VARS = {
    "SITE_BUCKET": SITE_BUCKET,
    "DATA_KEY": "data.json",
    "INSIGHTS_KEY": "insights.json",
    "CLOUDFRONT_DISTRIBUTION_ID": DISTRIBUTION_ID,
    "BEDROCK_MODEL_ID": MODEL_ID,
    "BEDROCK_REGION": REGION,
}

TRUST = {
    "Version": "2012-10-17",
    "Statement": [
        {"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"},
         "Action": "sts:AssumeRole"}
    ],
}

INLINE_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {"Sid": "ReadData", "Effect": "Allow", "Action": "s3:GetObject",
         "Resource": f"arn:aws:s3:::{SITE_BUCKET}/data.json"},
        {"Sid": "WriteInsights", "Effect": "Allow", "Action": "s3:PutObject",
         "Resource": f"arn:aws:s3:::{SITE_BUCKET}/insights.json"},
        {"Sid": "InvokeBedrock", "Effect": "Allow", "Action": "bedrock:InvokeModel",
         "Resource": [
             f"arn:aws:bedrock:{REGION}:{ACCOUNT}:inference-profile/{MODEL_ID}",
             "arn:aws:bedrock:*::foundation-model/amazon.nova-lite-v1:0",
         ]},
        {"Sid": "InvalidateCDN", "Effect": "Allow", "Action": "cloudfront:CreateInvalidation",
         "Resource": f"arn:aws:cloudfront::{ACCOUNT}:distribution/{DISTRIBUTION_ID}"},
    ],
}

iam = boto3.client("iam")
lam = boto3.client("lambda", region_name=REGION)
logs = boto3.client("logs", region_name=REGION)
events = boto3.client("events", region_name=REGION)


def _zip_handler() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("lambda_function.py", HANDLER_SRC.read_text(encoding="utf-8"))
    return buf.getvalue()


def ensure_role(dry: bool) -> str:
    arn = f"arn:aws:iam::{ACCOUNT}:role/{ROLE_NAME}"
    try:
        iam.get_role(RoleName=ROLE_NAME)
        exists = True
    except ClientError as e:
        if e.response["Error"]["Code"] != "NoSuchEntity":
            raise
        exists = False

    if dry:
        print(f"[dry-run] {'update' if exists else 'create'} role {ROLE_NAME}")
        print(f"[dry-run] put inline policy {POLICY_NAME}, attach AWSLambdaBasicExecutionRole")
        return arn

    if not exists:
        iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(TRUST),
            Description="bball-genai-insights daily pipeline",
        )
        print(f"created role {ROLE_NAME}")
    iam.attach_role_policy(
        RoleName=ROLE_NAME,
        PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
    )
    iam.put_role_policy(
        RoleName=ROLE_NAME, PolicyName=POLICY_NAME,
        PolicyDocument=json.dumps(INLINE_POLICY),
    )
    print(f"role {ROLE_NAME} policy synced")
    if not exists:
        print("waiting 10s for role propagation...")
        time.sleep(10)
    return arn


def ensure_function(role_arn: str, dry: bool) -> str:
    code = _zip_handler()
    try:
        lam.get_function(FunctionName=FN_NAME)
        exists = True
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
        exists = False

    if dry:
        print(f"[dry-run] {'update' if exists else 'create'} lambda {FN_NAME} "
              f"(python3.12, arm64, 256MB, 60s, no VPC)")
        print(f"[dry-run] env: {json.dumps(ENV_VARS)}")
        return f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:{FN_NAME}"

    cfg = dict(
        Runtime="python3.12", Role=role_arn, Handler="lambda_function.handler",
        Timeout=60, MemorySize=256,
        Environment={"Variables": ENV_VARS},
    )
    if exists:
        lam.update_function_code(FunctionName=FN_NAME, ZipFile=code)
        _wait_updated()
        lam.update_function_configuration(FunctionName=FN_NAME, **cfg)
        _wait_updated()
        print(f"updated lambda {FN_NAME}")
    else:
        for attempt in range(6):
            try:
                lam.create_function(FunctionName=FN_NAME, Code={"ZipFile": code},
                                    Publish=True, Architectures=["arm64"], **cfg)
                break
            except ClientError as e:
                if e.response["Error"]["Code"] == "InvalidParameterValueException" and attempt < 5:
                    time.sleep(5)
                    continue
                raise
        print(f"created lambda {FN_NAME}")
    return lam.get_function(FunctionName=FN_NAME)["Configuration"]["FunctionArn"]


def _wait_updated() -> None:
    for _ in range(30):
        st = lam.get_function(FunctionName=FN_NAME)["Configuration"].get("LastUpdateStatus")
        if st == "Successful":
            return
        if st == "Failed":
            raise RuntimeError("lambda update failed")
        time.sleep(2)


def ensure_log_retention(dry: bool) -> None:
    if dry:
        print(f"[dry-run] ensure log group {LOG_GROUP} + 14-day retention")
        return
    try:
        logs.create_log_group(logGroupName=LOG_GROUP)
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceAlreadyExistsException":
            raise
    logs.put_retention_policy(logGroupName=LOG_GROUP, retentionInDays=14)
    print(f"log group {LOG_GROUP} retention = 14 days")


def ensure_schedule(fn_arn: str, dry: bool) -> None:
    if dry:
        print(f"[dry-run] put rule {RULE_NAME} {SCHEDULE} -> {fn_arn}")
        print(f"[dry-run] add lambda permission for events.amazonaws.com")
        return
    rule_arn = events.put_rule(
        Name=RULE_NAME, ScheduleExpression=SCHEDULE, State="ENABLED",
        Description="Daily GenAI insights refresh for plusminus.cloud",
    )["RuleArn"]
    try:
        lam.add_permission(
            FunctionName=FN_NAME, StatementId="events-daily-invoke",
            Action="lambda:InvokeFunction", Principal="events.amazonaws.com",
            SourceArn=rule_arn,
        )
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceConflictException":
            raise
    events.put_targets(Rule=RULE_NAME, Targets=[{"Id": "lambda", "Arn": fn_arn}])
    print(f"rule {RULE_NAME} -> {FN_NAME} ({SCHEDULE})")


def test_invoke() -> None:
    print("invoking once...")
    r = lam.invoke(FunctionName=FN_NAME, InvocationType="RequestResponse",
                   LogType="Tail", Payload=b"{}")
    payload = r["Payload"].read().decode()
    print("status:", r["StatusCode"], "function-error:", r.get("FunctionError"))
    print("response:", payload)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--invoke", action="store_true", help="test-invoke after provisioning")
    args = ap.parse_args()

    if not HANDLER_SRC.exists():
        sys.exit(f"handler not found: {HANDLER_SRC}")

    role_arn = ensure_role(args.dry_run)
    fn_arn = ensure_function(role_arn, args.dry_run)
    ensure_log_retention(args.dry_run)
    ensure_schedule(fn_arn, args.dry_run)

    if args.dry_run:
        print("\n[dry-run] no changes made.")
        return 0

    print(f"\nprovisioned: {fn_arn}")
    if args.invoke:
        test_invoke()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
