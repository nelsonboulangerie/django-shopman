import os
import sys
from pathlib import Path

root = Path.cwd()
sys.path[:0] = [str(root), *[str(p) for p in sorted((root / 'packages').iterdir()) if p.is_dir()]]
assert os.environ['DATABASE_URL'] == 'postgres://orders_lab@127.0.0.1:55439/orders_lab'
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_test'
from django.conf import settings

settings.DATABASES['default'].setdefault('TEST', {})['NAME'] = 'test_orders_lab_h03'
import pytest

raise SystemExit(pytest.main(['-q', '-p', 'no:cacheprovider', '-c', 'pyproject.toml', *sys.argv[1:]]))
