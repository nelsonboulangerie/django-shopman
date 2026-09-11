"""Check the full restored ledger/receipt manifest after compatibility probes."""
import json
import sys

from restore import LAB, SOURCE, TARGET, snapshot

expected = json.loads((LAB / f"{TARGET}-result.json").read_text())["manifest"]
after_probes = sys.argv[2:] == ["--after-probes"]
assert not sys.argv[2:] or after_probes, "Unknown verification mode"
sequence_advances = {}
for database in (SOURCE, TARGET):
    actual = json.loads(json.dumps(snapshot(database)))
    assert actual["tables"] == expected["tables"], database
    if database == SOURCE or not after_probes:
        assert actual["sequences"] == expected["sequences"], database
        continue
    before_sequences = dict(expected["sequences"])
    after_sequences = dict(actual["sequences"])
    assert before_sequences.keys() == after_sequences.keys()
    sequence_advances = {name: {"before": value, "after": after_sequences[name]}
                         for name, value in before_sequences.items() if value != after_sequences[name]}
    # The current worker creates one alert inside the rolled-back probe. PostgreSQL
    # nextval is not transactional; no other sequence or table may change.
    assert set(sequence_advances) <= {"backstage_operatoralert_id_seq"}, sequence_advances
    for values in sequence_advances.values():
        assert values["after"] == (values["before"] or 0) + 1, values
summary = {"all_tables_and_sequences_still_equal": not sequence_advances,
    "all_tables_still_equal": True, "source_unchanged": True,
    "probe_sequence_advances": sequence_advances,
    "table_count": len(expected["tables"]), "sequence_count": len(expected["sequences"]),
    "book_rows": {name: expected["tables"][name]["rows"] for name in (
        "cashman_entry", "orderman_order", "orderman_directive", "orderman_idempotencykey",
        "payman_paymentintent", "payman_paymenttransaction", "stockman_move",
    )}}
print(json.dumps(summary, indent=2))
