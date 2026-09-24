"""Sugestão de catálogo para item de REVENDA, a partir do GTIN — campo a campo.

O que a casa produz, a receita descreve — e a derivação já cuida disso
(:mod:`shopman.shop.services.dietary_from_recipe`). O que a casa **revende**
não tem receita: geleia, queijo, chá em lata. Para esses, quem sabe o que tem
dentro é o fabricante, e a chave que abre essa porta é o GTIN.

Três fontes, em ordem de autoridade (:data:`SOURCE_PRIORITY`):

1. **A NF-e de compra** (``source="nfe"``). É a primeira porque é declaração
   fiscal do fornecedor sobre ESTE item, não cadastro de terceiro: GTIN, NCM,
   CEST e unidade chegam no XML do recebimento (ver
   :func:`suggest_from_invoice`, chamada pelo recebimento de revenda).
2. **Cosmos (Bluesoft)** — nome, marca, NCM, peso e foto. Base brasileira,
   alimentada por fabricante e varejo. Não devolve ingrediente nem alérgeno
   (conferido na documentação da API em 05/09/2026).
3. **Open Food Facts** — ingredientes, alérgeno estruturado e tabela
   nutricional. Colaborativo e aberto. Medido em 05/09/2026 numa amostra de 30
   produtos brasileiros: 73% com ``allergens_tags`` preenchido.

⚠️ **Nada daqui vira rótulo sozinho.** A sugestão mora em
``Product.metadata['enrichment']`` como rascunho POR CAMPO
(``fields[campo] = {value, source, fetched_at}``) e só entra no produto quando
alguém aceita AQUELE campo (:func:`accept_fields`, chamada pela ação do Admin).
Três travas, e as três doem:

1. **Valor preenchido à mão nunca é sobrescrito sem confirmação.** Aceitar um
   campo que já tem valor diferente exige ``replace`` explícito para ele.
2. **Alérgeno vazio na fonte é "não curado", jamais "não contém".** Na amostra
   do OFF, 93% dos que não tinham alérgeno marcado TINHAM a lista de
   ingredientes: o silêncio é falta de curadoria. Lista vazia nunca vira campo
   aceitável — vira nota.
3. **Foto de terceiro não vai para a vitrine.** A do OFF é CC BY-SA (exige
   atribuição e compartilhamento pela mesma licença); a da Cosmos não declara
   licença de uso nenhuma. As duas ficam como ``reference_photo`` — apoio para
   reconhecer o item, com licença e atribuição guardadas. A vitrine usa foto
   da casa.

A autoridade continua sendo o rótulo físico. E quando nenhuma fonte conhece o
GTIN, a frase é sobre a BUSCA, não sobre o produto: :data:`NOTHING_FOUND`.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from dataclasses import replace as dc_replace
from typing import Any

from django.conf import settings
from django.utils import timezone

from shopman.shop.adapters._external import inert

logger = logging.getLogger(__name__)

COSMOS_URL = "https://api.cosmos.bluesoft.com.br/gtins/{gtin}.json"
OFF_URL = "https://world.openfoodfacts.org/api/v2/product/{gtin}"
OFF_PRODUCT_PAGE = "https://world.openfoodfacts.org/product/{gtin}"
OFF_FIELDS = (
    "code,product_name,brands,image_front_url,allergens_tags,ingredients_text,"
    "nutriments,serving_quantity"
)

_TIMEOUT = 15
_USER_AGENT = "shopman/1.0 (catalogo de revenda; contato via loja)"

SOURCE_NFE = "nfe"
SOURCE_COSMOS = "cosmos"
SOURCE_OFF = "openfoodfacts"

#: Menor número = mais autoridade. A NF-e é declaração fiscal do fornecedor
#: sobre o item que chegou; as outras duas são cadastro de terceiro.
SOURCE_PRIORITY: dict[str, int] = {SOURCE_NFE: 0, SOURCE_COSMOS: 1, SOURCE_OFF: 2}

SOURCE_LABELS: dict[str, str] = {
    SOURCE_NFE: "NF-e de compra",
    SOURCE_COSMOS: "Cosmos (Bluesoft)",
    SOURCE_OFF: "Open Food Facts",
}

#: Os campos que uma sugestão pode trazer, na ordem em que a tela os mostra.
FIELD_LABELS: dict[str, str] = {
    "gtin": "GTIN (código de barras)",
    "name": "Nome",
    "brand": "Marca",
    "ncm": "NCM",
    "cest": "CEST",
    "fiscal_unit": "Unidade fiscal",
    "net_weight_g": "Peso líquido (g)",
    "ingredients_text": "Ingredientes",
    "allergens": "Alérgenos",
    "nutrition": "Tabela nutricional",
}

#: A frase de quando ninguém responde. Fala da busca, não do mundo: duas
#: fontes caladas não provam que o código não existe — a embalagem prova.
NOTHING_FOUND = "Nenhuma das fontes consultadas tem este GTIN; só a embalagem confirma."

ALLERGENS_NOT_CURATED = (
    "O Open Food Facts não marcou alérgeno para este GTIN. Isso é “não curado”, "
    "não “não contém”: confira no rótulo."
)

OFF_PHOTO_LICENSE = "CC BY-SA 3.0"
COSMOS_PHOTO_LICENSE = "sem licença de uso declarada"

_NCM_RE = re.compile(r"^\d{8}$")
_CEST_RE = re.compile(r"^\d{7}$")

# ── Alérgeno: do vocabulário do Open Food Facts para o da casa ──────────
#
# ⚠️ O que NÃO estiver aqui não é descartado — vai para `allergens_unmapped` e
# aparece para quem aceita. Aipo, molusco e tremoço são obrigatórios na União
# Europeia e NÃO estão na RDC 26/2015 brasileira: se um deles vier, quem decide
# é o dono, não um `dict.get()` que devolve None e some com a informação.
# Alérgeno descartado em silêncio é o pior defeito possível nesta superfície.
OFF_TO_CASA: dict[str, str] = {
    "en:gluten": "glúten",
    "en:milk": "leite",
    "en:eggs": "ovos",
    "en:soybeans": "soja",
    "en:peanuts": "amendoim",
    "en:fish": "peixes",
    "en:crustaceans": "crustáceos",
    "en:sesame-seeds": "gergelim",
    "en:mustard": "mostarda",
    "en:sulphur-dioxide-and-sulphites": "sulfitos",
    "en:nuts": "castanhas",
    "en:almonds": "amêndoa",
    "en:hazelnuts": "avelã",
    "en:cashew-nuts": "castanha-de-caju",
    "en:brazil-nuts": "castanha-do-brasil",
    "en:macadamia-nuts": "macadâmia",
    "en:walnuts": "nozes",
    "en:pecan-nuts": "pecã",
    "en:pistachio-nuts": "pistache",
}

# Nutriente do OFF (por 100 g) → campo da tabela da casa (por porção).
# Sódio vem em GRAMAS no OFF e a casa guarda em miligramas.
_OFF_NUTRIENTS: dict[str, tuple[str, float]] = {
    "energy-kcal_100g": ("energy_kcal", 1.0),
    "carbohydrates_100g": ("carbohydrates_g", 1.0),
    "sugars_100g": ("sugars_g", 1.0),
    "proteins_100g": ("proteins_g", 1.0),
    "fat_100g": ("total_fat_g", 1.0),
    "saturated-fat_100g": ("saturated_fat_g", 1.0),
    "trans-fat_100g": ("trans_fat_g", 1.0),
    "fiber_100g": ("fiber_g", 1.0),
    "sodium_100g": ("sodium_mg", 1000.0),
}


def _now() -> str:
    return timezone.now().isoformat()


def _is_empty(value: Any) -> bool:
    return value in (None, "", [], {})


@dataclass
class EnrichmentSuggestion:
    """O rascunho de UMA consulta, ainda não aplicado. Só o que veio."""

    gtin: str = ""
    fields: dict[str, dict[str, Any]] = field(default_factory=dict)
    reference_photo: dict[str, Any] | None = None
    allergens_unmapped: list[str] = field(default_factory=list)
    #: Fontes que RESPONDERAM com o GTIN.
    sources: list[str] = field(default_factory=list)
    #: Fontes perguntadas (responderam ou não).
    consulted: list[str] = field(default_factory=list)
    #: Fontes que ficaram de fora, com o motivo — para a ausência ter escopo.
    skipped: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def add(self, name: str, value: Any, source: str, **extra: Any) -> None:
        """Propõe ``value`` para o campo ``name`` — vazio não é proposta."""
        if _is_empty(value):
            return
        entry = {"value": value, "source": source, "fetched_at": _now()}
        entry.update({k: v for k, v in extra.items() if not _is_empty(v)})
        current = self.fields.get(name)
        if current is None or _priority(source) < _priority(current["source"]):
            self.fields[name] = entry

    def is_empty(self) -> bool:
        return not self.fields and not self.reference_photo

    def value(self, name: str) -> Any:
        entry = self.fields.get(name)
        return entry["value"] if entry else None

    def scope_note(self) -> str:
        """A ausência com o escopo colado: quem foi perguntado, quem ficou de fora."""
        parts = []
        if self.consulted:
            parts.append("consultadas: " + ", ".join(SOURCE_LABELS.get(s, s) for s in self.consulted))
        for source, reason in self.skipped.items():
            parts.append(f"{SOURCE_LABELS.get(source, source)} ficou de fora ({reason})")
        return "; ".join(parts)


def _priority(source: str) -> int:
    return SOURCE_PRIORITY.get(source, len(SOURCE_PRIORITY))


# ── Consulta ─────────────────────────────────────────────────────────────


def _get_json(url: str, headers: dict[str, str] | None = None) -> dict | None:
    """GET que devolve dict ou None. Falha de rede NUNCA sobe daqui.

    Enriquecimento é conveniência: um fornecedor fora do ar não pode derrubar
    o comando nem a tela de quem está cadastrando produto.
    """
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # 404 é resposta legítima ("não conheço este GTIN"), não incidente.
        level = logging.INFO if exc.code in (401, 404, 429) else logging.WARNING
        logger.log(level, "enrichment: %s devolveu HTTP %s", url, exc.code)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        logger.warning("enrichment: falha ao consultar %s", url, exc_info=True)
    return None


def cosmos_token() -> str:
    return str(getattr(settings, "SHOPMAN_COSMOS_TOKEN", "") or "").strip()


def fetch_cosmos(gtin: str) -> dict[str, Any] | None:
    """Nome, marca, NCM, peso e foto. Precisa de token (o plano grátis dá 25/dia)."""
    token = cosmos_token()
    if not token:
        logger.info("enrichment: SHOPMAN_COSMOS_TOKEN vazio; Cosmos inerte.")
        return None
    return _get_json(COSMOS_URL.format(gtin=gtin), {"X-Cosmos-Token": token})


def fetch_off(gtin: str) -> dict[str, Any] | None:
    """Ingredientes, alérgeno e nutrição. Aberto, sem chave."""
    url = OFF_URL.format(gtin=gtin) + "?" + urllib.parse.urlencode({"fields": OFF_FIELDS})
    data = _get_json(url)
    if not data or data.get("status") == 0:
        return None
    product = data.get("product")
    return product if isinstance(product, dict) else None


def _nutrition_from_off(off: dict[str, Any]) -> dict[str, Any] | None:
    """A tabela do OFF (por 100 g) levada à porção que o próprio OFF declara.

    Sem porção declarada não há tabela: inventar 100 g como porção produziria
    um rótulo que nenhuma embalagem tem.
    """
    nutriments = off.get("nutriments")
    try:
        serving = float(off.get("serving_quantity") or 0)
    except (TypeError, ValueError):
        serving = 0
    if not isinstance(nutriments, dict) or serving <= 0:
        return None
    facts: dict[str, Any] = {}
    for off_key, (casa_key, factor) in _OFF_NUTRIENTS.items():
        raw = nutriments.get(off_key)
        if isinstance(raw, (int, float)):
            facts[casa_key] = round(float(raw) * serving / 100 * factor, 2)
    if not facts:
        return None
    return {"serving_size_g": int(round(serving)), "servings_per_container": 1, **facts}


def build_suggestion(gtin: str) -> EnrichmentSuggestion:
    """Consulta Cosmos e Open Food Facts e devolve o rascunho. Não escreve nada."""
    s = EnrichmentSuggestion(gtin=str(gtin or "").strip())
    if not s.gtin:
        return s

    if inert("SHOPMAN_ENRICHMENT_ALLOW_IN_DEBUG"):
        logger.info("enrichment: inerte (DEBUG sem opt-in); GTIN %s não consultado.", s.gtin)
        s.notes.append("Consulta externa inerte neste ambiente.")
        return s

    if cosmos_token():
        s.consulted.append(SOURCE_COSMOS)
        cosmos = fetch_cosmos(s.gtin)
    else:
        s.skipped[SOURCE_COSMOS] = "sem SHOPMAN_COSMOS_TOKEN"
        cosmos = None
    if cosmos:
        s.sources.append(SOURCE_COSMOS)
        s.add("name", str(cosmos.get("description") or "").strip(), SOURCE_COSMOS)
        brand = cosmos.get("brand")
        if isinstance(brand, dict):
            s.add("brand", str(brand.get("name") or "").strip(), SOURCE_COSMOS)
        ncm = cosmos.get("ncm")
        if isinstance(ncm, dict):
            code = re.sub(r"\D", "", str(ncm.get("code") or ""))
            if _NCM_RE.match(code):
                s.add("ncm", code, SOURCE_COSMOS)
        cest = cosmos.get("cest")
        if isinstance(cest, dict):
            code = re.sub(r"\D", "", str(cest.get("code") or ""))
            if _CEST_RE.match(code):
                s.add("cest", code, SOURCE_COSMOS)
        peso = cosmos.get("net_weight")
        if isinstance(peso, (int, float)) and peso > 0:
            s.add("net_weight_g", int(peso), SOURCE_COSMOS)
        thumb = str(cosmos.get("thumbnail") or "").strip()
        if thumb:
            s.reference_photo = {
                "url": thumb,
                "source": SOURCE_COSMOS,
                "license": COSMOS_PHOTO_LICENSE,
                "attribution": "Bluesoft Cosmos (cosmos.bluesoft.com.br)",
                "fetched_at": _now(),
            }

    s.consulted.append(SOURCE_OFF)
    off = fetch_off(s.gtin)
    if off:
        s.sources.append(SOURCE_OFF)
        if SOURCE_COSMOS not in s.sources:
            s.add("name", str(off.get("product_name") or "").strip(), SOURCE_OFF)
            s.add("brand", str(off.get("brands") or "").split(",")[0].strip(), SOURCE_OFF)
        s.add("ingredients_text", str(off.get("ingredients_text") or "").strip(), SOURCE_OFF)

        tags = off.get("allergens_tags")
        mapped: list[str] = []
        if isinstance(tags, list):
            for tag in tags:
                casa = OFF_TO_CASA.get(str(tag))
                if casa:
                    if casa not in mapped:
                        mapped.append(casa)
                elif str(tag) not in s.allergens_unmapped:
                    s.allergens_unmapped.append(str(tag))
        if mapped:
            s.add("allergens", mapped, SOURCE_OFF)
        elif not s.allergens_unmapped:
            # O vazio do OFF não é declaração de ausência — e é aqui que ele
            # engana. Nunca vira campo aceitável ("[]" seria lido como "não
            # contém"); vira nota que diz o que ele é.
            s.notes.append(ALLERGENS_NOT_CURATED)

        s.add("nutrition", _nutrition_from_off(off), SOURCE_OFF)

        image = str(off.get("image_front_url") or "").strip()
        if image and not s.reference_photo:
            s.reference_photo = {
                "url": image,
                "source": SOURCE_OFF,
                "license": OFF_PHOTO_LICENSE,
                "attribution": (
                    "Open Food Facts contributors — " + OFF_PRODUCT_PAGE.format(gtin=s.gtin)
                ),
                "fetched_at": _now(),
            }

    if s.allergens_unmapped:
        s.notes.append(
            "Alérgeno fora da lista da casa: "
            + ", ".join(s.allergens_unmapped)
            + ". Aipo, molusco e tremoço são obrigatórios na UE e não na RDC 26/2015 — decida antes de aceitar."
        )
    if s.reference_photo:
        s.notes.append(
            "Foto de referência ("
            + SOURCE_LABELS[s.reference_photo["source"]]
            + ", "
            + s.reference_photo["license"]
            + "): serve para reconhecer o item, não vai para a vitrine."
        )
    if s.is_empty():
        scope = s.scope_note()
        s.notes.insert(0, NOTHING_FOUND + (f" ({scope}.)" if scope else ""))
    elif s.skipped:
        s.notes.append(s.scope_note().capitalize() + ".")
    return s


# ── A NF-e de compra como primeira fonte ─────────────────────────────────


def suggestion_from_invoice(
    *,
    gtin: str = "",
    other_gtin: str = "",
    ncm: str = "",
    cest: str = "",
    unit: str = "",
    access_key: str = "",
) -> EnrichmentSuggestion:
    """O que a NF-e de compra declara sobre o item: GTIN, NCM, CEST e unidade.

    Não consulta rede. O GTIN chega já conferido pelo leitor da nota (dígito
    verificador GS1); NCM e CEST só entram no formato certo.
    """
    from shopman.offerman.contrib.social.schema import _gtin_is_valid

    s = EnrichmentSuggestion(gtin=gtin if gtin and _gtin_is_valid(gtin) else "")
    ref = {"source_ref": access_key} if access_key else {}
    if s.gtin:
        detail = ""
        if other_gtin and other_gtin != s.gtin:
            detail = (
                f"A nota traz também o GTIN {other_gtin} (embalagem ou eixo tributável); "
                "confira qual está impresso na unidade."
            )
        s.add("gtin", s.gtin, SOURCE_NFE, detail=detail, **ref)
    ncm = re.sub(r"\D", "", ncm or "")
    if _NCM_RE.match(ncm):
        s.add("ncm", ncm, SOURCE_NFE, **ref)
    cest = re.sub(r"\D", "", cest or "")
    if _CEST_RE.match(cest):
        s.add("cest", cest, SOURCE_NFE, **ref)
    unit = (unit or "").strip().upper()
    if unit:
        s.add("fiscal_unit", unit, SOURCE_NFE, **ref)
    if not s.fields:
        return s
    s.sources.append(SOURCE_NFE)
    s.consulted.append(SOURCE_NFE)
    return s


def suggest_from_invoice(product, **invoice_fields: Any) -> bool:
    """Grava no rascunho do produto o que a NF-e declarou. Nunca no produto.

    Devolve True quando algo novo entrou no rascunho.
    """
    s = suggestion_from_invoice(**invoice_fields)
    if not s.fields:
        return False
    before = (product.metadata or {}).get("enrichment")
    metadata = merge_into_metadata(product.metadata, s)
    if metadata.get("enrichment") == before:
        return False
    product.metadata = metadata
    product.save(update_fields=["metadata", "updated_at"])
    return True


# ── O rascunho no produto ────────────────────────────────────────────────


def draft(product_or_metadata) -> dict[str, Any]:
    """O bloco ``metadata['enrichment']`` (cópia), ou ``{}``."""
    metadata = getattr(product_or_metadata, "metadata", product_or_metadata)
    block = (metadata or {}).get("enrichment") if isinstance(metadata, dict) else None
    return json.loads(json.dumps(block)) if isinstance(block, dict) else {}


def pending_fields(product_or_metadata) -> dict[str, dict[str, Any]]:
    """Os campos sugeridos e ainda não aceitos, na ordem de :data:`FIELD_LABELS`."""
    fields = draft(product_or_metadata).get("fields") or {}
    return {name: fields[name] for name in FIELD_LABELS if name in fields}


def merge_into_metadata(metadata: dict | None, s: EnrichmentSuggestion) -> dict:
    """Devolve ``metadata`` novo, com a sugestão fundida ao rascunho existente.

    Por campo, fica a fonte de mais autoridade; a que perde não some — vai para
    ``alternatives`` quando diverge, porque NCM da Cosmos diferente do NCM da
    nota é justamente o que quem aceita precisa ver. Campo já aceito com o
    MESMO valor não volta a ficar pendente.
    """
    new_meta = dict(metadata or {})
    block = draft(new_meta)
    fields: dict[str, dict[str, Any]] = dict(block.get("fields") or {})
    accepted: dict[str, dict[str, Any]] = dict(block.get("accepted") or {})

    for name, entry in s.fields.items():
        done = accepted.get(name)
        if done and _same(name, done.get("value"), entry["value"]):
            continue
        current = fields.get(name)
        if current is None:
            fields[name] = entry
            continue
        if _same(name, current["value"], entry["value"]):
            if _priority(entry["source"]) <= _priority(current["source"]):
                fields[name] = {**entry, **_keep_alternatives(current)}
            continue
        winner, loser = (
            (entry, current)
            if _priority(entry["source"]) <= _priority(current["source"])
            else (current, entry)
        )
        alternatives = [
            alt
            for alt in (current.get("alternatives") or [])
            if alt.get("source") not in (winner["source"], loser["source"])
        ]
        if loser["source"] != winner["source"]:
            alternatives.append(
                {"value": loser["value"], "source": loser["source"], "fetched_at": loser["fetched_at"]}
            )
        merged = {k: v for k, v in winner.items() if k != "alternatives"}
        if alternatives:
            merged["alternatives"] = alternatives
        fields[name] = merged

    if s.gtin:
        block["gtin"] = s.gtin
    block["fetched_at"] = _now()
    block["sources"] = sorted(set(block.get("sources") or []) | set(s.sources), key=_priority)
    if fields:
        block["fields"] = fields
    if accepted:
        block["accepted"] = accepted
    if s.reference_photo:
        block["reference_photo"] = s.reference_photo
    if s.allergens_unmapped:
        block["allergens_unmapped"] = s.allergens_unmapped
    # Notas são da CONSULTA de terceiros; a leitura da nota fiscal não as apaga.
    if s.consulted and s.consulted != [SOURCE_NFE]:
        block["notes"] = list(s.notes)
    new_meta["enrichment"] = block
    return new_meta


def _keep_alternatives(entry: dict[str, Any]) -> dict[str, Any]:
    return {"alternatives": entry["alternatives"]} if entry.get("alternatives") else {}


def _same(name: str, a: Any, b: Any) -> bool:
    if name == "allergens":
        return sorted(a or []) == sorted(b or [])
    if name == "nutrition":
        strip = lambda d: {k: v for k, v in (d or {}).items() if k != "auto_filled"}  # noqa: E731
        return strip(a) == strip(b)
    if isinstance(a, str) and isinstance(b, str):
        return a.strip() == b.strip()
    return a == b


# ── O produto: o que está lá hoje, e como um campo aceito entra ──────────


def current_value(product, name: str) -> Any:
    """O valor que o produto tem HOJE no destino do campo ``name``."""
    meta = product.metadata or {}
    social = meta.get("social") or {}
    fiscal = meta.get("fiscal") or {}
    if name == "gtin":
        return social.get("gtin") or ""
    if name == "brand":
        return social.get("brand") or ""
    if name == "name":
        return product.name or ""
    if name == "ncm":
        return fiscal.get("ncm") or ""
    if name == "cest":
        return fiscal.get("cest") or ""
    if name == "fiscal_unit":
        return fiscal.get("unit") or ""
    if name == "net_weight_g":
        return product.unit_weight_g
    if name == "ingredients_text":
        return product.ingredients_text or ""
    if name == "allergens":
        return list(meta.get("allergens") or [])
    if name == "nutrition":
        return dict(product.nutrition_facts or {})
    raise KeyError(name)


def needs_replace(product, name: str, value: Any) -> bool:
    """True quando o destino já tem valor, e é outro: aceitar exige confirmação."""
    current = current_value(product, name)
    return not _is_empty(current) and not _same(name, current, value)


def format_value(name: str, value: Any) -> str:
    """O valor numa linha legível, para a tela de aceite."""
    if _is_empty(value):
        return "—"
    if name == "allergens":
        return ", ".join(value)
    if name == "nutrition":
        facts = dict(value)
        porcao = facts.pop("serving_size_g", None)
        facts.pop("servings_per_container", None)
        facts.pop("auto_filled", None)
        corpo = ", ".join(f"{k}={v}" for k, v in facts.items() if v is not None)
        return f"porção {porcao} g: {corpo}" if porcao else corpo
    text = str(value)
    return text if len(text) <= 160 else text[:157] + "…"


@dataclass
class AcceptResult:
    applied: list[str] = field(default_factory=list)
    #: Campo com valor preenchido à mão, recusado por falta de ``replace``.
    conflicts: dict[str, Any] = field(default_factory=dict)
    #: Campo recusado por validação (GTIN inválido, CEST sem perfil ST, …).
    refused: dict[str, str] = field(default_factory=dict)


def accept_fields(product, names, *, replace=(), user=None) -> AcceptResult:
    """Aplica ao produto SÓ os campos ``names`` do rascunho.

    É o ÚNICO caminho pelo qual a sugestão vira dado do produto. Campo cujo
    destino já tem outro valor só entra se estiver também em ``replace`` — a
    confirmação explícita de quem tem a embalagem na mão. Cada campo aceito
    sai de ``fields`` e vai para ``accepted[campo]`` com fonte, data da
    consulta, quem aceitou, quando, e o valor que substituiu (se substituiu).
    """
    from shopman.offerman.contrib.social.schema import (
        _gtin_is_valid,
        get_social_attributes,
        set_social_attributes,
    )
    from shopman.offerman.nutrition import NutritionFacts

    result = AcceptResult()
    replace = set(replace)
    meta = dict(product.metadata or {})
    block = draft(meta)
    fields: dict[str, dict[str, Any]] = dict(block.get("fields") or {})
    accepted: dict[str, dict[str, Any]] = dict(block.get("accepted") or {})
    who = user.get_username() if user is not None and hasattr(user, "get_username") else ""

    for name in names:
        entry = fields.get(name)
        if not entry:
            continue
        value = entry["value"]
        previous = current_value(product, name)
        if needs_replace(product, name, value) and name not in replace:
            result.conflicts[name] = previous
            continue

        fiscal = dict(meta.get("fiscal") or {})
        if name == "gtin":
            if not _gtin_is_valid(str(value)):
                result.refused[name] = "GTIN com dígito verificador inválido."
                continue
            attrs = dc_replace(get_social_attributes(meta), gtin=str(value))
            meta = set_social_attributes(meta, attrs)
        elif name == "brand":
            attrs = dc_replace(get_social_attributes(meta), brand=str(value))
            meta = set_social_attributes(meta, attrs)
        elif name == "name":
            product.name = str(value)[: product._meta.get_field("name").max_length]
        elif name == "ncm":
            if not _NCM_RE.match(str(value)):
                result.refused[name] = "NCM deve ter 8 dígitos."
                continue
            fiscal["ncm"] = str(value)
            meta["fiscal"] = fiscal
        elif name == "cest":
            if not _CEST_RE.match(str(value)):
                result.refused[name] = "CEST deve ter 7 dígitos."
                continue
            if fiscal.get("profile") != "resale":
                result.refused[name] = (
                    "CEST só vale no perfil fiscal Revenda (com ST). "
                    "Escolha o perfil na aba Fiscal e aceite de novo."
                )
                continue
            fiscal["cest"] = str(value)
            meta["fiscal"] = fiscal
        elif name == "fiscal_unit":
            fiscal["unit"] = str(value)
            meta["fiscal"] = fiscal
        elif name == "net_weight_g":
            product.unit_weight_g = int(value)
        elif name == "ingredients_text":
            product.ingredients_text = str(value)
        elif name == "allergens":
            meta["allergens"] = list(value)
            # Aceite humano é o oposto de auto-preenchido: trava a derivação
            # por receita, que para revenda não existe mesmo.
            meta["dietary_auto_filled"] = False
        elif name == "nutrition":
            facts = NutritionFacts.from_dict({**value, "auto_filled": False})
            product.nutrition_facts = facts.to_dict() if facts else {}
        else:  # pragma: no cover - FIELD_LABELS e este if andam juntos
            continue

        record = {
            "value": value,
            "source": entry["source"],
            "fetched_at": entry.get("fetched_at", ""),
            "accepted_by": who,
            "accepted_at": _now(),
        }
        if entry.get("source_ref"):
            record["source_ref"] = entry["source_ref"]
        if not _is_empty(previous) and not _same(name, previous, value):
            record["replaced"] = previous
        accepted[name] = record
        fields.pop(name, None)
        result.applied.append(name)

    if not result.applied:
        return result

    block["fields"] = fields
    if not fields:
        block.pop("fields")
    block["accepted"] = accepted
    meta["enrichment"] = block
    product.metadata = meta
    product.save()
    return result
