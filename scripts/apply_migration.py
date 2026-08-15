"""Apply a single SQL migration file to Supabase (requires DATABASE_URL in .env)."""

import argparse
import os
import sys

import psycopg2
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "migration",
        nargs="?",
        default=os.path.join(BASE_DIR, "db", "migrations", "add_is_active.sql"),
        help="Path to a .sql migration file",
    )
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError(
            "Set DATABASE_URL in .env (Supabase Dashboard -> Settings -> Database -> Connection string)."
        )

    with open(args.migration, encoding="utf-8") as handle:
        sql = handle.read()

    conn = psycopg2.connect(database_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        print(f"Applied migration: {args.migration}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
