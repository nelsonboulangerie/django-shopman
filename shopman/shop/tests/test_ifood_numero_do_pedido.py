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
