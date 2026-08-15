"""Apply db/schema.sql to Supabase via direct Postgres connection.

Requires DATABASE_URL in the environment, e.g. from Supabase Dashboard:
Settings -> Database -> Connection string (URI, Session pooler or Direct).
"""

import os
import sys

import psycopg2
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_PATH = os.path.join(BASE_DIR, "db", "schema.sql")


def main() -> None:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError(
            "Set DATABASE_URL in .env (Supabase Dashboard -> Settings -> Database -> Connection string)."
        )

    with open(SCHEMA_PATH, encoding="utf-8") as handle:
        sql = handle.read()

    conn = psycopg2.connect(database_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        print(f"Applied schema from {SCHEMA_PATH}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
