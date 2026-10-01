"""O certificado avisa ANTES de vencer — e cada marco avisa uma vez só.

Até aqui a prontidão só acusava ``expired``: o aviso chegava com o Pix já parado
ou com as notas de compra já sem chegar. E o e-CNPJ A1 de Compras nem entrava na
leitura periódica, porque ``check_integration_drift`` só olhava a prontidão do
balcão.
"""

from __future__ import annotations

import base64
from datetime import UTC, date, datetime, timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from shopman.backstage.management.commands.check_integration_drift import (
    ALERT_TYPE,
    CERTIFICATE_ALERT_TYPE,
)
from shopman.backstage.models import OperatorAlert
from shopman.backstage.services.integration_readiness import (
    build_monitored_readiness,
    efi_pix_readiness,
    purchase_nfe_readiness,
)
from shopman.backstage.tests.certificate_fixtures import synthetic_certificate

pytestmark = pytest.mark.django_db

_READER = "shopman.shop.adapters.purchase_invoice_nfe.read_invoice"


def _purchase(*, start=-1, end=1, now=None) -> dict:
    data = base64.b64encode(synthetic_certificate(pfx=True, start=start, end=end, now=now)).decode()
    return {"certificate_pfx_base64": data, "certificate_password": ""}


def _brasilia(hour, minute, second=0, *, day=30, month=9):
    """Um instante no relógio da loja (``TIME_ZONE``), em 2026.

    O padrão é 30/09/2026, o dia em que o CI ficou vermelho perto da meia-noite.
    Entre 21h e 24h de Brasília a data UTC já é a do dia seguinte: é a janela em
    que contar dias em UTC mentiria para o gestor.

    Devolve o instante em UTC, como o ``timezone.now()`` de verdade: congelar
    com o fuso de Brasília embutido faria ``now.date()`` acertar por acaso e
    esconderia justamente o defeito que estes testes procuram.
    """
    return timezone.make_aware(datetime(2026, month, day, hour, minute, second)).astimezone(UTC)


def _run(*, at=None) -> None:
    if at is None:
        call_command("check_integration_drift", stdout=StringIO())
        return
    with patch("django.utils.timezone.now", return_value=at):
        call_command("check_integration_drift", stdout=StringIO())


def _certificate_alerts():
    return list(OperatorAlert.objects.filter(type=CERTIFICATE_ALERT_TYPE).order_by("created_at"))


# ── cada marco ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("hour,minute", [(12, 0), (23, 30)], ids=["12h00", "23h30"])
@pytest.mark.parametrize(
    "end,severity,phrase",
    [
        (30, "warning", "daqui a 30 dias"),
        (20, "warning", "daqui a 20 dias"),
        (15, "warning", "daqui a 15 dias"),
        (7, "warning", "daqui a 7 dias"),
        (3, "critical", "daqui a 3 dias"),
        (1, "critical", "vence amanhã"),
    ],
)
def test_cada_marco_de_antecedencia_vira_um_alerta(end, severity, phrase, hour, minute):
    # Um relógio só: o certificado nasce e o comando roda no MESMO instante. Com
    # dois (o da fixture e o do comando), a meia-noite local entre eles fazia o
    # "daqui a 7 dias" sair 6 (CI do #1312, perto das 00:00 de Brasília).
    now = _brasilia(hour, minute)
    with override_settings(SHOPMAN_PURCHASE_NFE=_purchase(end=end, now=now)):
        _run(at=now)

    [alert] = _certificate_alerts()
    assert alert.severity == severity
    assert alert.message.startswith("O e-CNPJ A1 de Compras vence ")
    assert phrase in alert.message
    # A data é a do calendário da loja: às 23:30 de 30/09 o vencimento em 7 dias
    # é 07/10, embora em UTC já seja 08/10.
    expires_on = date(2026, 9, 30) + timedelta(days=end)
    assert f"{expires_on:%d/%m/%Y}" in alert.message
    assert "Renove o e-CNPJ A1" in alert.message


def test_a_contagem_e_pelo_calendario_da_loja_entre_21h_e_24h():
    """23:30 de 30/09 em Brasília já é 01/10 em UTC: os dias contam pelo da loja.

    O certificado vence às 20:00 de 07/10 (23:00 UTC). Pelo calendário da loja
    faltam 7 dias; contando datas UTC (01/10 a 07/10) seriam 6.
    """
    now = _brasilia(23, 30)
    expires_at = _brasilia(20, 0, day=7, month=10)
    with override_settings(SHOPMAN_PURCHASE_NFE=_purchase(end=7, now=expires_at - timedelta(days=7))):
        _run(at=now)

    [alert] = _certificate_alerts()
    assert alert.message.startswith("O e-CNPJ A1 de Compras vence em 07/10/2026, daqui a 7 dias.")


