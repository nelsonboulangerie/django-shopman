"""Budgets never follow test exit status or silently drop slow samples."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[5] / '.orders-lab'
backend = json.loads((root / 'process-read-result.json').read_text())
browser = json.loads((root / 'browser-read-500.json').read_text())
assert backend['samples_per_configuration'] == 60
assert [(r['processes'], r['clients']) for r in backend['results']] == [(1, 1), (1, 2), (1, 10)]
assert len(browser['samples']) == 20
verdict = {'backend_limit_ms': 500, 'browser_limit_ms': 1500,
           'backend_p95_ms': [r['backend_ms']['p95'] for r in backend['results']],
           'browser_p95_ms': browser['p95_ms'],
           'scope': 'Ephemeral CI with application CPU/memory ceilings; no store PC/network or managed DB equivalence.'}
verdict['pass'] = all(v <= 500 for v in verdict['backend_p95_ms']) and verdict['browser_p95_ms'] <= 1500
(root / 'capacity-verdict.json').write_text(json.dumps(verdict, indent=2) + '\n')
print(json.dumps(verdict))
assert verdict['pass'], 'Original capacity budgets not met; publication gate remains pending'
