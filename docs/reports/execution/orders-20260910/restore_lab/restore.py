"""Loopback-only full database restore; prints counts/digests, never row contents."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from time import perf_counter

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[5]
LAB = ROOT / ".orders-lab"
CONN = {"host": "127.0.0.1", "port": 55439, "user": "orders_lab"}
SOURCE = "orders_lab"
TARGET = sys.argv[1] if len(sys.argv) > 1 else "orders_restore_lab"
assert TARGET in {"orders_restore_lab", "orders_restore_lab_stock"}
CLI = ["-h", CONN["host"], "-p", str(CONN["port"]), "-U", CONN["user"]]


def snapshot(database):
    output = {}
    with psycopg.connect(dbname=database, **CONN) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        tables = conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").fetchall()
        for (table,) in tables:
            rows = conn.execute(sql.SQL("SELECT row_to_json(t)::text FROM {} t ORDER BY row_to_json(t)::text").format(sql.Identifier(table))).fetchall()
            digest = hashlib.sha256()
            for (row,) in rows:
                digest.update(row.encode())
                digest.update(b"\n")
            output[table] = {"rows": len(rows), "sha256": digest.hexdigest()}
        sequences = conn.execute("SELECT sequencename, last_value FROM pg_sequences WHERE schemaname='public' ORDER BY sequencename").fetchall()
    return {"tables": output, "sequences": sequences}


def main():
    before = snapshot(SOURCE)
    archive = LAB / f"{TARGET}.dump"
    started = perf_counter()
    subprocess.run(["pg_dump", *CLI, "-Fc", "--no-owner", "--no-acl", "-f", str(archive), SOURCE], check=True)
    archive.chmod(0o600)
    dump_seconds = perf_counter() - started
    with psycopg.connect(dbname="postgres", autocommit=True, **CONN) as admin:
        assert not admin.execute("SELECT 1 FROM pg_database WHERE datname=%s", (TARGET,)).fetchone(), "Refuse to replace any existing database"
        admin.execute(sql.SQL("CREATE DATABASE {} OWNER orders_lab").format(sql.Identifier(TARGET)))
    started = perf_counter()
    subprocess.run(["pg_restore", *CLI, "--exit-on-error", "--no-owner", "--no-acl", "-d", TARGET, str(archive)], check=True)
    restore_seconds = perf_counter() - started
    after = snapshot(TARGET)
    assert before == after, "Restore changed table rows or sequence positions"
    assert before == snapshot(SOURCE), "Source changed during the assay"
    result = {"source": SOURCE, "target": TARGET, "dump_seconds": dump_seconds,
              "restore_seconds": restore_seconds, "archive_bytes": archive.stat().st_size,
              "all_tables_and_sequences_equal": True, "manifest": before}
    (LAB / f"{TARGET}-result.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({key: value for key, value in result.items() if key != "manifest"}, indent=2))


if __name__ == "__main__":
    main()
