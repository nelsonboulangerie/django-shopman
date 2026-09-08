"""check_integration_drift — a prontidão deixa de esperar alguém abrir a tela.

O que se prova aqui: provedor degradado vira ``OperatorAlert``; rodar de novo na
mesma janela não duplica; e a régua não grita crítico sobre o que é o estado
esperado do ambiente (ou decisão registrada do dono).
"""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.test import override_settings

from shopman.backstage.management.commands.check_integration_drift import ALERT_TYPE
from shopman.backstage.models import OperatorAlert
from shopman.backstage.services.integration_readiness import ProviderReadiness

pytestmark = pytest.mark.django_db

_TARGET = "shopman.backstage.services.integration_readiness.build_provider_readiness"


def _readiness(provider="efi_pix", status="warning", missing=("SHOPMAN_PIX_ADAPTER",)):
    return ProviderReadiness(
        provider=provider,
        label="Efí PIX",
        kind="payment_pix",
        environment="homologacao",
        status=status,
        message="homologacao: falta configuração: SHOPMAN_PIX_ADAPTER",
        missing=tuple(missing),
    )


def _run(*providers):
    with patch(_TARGET, return_value=tuple(providers)):
        call_command("check_integration_drift", stdout=StringIO())


# ── 4. provedor inseguro vira alerta, e só um por janela ─────────────────────


@override_settings(SHOPMAN_ENVIRONMENT="production")
def test_provedor_inseguro_em_producao_e_critico():
    _run(_readiness(status="error", missing=("EFI_SANDBOX_false",)))

    alert = OperatorAlert.objects.get(type=ALERT_TYPE)
    assert alert.severity == "critical"
    assert "configuração insegura" in alert.message
    assert "/admin/diagnostics/" in alert.message


@override_settings(SHOPMAN_ENVIRONMENT="production")
def test_rodar_de_novo_no_mesmo_dia_nao_duplica():
    inseguro = _readiness(status="error", missing=("EFI_SANDBOX_false",))
    _run(inseguro)
    _run(inseguro)
    _run(inseguro)

    assert OperatorAlert.objects.filter(type=ALERT_TYPE).count() == 1


@override_settings(SHOPMAN_ENVIRONMENT="production")
def test_alerta_reconhecido_tambem_segura_a_janela():
    inseguro = _readiness(status="error", missing=("EFI_SANDBOX_false",))
    _run(inseguro)
    OperatorAlert.objects.filter(type=ALERT_TYPE).update(acknowledged=True)
    _run(inseguro)

    assert OperatorAlert.objects.filter(type=ALERT_TYPE).count() == 1


@override_settings(SHOPMAN_ENVIRONMENT="production")
def test_pendencia_diferente_e_fato_novo():
    _run(_readiness(status="error", missing=("EFI_SANDBOX_false",)))
    _run(_readiness(status="error", missing=("EFI_SANDBOX_false", "EFI_WEBHOOK_TOKEN")))

    assert OperatorAlert.objects.filter(type=ALERT_TYPE).count() == 2


@override_settings(SHOPMAN_ENVIRONMENT="production")
def test_falta_de_configuracao_em_producao_e_erro_nao_critico():
    _run(_readiness(status="warning"))

    assert OperatorAlert.objects.get(type=ALERT_TYPE).severity == "error"


def test_provedor_pronto_nao_gera_alerta():
    _run(_readiness(status="ready", missing=()))

    assert not OperatorAlert.objects.filter(type=ALERT_TYPE).exists()


def test_dry_run_reporta_sem_alertar():
    with patch(_TARGET, return_value=(_readiness(status="error"),)):
        out = StringIO()
        call_command("check_integration_drift", "--dry-run", stdout=out)

    assert "efi_pix" in out.getvalue()
    assert not OperatorAlert.objects.filter(type=ALERT_TYPE).exists()


# ── 5. estado esperado do ambiente não vira crítico ──────────────────────────


@override_settings(SHOPMAN_ENVIRONMENT="staging")
def test_falta_de_configuracao_fora_de_producao_e_so_aviso():
    """O alpha roda `staging` com o Pix no simulador — escolha, não incêndio."""
    _run(_readiness(status="warning"))

    assert OperatorAlert.objects.get(type=ALERT_TYPE).severity == "warning"


@override_settings(SHOPMAN_ENVIRONMENT="staging")
def test_inseguranca_fora_de_producao_ainda_e_erro():
    """`sk_live_` num staging não é estado esperado de lugar nenhum."""
    _run(_readiness(status="error", missing=("STRIPE_SECRET_KEY_test",)))

    assert OperatorAlert.objects.get(type=ALERT_TYPE).severity == "error"


@override_settings(
    SHOPMAN_ENVIRONMENT="production",
    SHOPMAN_INTEGRATION_DRIFT_EXPECTED=("focus_nfe",),
)
def test_decisao_registrada_do_dono_nao_vira_critico():
    """NFC-e em homologação por escolha: lembrete semanal, não crítico diário."""
    _run(_readiness(provider="focus_nfe", status="error", missing=("FOCUS_NFE_ENVIRONMENT_producao",)))

    alert = OperatorAlert.objects.get(type=ALERT_TYPE)
    assert alert.severity == "warning"
    assert "decisão da casa" in alert.message


@override_settings(
    SHOPMAN_ENVIRONMENT="production",
    SHOPMAN_INTEGRATION_DRIFT_EXPECTED="focus_nfe, efi_pix",
)
def test_lista_de_decisoes_aceita_texto_separado_por_virgula():
    _run(_readiness(provider="efi_pix", status="error", missing=("EFI_SANDBOX_false",)))

    assert OperatorAlert.objects.get(type=ALERT_TYPE).severity == "warning"


@override_settings(
    SHOPMAN_ENVIRONMENT="production",
    SHOPMAN_INTEGRATION_DRIFT_EXPECTED=("focus_nfe",),
)
def test_decisao_registrada_nao_cobre_o_provedor_vizinho():
    _run(_readiness(provider="efi_pix", status="error", missing=("EFI_SANDBOX_false",)))

    assert OperatorAlert.objects.get(type=ALERT_TYPE).severity == "critical"


# ── o comando roda de verdade, contra a prontidão real ───────────────────────


def test_comando_roda_contra_a_prontidao_real():
    """Sem mock: prova que o comando existe, resolve e não explode no worker."""
    out = StringIO()
    call_command("check_integration_drift", "--dry-run", stdout=out)

    assert "integration_drift:" in out.getvalue()
