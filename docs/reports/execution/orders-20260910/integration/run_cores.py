import concurrent.futures
import os
import subprocess
import sys
from pathlib import Path

root = Path.cwd()
packages = ['refs','utils','offerman','stockman','craftsman','orderman','payman','guestman','doorman','buyman','fiscalman','cashman']
paths = [str(root/'packages'/name) for name in packages]
env = dict(os.environ, DATABASE_URL='', REDIS_URL='', PYTHONDONTWRITEBYTECODE='1')
env.pop('DJANGO_SETTINGS_MODULE', None)
code = 'import sys; sys.path[:0] = '+repr(paths)+'; import pytest; raise SystemExit(pytest.main(["-q", "-p", "no:cacheprovider"]))'
def run(name):
    path = root/'.orders-lab'/f'core-{name}.txt'
    with path.open('w') as out:
        result = subprocess.run([sys.executable, '-c', code], cwd=root/'packages'/name, env=env, stdout=out, stderr=subprocess.STDOUT)
    return name, result.returncode, path.read_text().splitlines()[-1:]
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    for result in pool.map(run, packages):
        print(result, flush=True)
