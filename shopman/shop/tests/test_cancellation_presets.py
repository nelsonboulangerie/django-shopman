"""Motivos de recusa e cancelamento (``Shop.cancellation_presets``).

O motivo vai ao cliente como ``Motivo: <motivo>.``: a régua aqui é a frase que
ele lê, e a lista aprovada pelo dono em 01/10/2026 (D4).
"""

from __future__ import annotations

import importlib

import pytest
from django.apps import apps
from django.core.exceptions import ValidationError

from shopman.shop.models import Shop
from shopman.shop.models.shop import (
    cancellation_preset_entries,
    cancellation_preset_reason_key,
    validate_cancellation_presets,
)
from shopman.shop.services import cancel_reasons
from shopman.shop.services.notification import _status_note

migration = importlib.import_module("shopman.shop.migrations.0085_motivos_de_recusa_aprovados")
keyed_migration = importlib.import_module("shopman.shop.migrations.0112_motivos_de_recusa_com_chave")

APPROVED_ORDER = [
    "Item indisponível no momento",
    "Sem um dos ingredientes hoje",
    "Pagamento não aprovado",
    "Pagamento não confirmado no prazo",
    "Endereço fora da nossa área de entrega",
    "Não conseguimos falar com você",
    "Alta demanda neste horário",
    "Sem entregador disponível neste horário",
    "Fora do horário de atendimento",
    "Você pediu o cancelamento",
    "Pedido em duplicidade",
]


class TestValidator:
    def test_plain_strings_stay_valid(self):
        validate_cancellation_presets(["Item indisponível no momento", "Fora do horário de atendimento"])

    def test_grouped_items_are_valid(self):
        validate_cancellation_presets([{"label": "Pagamento não aprovado", "group": "Pagamento"}])

    def test_reason_key_from_the_single_list_is_valid(self):
        validate_cancellation_presets(
            [{"label": "Você pediu o cancelamento", "group": "Cliente", "reason_key": "customer_request"}]
        )

    @pytest.mark.parametrize("key", ["", "customer_requested", "pix_expired", 3])
    def test_reason_key_outside_the_operator_list_is_refused(self, key):
        with pytest.raises(ValidationError, match="chave do motivo"):
            validate_cancellation_presets([{"label": "Item", "group": "Produto", "reason_key": key}])

    @pytest.mark.parametrize("label", ["Item acabou.", "Item acabou. ", "Acabou!", "Acabou…"])
    def test_trailing_punctuation_is_refused(self, label):
        with pytest.raises(ValidationError, match="Tire a pontuação do fim"):
            validate_cancellation_presets([label])
        with pytest.raises(ValidationError, match="Tire a pontuação do fim"):
            validate_cancellation_presets([{"label": label, "group": "Produto"}])

    @pytest.mark.parametrize(
        "value",
        [
            "Item indisponível",
            [{"group": "Produto"}],
            [{"label": "Item", "group": "Produto", "code": "X"}],
            [{"label": "Item", "group": 3}],
            [42],
        ],
    )
    def test_unknown_shapes_are_refused(self, value):
        with pytest.raises(ValidationError):
            validate_cancellation_presets(value)

    def test_model_full_clean_runs_the_validator(self, db):
        shop = Shop(name="Loja", cancellation_presets=["Item acabou."])
        with pytest.raises(ValidationError) as excinfo:
            shop.full_clean()
        assert "cancellation_presets" in excinfo.value.message_dict


