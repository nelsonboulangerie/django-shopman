"""Equivalência de release do Shopman para a sonda ``release_identity`` do Watchman.

O deploy é SELETIVO (``scripts/deploy_components.py``): um push que só mexe no
Django não reconstrói ``operator-floor``, e o grupo segue servindo o commit em
que foi construído por último. Comparar o commit vivo com o topo do ``main``
por igualdade acusaria atraso em todo componente que, corretamente, não mudou.

A pergunta honesta é a mesma do confronto com o registry
(``scripts/check_registry_drift.py``): **entre o commit vivo e o esperado, algum
arquivo que entra NESTE componente mudou?** A tabela de caminhos é a do
``deploy_components.py``, a mesma que decide o que construir; não há segunda
cópia aqui.

Precisa do histórico do git. Onde ele não existe (o contêiner de produção, um
checkout raso), a resposta é ``None`` e a sonda diz ``unknown``: ausência de
prova não vira prova.
"""

from __future__ import annotations

import importlib.util
import subprocess
from functools import cache
from pathlib import Path
from types import ModuleType

from django.conf import settings

ROOT = Path(settings.BASE_DIR)
DEPLOY_COMPONENTS = ROOT / "scripts" / "deploy_components.py"


@cache
def _deploy_components() -> ModuleType | None:
    if not DEPLOY_COMPONENTS.is_file():
        return None
    spec = importlib.util.spec_from_file_location("shopman_deploy_components", DEPLOY_COMPONENTS)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _has_commit(sha: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
            cwd=ROOT, capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def component_unchanged_since(target_id: str, live_sha: str, expected_sha: str) -> bool | None:
    """O commit vivo já serve tudo o que o esperado pede deste componente?

    ``True``: o vivo é ancestral do esperado e nada que entra no componente mudou
    entre os dois. ``False``: mudou, ou o vivo nem é ancestral (outro ramo,
    histórico reescrito). ``None``: não dá para saber aqui.
    """

    module = _deploy_components()
    if module is None or not _has_commit(live_sha) or not _has_commit(expected_sha):
        return None
    paths = module.component_paths(module.load_groups()).get(target_id)
    if paths is None:
        return None
    if not module.is_ancestor(live_sha, expected_sha, ROOT):
        return False
    try:
        changed = module.changed_files(live_sha, expected_sha, ROOT)
    except RuntimeError:
        return None
    return not any(module.touches(path, paths) for path in changed)
