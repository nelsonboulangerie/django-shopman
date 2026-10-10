"""Reputação da receita por VERSÃO, fatia 1: a leitura (relatório 06 §5.5).

O plano da fornada congela ``Recipe.meta["version_ref"]`` em
``WorkOrder.meta["_recipe_snapshot"]``; aqui se prova a segunda chave de
agrupamento: duas versões com fornadas diferentes dão agregados separados, a
fornada sem carimbo cai no balde "sem versão" (nunca numa versão), a
agregação por receita que os leitores de hoje recebem não muda, e os avisos
viajam no próprio dado.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe
from shopman.craftsman.services import recipe_book as craftsman

from shopman.backstage.models import DayClosing
from shopman.backstage.projections.recipe_book import build_recipe_entry, build_recipe_usage
from shopman.backstage.services.closing import (
    VERSION_CAVEATS,
    perform_day_closing,
    production_summary,
    production_summary_by_version,
)
from shopman.shop.models import QualityGrade

pytestmark = pytest.mark.django_db

TODAY = date.today()


def _ficha(ref: str, *, version_ref: str | None = None) -> Recipe:
    meta = {"version_ref": version_ref} if version_ref is not None else {}
    return Recipe.objects.create(ref=ref, name=ref, output_sku="PAO-V", batch_size=Decimal("10"), meta=meta)


def _publish(recipe: Recipe, version_ref: str) -> None:
    """O que ``publish_version`` faz com a ficha, no ponto que importa: o carimbo."""
    recipe.meta = {**(recipe.meta or {}), "version_ref": version_ref}
    recipe.save(update_fields=["meta"])


def _bake(recipe: Recipe, *, planned, started, finished, on: date = TODAY, finished_lines=None, wasted=None):
    wo = craft.plan(recipe, planned, date=on)
    craft.start(wo, quantity=started, expected_rev=0)
    craft.finish(wo, finished=finished_lines or finished, wasted=wasted, actor="test")
    return wo


def _two_versions_and_an_unversioned_batch() -> Recipe:
    """v1: duas fornadas (10→9, 10→8). v2: uma (12→12). Antes delas, uma sem carimbo (10→7)."""
    recipe = _ficha("pao-v")
    _bake(recipe, planned=10, started=10, finished=7)  # ficha nunca publicada: version_ref ""
    _publish(recipe, "pao-v@1")
    _bake(recipe, planned=10, started=10, finished=9)
    _bake(recipe, planned=10, started=10, finished=8)
    _publish(recipe, "pao-v@2")
    _bake(recipe, planned=12, started=12, finished=12)
    return recipe


# ── Fechamento do dia: segunda chave, a primeira intacta ─────────────────────


def test_two_versions_aggregate_separately_and_unversioned_stays_apart():
    _two_versions_and_an_unversioned_batch()

    summary = production_summary_by_version(TODAY)

    assert summary["caveats"] == list(VERSION_CAVEATS)
    rows = {row["version_ref"]: row for row in summary["rows"]}
    assert set(rows) == {"", "pao-v@1", "pao-v@2"}
    assert rows["pao-v@1"] | {"quality": None} == {
        "recipe_ref": "pao-v", "version_ref": "pao-v@1", "versioned": True, "output_sku": "PAO-V",
        "batches": 2, "executed": 2, "planned": 20, "finished": 17, "loss": 3, "quality": None,
    }
    assert (rows["pao-v@2"]["batches"], rows["pao-v@2"]["finished"], rows["pao-v@2"]["loss"]) == (1, 12, 0)
    unversioned = rows[""]
    assert unversioned["versioned"] is False
    assert (unversioned["batches"], unversioned["finished"], unversioned["loss"]) == (1, 7, 3)


def test_by_recipe_summary_is_unchanged_and_the_versions_add_up_to_it():
    _two_versions_and_an_unversioned_batch()

    by_recipe = production_summary(TODAY)

    # O payload que fechamento, pré-fechamento e DayClosing.data já recebiam.
    assert by_recipe == {
        "pao-v": {"recipe_ref": "pao-v", "output_sku": "PAO-V", "planned": 42, "finished": 36, "loss": 6},
    }
    rows = production_summary_by_version(TODAY)["rows"]
    for key in ("planned", "finished", "loss"):
        assert sum(row[key] for row in rows) == by_recipe["pao-v"][key]


def test_a_batch_planned_before_publishing_is_never_attributed_to_the_new_version():
    recipe = _ficha("pao-antes")
    wo = craft.plan(recipe, 10, date=TODAY)  # plano congela version_ref "" ...
    _publish(recipe, "pao-antes@1")  # ... e a publicação depois não o reescreve
    craft.start(wo, quantity=10, expected_rev=0)
    craft.finish(wo, finished=10, actor="test")

    (row,) = production_summary_by_version(TODAY)["rows"]
    assert (row["version_ref"], row["versioned"]) == ("", False)


def test_open_batches_count_as_planned_but_not_executed():
    recipe = _ficha("pao-aberto", version_ref="pao-aberto@1")
    _bake(recipe, planned=10, started=10, finished=9)
    craft.plan(recipe, 5, date=TODAY)

    (row,) = production_summary_by_version(TODAY)["rows"]
    assert (row["batches"], row["executed"], row["planned"], row["finished"]) == (2, 1, 15, 9)


def test_quality_mix_goes_to_the_version():
    recipe = _ficha("pao-qc", version_ref="pao-qc@3")
    _bake(
        recipe, planned=10, started=10, finished=None,
        finished_lines=[
            {"item_ref": "PAO-V", "quantity": "7", "quality_grade_ref": "standard"},
            {"item_ref": "PAO-V", "quantity": "2", "quality_grade_ref": "minimal"},
        ],
        wasted=[{"item_ref": "PAO-V", "quantity": "1"}],
    )

    (row,) = production_summary_by_version(TODAY)["rows"]
    assert row["version_ref"] == "pao-qc@3"
    assert row["quality"] == {"standard": 7, "minimal": 2}


def test_day_closing_persists_the_version_summary_next_to_the_recipe_summary(django_user_model):
    _two_versions_and_an_unversioned_batch()
    user = django_user_model.objects.create_user("o8-closing", password="pw")

    perform_day_closing(user=user, items=[], quantities_by_sku={}, closing_date=TODAY)

    data = DayClosing.objects.get(date=TODAY).data
    assert data["production_summary"] == production_summary(TODAY)
    assert data["production_by_version"]["caveats"] == list(VERSION_CAVEATS)
    assert {row["version_ref"] for row in data["production_by_version"]["rows"]} == {"", "pao-v@1", "pao-v@2"}


# ── Leitura por versão no intervalo (projection do inventário) ───────────────


def test_usage_reads_the_work_orders_by_version_newest_first():
    _two_versions_and_an_unversioned_batch()

    usage = build_recipe_usage("pao-v")

    assert [version.version_number for version in usage.versions] == [2, 1]
    v2, v1 = usage.versions
    assert (v1.version_ref, v1.label, v1.batches, v1.batches_display) == ("pao-v@1", "Versão 1", 2, "2 fornadas")
    assert (v1.planned_display, v1.finished_display, v1.loss_display) == ("20", "17", "3")
    assert (v1.yield_pct, v1.yield_display) == ("85", "85%")
    assert (v1.avg_loss, v1.avg_loss_display, v1.loss_pct_display) == ("1.5", "1,5 por fornada", "15%")
    assert v1.summary_display == "2 fornadas; aproveitamento médio 85%; perda média 1,5 por fornada"
    assert v1.started_assumed_batches == 0
    assert (v2.batches_display, v2.yield_display, v2.avg_loss_display) == ("1 fornada", "100%", "0 por fornada")


def test_usage_aproveitamento_is_realizado_over_previsto_not_planejado():
    """Decisão do dono (03/10): a base é o previsto. Planejado 12, previsto 10, realizado 9.

    Realizado ÷ previsto = 90%; a conta antiga (÷ planejado) dava 75%.
    """
    recipe = _ficha("pao-previsto", version_ref="pao-previsto@1")
    _bake(recipe, planned=12, started=10, finished=9)

    (version,) = build_recipe_usage("pao-previsto").versions

    assert (version.yield_pct, version.yield_display) == ("90", "90%")
    assert (version.loss_display, version.loss_pct_display) == ("1", "10%")
    assert version.summary_display == "1 fornada; aproveitamento médio 90%; perda média 1 por fornada"


def test_usage_says_when_the_previsto_was_assumed():
    """Fechamento sem abertura: o previsto foi assumido igual ao planejado, e o resumo diz."""
    recipe = _ficha("pao-assumido", version_ref="pao-assumido@1")
    _bake(recipe, planned=10, started=10, finished=10)
    wo = craft.plan(recipe, 10, date=TODAY)
    craft.finish(wo, finished=8, actor="test")  # sem abertura declarada

    (version,) = build_recipe_usage("pao-assumido").versions

    assert version.started_assumed_batches == 1
    assert version.yield_display == "90%"
    assert version.summary_display == (
        "2 fornadas; aproveitamento médio 90% (previsto assumido em 1 de 2); perda média 1 por fornada"
    )


def test_usage_puts_the_unstamped_batch_in_the_unversioned_bucket():
    _two_versions_and_an_unversioned_batch()

    usage = build_recipe_usage("pao-v")

    assert usage.unversioned is not None
    assert (usage.unversioned.is_versioned, usage.unversioned.version_number) == (False, None)
    assert (usage.unversioned.version_ref, usage.unversioned.label) == ("", "Sem versão")
    assert (usage.unversioned.batches, usage.unversioned.finished_display) == (1, "7")
    assert all(version.is_versioned for version in usage.versions)
    assert sum(version.batches for version in usage.versions) == 3


def test_usage_never_attributes_a_stamp_from_another_recipe():
    recipe = _ficha("pao-alheio", version_ref="outra-receita@4")
    _bake(recipe, planned=10, started=10, finished=10)

    usage = build_recipe_usage("pao-alheio")

    assert usage.versions == ()
    assert usage.unversioned is not None and usage.unversioned.batches == 1


def test_usage_counts_only_executed_batches_in_the_date_range():
    recipe = _ficha("pao-janela", version_ref="pao-janela@1")
    _bake(recipe, planned=10, started=10, finished=10, on=TODAY - timedelta(days=10))
    _bake(recipe, planned=10, started=10, finished=6, on=TODAY)
    craft.plan(recipe, 10, date=TODAY)  # planejada, não executada

    everything = build_recipe_usage("pao-janela")
    today_only = build_recipe_usage("pao-janela", date_from=TODAY, date_to=TODAY)

    assert everything.versions[0].batches == 2
    (today,) = today_only.versions
    assert (today.batches, today.finished_display, today.yield_display) == (1, "6", "60%")
    assert (today_only.date_from, today_only.date_to) == (TODAY.isoformat(), TODAY.isoformat())


def test_usage_carries_the_caveats_in_the_data():
    _ficha("pao-aviso", version_ref="pao-aviso@1")

    usage = build_recipe_usage("pao-aviso")

    codes = [caveat.code for caveat in usage.caveats]
    assert codes[:2] == ["loss_is_residual", "unversioned_not_attributed"]
    # Ficha sem bake_loss_pct: a perda de forno é o padrão da casa, estimativa.
    assert usage.bake_loss_basis == "house_default"
    assert "bake_loss_house_default" in codes
    assert all(caveat.message and "—" not in caveat.message for caveat in usage.caveats)
    assert usage.versions == () and usage.unversioned is None


def test_bake_loss_weighed_without_signature_is_still_an_estimate():
    Recipe.objects.create(
        ref="pao-pesado", name="Pesado", output_sku="PAO-P", batch_size=Decimal("10"),
        meta={"bake_loss_pct": "11", "bake_loss_source": "weighed"},
    )
    assert build_recipe_usage("pao-pesado").bake_loss_basis == "estimated"

    Recipe.objects.filter(ref="pao-pesado").update(meta={
        "bake_loss_pct": "11", "bake_loss_source": "weighed",
        "bake_loss_weighed_by": "maysa", "bake_loss_weighed_at": "2026-09-20",
    })
    usage = build_recipe_usage("pao-pesado")
    assert usage.bake_loss_basis == "weighed"
    assert not any(caveat.code.startswith("bake_loss_") for caveat in usage.caveats)


def test_quality_mix_follows_the_scale_not_the_volume():
    QualityGrade.objects.update_or_create(ref="excellent", defaults={"label": "Excelente", "rank": 40})
    QualityGrade.objects.update_or_create(ref="minimal", defaults={"label": "Mínima", "rank": 10})
    recipe = _ficha("pao-grau", version_ref="pao-grau@1")
    _bake(
        recipe, planned=10, started=10, finished=None,
        finished_lines=[
            {"item_ref": "PAO-V", "quantity": "2", "quality_grade_ref": "excellent"},
            {"item_ref": "PAO-V", "quantity": "6", "quality_grade_ref": "minimal"},
        ],
    )

    (version,) = build_recipe_usage("pao-grau").versions
    assert [(share.grade_ref, share.label, share.quantity_display, share.share_display) for share in version.quality] == [
        ("excellent", "Excelente", "2", "25%"),
        ("minimal", "Mínima", "6", "75%"),
    ]


def test_entry_detail_exposes_the_usage_for_a_published_entry():
    entry = craftsman.create_entry(ref="massa-o8", name="Massa O8", kind="bread", output_sku="MASSA-O8")
    craftsman.publish_version(craftsman.create_version(
        entry,
        formula={
            "anchor": {"kind": "flour"},
            "items": [{"sku": "FARINHA-O8", "name": "Farinha", "role": "flour", "quantity": 1000, "unit": "g"}],
            "parts": [],
        },
        yield_quantity="1", yield_unit="kg",
    ))
    ficha = Recipe.objects.get(ref="massa-o8")
    assert ficha.meta["version_ref"] == "massa-o8@1"
    assert build_recipe_entry("massa-o8").usage.versions == ()

    wo = craft.plan(ficha, 2, date=TODAY)
    craft.start(wo, quantity=2, expected_rev=0)
    craft.finish(wo, finished=2, actor="test")

    detail = build_recipe_entry("massa-o8")
    (version,) = detail.usage.versions
    assert (version.version_ref, version.version_number, version.batches) == ("massa-o8@1", 1, 1)
    assert detail.usage.unversioned is None
    assert [caveat.code for caveat in detail.usage.caveats][:2] == list(VERSION_CAVEATS)
