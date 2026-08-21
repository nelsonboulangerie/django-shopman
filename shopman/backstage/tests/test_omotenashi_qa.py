from __future__ import annotations

import json
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import CommandError, call_command

from shopman.backstage.services.omotenashi_qa import OmotenashiQACheck, OmotenashiQAReport


def test_omotenashi_qa_command_outputs_json():
    report = OmotenashiQAReport(
        generated_at="2026-05-05T12:00:00+00:00",
        checks=(
            OmotenashiQACheck(
                id="mobile.catalog.browse",
                surface="storefront",
                viewport="mobile 375x812",
                persona="cliente anonimo",
                title="Explorar cardapio",
                url="/menu/",
                expectation="Menu sem dead end.",
                evidence="sku=CROISSANT",
                status="ready",
            ),
        ),
    )
    stdout = StringIO()

    with patch(
        "shopman.backstage.management.commands.omotenashi_qa.build_omotenashi_qa_report",
        return_value=report,
    ):
        call_command("omotenashi_qa", json=True, stdout=stdout)

    data = json.loads(stdout.getvalue())
    assert data["status"] == "ready"
    assert data["counts"] == {"missing": 0, "ready": 1, "total": 1}
    assert data["checks"][0]["url"] == "/menu/"


def test_omotenashi_qa_strict_fails_when_seed_evidence_is_missing():
    report = OmotenashiQAReport(
        generated_at="2026-05-05T12:00:00+00:00",
        checks=(
            OmotenashiQACheck(
                id="mobile.payment.pix_expired",
                surface="storefront",
                viewport="mobile 375x812",
                persona="cliente distraido",
                title="PIX expirado",
                url="/tracking/ORDER_REF",
                expectation="Tela deve oferecer recuperacao.",
                evidence="-",
                status="missing",
                blocker="Rode make seed.",
            ),
        ),
    )

    with patch(
        "shopman.backstage.management.commands.omotenashi_qa.build_omotenashi_qa_report",
        return_value=report,
    ):
        with pytest.raises(CommandError):
            call_command("omotenashi_qa", strict=True, stdout=StringIO())


# ── A matriz precisa APONTAR para as superfícies, não só descrevê-las ────────


@pytest.mark.django_db
def test_every_check_has_a_navigable_url_when_the_surfaces_are_configured(settings):
    """Com as bases configuradas, NENHUM check pode nascer com ``url`` vazia.

    Seis dos onze checks — fila de pedidos, KDS, produção, PDV, fechamento do dia
    e caixa — saíam com ``url = ""`` porque as bases das superfícies de operador
    não estavam ligadas em lugar nenhum. O runner de browser pulava os seis em
    silêncio, e o gate ficava verde anunciando cobertura de onze telas enquanto
    nenhum browser tocava nas que movimentam dinheiro.

    Este teste é o par do ``--strict`` (que agora reprova em check pulado): ele
    prova que a matriz sabe construir a URL quando a base existe. Sem ele, o
    gate poderia ficar vermelho para sempre por um builder quebrado, e a saída
    fácil seria afrouxar o strict de novo.
    """
    settings.SHOPMAN_STOREFRONT_BASE_URL = "http://127.0.0.1:3100"
    settings.SHOPMAN_ORDERS_BASE_URL = "http://127.0.0.1:3101"
    settings.SHOPMAN_KDS_BASE_URL = "http://127.0.0.1:3102"
    settings.SHOPMAN_PRODUCTION_BASE_URL = "http://127.0.0.1:3103"
    settings.SHOPMAN_POS_BASE_URL = "http://127.0.0.1:3104"

    from shopman.backstage.services.omotenashi_qa import build_omotenashi_qa_report

    report = build_omotenashi_qa_report()

    sem_url = [check.id for check in report.checks if not check.url.strip()]
    assert not sem_url, f"checks sem URL navegável (o gate os pularia): {sem_url}"

    nao_resolvidas = [check.id for check in report.checks if check.url.startswith("unresolved:")]
    assert not nao_resolvidas, f"checks com rota Django morta: {nao_resolvidas}"

    # E cada superfície de operador aponta para a SUA base — trocar duas seria
    # invisível de outro jeito (as telas respondem 200 em qualquer uma).
    por_id = {check.id: check.url for check in report.checks}
    assert por_id["desktop.orders.queue"].startswith("http://127.0.0.1:3101")
    assert por_id["tablet.kds.station"].startswith("http://127.0.0.1:3102")
    assert por_id["tablet.production.floor"].startswith("http://127.0.0.1:3103")
    for check_id in ("desktop.pos.counter", "desktop.closing.day", "desktop.cash_register.shift"):
        assert por_id[check_id].startswith("http://127.0.0.1:3104"), check_id
