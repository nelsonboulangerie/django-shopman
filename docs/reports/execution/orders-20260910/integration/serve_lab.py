from pathlib import Path
import os,sys
root = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(root),str(root/'.orders-lab'),*[str(p) for p in sorted((root/'packages').iterdir()) if p.is_dir()]]
assert os.environ['DATABASE_URL'] == 'postgres://orders_lab@127.0.0.1:55439/orders_lab'
assert os.environ['REDIS_URL'] == 'redis://127.0.0.1:56389/0'
os.environ['DJANGO_SETTINGS_MODULE']='settings_orders_lab'
from daphne.cli import CommandLineInterface
CommandLineInterface().run(['-b','127.0.0.1','-p','8014','config.asgi:application'])
