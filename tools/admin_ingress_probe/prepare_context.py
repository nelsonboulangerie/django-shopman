"""Copy exactly five reviewed files, never a repository-wide Docker context."""
import hashlib
import json
import shutil
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
target = Path(sys.argv[1])
target.mkdir(parents=True, exist_ok=False)
files = {
    "Dockerfile": "tools/admin_ingress_probe/Dockerfile",
    ".dockerignore": "tools/admin_ingress_probe/.dockerignore",
    "requirements.txt": "tools/admin_ingress_probe/requirements.txt",
    "server.py": "tools/admin_ingress_probe/server.py",
    "observer_middleware.py": "shopman/backstage/services/admin_ip_probe.py",
}
manifest = {}
for name, source in files.items():
    shutil.copyfile(root / source, target / name)
    manifest[name] = hashlib.sha256((target / name).read_bytes()).hexdigest()
assert {p.name for p in target.iterdir()} == set(files)
print(json.dumps(manifest, sort_keys=True, indent=2))
