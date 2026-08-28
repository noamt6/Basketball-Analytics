# Deployment

Target AWS architecture (see `../logical-snacking-goblet.md` plan for the full rationale):

```
data/*.xlsx ──(ingest job)──► RDS PostgreSQL ──(export job)──► data.json ─┐
                                                                         ▼
                                          S3 bucket  ◄── dashboard.html + data.json
                                                                         │
                                                                   CloudFront (OAC)
                                                                         │
                                                                     viewers
```

* **RDS PostgreSQL** — new dedicated `db.t4g.micro`, `eu-central-1`, not publicly
  accessible. Credentials live in **AWS Secrets Manager**; `db_client.py` reads them
  when `DB_SECRET_ARN` is set (otherwise it uses the `DB_*` env vars from `.env`).
* **Batch image** (`Dockerfile`) — one image, sub-commands `migrate | ingest | export | test`
  (`docker-entrypoint.sh`). Pushed to **ECR**. Run it from your laptop over an SSM
  port-forward to the DB, or as a one-off **ECS Fargate** task.
* **Dashboard** — pure static: `dashboard.html` + `data.json` synced to **S3**, served
  through **CloudFront**. No backend.
* **Terraform** in [`infra/`](infra/) provisions all of the above (`terraform apply`).

## Local dev (Docker)

```bash
docker compose up -d db
docker compose run --rm app migrate      # apply schema.sql
docker compose run --rm app ingest       # load data/Basketball_Analytics.xlsx
docker compose run --rm app test         # leaderboards — compare to data/VIEWS.xlsx
docker compose run --rm app export       # writes ./out/data.json
```

Or without Docker: `python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt`,
`copy .env.example .env` (set `DB_SSLMODE=disable` for local Postgres), then
`python db_client.py`, `python ingest.py`, `python test_analytics.py`, `python export_dashboard_data.py`.

Preview the dashboard (it now `fetch()`es `data.json`, so it must be served, not opened as `file://`):

```bash
python -m http.server 8000        # from the project root; open http://localhost:8000/dashboard.html
```

## Cloud deploy sequence

1. `cd infra && terraform init && terraform apply`
   → RDS, Secrets Manager secret, ECR repo, S3 bucket, CloudFront distribution.
2. Build & push the batch image:
   ```bash
   aws ecr get-login-password --region eu-central-1 | docker login --username AWS --password-stdin <ecr-url>
   docker build -t <ecr-url>:latest .
   docker push <ecr-url>:latest
   ```
3. Point at RDS (laptop path): open an SSM tunnel to the DB, then
   `DB_SECRET_ARN=<arn> AWS_REGION=eu-central-1 python db_client.py` (migrate) and
   `... python ingest.py`. Or `aws ecs run-task ... --overrides '{"containerOverrides":[{"name":"app","command":["migrate"]}]}'` then `["ingest"]`.
4. `DB_SECRET_ARN=<arn> python export_dashboard_data.py --out data.json`
   (or `aws ecs run-task ... command=["export"]` and pull `data.json` from the task's output volume / S3).
5. Publish the site:
   ```bash
   aws s3 cp dashboard.html s3://<bucket>/dashboard.html
   aws s3 cp data.json      s3://<bucket>/data.json
   aws cloudfront create-invalidation --distribution-id <id> --paths '/dashboard.html' '/data.json'
   ```
6. Open the CloudFront URL; confirm the dashboard renders and `data.json` returns 200.

## Notes / open items

* `export_dashboard_data.py` reproduces the DB-derived fields via `metrics.py`. Three
  things are **not** in the DB and come from `dashboard_supplement.json`: `team.rank`
  (real league standings), player row display order, and `age_as_of`. Keep that file
  current when a new season is added.
* `efficiency` is now canonical (`metrics.efficiency_index`, subtracts turnovers) by
  default. The committed `data.json` baseline predates that decision and still carries
  the turnover-less value, so `python export_dashboard_data.py --check data.json` after
  the first real ingest will report an `efficiency` diff on most players — expected;
  the fresh export is the correct one. (`--no-efficiency-includes-tov` reproduces the
  old value if you ever need to.)
* Pin `requirements.txt` to exact versions (`pip freeze`) before the first image build
  if you want byte-reproducible builds.
* `dashboard.html` still needs `overflow-x: clip` (not `hidden`) on `html, body` — see
  the note in the project README; `scripts/qa_responsive_rtl.js` guards it (186/186).
