"""O ref da estação do KDS é o caminho da bancada (``/<ref>``), e URL de operador é
em inglês (CLAUDE.md). A migração ``backstage.0094`` renomeia os refs em português
que o seed gravava; sem redirect, porque pré go-live o endereço antigo morre junto.
"""

from __future__ import annotations

import importlib

import pytest
from django.apps import apps as django_apps

from shopman.backstage.models import KDSInstance

pytestmark = pytest.mark.django_db

migration = importlib.import_module("shopman.backstage.migrations.0094_kds_station_refs_in_english")


def _seed_portuguese():
    KDSInstance.objects.create(ref="lanches", name="Lanches", type="prep")
    KDSInstance.objects.create(ref="cafes", name="Cafés", type="prep")
    KDSInstance.objects.create(ref="encomendas", name="Encomendas", type="picking")
    KDSInstance.objects.create(ref="saida", name="Saída", type="expedition")


def test_os_refs_do_seed_viram_ingles_e_o_nome_fica():
    _seed_portuguese()

    migration.rename_to_english(django_apps, None)

    assert dict(KDSInstance.objects.values_list("ref", "name")) == {
        "snacks": "Lanches",
        "coffee": "Cafés",
        "preorders": "Encomendas",
        "exit": "Saída",
    }


def test_rodar_de_novo_nao_muda_nada():
    _seed_portuguese()
    migration.rename_to_english(django_apps, None)
    migration.rename_to_english(django_apps, None)

    assert set(KDSInstance.objects.values_list("ref", flat=True)) == {"snacks", "coffee", "preorders", "exit"}


def test_com_as_duas_estacoes_nada_se_apaga():
    KDSInstance.objects.create(ref="saida", name="Saída", type="expedition")
    KDSInstance.objects.create(ref="exit", name="Saída nova", type="expedition")

    migration.rename_to_english(django_apps, None)

    assert set(KDSInstance.objects.values_list("ref", flat=True)) == {"saida", "exit"}


def test_desfazer_volta_ao_portugues():
    _seed_portuguese()
    migration.rename_to_english(django_apps, None)

    migration.restore_portuguese(django_apps, None)

    assert set(KDSInstance.objects.values_list("ref", flat=True)) == {"lanches", "cafes", "encomendas", "saida"}
