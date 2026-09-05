"""De qual versão da receita veio cada fato que o catálogo mostra ao cliente.

O catálogo deriva da ficha três coisas hoje (nutrição, alérgenos/dieta,
ingredientes) e, com o WP-FICHA-DE-PRODUTO-E-PROMESSA, uma quarta: o peso da
peça. Até aqui a derivação acontecia e **não deixava rastro** — publicada uma
versão nova da ficha, o PDP continuava exibindo o número velho com cara de
atual. Este módulo é o rastro.

O carimbo mora em ``Product.metadata["derived_from"]``, um dicionário por fato::

    {
        "nutrition": {
            "source": "recipe",              # "recipe" | "manual"
            "recipe_ref": "baguete",
            "version_ref": "baguete@3",      # "" = ficha sem versão publicada
            "by": "",                        # quem conferiu (só em manual)
            "at": "2026-09-05T09:00:00+00:00",
        },
        ...
    }

Três decisões que não são detalhe:

- **Vencido é comparação exata.** ``version_ref`` gravado diferente do
  ``version_ref`` atual da ficha. Sem limiar, sem tolerância, sem data — data
  não sabe se a ficha andou, só sabe que o tempo passou.
- **Ficha sem versão não ganha número inventado.** Ficha criada pelo seed ou
  pelo Admin nunca passou por ``publish_version``, então não tem
  ``Recipe.meta["version_ref"]``. O carimbo dela é a string vazia — a mesma que
  ``CraftPlanning.plan["_recipe_snapshot"]["version_ref"]`` já usa para dizer
  exatamente isto. Vazio contra vazio nunca vence, e a leitura avisa que ali
  **não dá para detectar** defasagem (``is_versioned=False``), em vez de
  prometer um frescor que ninguém pode conferir.
- **Override manual tem autor.** O sistema nunca carimba um fato manual
  sozinho: número escrito à mão só é dado por conferido quando alguém assina
  (:func:`record_manual_audit`), como as conversões de insumo do Buyman, que a
  ADR-024 exige que tenham autor. Manual sem assinatura é reportado como
  "nunca conferido", que é a verdade.
"""

from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)

#: Chave do carimbo dentro de ``Product.metadata``.
PROVENANCE_KEY = "derived_from"

#: Os fatos que o catálogo mostra e vêm da ficha.
FACT_NUTRITION = "nutrition"
FACT_DIETARY = "dietary"
FACT_UNIT_WEIGHT = "unit_weight"

DERIVED_FACTS: tuple[str, ...] = (FACT_NUTRITION, FACT_DIETARY, FACT_UNIT_WEIGHT)

#: Espécies de origem.
SOURCE_RECIPE = "recipe"
SOURCE_MANUAL = "manual"


class ManualAuditWithoutActor(ValueError):
    """Conferência manual sem quem assina. Fato manual sem autor não é conferência."""


def recipe_version_ref(recipe) -> str:
    """``Recipe.meta["version_ref"]`` da ficha, ou ``""`` quando ela não tem.

    Ausente significa ficha que nunca foi publicada pelo inventário (nasceu no
    seed ou no Admin). Não inventamos número: quem lê precisa saber que ali a
    defasagem é indetectável.
    """
    meta = getattr(recipe, "meta", None) or {}
    return str(meta.get("version_ref") or "").strip()


def build_recipe_stamp(recipe, *, value: Any = None) -> dict[str, Any]:
    """Carimbo de um fato derivado da ficha, pronto para gravar.

    ``value`` guarda o número que a derivação escreveu, quando o fato é um
    escalar (o peso da peça). Serve para reconhecer a edição à mão que veio
    DEPOIS: campo diferente do que o sistema deixou ali é gente, e gente tem
    precedência. Fatos compostos (nutrição, dieta) não o usam — eles têm o
    próprio sentinela dentro do valor.
    """
    stamp = {
        "source": SOURCE_RECIPE,
        "recipe_ref": str(getattr(recipe, "ref", "") or ""),
        "version_ref": recipe_version_ref(recipe),
        "by": "",
        "at": timezone.now().isoformat(),
    }
    if value is not None:
        stamp["value"] = value
    return stamp


def read_stamp(product, fact: str) -> dict[str, Any] | None:
    """O carimbo gravado para ``fact``, ou ``None`` quando nunca houve um."""
    metadata = getattr(product, "metadata", None) or {}
    provenance = metadata.get(PROVENANCE_KEY)
    if not isinstance(provenance, dict):
        return None
    stamp = provenance.get(fact)
    return dict(stamp) if isinstance(stamp, dict) else None