class TestApprovedList:
    def test_seed_writes_the_approved_list_in_order(self):
        from config.management.commands.seed import CANCELLATION_PRESETS

        assert [label for _group, label in cancellation_preset_entries(CANCELLATION_PRESETS)] == APPROVED_ORDER
        assert "Problema técnico no preparo" not in APPROVED_ORDER

    def test_seed_and_migration_carry_the_same_list(self):
        from config.management.commands.seed import CANCELLATION_PRESETS

        assert keyed_migration.APPROVED_PRESETS == CANCELLATION_PRESETS
        # A lista de 01/10 (0085) é a mesma, sem as chaves.
        assert migration.APPROVED_PRESETS == [
            {"label": item["label"], "group": item["group"]} for item in CANCELLATION_PRESETS
        ]

    def test_every_approved_reason_has_a_key_of_the_single_list(self):
        from config.management.commands.seed import CANCELLATION_PRESETS

        for item in CANCELLATION_PRESETS:
            assert cancel_reasons.validation_message(item["reason_key"]) == "", item

    def test_the_customer_asked_maps_to_customer_request(self):
        from config.management.commands.seed import CANCELLATION_PRESETS

        assert cancellation_preset_reason_key(CANCELLATION_PRESETS, "Você pediu o cancelamento") == "customer_request"
        assert cancellation_preset_reason_key(CANCELLATION_PRESETS, "Texto que o operador escreveu") == ""

    def test_groups_follow_the_owner_split(self):
        groups = [group for group, _label in cancellation_preset_entries(migration.APPROVED_PRESETS)]
        assert groups == [
            "Produto", "Produto",
            "Pagamento", "Pagamento",
            "Endereço e contato", "Endereço e contato",
            "Capacidade", "Capacidade",
            "Horário",
            "Cliente",
            "Duplicidade",
        ]

    def test_every_reason_reads_as_one_clean_sentence_to_the_customer(self):
        validate_cancellation_presets(migration.APPROVED_PRESETS)
        for label in APPROVED_ORDER:
            note = _status_note(None, "order_rejected", label)
            assert note == f"Motivo: {label}."
            assert ".." not in note
            assert "—" not in note


class TestDataMigration:
    def _run(self):
        migration.apply_approved_presets(apps, None)

    def test_previous_seed_list_becomes_the_approved_list(self, db):
        shop = Shop.objects.create(name="Loja", cancellation_presets=list(migration.PREVIOUS_SEED_PRESETS))
        self._run()
        shop.refresh_from_db()
        assert shop.cancellation_presets == migration.APPROVED_PRESETS

    def test_empty_list_becomes_the_approved_list(self, db):
        shop = Shop.objects.create(name="Loja", cancellation_presets=[])
        self._run()
        shop.refresh_from_db()
        assert shop.cancellation_presets == migration.APPROVED_PRESETS

    def test_list_edited_by_the_operator_is_left_alone(self, db):
        edited = ["Item indisponível no momento", "Forno em manutenção hoje"]
        shop = Shop.objects.create(name="Loja", cancellation_presets=edited)
        self._run()
        shop.refresh_from_db()
        assert shop.cancellation_presets == edited

    def test_reordered_previous_list_counts_as_edited(self, db):
        reordered = list(reversed(migration.PREVIOUS_SEED_PRESETS))
        shop = Shop.objects.create(name="Loja", cancellation_presets=reordered)
        self._run()
        shop.refresh_from_db()
        assert shop.cancellation_presets == reordered

    def test_no_shop_is_a_no_op(self, db):
        Shop.objects.all().delete()
        self._run()
        assert not Shop.objects.exists()


class TestKeyedDataMigration:
    def _run(self):
        keyed_migration.add_reason_keys(apps, None)

    def test_approved_list_without_keys_gets_the_keys(self, db):
        shop = Shop.objects.create(name="Loja", cancellation_presets=list(migration.APPROVED_PRESETS))
        self._run()
        shop.refresh_from_db()
        assert shop.cancellation_presets == keyed_migration.APPROVED_PRESETS

    def test_operator_reason_is_left_alone_and_known_text_gets_its_key(self, db):
        edited = ["Forno em manutenção hoje", "Você pediu o cancelamento", {"label": "Outro", "group": "X"}]
        shop = Shop.objects.create(name="Loja", cancellation_presets=edited)
        self._run()
        shop.refresh_from_db()
        assert shop.cancellation_presets == [
            "Forno em manutenção hoje",
            {"label": "Você pediu o cancelamento", "reason_key": "customer_request"},
            {"label": "Outro", "group": "X"},
        ]

    def test_existing_key_is_kept(self, db):
        chosen = [{"label": "Você pediu o cancelamento", "group": "Cliente", "reason_key": "other"}]
        shop = Shop.objects.create(name="Loja", cancellation_presets=chosen)
        self._run()
        shop.refresh_from_db()
        assert shop.cancellation_presets == chosen
