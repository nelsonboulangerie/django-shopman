"""Read-only comparative source922fb522c, same synthetic DB and middleware."""
import os,sys,subprocess
from pathlib import Path
root=Path.cwd(); assert root.name=='django-shopman-orders-execution-20260910'
base=root.parent/'django-shopman-orders-validation-922fb522c'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=base,text=True).strip()=='922fb522c452da438c85db4d94b82075a64963ad'
sys.path[:0]=[str(base),*[str(p) for p in sorted((base/'packages').iterdir()) if p.is_dir()],str(root/'docs/reports/execution/orders-20260910/http_read_lab')]
os.environ.update(DATABASE_CONN_MAX_AGE='0',DATABASE_URL='postgres://orders_lab@127.0.0.1:55439/orders_perf_lab',REDIS_URL='redis://127.0.0.1:56389/2',DJANGO_SETTINGS_MODULE='http_lab_settings',SENTRY_DSN='')
port=int(sys.argv[1]); assert port in range(8016,8021)
from daphne.cli import CommandLineInterface
CommandLineInterface().run(['-b','127.0.0.1','-p',str(port),'--access-log','/dev/null','config.asgi:application'])
