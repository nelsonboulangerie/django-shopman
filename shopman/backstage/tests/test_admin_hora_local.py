"""Hora local da loja em toda tela do Admin (beta test 05/11/2026, ADM-04).

Às 07:40 em Brasília o Dashboard dizia 10:40, o título do turno dizia 11:45 com o
campo da mesma tela em 08:45, e a cobrança das 06:10 saía às 09:10. Formatar um
``datetime`` aware com ``strftime``/``date_format`` não converte para a hora
local: o banco devolve UTC. Os pontos abaixo agora passam por ``format_local``
(ou ``timezone.localtime``).

Mais o caixa sem código cru (ADM-11): o meio da venda e o resultado do
comprovante saíam como ``mixed``/``skipped``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from django.contrib.auth.models import User
from shopman.cashman import services as cash
from shopman.cashman.contrib.admin_unfold.admin import EntryInline, entry_detail
from shopman.cashman.models import Entry, Terminal
from shopman.payman.contrib.admin_unfold.admin import _format_datetime

from shopman.backstage.models import OperatorAlert
from shopman.backstage.projections.dashboard import build_dashboard

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _hora_de_brasilia(settings):
    settings.TIME_ZONE = "America/Sao_Paulo"
    settings.USE_TZ = True


UTC_13H = datetime(2026, 11, 5, 13, 0, tzinfo=UTC)


@pytest.fixture
def shift():
    terminal = Terminal.objects.create(ref="t-hora", label="Balcão", channel_ref="pdv")
    operator = User.objects.create_user("op-hora", password="pw", is_staff=True)
    shift = cash.open_shift(operator=operator, terminal=terminal, float_q=10000)
    type(shift).objects.filter(pk=shift.pk).update(opened_at=UTC_13H)
    shift.refresh_from_db()
    return shift


def test_titulo_do_turno_em_hora_local(shift):
    assert "05/11/2026 10:00" in str(shift)


def test_linha_do_tempo_do_turno_em_hora_local():
    # O livro é imutável: o lançamento do teste não é gravado.
    entry = Entry(kind=Entry.Kind.CASH_IN, amount_q=500, at=UTC_13H)
    from django.contrib import admin

    inline = EntryInline(Entry, admin.site)
    assert inline.at_display(entry) == "05/11 10:00"
    assert str(entry).startswith("05/11 10:00")


def test_data_da_cobranca_em_hora_local():
    assert _format_datetime(UTC_13H) == "05/11/26 · 10:00"
    assert _format_datetime(None) == "—"


def test_alerta_do_dashboard_em_hora_local():
    alert = OperatorAlert.objects.create(type="stale_new_order", severity="warning", message="x", audience="orders")
    OperatorAlert.objects.filter(pk=alert.pk).update(created_at=UTC_13H)
    rows = {a.pk: a for a in build_dashboard().operator_alerts}
    assert rows[alert.pk].created_at_display == "05/11 10:00"


def test_meio_da_venda_e_comprovante_em_portugues(shift):
    operator = shift.opened_by
    sale = cash.record(
        Entry.Kind.SALE, shift=shift, operator=operator, amount_q=1500,
        payload={"method": "mixed"}, order_ref="PDV-1",
    )
    assert "pagamento misto" in entry_detail(sale)
    assert "mixed" not in entry_detail(sale)
    receipt = Entry(kind=Entry.Kind.RECEIPT_RESULT, payload={"status": "skipped"})
    assert entry_detail(receipt) == "sem impressora"


def test_estoque_mostra_movimento_e_reserva_na_hora_da_loja():
    """Movimentos, reservas e alertas do estoque usavam ``strftime`` cru."""
    from shopman.stockman.contrib.admin_unfold.admin import _format_datetime as stock_datetime

    assert stock_datetime(UTC_13H) == "05/11/26 · 10:00"
    assert stock_datetime(None) == "-"
