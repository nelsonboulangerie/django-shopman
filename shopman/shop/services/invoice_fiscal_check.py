"""A NF-e de compra confere o cadastro fiscal do produto que ela abastece.

Decisão do dono (24/09/2026): "pendências que sobrarem confirmamos nas próximas
NFs". Cada nota de revenda que entra é uma declaração fiscal do fornecedor sobre
AQUELE item — NCM, CEST e se o ICMS veio por substituição tributária. Quando o
cadastro do produto discorda, a casa quer saber; e quer saber sem que a nota
mude o cadastro sozinha, porque fornecedor também erra NCM.

Por isso este módulo só **compara** e devolve divergências. Quem grava a
sugestão (NCM/CEST no rascunho de ``product_enrichment``) e quem levanta o
aviso é o recebimento do Compras (``backstage/services/purchase.py``); quem
aceita é gente, campo a campo, no Admin.

⚠️ Não depende das CHAVES dos perfis fiscais, que já foram renomeadas uma vez. "O cadastro é ST" é o perfil que emite
com CSOSN 500 (ou exige CEST); "a nota é ST" sai do CST/CSOSN do item e do valor
de ST que ele declara.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from shopman.fiscalman.classification import FISCAL_PROFILES, FiscalProfile, from_metadata

_NCM_RE = re.compile(r"^\d{8}$")
_CEST_RE = re.compile(r"^\d{7}$")

#: ST retida anteriormente: o item JÁ chegou com o imposto pago na cadeia.
#: Vale mesmo sem valor declarado — muito emissor não preenche ``vICMSSTRet``.
ST_RETAINED_CST = frozenset({"60"})
ST_RETAINED_CSOSN = frozenset({"500"})

#: ST cobrada nesta operação. O código diz que há substituição, mas só o valor
#: confirma: código de ST com valor zero é nota ambígua, e dela não se tira
#: conclusão nenhuma (nem "é ST", nem "não é").
ST_CHARGED_CST = frozenset({"10", "30", "70", "90"})
ST_CHARGED_CSOSN = frozenset({"201", "202", "203", "900"})

FIELD_NCM = "ncm"
FIELD_CEST = "cest"
FIELD_ST = "st"


@dataclass(frozen=True)
class FiscalDivergence:
    """Uma discordância entre a nota e o cadastro — nunca uma correção."""

    field: str
    catalog_value: str
    invoice_value: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "field": self.field,
            "catalogValue": self.catalog_value,
            "invoiceValue": self.invoice_value,
            "message": self.message,
        }


def invoice_has_st(*, icms_cst: str = "", icms_csosn: str = "", st_value_q: int = 0) -> bool | None:
    """A nota diz que o item veio com ICMS-ST? ``None`` quando ela não diz.

    - CST 60 / CSOSN 500: ST retida anteriormente → sim.
    - CST 10/30/70/90 ou CSOSN 201/202/203/900: sim se houver valor de ST;
      sem valor, ``None`` (código de ST sem imposto é nota ambígua).
    - Qualquer outro código declarado: não.
    - Nenhum grupo ICMS lido: ``None``.
    """
    cst = _digits(icms_cst)
    csosn = _digits(icms_csosn)
    if not cst and not csosn:
        return True if st_value_q > 0 else None
    if cst in ST_RETAINED_CST or csosn in ST_RETAINED_CSOSN:
        return True
    if st_value_q > 0:
        return True
    if cst in ST_CHARGED_CST or csosn in ST_CHARGED_CSOSN:
        return None
    return False


def catalog_has_st(profile: FiscalProfile) -> bool:
    """O perfil do cadastro emite com ST (CSOSN 500) ou exige CEST de ST."""
    return profile.csosn == "500" or bool(profile.requires_cest)


def check_invoice_fiscal(
    *,
    metadata: dict | None,
    ncm: str = "",
    cest: str = "",
    icms_cst: str = "",
    icms_csosn: str = "",
    st_value_q: int = 0,
) -> list[FiscalDivergence]:
    """Compara o que a linha da NF-e declara com ``Product.metadata['fiscal']``.

    Devolve uma lista vazia quando concordam — ou quando a nota não diz o
    bastante para discordar. Função pura: não lê banco, não grava nada.
    """
    fiscal_block = (metadata or {}).get("fiscal") or {}
    classified = bool(fiscal_block)
    classification = from_metadata(metadata)
    divergences: list[FiscalDivergence] = []

    invoice_ncm = _digits(ncm)
    catalog_ncm = _digits(classification.ncm) if classified else ""
    if _NCM_RE.match(invoice_ncm) and invoice_ncm != catalog_ncm:
        message = (
            f"NCM diverge: o cadastro diz {catalog_ncm}, a nota diz {invoice_ncm}."
            if catalog_ncm
            else f"O cadastro não tem NCM; a nota diz {invoice_ncm}."
        )
        divergences.append(FiscalDivergence(FIELD_NCM, catalog_ncm, invoice_ncm, message))

    invoice_cest = _digits(cest)
    catalog_cest = _digits(classification.cest) if classified else ""
    if _CEST_RE.match(invoice_cest) and invoice_cest != catalog_cest:
        message = (
            f"CEST diverge: o cadastro diz {catalog_cest}, a nota diz {invoice_cest}."
            if catalog_cest
            else f"O cadastro não tem CEST; a nota diz {invoice_cest}."
        )
        divergences.append(FiscalDivergence(FIELD_CEST, catalog_cest, invoice_cest, message))

    st_divergence = _st_divergence(
        classified=classified,
        profile=classification.fiscal_profile,
        invoice_st=invoice_has_st(icms_cst=icms_cst, icms_csosn=icms_csosn, st_value_q=st_value_q),
        code_label=_icms_code_label(icms_cst=icms_cst, icms_csosn=icms_csosn),
    )
    if st_divergence is not None:
        divergences.append(st_divergence)
    return divergences


def _st_divergence(
    *,
    classified: bool,
    profile: FiscalProfile | None,
    invoice_st: bool | None,
    code_label: str,
) -> FiscalDivergence | None:
    if invoice_st is None:
        return None
    if classified and profile is None:
        # Perfil com chave que o Fiscalman não conhece: a validação do cadastro
        # já grita isso; aqui não há como dizer se é ST.
        return None
    catalog_st = catalog_has_st(profile) if (classified and profile) else False
    if invoice_st == catalog_st:
        return None
    catalog_label = f"«{profile.name}»" if (classified and profile) else "sem perfil fiscal"
    code = f" ({code_label})" if code_label else ""
    if invoice_st:
        suggested = _st_profile()
        tail = f" A nota sugere o perfil «{suggested.name}»." if suggested else ""
        return FiscalDivergence(
            FIELD_ST,
            "sem ST",
            "com ST",
            f"A nota veio com ICMS-ST{code}; o cadastro está {_profile_phrase(catalog_label)}, sem ST.{tail}",
        )
    suggested = _resale_without_st_profile()
    tail = f" Confira se o perfil certo é «{suggested.name}»." if suggested else ""
    return FiscalDivergence(
        FIELD_ST,
        "com ST",
        "sem ST",
        f"A nota veio sem ICMS-ST{code}; o cadastro está {_profile_phrase(catalog_label)}, com ST.{tail}",
    )


def _profile_phrase(label: str) -> str:
    return label if label == "sem perfil fiscal" else f"no perfil {label}"


def _st_profile() -> FiscalProfile | None:
    return next((p for p in FISCAL_PROFILES.values() if catalog_has_st(p)), None)


def _resale_without_st_profile() -> FiscalProfile | None:
    """O perfil sem ST (o CEST é do produto, em qualquer perfil)."""
    return next((p for p in FISCAL_PROFILES.values() if not catalog_has_st(p)), None)


def _icms_code_label(*, icms_cst: str, icms_csosn: str) -> str:
    if _digits(icms_csosn):
        return f"CSOSN {_digits(icms_csosn)}"
    if _digits(icms_cst):
        return f"CST {_digits(icms_cst)}"
    return ""


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))
