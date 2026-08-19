"""Tests for optional ref field helpers."""

from django.db import models

from shopman.utils.refs import FallbackRefField, RefField


def test_ref_field_accepts_ref_type_and_deconstructs_as_charfield():
    field = RefField(ref_type="SKU")

    assert getattr(field, "ref_type", None) == "SKU"
    assert field.max_length == 64
    # Sem default de db_index, igual ao CharField. Um default True aqui não
    # sobrevivia ao Field.clone() — que reconstrói pelo deconstruct(), e o
    # deconstruct se disfarça de CharField, que omite db_index quando é False.
    # Campo declarado db_index=False voltava True, e o makemigrations escrevia
    # índice que ninguém pediu.
    assert field.db_index is False
    assert field.deconstruct()[1] == "django.db.models.CharField"


def test_ref_field_db_index_survives_clone():
    for declarado in (True, False):
        assert RefField(ref_type="SKU", db_index=declarado).clone().db_index is declarado


def test_fallback_ref_field_is_plain_charfield_compatible():
    field = FallbackRefField(ref_type="ORDER_REF", max_length=50, db_index=False)

    assert isinstance(field, models.CharField)
    assert field.ref_type == "ORDER_REF"
    assert field.max_length == 50
    assert field.db_index is False
    assert field.deconstruct()[1] == "django.db.models.CharField"
