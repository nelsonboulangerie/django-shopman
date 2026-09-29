"""O número do pedido no iFood é o número do pedido aqui.

Medido em 19/09/2026, durante a homologação: o wizard mandava cancelar o "pedido
4994", o operador buscava 4994 no Gestor e não achava nada — o ref era
``IFOOD-260919-D09``, e o único quatro dígitos na tela era o código de retirada,
outro número. A tradução dependia de alguém cruzar o UUID no log.

Estes testes travam as três pontas: o ref adota o ``displayId``, o card mostra o
número do canal só quando o ref não o carrega, e o prazo do marketplace vira
contagem em vez de conta de cabeça.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from shopman.backstage.projections.order_queue import _channel_display_id, _external_deadline
from shopman.shop.services import ifood_ingest, ifood_orders


def _raw(display_id="4994", order_id="order-uuid", created_at="2026-09-19T18:46:20Z"):
    return {
        "id": order_id,
        "displayId": display_id,
        "createdAt": created_at,
        "merchant": {"id": "merchant"},
        "items": [{"id": "bread", "name": "Pão", "quantity": 1, "unitPrice": 20, "totalPrice": 20}],
        "total": {"subTotal": 20, "orderAmount": 20},
    }


def _ingest(raw):
    with patch.object(ifood_ingest.order_changed, "send"):
        return ifood_ingest.ingest(ifood_orders.map_order(raw))


@pytest.fixture
def ifood_channel(db):
    from shopman.shop.models import Channel

    return Channel.objects.create(ref="ifood", name="iFood")


# ── O ref ──────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_ref_adota_o_numero_do_ifood(ifood_channel):
    order = _ingest(_raw(display_id="4994"))

    assert order.ref.endswith("-4994")
    assert order.data["ifood"]["ref_from_display_id"] is True


@pytest.mark.django_db
def test_numero_ocupado_no_mesmo_dia_cai_no_sorteio_e_se_declara(ifood_channel):
    """Dois pedidos com o mesmo displayId no mesmo dia: o segundo não pode falhar."""
    primeiro = _ingest(_raw(display_id="4994", order_id="order-1"))
    segundo = _ingest(_raw(display_id="4994", order_id="order-2"))

    assert primeiro.ref != segundo.ref
    assert segundo.data["ifood"]["ref_from_display_id"] is False
    # E o número segue guardado: é por ele que o operador vai procurar.
    assert segundo.data["ifood"]["display_id"] == "4994"


@pytest.mark.django_db
def test_pedido_sem_display_id_continua_ingerindo(ifood_channel):
    order = _ingest(_raw(display_id=""))

    assert order.ref.startswith("IFOOD-")
    assert order.data["ifood"]["ref_from_display_id"] is False


# ── O número no card ───────────────────────────────────────────────────────────


def _card_order(ref, display_id, status="new", **ifood):
    return SimpleNamespace(
        ref=ref, status=status, data={"ifood": {"display_id": display_id, **ifood}}
    )


def test_card_nao_repete_o_numero_que_o_ref_ja_mostra():
    assert _channel_display_id(_card_order("IFOOD-260919-4994", "4994")) == ""


def test_card_mostra_o_numero_quando_o_ref_divergiu():
    """Colisão no dia, ou pedido criado antes desta mudança: sem isso, some da busca."""
    assert _channel_display_id(_card_order("IFOOD-260919-D09", "4994")) == "4994"


def test_card_sem_numero_do_canal_nao_inventa_nada():
    assert _channel_display_id(_card_order("IFOOD-260919-D09", "")) == ""


# ── O prazo ────────────────────────────────────────────────────────────────────


def test_prazo_do_marketplace_vira_contagem_enquanto_espera_confirmacao():
    order = _card_order("IFOOD-260919-4994", "4994", confirm_by="2026-09-19T18:54:20Z")

    assert _external_deadline(order) == ("2026-09-19T18:54:20Z", "cancel")


def test_pedido_ja_confirmado_nao_conta_mais_prazo():
    """Confirmado não expira — contar ali seria alarme sobre o que já foi resolvido."""
    order = _card_order("IFOOD-260919-4994", "4994", status="accepted", confirm_by="2026-09-19T18:54:20Z")

    assert _external_deadline(order) is None


def test_canal_sem_sla_externo_nao_mostra_contagem():
    assert _external_deadline(_card_order("IFOOD-260919-4994", "4994")) is None


@pytest.mark.django_db
def test_sla_do_canal_vira_prazo_gravado_no_pedido(ifood_channel):
    """O prazo é fato da ingestão, contado do createdAt DELES — o relógio do iFood
    já estava correndo antes de o evento aparecer no nosso polling."""
    ifood_channel.config = {"confirmation": {"mode": "manual", "external_sla_minutes": 8}}
    ifood_channel.save(update_fields=["config"])

    order = _ingest(_raw(created_at="2026-09-19T18:46:20+00:00"))

    assert order.data["ifood"]["confirm_by"].startswith("2026-09-19T18:54:20")


@pytest.mark.django_db
def test_canal_sem_sla_configurado_nao_grava_prazo(ifood_channel):
    order = _ingest(_raw())

    assert "confirm_by" not in order.data["ifood"]


# ── O card cabe numa olhada ────────────────────────────────────────────────────
# Doze linhas para um pedido de dois itens, contra cinco do card do PDV na mesma
# coluna: a fila deixava de ser varredura. O que decide fica; o resto é detalhe.


def _scheduled(**schedule):
    return SimpleNamespace(
        channel_ref="ifood",
        data={"ifood": {"order_timing": "SCHEDULED", "schedule": schedule}},
    )


def test_codigo_de_retirada_vai_ao_card():
    from shopman.backstage.projections import ifood as proj

    order = SimpleNamespace(channel_ref="ifood", data={"ifood": {"pickup_code": "8913"}})

    assert proj.pickup_code(order) == "8913"


def test_codigo_de_retirada_so_existe_no_ifood():
    from shopman.backstage.projections import ifood as proj

    assert proj.pickup_code(SimpleNamespace(channel_ref="web", data={"ifood": {"pickup_code": "8913"}})) == ""


def test_pedido_imediato_nao_ganha_linha_de_agendamento():
    from shopman.backstage.projections import ifood as proj

    assert proj.schedule_label(SimpleNamespace(channel_ref="ifood", data={"ifood": {}})) == ""


@pytest.mark.django_db
def test_agendamento_vira_uma_linha_com_a_janela():
    """Três linhas de janela viravam três linhas no card. Uma basta para triar."""
    from django.utils import timezone

    from shopman.backstage.projections import ifood as proj

    hoje = timezone.localtime()
    inicio = hoje.replace(hour=21, minute=9, second=0, microsecond=0)
    fim = hoje.replace(hour=22, minute=9, second=0, microsecond=0)
    order = _scheduled(delivery_start_at=inicio.isoformat(), delivery_end_at=fim.isoformat())

    assert proj.schedule_label(order) == "Agendado · Hoje 21:09–22:09"


@pytest.mark.django_db
def test_agendamento_de_outro_dia_mostra_a_data():
    """Em pedido para hoje a data é ruído; em pedido para amanhã ela é o ponto."""
    from datetime import timedelta as _td

    from django.utils import timezone

    from shopman.backstage.projections import ifood as proj

    amanha = timezone.localtime() + _td(days=1)
    inicio = amanha.replace(hour=8, minute=0, second=0, microsecond=0)
    fim = amanha.replace(hour=9, minute=0, second=0, microsecond=0)
    order = _scheduled(delivery_start_at=inicio.isoformat(), delivery_end_at=fim.isoformat())

    assert proj.schedule_label(order) == f"Agendado · {inicio:%d/%m} 08:00–09:00"


@pytest.mark.django_db
def test_agendamento_sem_fim_de_janela_nao_inventa_horario():
    from django.utils import timezone

    from shopman.backstage.projections import ifood as proj

    inicio = timezone.localtime().replace(hour=15, minute=30, second=0, microsecond=0)

    assert proj.schedule_label(_scheduled(delivery_start_at=inicio.isoformat())) == "Agendado · Hoje a partir de 15:30"


def test_agendamento_sem_janela_nenhuma_ainda_se_declara():
    """Sem horário, o pedido continua sendo agendado — calar seria pior."""
    from shopman.backstage.projections import ifood as proj

    assert proj.schedule_label(_scheduled()) == "Agendado"
