"""A trava de numeração de migração — a colisão silenciosa vira veredito.

Cobre a checagem ``migrations.prefix_collisions`` de ``scripts/check_migrations.py``:

- duplicata de prefixo **herdada** (a dívida nomeada em
  :data:`LEGACY_PREFIX_COLLISIONS`) passa, e reprova sob ``SHOPMAN_MIGRATION_PREFIX_STRICT``;
- duplicata **nova** reprova;
- dois números de PONTA iguais sem merge reprovam, que é o caso que produz
  ``multiple leaf nodes in the migration graph``;
- o grafo real do repositório não tem nenhum dos dois.

O script vive fora da árvore do pacote, então o módulo é carregado por caminho
(mesmo padrão de ``test_adr015_gate.py``).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_migrations.py"
_spec = importlib.util.spec_from_file_location("check_migrations_gate", _SCRIPT)
check_migrations = importlib.util.module_from_spec(_spec)
# O módulo usa @dataclass, e a resolução de tipos do dataclasses consulta
# sys.modules pelo __module__ da classe: sem o registro antes do exec_module, a
# coleta explode com AttributeError em sys.modules.get(...).__dict__.
sys.modules[_spec.name] = check_migrations
_spec.loader.exec_module(check_migrations)


class _Graph:
    """Grafo no formato que o Django expõe: nós ``(app, nome)`` e folhas."""

    def __init__(self, nodes, leaves):
        self.nodes = dict.fromkeys(nodes, SimpleNamespace())
        self._leaves = tuple(leaves)

    def leaf_nodes(self):
        return list(self._leaves)


def _verdict(nodes, leaves, *, strict=None):
    return check_migrations.migration_prefix_check(_Graph(nodes, leaves), strict=strict)


# ---------------------------------------------------------------------------
# Grafo limpo
# ---------------------------------------------------------------------------


def test_sem_duplicata_passa():
    nodes = [("shop", "0001_initial"), ("shop", "0002_pedido")]
    resultado = _verdict(nodes, leaves=[("shop", "0002_pedido")])
    assert resultado.status == "passed"
    assert resultado.failed is False


# ---------------------------------------------------------------------------
# Colisão nova reprova
# ---------------------------------------------------------------------------


def test_colisao_nova_reprova():
    nodes = [("shop", "0001_initial"), ("shop", "0002_a"), ("shop", "0002_b")]
    resultado = _verdict(nodes, leaves=[("shop", "0002_a"), ("shop", "0002_b")])
    assert resultado.status == "failed"
    assert resultado.details["new_count"] == 1
    assert resultado.details["legacy_count"] == 0


def test_colisao_nova_reprova_mesmo_com_o_grafo_resolvido():
    """Dois '0002' em cadeia (um depende do outro) não deixam folha ambígua.

    Ainda assim o número repetido engana quem procura o próximo livre, então
    reprova — é a dívida que a trava não quer receber de novo.
    """
    nodes = [("shop", "0001_initial"), ("shop", "0002_a"), ("shop", "0002_b")]
    resultado = _verdict(nodes, leaves=[("shop", "0002_b")])
    assert resultado.status == "failed"
    assert resultado.details["ambiguous_leaf_count"] == 0
    assert resultado.details["new_count"] == 1


# ---------------------------------------------------------------------------
# Folha ambígua reprova com a mensagem que diz o que fazer
# ---------------------------------------------------------------------------


def test_folha_ambigua_reprova_com_instrucao_de_merge():
    nodes = [("shop", "0097_base"), ("shop", "0098_a"), ("shop", "0098_b")]
    resultado = _verdict(nodes, leaves=[("shop", "0098_a"), ("shop", "0098_b")])
    assert resultado.status == "failed"
    assert resultado.details["ambiguous_leaf_count"] == 1
    assert "makemigrations --merge" in resultado.message


def test_merge_reconcilia_e_nao_deixa_folha_ambigua():
    nodes = [
        ("shop", "0098_a"),
        ("shop", "0098_b"),
        ("shop", "0099_merge"),
    ]
    resultado = _verdict(nodes, leaves=[("shop", "0099_merge")], strict=True)
    # O prefixo 0099 não está no baseline herdado: reprova como colisão nova.
    assert resultado.status == "failed"
    assert resultado.details["new_count"] == 1
    assert resultado.details["ambiguous_leaf_count"] == 0


# ---------------------------------------------------------------------------
# A dívida herdada é nomeada, não varrida para baixo do tapete
# ---------------------------------------------------------------------------


def test_divida_herdada_passa_e_e_contada():
    """Prefixo herdado repetido, já reconciliado por um merge, segue verde.

    A dívida é de NOMENCLATURA: as duas cadeias existem, mas uma migração de
    merge as reconciliou, então há uma única folha e nada fica ambíguo.
    """
    nodes = [("shop", "0023_a"), ("shop", "0023_b"), ("shop", "0024_merge_x")]
    resultado = _verdict(nodes, leaves=[("shop", "0024_merge_x")], strict=False)
    assert resultado.status == "passed"
    assert resultado.details["legacy_count"] == 1
    assert resultado.details["ambiguous_leaf_count"] == 0
    assert resultado.details["legacy_note"]


def test_divida_herdada_nao_perdoa_folha_ambigua():
    """Herança não é salvo-conduto: duas folhas com o mesmo número reprovam."""
    nodes = [("shop", "0023_a"), ("shop", "0023_b")]
    resultado = _verdict(nodes, leaves=[("shop", "0023_a"), ("shop", "0023_b")], strict=False)
    assert resultado.status == "failed"
    assert resultado.details["ambiguous_leaf_count"] == 1
    assert resultado.details["legacy_count"] == 1


def test_divida_herdada_reprova_no_modo_estrito():
    nodes = [("shop", "0023_a"), ("shop", "0023_b"), ("shop", "0024_merge_x")]
    resultado = _verdict(nodes, leaves=[("shop", "0024_merge_x")], strict=True)
    assert resultado.status == "failed"
    assert "STRICT" in resultado.message


def test_modo_estrito_le_o_ambiente(monkeypatch):
    nodes = [("shop", "0023_a"), ("shop", "0023_b")]
    monkeypatch.setenv("SHOPMAN_MIGRATION_PREFIX_STRICT", "1")
    resultado = check_migrations.migration_prefix_check(_Graph(nodes, [("shop", "0023_a")]), strict=None)
    assert resultado.status == "failed"


def test_app_do_baseline_nao_vaza_para_outro_app():
    """O baseline é por (app, prefixo): '0023' de backstage não é o de shop."""
    nodes = [("backstage", "0023_a"), ("backstage", "0023_b")]
    resultado = _verdict(nodes, leaves=[("backstage", "0023_a")])
    assert resultado.status == "failed"
    assert resultado.details["new_count"] == 1


# ---------------------------------------------------------------------------
# O grafo real do repositório
# ---------------------------------------------------------------------------


def test_grafo_real_nao_tem_colisao_nova_nem_folha_ambigua():
    """O veredito que o CI vai dar: verde, com a dívida herdada nomeada."""
    from django.db.migrations.loader import MigrationLoader

    graph = MigrationLoader(None, ignore_no_migrations=True).graph
    resultado = check_migrations.migration_prefix_check(graph, strict=False)
    assert resultado.status == "passed", resultado.message
    assert resultado.details["new_count"] == 0
    assert resultado.details["ambiguous_leaf_count"] == 0
    # A dívida existe e está declarada: se alguém renumerar, este número cai e
    # o baseline do script precisa encolher junto.
    assert resultado.details["legacy_count"] > 0


def test_baseline_herdado_bate_com_as_duplicatas_do_repositorio():
    """Guarda contra apodrecimento: baseline que não corresponde mais mente.

    Se alguém renumerar as migrações antigas, o prefixo sai do repositório mas
    continua no baseline, e a trava passaria a perdoar uma colisão nova naquele
    número. Este teste reprova nesse caso, e manda encolher o baseline.
    """
    repo_root = _SCRIPT.parents[1]
    apps = {
        "shop": "shopman/shop/migrations",
        "backstage": "shopman/backstage/migrations",
    }
    for app, relative in apps.items():
        listing = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "HEAD", f"{relative}/"],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if listing.returncode != 0:
            continue  # árvore sem git: o teste do grafo real já cobre o essencial
        prefixes: dict[str, int] = {}
        for line in listing.stdout.splitlines():
            name = line.rsplit("/", 1)[-1]
            if not name[:4].isdigit():
                continue
            prefixes[name.split("_", 1)[0]] = prefixes.get(name.split("_", 1)[0], 0) + 1
        duplicados = {prefix for prefix, count in prefixes.items() if count > 1}
        baseline = {prefix for baseline_app, prefix in check_migrations.LEGACY_PREFIX_COLLISIONS if baseline_app == app}
        assert duplicados == baseline, (
            f"{app}: duplicatas no repositório {sorted(duplicados)} != baseline {sorted(baseline)}. "
            "Encolha LEGACY_PREFIX_COLLISIONS para casar."
        )
