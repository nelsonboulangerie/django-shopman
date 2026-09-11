import cProfile
import json
import pstats
import sys
from pathlib import Path
from unittest.mock import patch

root = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(root / 'docs/reports/execution/orders-20260910/http_read_lab'))
import run_http_lab

run_http_lab.setup()
from django.test import Client
from django.utils import timezone

client = Client()
for key, value in json.loads((root / '.orders-lab/http-lab-auth.json').read_text())['cookies'].items():
    client.cookies[key] = value
stamp_file = root / '.orders-lab/profile-read-stamp.txt'
if not stamp_file.exists():
    stamp_file.write_text(timezone.now().isoformat())
stamp = timezone.datetime.fromisoformat(stamp_file.read_text())
with patch('django.utils.timezone.now', return_value=stamp):
    assert client.get('/api/v1/backstage/orders/').status_code == 200
    profile = cProfile.Profile()
    response = profile.runcall(client.get, '/api/v1/backstage/orders/')
    assert response.status_code == 200
    assert response.json()['queue']['total_count'] == 500
(root / f'.orders-lab/projection-{sys.argv[1]}.json').write_text(json.dumps(response.json(), sort_keys=True))
pstats.Stats(profile).sort_stats('cumtime').print_stats(65)
