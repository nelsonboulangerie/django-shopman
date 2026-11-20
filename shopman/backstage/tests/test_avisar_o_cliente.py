"""Avisar o cliente com um toque (WP-G07): quando cabe, a frase, a mensagem e o envio.

O texto é o aprovado pelo dono em 20/11/2026; o envio é o caminho de notificação de
sempre (Directive ``notification.send``), e nenhum teste aqui sai do processo: a
Directive fica na fila, ninguém a executa.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils import timezone
from shopman.orderman.models import Directive, Order

from shopman.shop.models import Channel, Shop
from shopman.shop.services import customer_notice
from shopman.shop.services import notification as notification_svc

OPTIONS_URL = "/api/v1/backstage/orders/{ref}/customer-notice/preview/"
SEND_URL = "/api/v1/backstage/orders/{ref}/customer-notice/"
SP = ZoneInfo("America/Sao_Paulo")


def _order(ref="AV-1", *, status=Order.Status.ACCEPTED, channel="web", data=None, items=(("Focaccia", 2),)):
    base = {"customer": {"name": "Ana Souza", "phone": "+5543999990002"}, "fulfillment_type": "pickup"}
    base.update(data or {})
    order = Order.objects.create(ref=ref, channel_ref=channel, session_key=f"s-{ref}", status=status, total_q=1000, data=base)
    for i, (name, qty) in enumerate(items, start=1):
        order.items.create(line_id=f"L{i}", sku=f"SKU-{i}", name=name, qty=Decimal(str(qty)), unit_price_q=500,
                           line_total_q=500 * int(Decimal(str(qty))) or 500)
    return order


def _preorder(ref="AV-2", **kw):
    tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
    return _order(ref, data={"delivery_date": tomorrow, "delivery_time_slot": "slot-09", "is_preorder": True}, **kw)


def _directives(ref, template):
    return Directive.objects.filter(topic=notification_svc.TOPIC, payload__order_ref=ref, payload__template=template)


@pytest.fixture
def shop(db):
    return Shop.objects.create(name="Nelson Boulangerie", brand_name="Nelson Boulangerie")


# ── A frase de cada aviso ───────────────────────────────────────────────────


def test_horas_prontas_do_atraso_caem_em_multiplos_de_dez(shop):
    now = datetime(2026, 11, 20, 15, 57, tzinfo=SP)
    choices = customer_notice.delay_choices(_order(), now=now)
    assert [c.label for c in choices] == ["16h30 (em 30 min)", "17h (em 1 hora)", "18h (em 2 horas)"]
    assert [c.note for c in choices] == ["hoje, às 16h30", "hoje, às 17h", "hoje, às 18h"]


def test_atraso_que_vira_o_dia_diz_amanha(shop):
    now = datetime(2026, 11, 20, 23, 20, tzinfo=SP)
    with _today(now):
        assert customer_notice.delay_choices(_order(), now=now)[1].note == "amanhã, às 0h20"


def test_o_que_falta_leva_o_nome_e_a_quantidade(shop):
    order = _order(items=(("Focaccia", 2), ("Brioche", 1), ("Baguete", 3)))
    assert customer_notice.missing_phrase(order, [{"line_id": "L1"}]) == "Focaccia (2 unidades)"
    assert (
        customer_notice.missing_phrase(order, [{"line_id": "L1"}, {"line_id": "L2"}, {"line_id": "L3", "qty": "1"}])
        == "Focaccia (2 unidades), Brioche (1 unidade) e Baguete (1 unidade)"
    )


def test_o_que_falta_recusa_quantidade_maior_que_a_linha(shop):
    order = _order()
    with pytest.raises(customer_notice.CustomerNoticeRefused) as exc:
        customer_notice.missing_phrase(order, [{"line_id": "L1", "qty": "3"}])
    assert exc.value.field == "lines"
    with pytest.raises(customer_notice.CustomerNoticeRefused):
        customer_notice.missing_phrase(order, [])


def test_quantidade_por_peso_sai_em_kg():
    assert customer_notice.qty_display(Decimal("0.500"), "kg") == "0,5 kg"
    assert customer_notice.qty_display(Decimal("2.000")) == "2 unidades"
    assert customer_notice.qty_display(Decimal("1.000")) == "1 unidade"


def test_remarcar_so_existe_na_encomenda(shop):
    kinds = {a.kind: a for a in customer_notice.availability(_order())}
    assert not kinds["reschedule"].enabled
    assert kinds["reschedule"].reason == "Só a encomenda tem data combinada para remarcar."
    kinds = {a.kind: a for a in customer_notice.availability(_preorder())}
    assert kinds["reschedule"].enabled
    # A encomenda de outro dia não "atrasa": remarca.
    assert not kinds["delayed"].enabled


def test_nenhum_aviso_cabe_no_ifood_no_pronto_ou_sem_telefone(shop):
    cases = {
        "O cliente do iFood fala com a casa pelo app do iFood.": _order("AV-I", channel="ifood"),
        "O pedido já ficou pronto ou terminou: não há o que avisar por aqui.": _order("AV-R", status=Order.Status.READY),
        "O pedido não tem o telefone do cliente.": _order("AV-T", data={"customer": {"name": "Ana"}}),
    }
    for reason, order in cases.items():
        assert {(a.enabled, a.reason) for a in customer_notice.availability(order)} == {(False, reason)}


def test_a_mensagem_e_o_texto_aprovado_com_o_nome_o_pedido_e_a_frase(shop):
    order = _preorder("2026-11-20-A17")
    assert customer_notice.message(order, "delayed", "hoje, às 16h30") == (
        "Oi, Ana Souza! Aqui é da Nelson Boulangerie 💛 Seu pedido A17 vai atrasar um pouco: a nova previsão é "
        "hoje, às 16h30, e sinto muito por isso. Qualquer dúvida, é só responder aqui."
    )
    assert customer_notice.message(order, "item_missing", "Focaccia (2 unidades)") == (
        "Oi, Ana Souza! Aqui é da Nelson Boulangerie 💛 No seu pedido A17, vai faltar o item Focaccia (2 unidades), "
        "e sinto muito por isso. Posso trocar por outro produto ou devolver esse valor. Me responde aqui como "
        "fica melhor para você."
    )
    note = customer_notice.note_for(order, "reschedule")
    assert note.startswith("retirada amanhã")
    assert customer_notice.message(order, "reschedule", note).startswith(
        f"Oi, Ana Souza! Aqui é da Nelson Boulangerie 💛 Não vamos conseguir aprontar seu pedido A17 para {note}, como combinamos"
    )


def test_status_note_do_aviso_nunca_fica_vazio(shop):
    order = _preorder()
    for template in ("order_delayed", "order_item_missing", "order_reschedule_needed"):
        assert notification_svc._status_note(order, template, None)
        assert notification_svc._status_note(order, template, None, note="hoje, às 16h30") == "hoje, às 16h30"


def test_send_enfileira_o_aviso_com_a_frase(shop):
    order = _order("AV-SEND")
    directive = customer_notice.send(order, customer_notice.DELAYED, "hoje, às 16h30")
    assert directive.payload["template"] == "order_delayed"
    assert directive.payload["status_note"] == "hoje, às 16h30"
    assert directive.dedupe_key.endswith(":order_delayed:1")


def test_atraso_recusa_hora_que_ja_passou(shop):
    order = _order()
    past = (timezone.now() - timedelta(minutes=5)).isoformat()
    with pytest.raises(customer_notice.CustomerNoticeRefused) as exc:
        customer_notice.note_for(order, "delayed", eta=past)
    assert exc.value.field == "eta"


class _today:
    """Congela o "hoje" do serviço no dia de ``now``."""

    def __init__(self, now):
        self.now = now

    def __enter__(self):
        from unittest import mock

        self.patch = mock.patch("django.utils.timezone.now", return_value=self.now)
        self.patch.start()

    def __exit__(self, *exc):
        self.patch.stop()


# ── A rota ──────────────────────────────────────────────────────────────────


class AvisarOClienteApiTests(TestCase):
    def setUp(self):
        Shop.objects.create(name="Nelson Boulangerie", brand_name="Nelson Boulangerie")
        Channel.objects.create(ref="web", name="Loja", is_active=True, config={})
        User = get_user_model()
        self.operator = User.objects.create_user("op-aviso", password="x", is_staff=True)
        self.operator.user_permissions.add(
            Permission.objects.get(content_type=ContentType.objects.get(app_label="shop", model="shop"), codename="manage_orders")
        )
        self.client.force_login(self.operator)
        self.order = _order("AV-API", items=(("Focaccia", 2), ("Brioche", 1)))

    def _send(self, body, *, key=None, base=None):
        payload = {
            "expected_actor_id": self.operator.pk,
            "base_revision": base or customer_notice.notice_revision(self.order),
            "idempotency_key": key or str(uuid4()),
            **body,
        }
        return self.client.post(SEND_URL.format(ref=self.order.ref), data=payload, content_type="application/json")

    def test_as_opcoes_dizem_o_que_cada_aviso_pede(self):
        response = self.client.get(OPTIONS_URL.format(ref=self.order.ref))
        self.assertEqual(response.status_code, 200, response.content)
        notices = {n["kind"]: n for n in response.json()["notices"]}
        self.assertEqual(list(notices), ["delayed", "item_missing", "reschedule"])
        self.assertEqual(len(notices["delayed"]["delay_choices"]), 3)
        self.assertEqual([line["qty_display"] for line in notices["item_missing"]["lines"]], ["2 unidades", "1 unidade"])
        self.assertFalse(notices["reschedule"]["enabled"])
        schema = response.json()["payload_schema"]
        self.assertEqual(schema["expected_actor_id"], self.operator.pk)
        self.assertEqual(schema["base_revision"], customer_notice.notice_revision(self.order))

    def test_previa_devolve_a_mensagem_e_nao_envia_nada(self):
        response = self.client.post(
            OPTIONS_URL.format(ref=self.order.ref),
            data={"kind": "item_missing", "lines": [{"line_id": "L2"}]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("vai faltar o item Brioche (1 unidade)", response.json()["message"])
        self.assertFalse(Directive.objects.filter(topic=notification_svc.TOPIC).exists())

    def test_previa_recusa_apontando_a_escolha(self):
        response = self.client.post(
            OPTIONS_URL.format(ref=self.order.ref), data={"kind": "item_missing", "lines": []}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["field"], "lines")

    def test_envia_pelo_caminho_de_sempre_com_a_frase_no_payload(self):
        choice = customer_notice.delay_choices(self.order)[0]
        response = self._send({"kind": "delayed", "eta": choice.value})
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["outcome"], "applied")
        self.assertEqual(body["effect_status"], "queued")
        self.assertIn(choice.note, body["message"])
        (directive,) = _directives(self.order.ref, "order_delayed")
        self.assertEqual(directive.payload["status_note"], choice.note)
        self.assertTrue(directive.payload["requires_active_notification"])
        # O pedido volta junto, com o recibo do aviso na lista.
        self.assertIn("order", body)

    def test_mesma_intencao_nao_envia_duas_vezes(self):
        key = str(uuid4())
        first = self._send({"kind": "item_missing", "lines": [{"line_id": "L1"}]}, key=key)
        again = self._send({"kind": "item_missing", "lines": [{"line_id": "L1"}]}, key=key)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(again.status_code, 200, again.content)
        self.assertTrue(again.json()["replayed"])
        self.assertEqual(_directives(self.order.ref, "order_item_missing").count(), 1)

    def test_o_mesmo_aviso_logo_em_seguida_e_recusado(self):
        self._send({"kind": "item_missing", "lines": [{"line_id": "L1"}]})
        again = self._send({"kind": "item_missing", "lines": [{"line_id": "L2"}]})
        self.assertEqual(again.status_code, 409, again.content)
        self.assertEqual(again.json()["error"]["code"], "notification_send_pending")
        self.assertEqual(_directives(self.order.ref, "order_item_missing").count(), 1)

    def test_segundo_aviso_legitimo_e_outra_ocorrencia(self):
        self._send({"kind": "item_missing", "lines": [{"line_id": "L1"}]})
        first = _directives(self.order.ref, "order_item_missing").get()
        first.status = "done"
        first.payload["notification_delivery"] = {"status": "accepted"}
        first.save(update_fields=["status", "payload", "updated_at"])
        Directive.objects.filter(pk=first.pk).update(created_at=timezone.now() - timedelta(minutes=5))
        again = self._send({"kind": "item_missing", "lines": [{"line_id": "L2"}]})
        self.assertEqual(again.status_code, 200, again.content)
        self.assertEqual(_directives(self.order.ref, "order_item_missing").count(), 2)

    def test_pedido_que_mudou_recusa_o_envio(self):
        response = self._send({"kind": "item_missing", "lines": [{"line_id": "L1"}]}, base="revisao-velha")
        self.assertEqual(response.status_code, 409, response.content)
        self.assertFalse(_directives(self.order.ref, "order_item_missing").exists())

    def test_sem_permissao_nao_envia(self):
        plain = get_user_model().objects.create_user("plain-aviso", password="x", is_staff=True)
        self.client.force_login(plain)
        response = self.client.post(
            SEND_URL.format(ref=self.order.ref),
            data={"kind": "delayed", "expected_actor_id": plain.pk, "base_revision": "x", "idempotency_key": str(uuid4())},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Directive.objects.filter(topic=notification_svc.TOPIC).exists())

    def test_o_menu_do_pedido_oferece_o_gesto_so_no_pedido_aberto_da_casa(self):
        from shopman.backstage.projections.order_queue import build_operator_order

        def action(order):
            found = [a for a in build_operator_order(order, user=self.operator).actions if a.ref == "customer-notice"]
            return found[0] if found else None

        offered = action(self.order)
        self.assertIsNotNone(offered)
        self.assertEqual((offered.label, offered.enabled), ("Avisar o cliente", True))
        self.assertEqual(offered.payload_schema["base_revision"], customer_notice.notice_revision(self.order))
        no_phone = action(_order("AV-SEM", data={"customer": {"name": "Ana"}}))
        self.assertEqual((no_phone.enabled, no_phone.reason), (False, "O pedido não tem o telefone do cliente."))
        self.assertIsNone(action(_order("AV-PRONTO", status=Order.Status.READY)))
        # O iFood avisa pelo app dele (o detalhe do iFood pede o canal montado: a régua basta).
        self.assertFalse(customer_notice.offered(_order("AV-IFOOD", channel="ifood")))
