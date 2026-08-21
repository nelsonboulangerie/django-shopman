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


def mask_badge(token: str, *, keep: int = 4) -> str:
    """As pontas do token, para reconhecer sem revelar: ``14c0…f058``.

    Um lugar só, porque o mesmo par de pontas precisa aparecer em três telas
    diferentes — a folha do crachá, o `--doctor` do agente do balcão e o
    terminal no Admin. Máscaras diferentes em cada lugar não dariam para
    comparar, que é justamente para o que elas servem.

    Token curto demais para mascarar sai inteiro: esconder 4 de 6 caracteres não
    protege nada e ainda tira a única utilidade da máscara, que é comparar.
    """
    token = (token or "").strip()
    if len(token) <= keep * 2:
        return token
    return f"{token[:keep]}…{token[-keep:]}"


@dataclass(frozen=True)
class OperatorBadge:
    """Um crachá pronto para imprimir."""

    operator_name: str
    operator_username: str
    #: O token MASCARADO, que é o que a folha mostra: ``14c0…f058``.
    #:
    #: A versão anterior imprimia o token inteiro embaixo do código de barras,
    #: para alguém digitar se o leitor falhasse. O crachá vive pendurado no
    #: pescoço, à vista do balcão inteiro — e um número legível ali é um crachá
    #: que qualquer um copia num papel e reproduz depois, sem nunca tocar no
    #: original. As pontas bastam para o que a impressão precisa de verdade:
    #: reconhecer que este é o crachá certo, e que foi reemitido.
    #:
    #: ⚠️ Digitar deixou de ser saída, e é decisão: o token só entra pelo leitor.
    #: Se o leitor falhar, o caminho é o PIN, que já existe e não fica à vista.
    token_masked: str
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
    """Monta o crachá imprimível para ``token``.

    O token completo entra (o código de barras precisa dele inteiro) e sai
    mascarado: o que vai para a folha em texto são só as pontas.
    """
    return OperatorBadge(
        operator_name=operator_name.strip() or operator_username,
        operator_username=operator_username,
        token_masked=mask_badge(token),
        barcode_svg=code128_svg(token, module_mm=module_mm, height_mm=height_mm),
        width_mm=round(code128_width_mm(token, module_mm=module_mm), 1),
        height_mm=height_mm,
    )
