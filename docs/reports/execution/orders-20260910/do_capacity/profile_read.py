"""Read-only CPU diagnosis on the existing synthetic fixture, no frozen-time mock."""
import cProfile
import json
import os
import pstats
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[5]
assert os.environ.get('ORDERS_ISOLATED_CAPACITY') == '1'
sys.path.insert(0, str(root / 'docs/reports/execution/orders-20260910/http_read_lab'))
import run_http_lab  # noqa: E402

run_http_lab.setup()
from django.test import Client  # noqa: E402

client = Client()
for key, value in json.loads((root / '.orders-lab/http-lab-auth.json').read_text())['cookies'].items():
    client.cookies[key] = value
assert client.get('/api/v1/backstage/orders/').status_code == 200
profile = cProfile.Profile()
response = profile.runcall(client.get, '/api/v1/backstage/orders/')
assert response.status_code == 200 and response.json()['queue']['total_count'] == 500
pstats.Stats(profile).strip_dirs().sort_stats('cumtime').print_stats(120)
pstats.Stats(profile).strip_dirs().sort_stats('tottime').print_stats(60)
