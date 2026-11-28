"""O erro de transporte não pode apagar o resultado nem vazar campos do curl."""

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("capture_tail_http", Path(__file__).with_name("capture_tail_http.py"))
CAPTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CAPTURE)


class CaptureTailHttpTests(unittest.TestCase):
    def test_receive_error_is_retained_and_later_transfers_are_not_lost(self):
        rows = []
        for route, exitcode in [("catalog/", 0), ("catalog/", 0), ("products/FENDU/", 56), ("products/FENDU/", 0)]:
            raw = {
                "url_effective": CAPTURE.BASES["bff"] + "/api/v1/storefront/" + route,
                "http_code": 0 if exitcode else 200, "exitcode": exitcode,
                "errormsg": "Recv failure: Connection reset by peer" if exitcode else None,
                "time_total": 0.5, "local_ip": "not-for-the-report", "certs": "not-for-the-report",
            }
            rows.append(json.dumps(raw) + "\t" + "\t".join("" for _ in CAPTURE.HEADERS))
        result = SimpleNamespace(returncode=56, stdout="\n".join(rows) + "\n")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture.json"
            args = ["capture", "--samples", "2", "--label", "test", "--output", str(output)]
            with patch("sys.argv", args), patch.object(CAPTURE.subprocess, "run", return_value=result) as run, contextlib.redirect_stdout(io.StringIO()):
                CAPTURE.main()
            saved = json.loads(output.read_text())
            self.assertEqual(saved["observed_samples"], 4)
            self.assertEqual(saved["summary"]["pdp"]["failed"], 1)
            self.assertEqual(saved["summary"]["pdp"]["successful"], 1)
            self.assertEqual(saved["samples"][2]["exitcode"], 56)
            self.assertIn("reset by peer", saved["samples"][2]["errormsg"])
            self.assertNotIn("not-for-the-report", output.read_text())
            self.assertFalse(run.call_args.kwargs["check"])
            self.assertNotIn("--fail-early", run.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
