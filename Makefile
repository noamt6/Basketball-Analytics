# Convenience wrapper. `make help` lists targets.
# Assumes a populated .env (or DB_SECRET_ARN) — see .env.example.
PY ?= python

.PHONY: help venv install migrate reset ingest test export dq qa docker-build \
        compose-up compose-down tf-init tf-plan tf-apply

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  %-14s %s\n", $$1, $$2}'

venv: ## create .venv
	$(PY) -m venv .venv

install: ## install python deps into the active interpreter
	$(PY) -m pip install -r requirements.txt

migrate: ## apply schema.sql
	$(PY) -m db_client

reset: ## DROP all tables (needs --yes); then re-migrate + ingest
	$(PY) scripts/reset_db.py --yes && $(PY) -m db_client

ingest: ## load the season workbook ($$WORKBOOK or the bundled one)
	$(PY) ingest.py

test: ## print leaderboards (compare to data/VIEWS.xlsx)
	$(PY) test_analytics.py

export: ## regenerate ./data.json from the DB
	$(PY) export_dashboard_data.py --out data.json

check-export: ## diff a fresh DB export against the committed data.json
	$(PY) export_dashboard_data.py --check data.json

dq: ## data-quality audit of the workbook
	$(PY) scripts/check_data_quality.py --fail-on fg

qa: ## responsive / RTL sweep of dashboard.html
	node scripts/qa_responsive_rtl.js

serve: ## preview the dashboard at http://localhost:8000/dashboard.html
	$(PY) -m http.server 8000

docker-build: ## build the batch image
	docker build -t bball-batch:local .

compose-up: ## local postgres via docker compose
	docker compose up -d db

compose-down:
	docker compose down

tf-init: ## terraform init (needs infra/backend.hcl)
	cd infra && terraform init -backend-config=backend.hcl

tf-plan:
	cd infra && terraform plan

tf-apply:
	cd infra && terraform apply
