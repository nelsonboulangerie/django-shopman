"""Sugestão de catálogo para item de REVENDA, a partir do GTIN.

O que a casa produz, a receita descreve — e a derivação já cuida disso
(:mod:`shopman.shop.services.dietary_from_recipe`). O que a casa **revende**
não tem receita: geleia, queijo, chá em lata. Para esses, quem sabe o que tem
dentro é o fabricante, e a chave que abre essa porta é o GTIN.

Duas fontes, uma por campo — nenhuma delas escolhida por acaso:

- **Cosmos (Bluesoft)** dá **foto oficial, nome, marca e NCM**. É base
  brasileira, alimentada por fabricante e varejo. Não devolve ingrediente nem
  alérgeno: conferido na documentação da API em 05/09/2026, o retorno de
  ``/gtins/{gtin}.json`` tem ``description``, ``brand``, ``thumbnail``,
  ``ncm``, ``gpc`` e pesos, e nada mais.
- **Open Food Facts** dá **alérgeno estruturado**. É colaborativo e aberto.
  Medido em 05/09/2026 numa amostra de 30 produtos brasileiros: 73% com
  ``allergens_tags`` preenchido.

⚠️ **Nada daqui vira rótulo sozinho.** A sugestão é gravada em
``Product.metadata['enrichment']`` com ``status="pending"`` e só entra no
produto quando alguém aceita (ação do Admin). Duas razões, e as duas doem:

1. O Open Food Facts é colaborativo — campo vazio quase nunca significa "não
   contém". Na mesma amostra, **93% dos que não tinham alérgeno marcado TINHAM
   a lista de ingredientes preenchida**: ou seja, o silêncio é falta de
   curadoria, não ausência do alérgeno. Auto-preencher importaria exatamente o
   defeito que esta casa combate — silêncio lido como promessa.
2. A própria Cosmos avisa na página de planos que "os dados devem ser revisados
   antes do uso, não há garantia de que estejam corretos e atuais".

A autoridade continua sendo o rótulo físico. Isto aqui é rascunho.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings
from django.utils import timezone

from shopman.shop.adapters._external import inert

logger = logging.getLogger(__name__)

COSMOS_URL = "https://api.cosmos.bluesoft.com.br/gtins/{gtin}.json"
OFF_URL = "https://world.openfoodfacts.org/api/v2/product/{gtin}"
OFF_FIELDS = "code,product_name,brands,image_front_url,allergens_tags,ingredients_text"

_TIMEOUT = 15
_USER_AGENT = "shopman/1.0 (catalogo de revenda; contato via loja)"

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


@dataclass
class EnrichmentSuggestion:
    """O rascunho, ainda não aplicado. Só o que veio; sem inventar default."""

    gtin: str = ""
    name: str = ""
    brand: str = ""
    image_url: str = ""
    ncm: str = ""
    gpc: str = ""
    net_weight_g: int | None = None
    allergens: list[str] = field(default_factory=list)
    allergens_unmapped: list[str] = field(default_factory=list)
    ingredients_text: str = ""
    sources: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.name or self.image_url or self.ncm or self.allergens)

    def to_metadata(self) -> dict[str, Any]:
        """O sub-dict de ``Product.metadata['enrichment']``.

        `status="pending"` é o que impede a sugestão de virar rótulo: quem lê o
        produto ignora este bloco por completo até alguém aceitar.
        """
        payload = {
            "status": "pending",
            "fetched_at": timezone.now().isoformat(),
            "sources": self.sources,
            "suggested": {
                k: v
                for k, v in {
                    "gtin": self.gtin,
                    "name": self.name,
                    "brand": self.brand,
                    "image_url": self.image_url,
                    "ncm": self.ncm,
                    "gpc": self.gpc,
                    "net_weight_g": self.net_weight_g,
                    "allergens": self.allergens,
                    "allergens_unmapped": self.allergens_unmapped,
                    "ingredients_text": self.ingredients_text,
                }.items()
                if v not in (None, "", [], {})
            },
        }
        if self.notes:
            payload["notes"] = self.notes
        return payload


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


def fetch_cosmos(gtin: str) -> dict[str, Any] | None:
    """Foto, nome, marca e NCM. Precisa de token (o plano grátis dá 25/dia)."""
    token = getattr(settings, "SHOPMAN_COSMOS_TOKEN", "") or ""
    if not token:
        logger.info("enrichment: SHOPMAN_COSMOS_TOKEN ausente; pulando Cosmos.")
        return None
    return _get_json(COSMOS_URL.format(gtin=gtin), {"X-Cosmos-Token": token})


def fetch_off(gtin: str) -> dict[str, Any] | None:
    """Alérgeno estruturado. Aberto, sem chave."""
    url = OFF_URL.format(gtin=gtin) + "?" + urllib.parse.urlencode({"fields": OFF_FIELDS})
    data = _get_json(url)
    if not data or data.get("status") == 0:
        return None
    product = data.get("product")
    return product if isinstance(product, dict) else None


def build_suggestion(gtin: str) -> EnrichmentSuggestion:
    """Consulta as duas fontes e devolve o rascunho. Não escreve nada."""
    s = EnrichmentSuggestion(gtin=str(gtin or "").strip())
    if not s.gtin:
        return s

    if inert("SHOPMAN_ENRICHMENT_ALLOW_IN_DEBUG"):
        logger.info("enrichment: inerte (DEBUG sem opt-in); GTIN %s não consultado.", s.gtin)
        s.notes.append("Consulta externa inerte neste ambiente.")
        return s

    cosmos = fetch_cosmos(s.gtin)
    if cosmos:
        s.sources.append("cosmos")
        s.name = str(cosmos.get("description") or "").strip()
        brand = cosmos.get("brand")
        if isinstance(brand, dict):
            s.brand = str(brand.get("name") or "").strip()
        s.image_url = str(cosmos.get("thumbnail") or "").strip()
        ncm = cosmos.get("ncm")
        if isinstance(ncm, dict):
            s.ncm = str(ncm.get("code") or "").strip()
        gpc = cosmos.get("gpc")
        if isinstance(gpc, dict):
            s.gpc = str(gpc.get("description") or "").strip()
        peso = cosmos.get("net_weight")
        if isinstance(peso, (int, float)) and peso > 0:
            s.net_weight_g = int(peso)

    off = fetch_off(s.gtin)
    if off:
        s.sources.append("openfoodfacts")
        tags = off.get("allergens_tags")
        if isinstance(tags, list):
            for tag in tags:
                casa = OFF_TO_CASA.get(str(tag))
                if casa:
                    if casa not in s.allergens:
                        s.allergens.append(casa)
                elif str(tag) not in s.allergens_unmapped:
                    s.allergens_unmapped.append(str(tag))
        s.ingredients_text = str(off.get("ingredients_text") or "").strip()
        if not s.image_url:
            s.image_url = str(off.get("image_front_url") or "").strip()
            if s.image_url:
                # ⚠️ Foto do OFF é CC-BY-SA (colaborativa). Serve de apoio para
                # reconhecer o item; publicar na vitrine exige atribuição.
                s.notes.append("Foto veio do Open Food Facts (CC-BY-SA): exige atribuição se publicada.")

        # O silêncio do OFF não é declaração de ausência — e é justamente aqui
        # que ele engana. Se veio ingrediente e não veio alérgeno, diga isso.
        if not tags and s.ingredients_text:
            s.notes.append(
                "O Open Food Facts tem os ingredientes mas NÃO marcou alérgeno. "
                "Isso é falta de curadoria, não ausência — confira no rótulo."
            )

    if s.allergens_unmapped:
        s.notes.append(
            "Alérgeno fora da lista da casa: "
            + ", ".join(s.allergens_unmapped)
            + ". Aipo, molusco e tremoço são obrigatórios na UE e não na RDC 26/2015 — decida antes de aceitar."
        )
    return s
