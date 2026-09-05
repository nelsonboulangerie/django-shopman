"""Leitura e escrita de atributos de produto, validadas contra o registro.

Este módulo é **a única porta** para ``Product.metadata["attributes"]``. Não há
``product.attr()``: o Product é do Core e o registro é configuração do tenant —
pendurar o acesso no model faria o Offerman depender do ``shop``, que é
exatamente a dependência que a casa não tem.

    from shopman.shop.services import attributes

    attributes.get(product, "sabor")                      # "doce" | None
    attributes.set(product, "sabor", "doce", source="ai")  # valida e grava
    attributes.get_many(products, "natureza")              # {sku: valor}

A validação é por tipo e por opção: gravar ``sabor="azedo"`` levanta
``AttributeError_`` porque "azedo" não está nas opções da definição. Atributo
que não existe no registro também é erro — é o que impede "cor", "Cor" e "côr"
de conviverem.

**Proveniência.** Todo valor gravado por aqui deixa
``metadata["attributes"][ref] = {"source": ..., "reviewed": ...}``, mesmo quando
o valor mora numa coluna ou numa chave legada. Valor sem registro de
proveniência lê como ``manual``: se está lá e ninguém disse o contrário, foi
gente que pôs.

⚠️ A proveniência é a **palavra final** sobre quem pode sobrescrever: o
``dietary_from_recipe`` só recalcula alérgenos e dieta quando o valor gravado
veio dele (``source="recipe"``). O sentinela ``dietary_auto_filled``, que dizia
isso à parte, morreu no WP de rename — duas fontes para a mesma verdade era
exatamente como ela divergia.
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.cache import cache

from shopman.shop.models.attributes import (
    METADATA_ROOT,
    AttributeDefinition,
    AttributeSource,
    AttributeType,
)

logger = logging.getLogger(__name__)

CACHE_KEY = "shopman_attribute_definitions"
CACHE_TIMEOUT = 60 * 60  # invalidado no save/delete da definição


class AttributeError_(ValueError):
    """Ref desconhecida, ou valor que a definição recusa.

    O sublinhado evita sombrear o ``AttributeError`` do Python, que significa
    outra coisa inteiramente e apareceria em ``except`` alheios.
    """


# --- o registro ------------------------------------------------------------


def registry() -> tuple[AttributeDefinition, ...]:
    """Definições ativas, em cache de uma hora (invalidado no save)."""
    cached = cache.get(CACHE_KEY)
    if cached is None:
        cached = tuple(AttributeDefinition.objects.active().order_by("ordering", "ref"))
        cache.set(CACHE_KEY, cached, CACHE_TIMEOUT)
    return cached


def definition(ref: str) -> AttributeDefinition | None:
    """A definição ativa de ``ref``, ou ``None``."""
    for d in registry():
        if d.ref == ref:
            return d
    return None


def require(ref: str) -> AttributeDefinition:
    """Como ``definition``, mas levanta em vez de devolver ``None``."""
    found = definition(ref)
    if found is None:
        known = ", ".join(d.ref for d in registry()) or "(registro vazio)"
        raise AttributeError_(f"Atributo '{ref}' não existe no registro. Conheço: {known}.")
    return found


def for_purpose(purpose: str) -> tuple[AttributeDefinition, ...]:
    """Definições ativas que servem a ``purpose`` (facet, rule, feed, …)."""
    return tuple(d for d in registry() if d.serves(purpose))


def invalidate_cache(sender=None, **kwargs) -> None:
    """Handler de ``post_save``/``post_delete`` da definição."""
    cache.delete(CACHE_KEY)


# --- leitura ---------------------------------------------------------------


def get(product, ref: str, default: Any = None) -> Any:
    """Valor de ``ref`` em ``product``, tipado, ou ``default``.

    Lê de onde a definição disser: do ``attributes``, de uma coluna do Product
    ou de uma chave legada do ``metadata``. Valor guardado que não passa mais na
    definição (opção removida, por exemplo) lê como ausente — o registro é a
    verdade, e um valor órfão não deve vazar para uma regra.
    """
    d = require(ref)
    raw = _read_raw(product, d)
    if raw is None:
        return default
    try:
        return _coerce(d, raw)
    except AttributeError_:
        logger.warning(
            "attributes: valor fora da definição em %s.%s (%r) — lendo como ausente.",
            getattr(product, "sku", "?"), ref, raw,
        )
        return default


def get_all(product) -> dict[str, Any]:
    """Todos os atributos definidos que ``product`` tem preenchidos."""
    out: dict[str, Any] = {}
    for d in registry():
        value = get(product, d.ref)
        if value is not None:
            out[d.ref] = value
    return out


def get_many(products, ref: str) -> dict[str, Any]:
    """``{sku: valor}`` para uma coleção de produtos — uma definição, N produtos.

    Existe para o motor de sugestão, que pergunta o mesmo atributo de dezenas de
    candidatos e não deve pagar um ``require()`` por produto.
    """
    d = require(ref)
    out: dict[str, Any] = {}
    for product in products:
        raw = _read_raw(product, d)
        if raw is None:
            continue
        try:
            out[product.sku] = _coerce(d, raw)
        except AttributeError_:
            continue
    return out


def source(product, ref: str) -> str:
    """Proveniência do valor: manual, ai, derived ou recipe."""
    require(ref)
    record = _provenance_record(product, ref)
    return str(record.get("source") or AttributeSource.MANUAL)


def is_reviewed(product, ref: str) -> bool:
    """Se um valor proposto pela IA já foi aprovado pelo gestor.

    Valor de proveniência ``manual`` é revisado por definição: o gestor é quem
    escreveu.
    """
    # Usa o MESMO default de `source()` de propósito: valor sem proveniência
    # registrada lê como `manual` nas duas funções. Quando elas divergiam, o
    # mesmo valor era "escrito pelo gestor" e "não revisado" ao mesmo tempo.
    if source(product, ref) == AttributeSource.MANUAL:
        return True
    return bool(_provenance_record(product, ref).get("reviewed", False))


# --- escrita ---------------------------------------------------------------


def set(  # noqa: A001 — o verbo é o certo; o módulo é o namespace
    product,
    ref: str,
    value: Any,
    *,
    source: str = AttributeSource.MANUAL,
    reviewed: bool | None = None,
    save: bool = True,
) -> Any:
    """Valida ``value`` contra a definição e grava. Devolve o valor tipado.

    ``save=False`` deixa o produto sujo na memória, para quem grava em lote.
    """
    d = require(ref)
    if str(source) not in set_of_sources():
        raise AttributeError_(
            f"Proveniência '{source}' não existe. Use: {', '.join(sorted(set_of_sources()))}."
        )

    typed = _coerce(d, value) if value is not None else None

    column = d.column_field
    metadata_key = d.metadata_key
    metadata = dict(product.metadata or {})
    root = dict(metadata.get(METADATA_ROOT) or {})

    # 1. O valor, onde a definição disser.
    if column:
        setattr(product, column, typed)
    elif metadata_key:
        if typed is None:
            metadata.pop(metadata_key, None)
        else:
            metadata[metadata_key] = typed

    # 2. A proveniência, sempre no mesmo lugar — é o que permite ao Admin
    #    listar "proposto pela IA, não revisado" sem saber onde cada valor
    #    está guardado. Para o storage padrão, o valor mora no mesmo registro.
    if typed is None:
        root.pop(ref, None)
    else:
        record: dict[str, Any] = {
            "source": str(source),
            "reviewed": (
                bool(reviewed)
                if reviewed is not None
                else str(source) == AttributeSource.MANUAL
            ),
        }
        if column is None and metadata_key is None:
            record["value"] = typed
        root[ref] = record

    if root:
        metadata[METADATA_ROOT] = root
    else:
        metadata.pop(METADATA_ROOT, None)

    product.metadata = metadata

    if save:
        update_fields = ["metadata"]
        if column:
            update_fields.append(column)
        product.save(update_fields=update_fields)

    return typed


def clear(product, ref: str, *, save: bool = True) -> None:
    """Apaga o valor e a proveniência de ``ref``."""
    set(product, ref, None, save=save)


def set_of_sources() -> frozenset[str]:
    return frozenset(AttributeSource.values)


# --- internals -------------------------------------------------------------


def _provenance_record(product, ref: str) -> dict:
    root = (product.metadata or {}).get(METADATA_ROOT) or {}
    record = root.get(ref)
    return dict(record) if isinstance(record, dict) else {}


def _read_raw(product, d: AttributeDefinition) -> Any:
    """O valor cru, de onde quer que a definição diga que ele mora."""
    column = d.column_field
    if column:
        return getattr(product, column, None)

    metadata = product.metadata or {}
    metadata_key = d.metadata_key
    if metadata_key:
        return metadata.get(metadata_key)

    record = (metadata.get(METADATA_ROOT) or {}).get(d.ref)
    if isinstance(record, dict):
        return record.get("value")
    return None


def _coerce(d: AttributeDefinition, raw: Any) -> Any:
    """Converte e valida ``raw`` conforme o tipo da definição."""
    if d.type == AttributeType.CHOICE:
        value = str(raw)
        if value not in d.option_values():
            raise AttributeError_(
                f"'{value}' não é opção de '{d.ref}'. Use: {', '.join(d.option_values())}."
            )
        return value

    if d.is_list:
        # `str` é uma sequência, e aceitá-la faria "doce" virar
        # ["d","o","c","e"] em silêncio. Lista é lista.
        if isinstance(raw, str) or not isinstance(raw, (list, tuple)):
            raise AttributeError_(f"'{d.ref}' é lista: passe uma lista.")
        allowed = d.option_values() if d.is_choice else ()
        values: list[str] = []
        for item in raw:
            value = str(item).strip()
            if not value:
                continue
            if allowed and value not in allowed:
                raise AttributeError_(
                    f"'{value}' não é opção de '{d.ref}'. Use: {', '.join(allowed)}."
                )
            if value not in values:
                values.append(value)
        return values

    if d.type == AttributeType.NUMBER:
        if isinstance(raw, bool):
            raise AttributeError_(f"'{d.ref}' é número, não Sim/Não.")
        try:
            number = float(raw)
        except (TypeError, ValueError) as exc:
            raise AttributeError_(f"'{raw}' não é número para '{d.ref}'.") from exc
        return int(number) if number.is_integer() else number

    if d.type == AttributeType.BOOLEAN:
        if isinstance(raw, bool):
            return raw
        raise AttributeError_(f"'{d.ref}' é Sim/Não: passe True ou False.")

    value = str(raw).strip()
    if not value:
        raise AttributeError_(f"'{d.ref}' é texto e não aceita vazio.")
    return value


# --- o seam com o Core ------------------------------------------------------


class LabelAttributesProvider:
    """O que o formulário de rótulo do Offerman usa para ler e escrever.

    O Offerman é Core e **não importa o orquestrador** — mas os campos de
    alérgeno, dieta e porções são vocabulário do tenant, que mora aqui. O
    pacote pergunta por este provedor
    (``OFFERMAN["LABEL_ATTRIBUTES_PROVIDER"]``) do mesmo jeito que o Craftsman
    pergunta as variantes de lifecycle: sem provedor, sem campo, e o Core segue
    de pé sozinho.

    ``set`` levanta ``ValueError`` quando o valor não passa na definição — é o
    que faz um alérgeno digitado errado ser recusado no Admin, com mensagem, em
    vez de virar um rótulo que mente.
    """

    def get(self, product, ref: str):
        try:
            return get(product, ref)
        except AttributeError_:
            # Atributo que saiu do registro: o campo aparece vazio em vez de a
            # tela inteira quebrar por causa de uma configuração.
            logger.warning("label provider: atributo '%s' não está no registro.", ref)
            return None

    def set(self, product, ref: str, value) -> None:
        set(product, ref, value, source=AttributeSource.MANUAL, save=False)


def label_attributes_provider() -> LabelAttributesProvider:
    """Fábrica apontada por ``OFFERMAN["LABEL_ATTRIBUTES_PROVIDER"]``."""
    return LabelAttributesProvider()