def test_passada_a_meia_noite_o_dia_ja_virou():
    """A mensagem que o CI do #1312 viu era a CERTA para o instante em que rodou.

    O certificado nasceu às 23:59:59 de 30/09 e o comando rodou às 00:00:01 de
    01/10: dali até 07/10 são 6 dias. O defeito era do teste, que lia o relógio
    duas vezes; o produto conta o calendário da loja.
    """
    born = _brasilia(23, 59, 59)
    with override_settings(SHOPMAN_PURCHASE_NFE=_purchase(end=7, now=born)):
        _run(at=_brasilia(0, 0, 1, day=1, month=10))

    [alert] = _certificate_alerts()
    assert alert.message.startswith("O e-CNPJ A1 de Compras vence em 07/10/2026, daqui a 6 dias.")


def test_longe_do_vencimento_nao_avisa():
    with override_settings(SHOPMAN_PURCHASE_NFE=_purchase(end=40)):
        _run()

    assert _certificate_alerts() == []


def test_vencido_e_critico_e_diz_que_venceu(tmp_path):
    path = tmp_path / "efi.pem"
    path.write_bytes(synthetic_certificate(start=-10, end=-1))
    with override_settings(SHOPMAN_EFI={"certificate_path": str(path)}):
        _run()

    [alert] = _certificate_alerts()
    assert alert.severity == "critical"
    assert alert.message.startswith("O certificado da Efí (Pix) venceu em ")
    assert "o Pix não gera cobrança" in alert.message
    assert "EFI_CERTIFICATE_PEM_BASE64" in alert.message


# ── dedupe por certificado + marco ───────────────────────────────────────────


def test_o_marco_nao_dispara_todo_dia_e_o_seguinte_dispara():
    now = timezone.now()
    with override_settings(SHOPMAN_PURCHASE_NFE=_purchase(end=30, now=now)):
        _run(at=now)
        _run(at=now + timedelta(days=1))  # ainda no marco de 30 dias
        _run(at=now + timedelta(days=2))
        assert len(_certificate_alerts()) == 1

        OperatorAlert.objects.filter(type=CERTIFICATE_ALERT_TYPE).update(acknowledged=True)
        _run(at=now + timedelta(days=3))
        assert len(_certificate_alerts()) == 1, "reconhecer não reabre o marco"

        # A chave do marco "3" está contida na do "30" se não tiver fecho.
        _run(at=now + timedelta(days=27))
        _run(at=now + timedelta(days=28))
        _run(at=now + timedelta(days=31))
        _run(at=now + timedelta(days=32))

    alerts = _certificate_alerts()
    assert [a.severity for a in alerts] == ["warning", "critical", "critical"]
    assert "daqui a 30 dias" in alerts[0].message
    assert "daqui a 3 dias" in alerts[1].message
    assert "venceu em" in alerts[2].message


def test_certificado_renovado_recomeca_os_marcos():
    with override_settings(SHOPMAN_PURCHASE_NFE=_purchase(end=10)):
        _run()
    with override_settings(SHOPMAN_PURCHASE_NFE=_purchase(end=12)):
        _run()

    assert len(_certificate_alerts()) == 2


# ── Compras entra na leitura periódica ───────────────────────────────────────


def test_compras_ligada_entra_na_checagem_periodica():
    with override_settings(
        SHOPMAN_PURCHASE_INVOICE_READER=_READER,
        SHOPMAN_PURCHASE_NFE=_purchase(start=-10, end=-1),
    ):
        _run()

    drift = OperatorAlert.objects.filter(type=ALERT_TYPE, message__contains="purchase_nfe")
    assert drift.exists(), "o certificado vencido de Compras precisa virar alerta de prontidão"
    assert "PURCHASE_NFE_CERTIFICATE_expired" in drift.first().message


def test_compras_desligada_nao_vira_pendencia():
    with override_settings(SHOPMAN_PURCHASE_INVOICE_READER="", SHOPMAN_PURCHASE_NFE={}):
        providers = {item.provider for item in build_monitored_readiness()}
    assert "purchase_nfe" not in providers


# ── a data aparece na prontidão ──────────────────────────────────────────────


def test_a_prontidao_mostra_a_data_de_vencimento(tmp_path):
    path = tmp_path / "efi.pem"
    # Um relógio só (ver o teste dos marcos): a data esperada sai do MESMO
    # instante em que o certificado nasce.
    now = timezone.now()
    path.write_bytes(synthetic_certificate(end=45, now=now))
    expires_on = timezone.localtime(now + timedelta(days=45)).date()
    with override_settings(SHOPMAN_EFI={"certificate_path": str(path)}):
        projection = efi_pix_readiness().as_projection()
    assert projection["certificate_expires_on"] == expires_on.isoformat()
    assert f"Certificado válido até {expires_on:%d/%m/%Y}." in projection["message"]

    with override_settings(SHOPMAN_PURCHASE_NFE=_purchase(end=45, now=now)):
        projection = purchase_nfe_readiness().as_projection()
    assert projection["certificate_expires_on"] == expires_on.isoformat()


def test_sem_certificado_a_projecao_nao_inventa_data():
    with override_settings(SHOPMAN_EFI={}):
        projection = efi_pix_readiness().as_projection()
    assert "certificate_expires_on" not in projection
