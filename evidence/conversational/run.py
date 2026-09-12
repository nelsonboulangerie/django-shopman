import os
import sys
from pathlib import Path

root=Path.cwd()
sys.path[:0]=[str(root),*[str(p) for p in sorted((root/'packages').iterdir()) if p.is_dir()]]
os.environ['DJANGO_SETTINGS_MODULE']='config.settings_test'
os.environ.setdefault('DATABASE_URL','')
os.environ.setdefault('REDIS_URL','')
os.environ['AI_ASSIST_API_KEY']=''
os.environ['SHOPMAN_CONCIERGE_ENABLED']='false'
import shopman.guestman
import shopman.orderman

print('AUDIT_IMPORTS',list(shopman.orderman.__path__),list(shopman.guestman.__path__))
import pytest

raise SystemExit(pytest.main(['-q','-p','no:cacheprovider','-c',str(root/'pyproject.toml'),*sys.argv[1:]]))
