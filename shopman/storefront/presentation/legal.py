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


#: Cópias permanentes das versões publicadas: versão → SHA-256 de cada arquivo em
#: `surfaces/storefront-nuxt/public/legal/<privacy|terms>/<versão>.html`.
#:
#: A página viva muda; o pedido precisa continuar apontando para o texto que valia
#: quando foi feito. Por isso cada versão vira um ARQUIVO NOVO, que nunca é reescrito
#: (`scripts/check_legal_archive.py` reprova alteração ou remoção no CI), e o
#: checkout grava no pedido a versão, a URL e o hash (`order_legal_snapshot`).
#:
#: ⚠️ Arquivar vem DEPOIS do deploy, e não junto da troca de texto: a lista de
#: operadores sai da configuração do ambiente (`privacy_inventory`), então só a
#: página publicada mostra o que o cliente leu. Trocou `LEGAL_VERSION`? Depois que o
#: deploy subir, rode `python scripts/archive_legal_version.py` e cole aqui a linha
#: que ele imprime. Até lá, o pedido grava versão e URL, sem hash, e diz
#: `archived: False` — é lacuna declarada, não prova inventada.
LEGAL_ARCHIVE: dict[str, dict[str, str]] = {
    "2026-09-24": {
        "privacy": "cdfdde12a9817d1941f5bece934b1d4abfb6d5e337653567ad202a176c9815aa",
        "terms": "f3dbb90e983fe586bb4022345837a448a86016230eec0bd9ad157d329f2da778",
    },
}

LEGAL_ARCHIVE_KINDS = ("privacy", "terms")


def legal_archive_path(kind: str, version: str) -> str:
    """URL pública (relativa à loja) da cópia permanente de uma versão."""
    if kind not in LEGAL_ARCHIVE_KINDS:
        raise ValueError(f"documento legal desconhecido: {kind!r}")
    return f"/legal/{kind}/{version}.html"


def order_legal_snapshot(version: str = LEGAL_VERSION) -> dict:
    """O que o pedido guarda sobre os documentos que valiam no momento do checkout.

    Vai para `Session.data["legal"]` e, pelo commit, para `Order.snapshot["data"]`
    — a parte selada do pedido, que não muda depois. Versão e URL sempre; o SHA-256
    só quando a versão já foi arquivada (ver `LEGAL_ARCHIVE`).
    """
    hashes = LEGAL_ARCHIVE.get(version)
    snapshot: dict = {"version": version, "archived": hashes is not None}
    for kind in LEGAL_ARCHIVE_KINDS:
        snapshot[f"{kind}_url"] = legal_archive_path(kind, version)
        if hashes is not None:
            snapshot[f"{kind}_sha256"] = hashes[kind]
    return snapshot


def _project(processor: Processor) -> ProcessorProjection:
    return ProcessorProjection(name=processor.name, role=processor.role, shares=processor.shares)


def build_legal() -> LegalProjection:
    return LegalProjection(
        version=LEGAL_VERSION,
        updated_at=LEGAL_UPDATED_AT,
        processors=tuple(_project(processor) for processor in active_processors()),
    )
