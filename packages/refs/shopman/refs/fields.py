"""
RefField — CharField subclass for string refs.
"""

from __future__ import annotations

from django.db.models import CharField


class RefField(CharField):
    """
    A CharField with ref-aware defaults and optional RefSourceRegistry integration.

    Usage:
        ref = RefField()                 # identity ref — max_length=64
        sku = RefField(ref_type="SKU")   # registers in RefSourceRegistry for cascade ops

    Migration impact:
        RefField deconstructs as django.db.models.CharField, so converting an
        existing CharField produces no migration. ref_type is runtime-only
        metadata held by RefSourceRegistry, never DB schema.

    ⚠️ No db_index default, deliberately. This class used to default it to True,
    and that default did not survive a round-trip: deconstruct() masquerades as
    CharField, which omits db_index when it equals Django's default (False), and
    Field.clone() — used by makemigrations — rebuilds through __init__, where the
    True default was reapplied. A field declared db_index=False therefore came
    back True, and makemigrations kept writing indexes nobody asked for, including
    duplicates on unique fields. Any index this field needs is declared at the
    call site or in Meta.indexes, where it is visible.
    """

    def __init__(self, ref_type: str | None = None, **kwargs) -> None:
        kwargs.setdefault("max_length", 64)
        self.ref_type = ref_type
        super().__init__(**kwargs)

    def contribute_to_class(self, cls, name: str, private_only: bool = False) -> None:
        super().contribute_to_class(cls, name, private_only=private_only)
        from shopman.refs.registry import _ref_source_registry
        _ref_source_registry.register_lazy(
            app_label_model=f"{cls._meta.app_label}.{cls.__name__}",
            field_name=name,
            ref_type=self.ref_type,
        )

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        # Always masquerade as plain CharField: ref_type is runtime-only metadata
        # managed by RefSourceRegistry, not DB schema. This ensures CharField→RefField
        # conversions produce zero migration churn regardless of ref_type.
        path = "django.db.models.CharField"
        return name, path, args, kwargs
