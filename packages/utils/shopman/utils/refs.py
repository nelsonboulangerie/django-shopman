"""Optional ref-aware model field helpers.

``shopman-refs`` is an official suite utility, but not every kernel must depend
on it to define a string reference field. Import ``RefField`` from here when a
model only needs CharField-compatible storage and should gain registry behavior
when ``shopman.refs`` is installed.
"""

from __future__ import annotations

from django.db.models import CharField


class FallbackRefField(CharField):
    """CharField-compatible fallback used when shopman-refs is not installed.

    Mirrors RefField, including the absence of a db_index default — see the
    warning in shopman.refs.fields.RefField.
    """

    def __init__(self, ref_type: str | None = None, **kwargs) -> None:
        kwargs.setdefault("max_length", 64)
        self.ref_type = ref_type
        super().__init__(**kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        path = "django.db.models.CharField"
        return name, path, args, kwargs


try:
    from shopman.refs.fields import RefField as RefField

    REFS_AVAILABLE = True
except ImportError:
    RefField = FallbackRefField
    REFS_AVAILABLE = False


__all__ = ["FallbackRefField", "REFS_AVAILABLE", "RefField"]
