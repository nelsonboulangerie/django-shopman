"""Projection do crachá do operador — o que a folha de impressão mostra.

O crachá é uma credencial de POSSE: o token é sorteado, guardado só como digest
(`PinCredential.badge_hash`) e mostrado **uma vez**. Esta projection é a única vez em
que ele existe em texto, no caminho entre "emitir" e "imprimir" — depois disso nem o
gerente consegue recuperá-lo, só emitir outro (o que invalida o anterior).

Por isso a projection recebe o token de fora em vez de buscá-lo: não há de onde buscar.
"""

from __future__ import annotations

from dataclasses import dataclass

from shopman.backstage.presentation.barcode import (
    DEFAULT_MODULE_MM,
    code128_svg,
    code128_width_mm,
)


@dataclass(frozen=True)
class OperatorBadge:
    """Um crachá pronto para imprimir."""

    operator_name: str
    operator_username: str
    #: O token em texto. Aparece na folha por baixo do código de barras para o caso de o
    #: leitor falhar e alguém precisar digitar — e some junto com a folha.
    token: str
    barcode_svg: str
    #: Largura física do símbolo, com zona muda. É o número que decide se cabe na
    #: etiqueta que a padaria comprou, então aparece na tela em vez de ficar implícito.
    width_mm: float
    height_mm: float


def build_operator_badge(
    *,
    operator_name: str,
    operator_username: str,
    token: str,
    module_mm: float = DEFAULT_MODULE_MM,
    height_mm: float = 15.0,
) -> OperatorBadge:
    """Monta o crachá imprimível para ``token``."""
    return OperatorBadge(
        operator_name=operator_name.strip() or operator_username,
        operator_username=operator_username,
        token=token,
        barcode_svg=code128_svg(token, module_mm=module_mm, height_mm=height_mm),
        width_mm=round(code128_width_mm(token, module_mm=module_mm), 1),
        height_mm=height_mm,
    )
