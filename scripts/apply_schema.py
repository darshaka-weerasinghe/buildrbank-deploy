"""
Create the tables, without touching the Supabase dashboard.

    python scripts/apply_schema.py

Creating tables is not something the normal Supabase API can do - it only
reads and writes rows. So this connects straight to the Postgres database
underneath and runs scripts/schema.sql against it.

Needs one extra line in .env:

    SUPABASE_DB_PASSWORD=...        (Settings -> Database -> Reset password)

If you would rather not keep a database password around, skip this script
entirely: open scripts/schema.sql, copy it, and paste it into
Dashboard -> SQL Editor -> Run. Same result.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import settings                                    # noqa: E402

SCHEMA = Path(__file__).parent / "schema.sql"

# Supabase offers two ways in, and which one works depends on your network:
#
#   direct   db.<ref>.supabase.co      - on new projects this is IPv6 only,
#                                        so it fails on most home/mobile
#                                        connections
#   pooler   aws-N-<region>.pooler...  - plain IPv4, works everywhere
#
# The pooler is region-specific and we cannot ask the project where it
# lives, so we simply try the likely ones and keep the first that answers.
REGIONS = ["ap-south-1", "ap-southeast-1", "ap-northeast-1",
           "us-east-1", "us-east-2", "us-west-1", "eu-central-1", "eu-west-2"]


def candidates(ref: str, password: str) -> list[tuple[str, str]]:
    out = [("direct (IPv6)",
            f"postgresql://postgres:{password}@db.{ref}.supabase.co:5432/postgres")]
    for prefix in ("aws-1", "aws-0"):
        for region in REGIONS:
            out.append((
                f"pooler {prefix}-{region}",
                # port 5432 is the SESSION pooler. Use this one, not 6543 -
                # the 6543 transaction pooler cannot run some statements.
                f"postgresql://postgres.{ref}:{password}"
                f"@{prefix}-{region}.pooler.supabase.com:5432/postgres",
            ))
    return out


def main() -> int:
    settings.configure()
    import psycopg

    password = os.environ.get("SUPABASE_DB_PASSWORD", "").strip()
    if not password:
        print("  SUPABASE_DB_PASSWORD is not set in .env.")
        print("  Either add it, or paste scripts/schema.sql into the dashboard.")
        return 1

    ref = re.sub(r"^https?://", "", os.environ["SUPABASE_URL"]).split(".")[0]
    print(f"  project: {ref}")

    conn = None
    for label, dsn in candidates(ref, password):
        try:
            conn = psycopg.connect(dsn, connect_timeout=12)
            print(f"  connected via {label}\n")
            break
        except Exception as e:
            short = str(e).strip().splitlines()[0][:70]
            print(f"    {label:<26} no ({short})")

    if conn is None:
        print("\n  Could not reach the database on any route.")
        print("  Paste scripts/schema.sql into the dashboard SQL editor instead.")
        return 1

    sql = SCHEMA.read_text(encoding="utf-8")
    with conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            print(f"  ran {SCHEMA.name} ({len(sql.splitlines())} lines)")

            cur.execute("""
                select table_name from information_schema.tables
                where table_schema = 'public' order by table_name
            """)
            tables = [r[0] for r in cur.fetchall()]

            cur.execute("""
                select routine_name from information_schema.routines
                where routine_schema = 'public' and routine_name like 'match_%'
                   or routine_schema = 'public' and routine_name = 'cleanup_expired'
                order by routine_name
            """)
            funcs = sorted({r[0] for r in cur.fetchall()})

    conn.close()

    print(f"\n  tables ({len(tables)}):    {', '.join(tables)}")
    print(f"  functions ({len(funcs)}):  {', '.join(funcs)}")
    print("\nNext:  python scripts/seed.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
