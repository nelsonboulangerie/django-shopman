"""Projeção das páginas legais — o que a loja AFIRMA ao cliente, saindo de onde é verdade.

A política de privacidade listava os operadores em prosa, dentro do `.vue`. Em
23/09/2026 cinco terceiros já recebiam dado de cliente sem estar naquela lista, e a
página continuava dizendo "é a lista inteira". Ninguém errou de propósito: a lista era
uma cópia, e cópia não sabe que a verdade mudou.

Aqui ela deixa de ser cópia. A fonte é `shopman.shop.privacy_inventory`, o mesmo lugar
que a trava de `test_privacy_inventory.py` obriga a estar completo — então o caminho
para um operador novo chegar à tela passa a ser o mesmo caminho que o faz existir.

⚠️ A **data** também sai daqui, e pelo mesmo motivo: ela estava cravada no `.vue` e a
página prometia que mudaria junto com o texto. Não mudou — o `terms.vue` foi editado em
28/08 e em 22/09 e a data continuava em 20/08. Prometer o que o código não faz é a
forma mais cara de mentir, porque parece cuidado.
"""

from __future__ import annotations

from dataclasses import dataclass

from shopman.shop.privacy_inventory import Processor, active_processors


@dataclass(frozen=True)
class ProcessorProjection:
    name: str
    role: str
    shares: str


@dataclass(frozen=True)
class LegalProjection:
    #: Versão do documento. Muda quando o texto muda — é o que a trava cobra.
    version: str
    #: A data que o cliente lê, derivada da versão.
    updated_at: str
    processors: tuple[ProcessorProjection, ...]


#: A versão vigente dos documentos legais. **Mexeu no texto de `privacy.vue` ou de
#: `terms.vue`? Mexa aqui.** `surfaces/storefront-nuxt/tests/legalVersion.test.ts`
#: reprova se um mudar sem o outro — foi a promessa quebrada que originou a trava.
LEGAL_VERSION = "2026-09-24"
LEGAL_UPDATED_AT = "24 de setembro de 2026"


def _project(processor: Processor) -> ProcessorProjection:
    return ProcessorProjection(name=processor.name, role=processor.role, shares=processor.shares)


def build_legal() -> LegalProjection:
    return LegalProjection(
        version=LEGAL_VERSION,
        updated_at=LEGAL_UPDATED_AT,
        processors=tuple(_project(processor) for processor in active_processors()),
    )
