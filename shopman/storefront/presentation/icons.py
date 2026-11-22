"""O ícone de uma coleção na loja: o do cadastro.

Cada coleção guarda o próprio ícone em ``metadata.icon`` (nome Lucide, sem o prefixo
``lucide:``), o mesmo que veste o card de produto sem foto (``category_icon``). A loja
não adivinha ícone pelo ``ref``: sem ícone no cadastro, devolve ``""`` e a tela usa o
padrão dela (#3253).
"""

from __future__ import annotations

from typing import Any


def collection_icon(collection: Any) -> str:
    """Nome Lucide do ícone do cadastro da coleção, ou ``""`` quando não há."""
    metadata = getattr(collection, "metadata", None)
    if not isinstance(metadata, dict):
        return ""
    return str(metadata.get("icon") or "").strip()
