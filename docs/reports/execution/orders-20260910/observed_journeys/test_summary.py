import json
import unittest

from summarize import summarize


class SummaryTests(unittest.TestCase):
    def test_receipt_is_not_counted_as_another_application_and_secrets_are_omitted(self):
        common = {"intention_digest": "synthetic-key", "resource_ref": "SECRET-REF", "note": "SECRET-NOTE"}
        rows = [
            {**common, "timestamp": "2026-09-11T00:00:00Z", "event": "operator.command.local_result", "outcome": "applied", "replayed": False},
            {**common, "timestamp": "2026-09-11T00:00:01Z", "event": "operator.command.receipt", "outcome": "applied", "replayed": True},
            {"timestamp": "2026-09-11T00:00:02Z", "event": "operator.request.finished", "method": "POST", "outcome": "transport_unknown", "response_status": 500, "view_elapsed_ms": 12.5},
        ]
        result = summarize(map(json.dumps, rows))
        self.assertEqual(result["counters"]["command.applied"], 1)
        self.assertEqual(result["counters"]["receipt.applied"], 1)
        self.assertEqual(result["server_receipt_read_after_apply_ms"]["p95"], 1000)
        self.assertIsNone(result["last_observed_unresolved_effects"])
        self.assertNotIn("SECRET", json.dumps(result))
        self.assertNotIn("synthetic-key", json.dumps(result))

    def test_endpoint_labels_are_bounded_and_missing_trace_is_not_zero(self):
        common = {"timestamp": "2026-09-11T00:00:00Z", "event": "operator.request.finished", "method": "POST", "response_status": 403}
        rows = [{**common, "operation": "OrderCancelView", "request_id": "SECRET-ID"},
                {**common, "operation": "SECRET-CUSTOMER-PATH"}]
        result = summarize(map(json.dumps, rows))
        self.assertEqual(result["counters"]["endpoint.OrderCancelView.POST.403"], 1)
        self.assertEqual(result["counters"]["endpoint.other.POST.403"], 1)
        self.assertEqual(result["counters"]["trace.missing"], 1)
        self.assertEqual(result["counters"]["trace.present"], 1)
        self.assertNotIn("SECRET", json.dumps(result))

    def test_known_acceptance_clears_only_the_observed_pending_effect(self):
        rows = [
            {"timestamp": "2026-09-11T00:00:00Z", "event": "operator.effect.state", "directive_id": 1, "effect_state": "started"},
            {"timestamp": "2026-09-11T00:00:01Z", "event": "operator.effect.state", "directive_id": 1, "effect_state": "accepted"},
            {"timestamp": "2026-09-11T00:00:02Z", "event": "operator.effect.state", "directive_id": 2, "effect_state": "unknown"},
        ]
        result = summarize(map(json.dumps, rows))
        self.assertEqual(result["last_observed_unresolved_effects"], 1)
        self.assertIn("canonical_due_effect_backlog", result["unmeasured"])


if __name__ == "__main__":
    unittest.main()
