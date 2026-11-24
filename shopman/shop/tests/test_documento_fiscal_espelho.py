"""Trava: o espelho ``nfce_*`` em ``Order.data`` tem um escritor só (D-037, #3428).

A autoridade da nota é o ``fiscalman.FiscalDocument``. As chaves do espelho
(``services/fiscal_mirror.MIRROR_KEYS``) só podem ser gravadas por
``services/fiscal_mirror.py``, a partir do documento e na transação que o
gravou. Um segundo escritor faria o espelho divergir do documento em silêncio.

A varredura é por AST no código de produção (``shopman``, ``packages``,
``config``; fora testes e migrações) e pega as formas de gravar uma chave num
dicionário: ``d["k"] = …``, ``d["k"] += …``, ``del d["k"]``, ``d.update({"k": …})``,
``d.update(k=…)``, ``d.setdefault("k", …)``, ``d.pop("k")`` e ``{**d, "k": …}``.
Dicionário literal sem ``**`` (a saída de uma projeção, por exemplo) não é
gravação e fica de fora.
"""

from __future__ import annotations

import ast
from pathlib import Path

from shopman.shop.services.fiscal_mirror import MIRROR_KEYS

ROOT = Path(__file__).resolve().parents[3]
SCANNED = ("shopman", "packages", "config")
SKIP_PARTS = {"tests", "migrations", "node_modules", "__pycache__", "build", "dist"}
THE_WRITER = Path("shopman/shop/services/fiscal_mirror.py")
KEYS = frozenset(MIRROR_KEYS)
MUTATORS = {"update", "setdefault", "pop"}


def _sources():
    for top in SCANNED:
        for path in (ROOT / top).rglob("*.py"):
            rel = path.relative_to(ROOT)
            if SKIP_PARTS.intersection(rel.parts) or rel.name.startswith("test_") or rel.name == "conftest.py":
                continue
            yield rel, path


def _key(node) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in KEYS:
        return node.value
    return None


def _dict_keys(node) -> list[str]:
    if not isinstance(node, ast.Dict):
        return []
    return [key for key in (_key(k) for k in node.keys if k is not None) if key]


def _writes(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store | ast.Del):
            key = _key(node.slice)
            if key:
                yield node.lineno, key
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in MUTATORS:
            if node.func.attr == "update":
                for arg in node.args:
                    for key in _dict_keys(arg):
                        yield node.lineno, key
                for keyword in node.keywords:
                    if keyword.arg in KEYS:
                        yield node.lineno, keyword.arg
            elif node.args:
                key = _key(node.args[0])
                if key:
                    yield node.lineno, key
        elif isinstance(node, ast.Dict) and None in node.keys:
            # ``{**data, "nfce_x": …}``: um dicionário montado em cima de outro.
            for key in _dict_keys(node):
                yield node.lineno, key
        if isinstance(node, ast.BinOp | ast.AugAssign) and isinstance(node.op, ast.BitOr):
            # ``data | {"nfce_x": …}`` e ``data |= {…}``.
            right = node.right if isinstance(node, ast.BinOp) else node.value
            for key in _dict_keys(right):
                yield node.lineno, key
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "dict":
            # ``dict(data, nfce_x=…)``.
            for keyword in node.keywords:
                if keyword.arg in KEYS:
                    yield node.lineno, keyword.arg
        if isinstance(node, ast.Call):
            # ``Order.objects.filter(…).update(data={"nfce_x": …})``.
            for keyword in node.keywords:
                if keyword.arg == "data":
                    for key in _dict_keys(keyword.value):
                        yield node.lineno, key
        elif isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Attribute) and target.attr == "data" for target in node.targets
        ):
            # ``order.data = {"nfce_x": …}``: literal sem ``**`` também grava aqui.
            for key in _dict_keys(node.value):
                yield node.lineno, key


def test_so_o_fiscal_mirror_grava_as_chaves_do_espelho():
    offenders = []
    scanned = 0
    for rel, path in _sources():
        scanned += 1
        if rel == THE_WRITER:
            continue
        found = _writes(ast.parse(path.read_text(encoding="utf-8"), filename=str(rel)))
        offenders.extend(f"{rel}:{line} grava {key}" for line, key in found)

    # A varredura andou de verdade: uma raiz errada daria verde sem ler nada.
    assert scanned > 1000
    assert not offenders, (
        "Só shopman/shop/services/fiscal_mirror.py grava o espelho da nota em Order.data "
        "(D-037, #3428). Grave o FiscalDocument pelo shopman.fiscalman.services e chame "
        "fiscal_mirror.write na mesma transação:\n" + "\n".join(offenders)
    )


def test_a_varredura_pega_cada_forma_de_gravar():
    sample = ast.parse(
        "\n".join([
            'data["nfce_access_key"] = 1',
            'data["nfce_number"] += 1',
            'del data["nfce_series"]',
            'data.update({"nfce_protocol": 1})',
            "data.update(nfce_status=1)",
            'data.setdefault("nfce_cancelled", True)',
            'data.pop("nfce_danfe_url")',
            'merged = {**data, "nfce_xml_url": 1}',
            'merged = data | {"nfce_authorized_at": 1}',
            'data |= {"nfce_cancellation_protocol": 1}',
            "merged = dict(data, nfce_qrcode_url=1)",
            'Order.objects.filter(pk=1).update(data={"nfce_access_key": 1})',
            'order.data = {"nfce_protocol": 1}',
            'projection = {"nfce_qrcode_url": 1}',  # saída de projeção: não é gravação
            'data["nfce_email_sent_at"] = 1',  # não é chave do espelho
        ])
    )

    assert sorted(key for _, key in _writes(sample)) == sorted([
        "nfce_access_key", "nfce_number", "nfce_series", "nfce_protocol",
        "nfce_status", "nfce_cancelled", "nfce_danfe_url", "nfce_xml_url",
        "nfce_authorized_at", "nfce_cancellation_protocol", "nfce_qrcode_url",
        "nfce_access_key", "nfce_protocol",
    ])
