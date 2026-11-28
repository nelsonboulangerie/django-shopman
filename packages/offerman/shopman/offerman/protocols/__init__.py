"""Offerman protocols."""

from shopman.offerman.protocols.catalog import (
    CatalogBackend,
    ContextualPrice,
    PriceAdjustment,
    PricingBackend,
    ProductInfo,
    SkuValidation,
)
from shopman.offerman.protocols.cost import CostBackend, CostGapExplainer
from shopman.offerman.protocols.label import LabelAttributesProvider
from shopman.offerman.protocols.projection import (
    CatalogProjectionBackend,
    IncrementalCatalogProjectionBackend,
    ProjectedItem,
    ProjectionResult,
)

__all__ = [
    "CatalogBackend",
    "CatalogProjectionBackend",
    "ContextualPrice",
    "PricingBackend",
    "CostBackend",
    "CostGapExplainer",
    "IncrementalCatalogProjectionBackend",
    "LabelAttributesProvider",
    "PriceAdjustment",
    "ProductInfo",
    "ProjectedItem",
    "ProjectionResult",
    "SkuValidation",
]
