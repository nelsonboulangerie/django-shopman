"""A estação "Expedição" do KDS virou "Saída" (decisão do dono, 26/09/2026).

"Expedição" é o fechamento de lote da Produção. A estação do KDS por onde o
pedido pronto sai ganha nome próprio, e a que o seed já tinha gravado é
renomeada por migração (``backstage.0076``), não por reseed.
"""

from __future__ import annotations

import importlib

import pytest
from django.apps import apps as django_apps

from shopman.backstage.models import KDSInstance

pytestmark = pytest.mark.django_db

migration = importlib.import_module("shopman.backstage.migrations.0076_estacao_saida")


def test_o_tipo_se_le_saida_e_o_valor_gravado_continua_expedition():
    station = KDSInstance.objects.create(ref="saida-t", name="Saída", type="expedition")
    assert station.get_type_display() == "Saída"


def test_a_estacao_do_seed_vira_saida():
    KDSInstance.objects.create(ref="expedicao", name="Expedição", type="expedition")

    migration.rename_station(django_apps, None)

    station = KDSInstance.objects.get(ref="saida")
    assert station.name == "Saída"
    assert not KDSInstance.objects.filter(ref="expedicao").exists()


def test_rodar_de_novo_nao_muda_nada():
    KDSInstance.objects.create(ref="expedicao", name="Expedição", type="expedition")
    migration.rename_station(django_apps, None)
    migration.rename_station(django_apps, None)

    assert list(KDSInstance.objects.values_list("ref", "name")) == [("saida", "Saída")]


def test_nome_escolhido_pelo_gestor_fica():
    KDSInstance.objects.create(ref="expedicao", name="Balcão de saída", type="expedition")

    migration.rename_station(django_apps, None)

    assert KDSInstance.objects.get(ref="saida").name == "Balcão de saída"


def test_com_as_duas_estacoes_nada_se_apaga():
    KDSInstance.objects.create(ref="expedicao", name="Expedição", type="expedition")
    KDSInstance.objects.create(ref="saida", name="Saída", type="expedition")

    migration.rename_station(django_apps, None)

    assert set(KDSInstance.objects.values_list("ref", flat=True)) == {"expedicao", "saida"}
