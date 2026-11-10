"""
LabelAttributesProvider protocol.

Os campos de rótulo que o TENANT define (alérgenos, dieta, porções) são
vocabulário do orquestrador. O formulário de rótulo do Offerman lê e escreve
esses campos pelo provedor apontado em ``OFFERMAN["LABEL_ATTRIBUTES_PROVIDER"]``
(uma fábrica sem argumentos que devolve um objeto deste contrato). Sem
provedor, sem campo: o pacote segue de pé sozinho.
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LabelAttributesProvider(Protocol):
    """Lê e grava um atributo de rótulo de um produto, pelo ``ref`` do tenant."""

    def get(self, product: Any, ref: str) -> Any:
        """Return the attribute value, or ``None`` when the product has none."""
        ...

    def set(self, product: Any, ref: str, value: Any) -> None:
        """Write the value without saving the product; raise ``ValueError`` if invalid."""
        ...
