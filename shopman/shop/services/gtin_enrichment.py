"""API compartilhada de busca e rascunho por GTIN.

Este é o ponto neutro usado por Produto e Material. O mapeamento das fontes,
a prioridade NF-e/Cosmos/Open Food Facts e a fusão por campo continuam tendo
uma implementação única em ``product_enrichment``; esta fachada separa o
contrato de consulta dos destinos específicos sem criar adapter/Protocol para
uma única implementação externa.
"""

from shopman.shop.services.product_enrichment import (
    ALLERGENS_NOT_CURATED,
    COSMOS_PHOTO_LICENSE,
    FIELD_LABELS,
    NOTHING_FOUND,
    OFF_PHOTO_LICENSE,
    SOURCE_COSMOS,
    SOURCE_LABELS,
    SOURCE_NFE,
    SOURCE_OFF,
    EnrichmentSuggestion,
    build_suggestion,
    draft,
    fetch_cosmos,
    fetch_off,
    format_value,
    merge_into_metadata,
    pending_fields,
    suggestion_from_invoice,
)

__all__ = (
    "ALLERGENS_NOT_CURATED",
    "COSMOS_PHOTO_LICENSE",
    "EnrichmentSuggestion",
    "FIELD_LABELS",
    "NOTHING_FOUND",
    "OFF_PHOTO_LICENSE",
    "SOURCE_COSMOS",
    "SOURCE_LABELS",
    "SOURCE_NFE",
    "SOURCE_OFF",
    "build_suggestion",
    "draft",
    "fetch_cosmos",
    "fetch_off",
    "format_value",
    "merge_into_metadata",
    "pending_fields",
    "suggestion_from_invoice",
)
