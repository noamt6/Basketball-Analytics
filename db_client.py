"""
PostgreSQL connection management for the Basketball Analytics engine.

Connection settings come from one of two places:

  * **AWS Secrets Manager** — if ``DB_SECRET_ARN`` (or ``DB_SECRET_NAME``) is
    set, the secret's JSON (``{host, port, dbname, username, password}`` — the
    standard RDS secret shape) is used. This is the cloud path; no ``.env``.
  * **``.env`` / environment** — the ``DB_*`` variables (see ``.env.example``).
    This is the local-dev path and the default.

Exposes a SQLAlchemy engine, a session context manager, and a helper to
(re)create the schema from ``schema.sql``.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Iterator
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable '{name}'. "
            "Copy .env.example to .env and fill in your DB credentials, "
            "or set DB_SECRET_ARN to read them from AWS Secrets Manager."
        )
    return value


@lru_cache(maxsize=1)
def _secret_credentials() -> dict | None:
    """
    Return the DB connection dict from AWS Secrets Manager, or ``None`` when no
    secret is configured. Cached so the API is hit at most once per process.
    """
    secret_id = os.getenv("DB_SECRET_ARN") or os.getenv("DB_SECRET_NAME")
    if not secret_id:
        return None
    try:
        import boto3  # imported lazily so local dev doesn't need boto3 installed
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError(
            "DB_SECRET_ARN/DB_SECRET_NAME is set but boto3 is not installed. "
            "Run `pip install -r requirements.txt`."
        ) from exc

    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    client = boto3.client("secretsmanager", region_name=region) if region else boto3.client("secretsmanager")
    raw = client.get_secret_value(SecretId=secret_id)["SecretString"]
    data = json.loads(raw)
    # Accept both RDS-managed key names and our own.
    return {
        "host": data.get("host") or data.get("DB_HOST"),
        "port": str(data.get("port") or data.get("DB_PORT") or "5432"),
        "dbname": data.get("dbname") or data.get("DB_NAME"),
        "username": data.get("username") or data.get("DB_USER"),
        "password": data.get("password") or data.get("DB_PASSWORD"),
    }


def get_database_url() -> str:
    secret = _secret_credentials()
    if secret:
        host, port = secret["host"], secret["port"]
        name, user, password = secret["dbname"], secret["username"], secret["password"]
    else:
        host = _require_env("DB_HOST")
        port = os.getenv("DB_PORT", "5432")
        name = _require_env("DB_NAME")
        user = _require_env("DB_USER")
        password = _require_env("DB_PASSWORD")
    # quote_plus so credentials with @ / : # etc. don't corrupt the URL.
    return (
        f"postgresql+psycopg2://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{name}"
    )


def _connect_args() -> dict:
    """psycopg2 connect args — TLS settings for a managed (RDS) database."""
    args: dict[str, str] = {"sslmode": os.getenv("DB_SSLMODE", "prefer")}
    root_cert = os.getenv("DB_SSLROOTCERT")
    if root_cert:
        args["sslrootcert"] = root_cert
    return args


def get_engine() -> Engine:
    """Return a process-wide SQLAlchemy engine, creating it on first use."""
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(
            get_database_url(),
            pool_pre_ping=True,
            pool_recycle=1800,
            connect_args=_connect_args(),
        )
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


@contextmanager
def get_session() -> Iterator[Session]:
    """Context-managed SQLAlchemy session; commits on success, rolls back on error."""
    get_engine()  # ensure engine/sessionmaker are initialized
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _strip_sql_line_comments(ddl: str) -> str:
    """Drop `-- ...` line comments before splitting on `;`. schema.sql has
    semicolons inside its comment prose, and it has no string literals
    containing `--`, so this is safe and keeps statement splitting correct."""
    return "\n".join(line.split("--", 1)[0] for line in ddl.splitlines())


def init_db(schema_path: Path = SCHEMA_PATH) -> None:
    """Execute schema.sql against the configured database (idempotent — uses CREATE IF NOT EXISTS)."""
    ddl = _strip_sql_line_comments(schema_path.read_text(encoding="utf-8"))
    engine = get_engine()
    with engine.begin() as conn:
        for statement in (s.strip() for s in ddl.split(";")):
            if statement:
                conn.execute(text(statement))


if __name__ == "__main__":
    init_db()
    print("Schema applied successfully.")
