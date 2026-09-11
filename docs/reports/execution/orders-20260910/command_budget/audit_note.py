"""Read the synthetic order's canonical event count without exporting note text."""
import json
import sys

import psycopg

ref = sys.argv[1]
assert ref.startswith("LAB-OLD-BROWSER-")
with psycopg.connect(host="127.0.0.1", port=55439, user="orders_lab", dbname="orders_lab") as conn:
    conn.execute("SET TRANSACTION READ ONLY")
    count = conn.execute("SELECT count(*) FROM orderman_orderevent e JOIN orderman_order o ON o.id=e.order_id WHERE o.ref=%s AND e.type='kitchen_note_changed'", (ref,)).fetchone()[0]
print(json.dumps({"kitchen_note_events": count}))
