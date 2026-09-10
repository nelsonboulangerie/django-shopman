"""Seed values are test data; signed shelf-life decisions are store data."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from shopman.craftsman.models import Recipe

pytestmark = pytest.mark.django_db


def test_seed_flush_preserves_a_signed_shelf_life_review(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "strong-seed-admin-password")
    call_command("seed", "--flush", "--profile", "qa", stdout=StringIO())
    cream = Recipe.objects.get(ref="creme-baunilha")
    cream.meta = {
        **(cream.meta or {}),
        "shelf_life_days": 4,
        "shelf_life_reviewed_days": 4,
        "shelf_life_reviewed_by": "responsavel-tecnica",
        "shelf_life_reviewed_at": "2026-09-10T12:00:00-03:00",
        "shelf_life_source": "manager_review",
    }
    cream.save(update_fields=("meta",))

    call_command("seed", "--flush", "--profile", "qa", stdout=StringIO())
    meta = Recipe.objects.get(ref="creme-baunilha").meta

    assert meta["shelf_life_days"] == 4
    assert meta["shelf_life_reviewed_days"] == 4
    assert meta["shelf_life_reviewed_by"] == "responsavel-tecnica"
    assert meta["shelf_life_source"] == "manager_review"
    assert "shelf_life_review_required" not in meta
