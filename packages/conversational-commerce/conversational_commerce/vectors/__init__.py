"""Vetores de conformidade dos contratos: documentos com o resultado esperado.

``terms.json``: termos, com a forma canônica e o hash que cada um tem que dar.
``grants.json``: concessões presas a esses termos. Positivos e negativos; um
leitor de outra linguagem passa nestes vetores ou não lê o mesmo contrato.
Formato e regras: ``spec/01-contracts.md``, seção "Vetores".
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any


def load(name: str) -> dict[str, Any]:
    """Lê ``<name>.json`` deste diretório (funciona da árvore e do wheel)."""
    text = resources.files(__name__).joinpath(f"{name}.json").read_text(encoding="utf-8")
    return json.loads(text)
