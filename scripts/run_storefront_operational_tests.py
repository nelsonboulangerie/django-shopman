"""Run isolated storefront proofs with worktree packages ahead of editable installs.

Default: SQLite, no Redis. --postgres-url must address a local disposable DB.
No production dotenv, providers, messages, or transactions are authorized here.
"""

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--postgres-url", default="")
options, pytest_args = parser.parse_known_args()
if options.postgres_url and urlparse(options.postgres_url).hostname not in {"localhost", "127.0.0.1", "::1"}:
    parser.error("Use only an explicitly provisioned local disposable database.")
sys.path[:0] = [str(root), *[str(path) for path in sorted((root / "packages").iterdir()) if path.is_dir()]]
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings_test"
os.environ["DATABASE_URL"] = options.postgres_url
os.environ["REDIS_URL"] = ""
os.chdir(root)
import pytest  # noqa: E402

raise SystemExit(pytest.main(["-q", "-c", str(root / "pyproject.toml"), *pytest_args]))
