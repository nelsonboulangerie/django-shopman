"""Assina arquivos do candidato contra a base auditada, sem acessar ambiente externo."""
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

root = Path.cwd()
base = "1138c95eee0862630330328cf3bfe2f0b6424796"
output = Path("evidence/conversational/manifest.json")

def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()

paths = set(git("diff", "--name-only", base).splitlines())
paths.update(git("ls-files", "--others", "--exclude-standard").splitlines())
entries = []
for name in sorted(paths):
    path = root / name
    if name == str(output) or not path.is_file() or path.is_symlink() or "__pycache__" in path.parts:
        continue
    content = path.read_bytes()
    entries.append({"path": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
manifest = {"generated_at": datetime.now(UTC).isoformat(), "base_sha": base, "candidate_head": git("rev-parse", "HEAD"), "branch": git("branch", "--show-current"), "worktree": str(root), "dirty": bool(git("status", "--porcelain")), "files": entries}
output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n")
print(json.dumps({"manifest": str(output), "candidate_head": manifest["candidate_head"], "files": len(entries), "dirty": manifest["dirty"]}))
