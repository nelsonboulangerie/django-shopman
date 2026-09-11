"""Check the full restored ledger/receipt manifest after compatibility probes."""
import json

from restore import LAB, SOURCE, TARGET, snapshot

expected = json.loads((LAB / f"{TARGET}-result.json").read_text())["manifest"]
for database in (SOURCE, TARGET):
    assert json.loads(json.dumps(snapshot(database))) == expected, database
summary = {"all_tables_and_sequences_still_equal": True,
    "table_count": len(expected["tables"]), "sequence_count": len(expected["sequences"]),
    "book_rows": {name: expected["tables"][name]["rows"] for name in (
        "cashman_entry", "orderman_order", "orderman_directive", "orderman_idempotencykey",
        "payman_paymentintent", "payman_paymenttransaction", "stockman_move",
    )}}
print(json.dumps(summary, indent=2))
