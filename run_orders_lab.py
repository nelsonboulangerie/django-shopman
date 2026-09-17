from pathlib import Path
import os, sys
root = Path.cwd()
sys.path[:0] = [str(root), *[str(p) for p in sorted((root / "packages").iterdir()) if p.is_dir()]]
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings_test"
import pytest
raise SystemExit(pytest.main(["-q", "-p", "no:cacheprovider", "-c", "pyproject.toml", *sys.argv[1:]]))
