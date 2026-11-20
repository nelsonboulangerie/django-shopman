"""
Stockman signals — domain events emitted by stock operations.
"""

from __future__ import annotations

from django.dispatch import Signal

# Emitted when planned holds are materialized (transferred from planned → physical quant).
# Kwargs: hold_ids (list[str]), sku (str), target_date (date), to_position (Position)
holds_materialized = Signal()

# Emitted after ``release_expired`` releases holds whose deadline passed. The release
# is a bulk ``update`` (no ``post_save``), so this is the only announcement that the
# released quantity is available again.
# Kwargs: skus (list[str], sorted, one entry per SKU)
holds_expired = Signal()
