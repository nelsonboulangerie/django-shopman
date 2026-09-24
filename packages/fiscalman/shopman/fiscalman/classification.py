"""Fiscal classification for sellable products — Brazilian NFC-e / NF-e.

Single source of truth for the schema of ``Product.metadata["fiscal"]`` and the
suite's named fiscal profiles. Dataclass-driven: the dataclasses below give
Python typing, drive the admin form (one field per concept, no raw JSON), and
validate fiscal invariants. **No new Core columns** — fiscal data lives in the
product's JSONField; Offerman stores the blob, Fiscalman owns the schema.

Design (decisions locked with the owner, 2026-06-28):

- Regime: **Simples Nacional**. Document: **NFC-e (model 65)** intrastate; NF-e
  (model 55) interstate is future scope.
- Two named profiles instead of copying CFOP/CSOSN into every product. The
  profile answers ONE question — **tributação: ST ou não** (parametrização do
  contador, SEFA-PR):
    * ``standard`` — sem ST: o que a casa faz e a revenda fora do Anexo IX do
      RICMS/PR (pães, doces, bebidas preparadas, queijo, manteiga, azeite,
      geleia, chá em folhas). CSOSN 102, **CFOP 5102/6102**.
    * ``tax_substitution`` — com ST (refrigerante, água, mostarda preparada,
      requeijão e similares). CSOSN 500, CFOP 5405/6405, e o CEST é obrigatório.
- **O CEST é atributo do produto, não do perfil.** Ele identifica a mercadoria
  no catálogo de segmentos do Conv. ICMS 142/2018 — não define tributação — e
  a lei manda informá-lo sempre que o item estiver listado, "ainda que a
  operação não esteja sujeita ao regime de ST" (cl. 20ª, I; cl. 3ª para o
  Simples; RICMS/PR, Anexo X, art. 1º). Então: aceito em qualquer perfil,
  enviado na NFC-e sempre que presente, obrigatório só com ST, e conferido
  contra o NCM pela tabela do Anexo como **aviso** (:mod:`.cest_table`).
- A product carries only what *varies per product*: ``profile`` + ``ncm`` +
  ``cest`` + ``origin`` + ``unit``. The profile supplies CFOP/CSOSN and
  PIS/COFINS CST. **A origem é do produto** (tabela de origem da mercadoria,
  campo ``orig`` do ICMS): nacional é ``0``; o importado que a casa compra de
  um distribuidor no Brasil é ``2`` ("estrangeira, adquirida no mercado
  interno") — os queijos Ile de France, as mostardas Maille e as geleias St.
  Dalfour (a manteiga Président é fabricada no Brasil: 0). ``resolve_fiscal_item`` merges both into the flat dict the fiscal
  adapter consumes.

PIS/COFINS CST = ``99`` (outras operações) — conforme a parametrização do contador
(doc "PROCEDIMENTO E PARAMETRIZAÇÃO", SEFA-PR, Simples Nacional CRT-01).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Fiscal codes are textual (leading zeros are significant) — never ints.
NCM_RE = re.compile(r"^\d{8}$")   # NCM: 8 digits.
CEST_RE = re.compile(r"^\d{7}$")  # CEST: 7 digits (format SS.III.DD).

#: Origem da mercadoria (campo ``orig`` do ICMS, tabela A do Anexo do Ajuste
#: SINIEF 07/05 — a mesma do Manual de Orientação da NF-e).
ORIGINS: dict[str, str] = {
    "0": "0 — Nacional",
    "1": "1 — Estrangeira, importação direta",
    "2": "2 — Estrangeira, adquirida no mercado interno",
    "3": "3 — Nacional, conteúdo de importação acima de 40% e até 70%",
    "4": "4 — Nacional, produzida conforme processos produtivos básicos",
    "5": "5 — Nacional, conteúdo de importação de até 40%",
    "6": "6 — Estrangeira, importação direta, sem similar nacional (lista CAMEX)",
    "7": "7 — Estrangeira, mercado interno, sem similar nacional (lista CAMEX)",
    "8": "8 — Nacional, conteúdo de importação acima de 70%",
}
DEFAULT_ORIGIN = "0"


@dataclass(frozen=True)
class FiscalProfile:
    """A reusable, named fiscal preset shared by many products.

    Holds the fields that depend on the *operation* (not the individual
    product): CFOP, CSOSN, PIS/COFINS CST. CFOP comes in two flavours —
    intrastate and interstate — and the emission layer picks one by the buyer's
    UF (see ``resolve_fiscal_item``).

    **CFOP da fabricação própria = 5102 (interno) / 6102 (interestadual).**
    Decisão do dono em 2026-08-19. Razão: a Nelson fabrica o que vende mas NÃO é
    registrada como indústria — 5101 é venda de produção do estabelecimento
    industrial —, e sob Simples Nacional (CRT-01) o CFOP não altera o imposto,
    recolhido no DAS. É também o que a parametrização do contador registra
    ("alimentação em geral, salgados, doces" = comercialização).
    Referências: ``docs/reference/fiscal-cfop-5101-vs-5102.md`` (decisão) e
    ``docs/reference/fiscal-parametrizacao-nfce.md`` §2 (parametrização).
    """

    key: str
    name: str
    csosn: str             # ICMS situação tributária no Simples (e.g. "102", "500").
    cfop_internal: str     # Operação interna (mesmo estado), e.g. "5102".
    cfop_interstate: str   # Operação interestadual, e.g. "6102".
    pis_cst: str = "99"        # Simples (CRT-01): 99 = outras operações (parametrização do contador).
    cofins_cst: str = "99"
    requires_cest: bool = False


STANDARD = FiscalProfile(
    key="standard",
    name="Sem substituição tributária",
    csosn="102",
    cfop_internal="5102",
    cfop_interstate="6102",
)

TAX_SUBSTITUTION = FiscalProfile(
    key="tax_substitution",
    name="Com substituição tributária (ST)",
    csosn="500",
    cfop_internal="5405",
    cfop_interstate="6405",
    requires_cest=True,
)

FISCAL_PROFILES: dict[str, FiscalProfile] = {p.key: p for p in (STANDARD, TAX_SUBSTITUTION)}
DEFAULT_PROFILE_KEY = STANDARD.key


@dataclass(frozen=True)
class ProductFiscalClassification:
    """Typed view of ``Product.metadata['fiscal']`` — per-product fiscal data.

    Only the per-product variable bits live here; the rest is resolved from the
    named :class:`FiscalProfile`.
    """

    profile: str = DEFAULT_PROFILE_KEY
    ncm: str = ""
    cest: str = ""
    unit: str = "UN"
    origin: str = DEFAULT_ORIGIN

    @property
    def fiscal_profile(self) -> FiscalProfile | None:
        return FISCAL_PROFILES.get(self.profile)

    def errors(self) -> list[str]:
        """Validation messages (empty == valid). Drives ``Product.clean()``."""
        profile = self.fiscal_profile
        if profile is None:
            return [f"Perfil fiscal desconhecido: {self.profile!r}."]

        problems: list[str] = []
        if not NCM_RE.match(self.ncm or ""):
            problems.append("NCM deve ter 8 dígitos.")
        if self.cest and not CEST_RE.match(self.cest):
            problems.append("CEST deve ter 7 dígitos.")
        elif profile.requires_cest and not self.cest:
            problems.append("CEST (7 dígitos) é obrigatório com substituição tributária.")
        if self.origin not in ORIGINS:
            problems.append("Origem da mercadoria deve ser um código de 0 a 8.")
        return problems

    def warnings(self) -> list[str]:
        """Avisos que não impedem salvar nem emitir: o CEST contra o NCM."""
        from .cest_table import cest_ncm_warnings

        if self.cest and not CEST_RE.match(self.cest):
            return []
        return cest_ncm_warnings(self.ncm, self.cest)

    @property
    def is_valid(self) -> bool:
        return not self.errors()


def from_metadata(metadata: dict | None) -> ProductFiscalClassification:
    """Read a classification from ``Product.metadata`` (tolerant of legacy keys)."""
    raw = (metadata or {}).get("fiscal") or {}
    return ProductFiscalClassification(
        profile=str(raw.get("profile") or DEFAULT_PROFILE_KEY),
        ncm=str(raw.get("ncm") or raw.get("codigo_ncm") or ""),
        cest=str(raw.get("cest") or ""),
        unit=str(raw.get("unit") or raw.get("unidade_comercial") or "UN"),
        origin=str(raw.get("origin") or DEFAULT_ORIGIN),
    )


def validate_for_emission(metadata: dict | None) -> list[str]:
    """Erros que impedem este produto de virar item de documento fiscal.

    Lista vazia == pronto para emitir. Existe para que a pergunta de completude
    fiscal tenha um dono só, em vez de ser respondida tarde (hoje só o adapter
    recusa item sem NCM, na emissão — ``shop/adapters/fiscal_focusnfe._map_item``).

    Recebe o **blob** ``Product.metadata``, não o model: o Fiscalman é dono do
    schema e não importa o Offerman (cores não se importam — a ponte é
    ``fiscalman/contrib/offerman``). Quem tem o produto na mão passa
    ``product.metadata``; é o mesmo caminho que :func:`from_metadata` já serve à
    ponte do admin e ao builder de itens do orquestrador.

    Produto **nunca classificado** responde uma mensagem própria: para quem
    audita o catálogo, "ninguém preencheu" é um problema diferente (e de outro
    dono) de "preencheram torto".
    """
    if not ((metadata or {}).get("fiscal") or {}):
        return ["Sem classificação fiscal: defina perfil e NCM em metadata['fiscal']."]
    return from_metadata(metadata).errors()


def to_metadata_fiscal(classification: ProductFiscalClassification) -> dict:
    """Serialize back to the compact shape stored in ``Product.metadata['fiscal']``."""
    data = {
        "profile": classification.profile,
        "ncm": classification.ncm,
        "unit": classification.unit,
    }
    if classification.cest:
        data["cest"] = classification.cest
    if classification.origin != DEFAULT_ORIGIN:
        data["origin"] = classification.origin
    return data


def resolve_fiscal_item(
    classification: ProductFiscalClassification,
    *,
    interstate: bool = False,
) -> dict:
    """Merge a product's classification with its profile into the flat dict the
    fiscal adapter consumes (``fiscal_focusnfe`` reads exactly these keys).

    ``interstate`` selects the CFOP flavour by the buyer's UF (intrastate is the
    default; interstate is rare and, for consumer sales, ultimately needs NF-e).
    """
    profile = classification.fiscal_profile
    if profile is None:
        raise ValueError(f"Perfil fiscal desconhecido: {classification.profile!r}.")

    item = {
        "ncm": classification.ncm,
        "cfop": profile.cfop_interstate if interstate else profile.cfop_internal,
        "unit": classification.unit,
        "icms_origem": classification.origin,
        "icms_situacao_tributaria": profile.csosn,
        "pis_situacao_tributaria": profile.pis_cst,
        "cofins_situacao_tributaria": profile.cofins_cst,
    }
    if classification.cest:
        item["cest"] = classification.cest
    return item
