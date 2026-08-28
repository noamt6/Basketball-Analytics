# Batch/job image for the Basketball Analytics pipeline.
# One image, four sub-commands: migrate | ingest | export | test
# It is NOT a server — every command runs to completion and exits.
FROM python:3.12-slim

# psycopg2-binary ships its own libpq, so no build deps are needed.
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code + the things the jobs read at runtime.
COPY db_client.py ingest.py metrics.py test_analytics.py export_dashboard_data.py ./
COPY schema.sql dashboard_supplement.json ./
COPY data/ ./data/
COPY dashboard.html ./
COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh

# Written by `export`; also the CWD the dashboard's data.json lands in.
VOLUME ["/app/out"]

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["test"]
