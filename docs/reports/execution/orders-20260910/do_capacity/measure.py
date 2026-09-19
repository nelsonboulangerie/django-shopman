"""Reuse the established assay, with its explicit ephemeral-CI guard."""
import os
import runpy
from pathlib import Path

root = Path(__file__).resolve().parents[5]
assert os.environ.get("GITHUB_ACTIONS") == "true"
assert os.environ.get("ORDERS_ISOLATED_CAPACITY") == "1"
runpy.run_path(str(root / "docs/reports/execution/orders-20260910/process_read_lab/measure.py"), run_name="__main__")