def with_stamp(metadata: dict[str, Any] | None, fact: str, stamp: dict[str, Any]) -> dict[str, Any]:
    """``metadata`` com o carimbo de ``fact`` trocado — cópia, nunca mutação.

    Devolve um dicionário novo porque quem chama compara com o anterior para
    decidir se precisa gravar; mutar no lugar apagaria a comparação.
    """
    new_metadata = dict(metadata or {})
    provenance = dict(new_metadata.get(PROVENANCE_KEY) or {})
    provenance[fact] = dict(stamp)
    new_metadata[PROVENANCE_KEY] = provenance
    return new_metadata


def stamp_moved(current: dict[str, Any] | None, incoming: dict[str, Any]) -> bool:
    """A origem mudou? Compara a ORIGEM, nunca o instante em que se carimbou.

    ``at`` muda a cada chamada, então incluí-lo faria toda gravação de ficha
    reescrever o produto sem nada ter mudado. O que importa é de onde o número
    veio: espécie, ficha, versão — e o ``value``, quando existe, porque uma
    ficha editada sem publicar versão nova muda o número sem mudar a versão, e
    um ``value`` parado travaria a próxima derivação.
    """
    if not current:
        return True
    return any(
        str(current.get(key) or "") != str(incoming.get(key) or "")
        for key in ("source", "recipe_ref", "version_ref", "value")
    )


def stamp_is_stale(stamp: dict[str, Any] | None, current_version_ref: str) -> bool:
    """Vencido = versão de origem diferente da versão atual da ficha. Exato.

    Sem carimbo não há o que comparar: a resposta é ``False`` e quem lê recebe
    ``needs_audit`` no lugar. Ficha sem versão carimba ``""`` contra ``""`` e
    também não vence — a leitura marca ``is_versioned=False`` para não passar
    por frescor conferido o que ninguém pode conferir.
    """
    if not stamp:
        return False
    return str(stamp.get("version_ref") or "") != str(current_version_ref or "")


def is_manual(stamp: dict[str, Any] | None) -> bool:
    return bool(stamp) and str(stamp.get("source") or "") == SOURCE_MANUAL


def is_derived(stamp: dict[str, Any] | None) -> bool:
    return bool(stamp) and str(stamp.get("source") or "") == SOURCE_RECIPE


def record_manual_audit(product, fact: str, *, actor: str, recipe=None) -> dict[str, Any]:
    """Assina um valor escrito à mão: quem conferiu, quando, e sobre qual versão.

    É o que torna a defasagem de um override manual exata. Sem isto, o número
    manual só pode ser reportado como "nunca conferido" — nada nele diz contra
    qual ficha ele foi checado.

    ``recipe`` opcional; quando omitido, busca a ficha ativa do SKU. Ficha
    inexistente ainda assina (o produto pode ser revendido), com
    ``version_ref`` vazio.

    Levanta :class:`ManualAuditWithoutActor` quando ninguém assina: conferência
    anônima é indistinguível de nenhuma conferência, e registrá-la daria a um
    número não conferido a aparência de conferido.
    """
    signer = str(actor or "").strip()
    if not signer:
        raise ManualAuditWithoutActor(
            "Conferência manual precisa de quem assina — número à mão sem autor "
            "não é conferência."
        )
    if fact not in DERIVED_FACTS:
        raise ValueError(f"Fato derivado desconhecido: {fact!r}.")

    if recipe is None:
        recipe = _active_recipe_for(product)

    stamp = {
        "source": SOURCE_MANUAL,
        "recipe_ref": str(getattr(recipe, "ref", "") or "") if recipe else "",
        "version_ref": recipe_version_ref(recipe) if recipe else "",
        "by": signer,
        "at": timezone.now().isoformat(),
    }
    product.metadata = with_stamp(product.metadata, fact, stamp)
    product.save(update_fields=["metadata"])
    logger.info(
        "derived_provenance: %s conferiu %s de %s sobre %s.",
        signer, fact, product.sku, stamp["version_ref"] or "ficha sem versão",
    )
    return stamp


def _active_recipe_for(product):
    try:
        from shopman.craftsman.services.recipes import get_active_recipe_for_output_sku
    except ImportError:
        return None
    return get_active_recipe_for_output_sku(product.sku)
