"""Start only one explicit localhost performance lab reader, never a worker."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "docs/reports/execution/orders-20260910/http_read_lab"))
import run_http_lab  # noqa: F401 — fixed synthetic settings/environment

port = int(sys.argv[1])
assert port in {8016, 8017, 8018, 8019}
from daphne.cli import CommandLineInterface

CommandLineInterface().run(["-b", "127.0.0.1", "-p", str(port), "--access-log", "/dev/null", "config.asgi:application"])
