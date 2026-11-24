"""Trava X16 (OC-14): a Nice usa as regras comerciais PÚBLICAS do orquestrador.

Regra comercial (data de encomenda, janela, validade da reserva, forma de
pagamento assumida, linha fixa do pedido) mora em ``shopman/shop/services/``,
numa função pública. A Concierge (``storefront/concierge/``) e a porta de
leitura da conversa (``shop/conversational/``) chamam essa função; importar o
``_privado`` de um serviço é manter uma segunda autoridade em potencial, que
deriva em silêncio quando o serviço muda por dentro.

A leitura é por AST (não por regex de linha), e pega as duas formas:
``from <serviço> import _x`` e ``<módulo de serviço>._x``.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

#: Quem não pode ter regra comercial própria.
SUBJECT_ROOTS = (
    REPO_ROOT / "shopman" / "storefront" / "concierge",
    REPO_ROOT / "shopman" / "shop" / "conversational",
)

#: Onde a regra mora (serviços e políticas do orquestrador). Símbolo privado daqui não sai daqui.
PROTECTED_PREFIXES = (
    "shopman.shop.policies",
    "shopman.shop.services",
    "shopman.storefront.services",
)


def _protected(module: str) -> bool:
    return any(module == prefix or module.startswith(prefix + ".") for prefix in PROTECTED_PREFIXES)


def _private(name: str) -> bool:
    return name.startswith("_") and not name.startswith("__")


def private_rule_imports(source: str, filename: str = "<src>") -> list[str]:
    """Cada uso de símbolo privado de um serviço protegido, como ``arquivo:linha: símbolo``."""
    tree = ast.parse(source, filename=filename)
    found: list[str] = []
    modules: dict[str, str] = {}  # nome local → módulo de serviço protegido
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for alias in node.names:
                if _protected(node.module) and _private(alias.name):
                    found.append(f"{filename}:{node.lineno}: from {node.module} import {alias.name}")
                    continue
                qualified = f"{node.module}.{alias.name}"
                if _protected(qualified):
                    modules[alias.asname or alias.name] = qualified
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if _protected(alias.name):
                    modules[alias.asname or alias.name.split(".")[0]] = alias.name
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and _private(node.attr)
            and isinstance(node.value, ast.Name)
            and node.value.id in modules
        ):
            found.append(f"{filename}:{node.lineno}: {modules[node.value.id]}.{node.attr}")
    return found


def test_concierge_and_conversation_port_use_only_public_rules():
    offenders: list[str] = []
    for root in SUBJECT_ROOTS:
        for path in sorted(root.rglob("*.py")):
            offenders += private_rule_imports(path.read_text(encoding="utf-8"), str(path.relative_to(REPO_ROOT)))
    assert offenders == [], (
        "Regra comercial importada por símbolo privado; exponha uma função pública no serviço dono "
        "(shopman/shop/services/) e chame-a:\n" + "\n".join(offenders)
    )


def test_the_lock_catches_both_forms_of_private_access():
    """A trava não é decorativa: as duas formas de importar o privado reprovam; a pública passa."""
    from_import = "from shopman.shop.services.fulfillment_window import _secret\n"
    module_attr = (
        "def f():\n"
        "    from shopman.shop.services import availability\n"
        "    return availability._secret('x')\n"
    )
    storefront = "import shopman.storefront.services.pickup_slots as slots\nslots._secret()\n"
    public = "from shopman.shop.services.fulfillment_window import slot_start, hour_pair\n"

    assert private_rule_imports(from_import) == [
        "<src>:1: from shopman.shop.services.fulfillment_window import _secret"
    ]
    assert private_rule_imports(module_attr) == ["<src>:3: shopman.shop.services.availability._secret"]
    assert private_rule_imports(storefront) == ["<src>:2: shopman.storefront.services.pickup_slots._secret"]
    assert private_rule_imports(public) == []
