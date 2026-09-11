"""Read-only business-table fingerprints in the fixed synthetic integration DB."""
import hashlib
import json

import psycopg
from psycopg import sql

TABLES = ("orderman_order", "orderman_orderitem", "orderman_orderevent", "orderman_directive",
          "orderman_idempotencykey", "cashman_entry", "payman_paymentintent", "payman_paymenttransaction", "stockman_move")
result = {}
with psycopg.connect(host="127.0.0.1", port=55439, user="orders_lab", dbname="orders_lab") as conn:
    conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    for table in TABLES:
        rows = conn.execute(sql.SQL("SELECT row_to_json(t)::text FROM {} t ORDER BY row_to_json(t)::text").format(sql.Identifier(table))).fetchall()
        digest = hashlib.sha256()
        for (row,) in rows:
            digest.update(row.encode())
            digest.update(b"\n")
        result[table] = {"rows": len(rows), "sha256": digest.hexdigest()}
print(json.dumps(result, sort_keys=True))
