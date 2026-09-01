"""Operator order queue projection and surface guardrails."""

from __future__ import annotations

from django.test import TestCase
from django.utils.dateparse import parse_datetime
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.presentation.status import order_status_label
from shopman.backstage.projections.order_queue import build_order_card, build_two_zone_queue


def _order(ref: str, status: str, fulfillment_type: str = "pickup") -> Order:
    order = Order.objects.create(
        ref=ref,
        channel_ref="web",
        session_key=f"session-{ref}",
        status=status,
        total_q=1500,
        data={
            "customer": {"name": f"Cliente {ref}"},
            "fulfillment_type": fulfillment_type,
            "payment": {"method": "cash"},
        },
    )
    OrderItem.objects.create(
        order=order,
        line_id=f"{ref}-1",
        sku="PAO",
        name="Pão",
        qty=1,
        unit_price_q=1500,
        line_total_q=1500,
    )
    return order


def _phone_order(ref: str, phone: str) -> Order:
    order = _order(ref, "new")
    order.data = {
        "customer": {"phone": phone},
        "fulfillment_type": "pickup",
        "payment": {"method": "cash"},
    }
    order.handle_ref = phone
    order.save(update_fields=["data", "handle_ref", "updated_at"])
    return order


class OrderQueueSurfaceTests(TestCase):
    def test_confirmed_and_preparing_orders_are_visible_in_prep(self) -> None:
        _order("Q-NEW", "new")
        _order("Q-CONF", "accepted")
        _order("Q-PREP", "preparing")
        _order("Q-READY", "ready")
        _order("Q-DISP", "dispatched", "delivery")
        _order("Q-DELIV", "delivered", "delivery")

        queue = build_two_zone_queue()

        self.assertEqual([o.ref for o in queue.intake], ["Q-NEW"])
        self.assertEqual([o.ref for o in queue.prep], ["Q-CONF", "Q-PREP"])
        self.assertEqual(queue.preparing_count, 2)
        self.assertEqual([o.ref for o in queue.expedition_pickup], ["Q-READY"])
        self.assertEqual([o.ref for o in queue.expedition_delivery_transit], ["Q-DISP", "Q-DELIV"])
        self.assertEqual(queue.expedition_delivery_count, 2)
        self.assertEqual(queue.total_count, 6)

    def test_future_preorder_leaves_the_day_columns_for_the_preorders_group(self) -> None:
        """WP-D: encomenda para data futura sai das colunas do dia e vive no grupo
        "Agendados", ordenada pela data combinada. Vale para pedido NOVO (ainda a
        aceitar) e confirmado: ambos carregam o badge "Agendado · <data>", então
        um novo na Entrada com esse badge seria contraditório — pertence aqui."""
        from datetime import timedelta

        from django.utils import timezone

        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
        saturday = (timezone.localdate() + timedelta(days=3)).isoformat()

        _order("Q-HOJE", "accepted")
        later = _order("Q-SAB", "accepted")
        later.data["delivery_date"] = saturday
        later.save(update_fields=["data", "updated_at"])
        sooner = _order("Q-AMANHA", "accepted")
        sooner.data["delivery_date"] = tomorrow
        sooner.save(update_fields=["data", "updated_at"])
        new_preorder = _order("Q-NOVA-ENC", "new")
        new_preorder.data["delivery_date"] = tomorrow
        new_preorder.save(update_fields=["data", "updated_at"])

        queue = build_two_zone_queue()

        self.assertEqual([o.ref for o in queue.prep], ["Q-HOJE"])
        # Novo e confirmado, todos futuros → grupo Agendados; a Entrada não recebe
        # card com badge "Agendado" (badge e seção concordam). Ordem: data, criação.
        self.assertEqual([o.ref for o in queue.preorders], ["Q-AMANHA", "Q-NOVA-ENC", "Q-SAB"])
        self.assertEqual(queue.preorders_count, 3)
        self.assertEqual([o.ref for o in queue.intake], [])

        cards = {c.ref: c for c in queue.preorders + queue.intake + queue.prep}
        self.assertTrue(cards["Q-AMANHA"].is_preorder)
        self.assertEqual(cards["Q-AMANHA"].commitment_date, tomorrow)
        self.assertEqual(cards["Q-AMANHA"].commitment_date_display, "amanhã")
        # O card novo segue com o badge de encomenda E a ação de aceitar.
        self.assertTrue(cards["Q-NOVA-ENC"].is_preorder)
        self.assertTrue(cards["Q-NOVA-ENC"].can_confirm)
        self.assertFalse(cards["Q-HOJE"].is_preorder)
        self.assertEqual(cards["Q-HOJE"].commitment_date_display, "")

    def test_past_or_today_commitment_date_is_not_a_preorder(self) -> None:
        """No dia (ou depois dela) a encomenda volta ao fluxo normal do board."""
        from django.utils import timezone

        today_order = _order("Q-DIA", "accepted")
        today_order.data["delivery_date"] = timezone.localdate().isoformat()
        today_order.save(update_fields=["data", "updated_at"])

        queue = build_two_zone_queue()

        self.assertEqual([o.ref for o in queue.prep], ["Q-DIA"])
        self.assertEqual(queue.preorders, ())

    def test_confirmation_deadline_surfaces_on_new_card(self) -> None:
        from shopman.orderman.models import Directive

        _order("Q-DEADLINE", "new")
        Directive.objects.create(
            topic="confirmation.timeout",
            status="queued",
            payload={
                "order_ref": "Q-DEADLINE",
                "action": "cancel",  # valor real do directive (não "auto_cancel")
                "expires_at": "2026-07-04T12:00:00+00:00",
            },
        )
        _order("Q-NODEADLINE", "new")  # sem timer → campos vazios

        queue = build_two_zone_queue()
        cards = {c.ref: c for c in queue.intake}

        assert cards["Q-DEADLINE"].confirmation_deadline_iso == "2026-07-04T12:00:00+00:00"
        assert cards["Q-DEADLINE"].confirmation_action == "cancel"
        assert cards["Q-NODEADLINE"].confirmation_deadline_iso == ""

    def test_all_active_operator_statuses_have_advance_action_after_confirmation(self) -> None:
        expected_labels = {
            "accepted": "Iniciar preparo",
            "preparing": "Marcar pronto",
            "dispatched": "Marcar como Entregue",
            "delivered": "Concluir",
        }

        for status, label in expected_labels.items():
            with self.subTest(status=status):
                card = build_order_card(_order(f"A-{status}", status, "delivery"))
                self.assertTrue(card.can_advance)
                self.assertEqual(card.next_action_label, label)

        pickup_ready = build_order_card(_order("A-ready-pickup", "ready", "pickup"))
        delivery_ready = build_order_card(_order("A-ready-delivery", "ready", "delivery"))
        self.assertEqual(pickup_ready.next_action_label, "Marcar como Retirado")
        self.assertEqual(delivery_ready.next_action_label, "Marcar saída para entrega")

    def test_new_orders_keep_confirm_or_reject_as_the_only_primary_decision(self) -> None:
        card = build_order_card(_order("A-NEW", "new"))

        self.assertTrue(card.can_confirm)
        self.assertFalse(card.can_advance)

    def test_cash_marked_paid_is_not_operator_payment_status_source(self) -> None:
        order = _order("A-PAID-CASH", "new")
        order.data["payment"]["marked_paid_by"] = "ana"
        order.save(update_fields=["data", "updated_at"])

        card = build_order_card(order)

        self.assertEqual(card.status, "new")
        self.assertEqual(card.payment_status, "")
        self.assertFalse(card.payment_pending)
        self.assertTrue(card.can_confirm)

    def test_captured_digital_payment_releases_confirm_button_gate(self) -> None:
        from shopman.payman import PaymentService

        order = _order("A-PAID-PIX", "new")
        intent = PaymentService.create_intent(
            order_ref=order.ref,
            amount_q=order.total_q,
            method="pix",
        )
        order.data["payment"] = {"method": "pix", "intent_ref": intent.ref}
        order.save(update_fields=["data", "updated_at"])
        PaymentService.authorize(intent.ref, gateway_id="pix-paid-gw")
        PaymentService.capture(intent.ref)

        card = build_order_card(Order.objects.get(pk=order.pk))

        self.assertEqual(card.payment_status, "captured")
        self.assertFalse(card.payment_pending)
        self.assertTrue(card.can_confirm)

    def test_finished_order_offers_no_disabled_advance_button(self) -> None:
        """Bloqueio definitivo não vira botão: não há espera que o resolva.

        A superfície desenha o botão desabilitado sempre que há
        ``advance_block_label``. Um pedido cancelado também está "bloqueado" —
        mas por não ter próxima etapa — e ganhava um "Ainda não dá para avançar"
        que jamais destravaria.
        """
        for status in ("cancelled", "completed", "new"):
            with self.subTest(status=status):
                card = build_order_card(_order(f"A-FIM-{status}", status))

                self.assertEqual(card.advance_block_label, "")

    def test_accepted_order_awaiting_payment_keeps_the_button_in_place(self) -> None:
        """Bloqueio temporário ocupa o lugar e diz o que falta."""
        order = _order("A-ESPERA-PIX", "accepted")
        order.data["payment"] = {"method": "pix", "amount_q": order.total_q}
        order.save(update_fields=["data", "updated_at"])

        card = build_order_card(Order.objects.get(pk=order.pk))

        self.assertEqual(card.advance_block_label, "Aguardando pagamento…")
        self.assertIn("Pagamento", card.advance_block_reason)
        # Só esperando pagamento é ampulheta (warning), não alarme (danger):
        # quem não paga a tempo é cancelado e sai do board.
        self.assertEqual(card.payment_tone, "warning")

    def test_external_marketplace_order_reads_as_paid(self) -> None:
        """iFood/marketplace chega pré-pago: o pill é verde, não neutro — pago é
        pago, independente do canal/meio."""
        order = _order("A-IFOOD-PAGO", "accepted")
        order.data["payment"] = {"method": "external"}
        order.save(update_fields=["data", "updated_at"])

        card = build_order_card(Order.objects.get(pk=order.pk))

        self.assertEqual(card.payment_tone, "success")

    def test_cash_settled_at_the_counter_reads_as_paid(self) -> None:
        """Dinheiro liquidado no PDV (tender ``received``) é verde: pago no caixa."""
        order = _order("A-CASH-BALCAO", "preparing")
        order.data["payment"] = {
            "method": "cash",
            "tenders": [{"method": "cash", "amount_q": order.total_q, "status": "received"}],
        }
        order.save(update_fields=["data", "updated_at"])

        card = build_order_card(Order.objects.get(pk=order.pk))

        self.assertEqual(card.payment_tone, "success")

    def test_cash_on_delivery_pending_stays_neutral(self) -> None:
        """Dinheiro na entrega ainda não acertado (tender ``pending``) fica neutro:
        não há recebimento a afirmar até o entregador liquidar."""
        order = _order("A-CASH-COD", "preparing")
        order.data["payment"] = {
            "method": "cash",
            "collection": "on_delivery",
            "tenders": [{"method": "cash", "amount_q": order.total_q, "status": "pending"}],
        }
        order.save(update_fields=["data", "updated_at"])

        card = build_order_card(Order.objects.get(pk=order.pk))

        self.assertEqual(card.payment_tone, "neutral")

    def test_web_pay_on_pickup_cash_stays_neutral(self) -> None:
        """Pedido web para pagar na retirada não tem tender ainda: neutro, não verde."""
        order = _order("A-CASH-RETIRA", "preparing")
        order.data["payment"] = {"method": "cash"}
        order.save(update_fields=["data", "updated_at"])

        card = build_order_card(Order.objects.get(pk=order.pk))

        self.assertEqual(card.payment_tone, "neutral")

    def test_order_without_any_payment_info_is_flagged_not_silent(self) -> None:
        """Pedido sem NENHUM rastro de cobrança (sem meio/intent/tender) não pode
        ficar mudo no board: pill explícito 'Pagamento não informado' em âmbar, para
        o operador ver que não sabemos o status — e não confundir com pago."""
        order = _order("A-SEM-PGTO", "ready")
        order.data["payment"] = {}
        order.save(update_fields=["data", "updated_at"])

        card = build_order_card(Order.objects.get(pk=order.pk))

        self.assertEqual(card.payment_method, "")
        self.assertEqual(card.payment_method_label, "Pagamento não informado")
        self.assertEqual(card.payment_tone, "warning")

    def test_card_timer_is_anchored_to_server_time(self) -> None:
        card = build_order_card(_order("A-TIMER", "new"))

        self.assertIsNotNone(parse_datetime(card.created_at_iso))
        self.assertIsNotNone(parse_datetime(card.server_now_iso))
        self.assertGreaterEqual(card.elapsed_seconds, 0)

    def test_customer_phone_is_formatted_for_operator_scan(self) -> None:
        card = build_order_card(_phone_order("A-PHONE", "+5543984049009"))

        self.assertEqual(card.customer_name, "(43) 98404-9009")

    def test_customer_landline_phone_is_formatted_without_brazil_country_code(self) -> None:
        card = build_order_card(_phone_order("A-LANDLINE", "554333231997"))

        self.assertEqual(card.customer_name, "(43) 3323-1997")

    def test_international_customer_phone_keeps_country_code(self) -> None:
        card = build_order_card(_phone_order("A-INTL", "+14155552671"))

        self.assertEqual(card.customer_name, "+14155552671")


class OperatorOrderPresetTests(TestCase):
    def test_detail_projection_exposes_store_cancellation_presets(self) -> None:
        from django.core.cache import cache

        from shopman.backstage.projections.order_queue import build_operator_order
        from shopman.shop.models import Shop

        Shop.objects.create(
            name="Loja Teste",
            cancellation_presets=["Item indisponível", "  ", "Problema técnico"],
        )
        cache.clear()  # Shop.load() memoizes the singleton

        proj = build_operator_order(_order("PRESET-1", "new"))

        # Blank entries are dropped; the rest are exposed in order for the gestor.
        self.assertEqual(proj.cancellation_presets, ("Item indisponível", "Problema técnico"))

    def test_detail_projection_exposes_store_kitchen_note_tags(self) -> None:
        from django.core.cache import cache

        from shopman.backstage.projections.order_queue import build_operator_order
        from shopman.shop.models import Shop

        Shop.objects.create(
            name="Loja Teste",
            kitchen_note_tags=["Bem assado", "  ", "Sem cebola"],
        )
        cache.clear()  # Shop.load() memoizes the singleton

        proj = build_operator_order(_order("KTAG-1", "new"))

        # Blank entries dropped; the rest exposed in order for the gestor's tag buttons.
        self.assertEqual(proj.kitchen_note_tags, ("Bem assado", "Sem cebola"))

    def test_detail_projection_reads_kitchen_note(self) -> None:
        from shopman.backstage.projections.order_queue import build_operator_order

        order = _order("KNOTE-1", "new")
        order.data = {**order.data, "kitchen_note": "Sem cebola. Cortar ao meio."}
        order.save(update_fields=["data", "updated_at"])

        proj = build_operator_order(order)

        self.assertEqual(proj.kitchen_note, "Sem cebola. Cortar ao meio.")

# As ações do operador (advance/reject/confirm) agora são exercidas no contrato
# headless em test_api_orders_surface.py; a semântica de lifecycle (new não avança,
# terminal não avança, reject só em new) é coberta nos testes de shop/operator_orders.


class CustomerNoteAndGiftReachTheOperatorTests(TestCase):
    """A observação do CLIENTE (``order_notes``) e o presente chegam ao Gestor.

    O CommitService grava ``order_notes`` e o KDS a exibia, mas a fila do
    operador só olhava ``kitchen_note`` (nota do OPERADOR) — o antigo
    ``has_notes`` era a nota errada com o nome genérico. O card indica presença
    (selo compacto); o conteúdo mora no detalhe.
    """

    def test_card_flags_customer_note_and_kitchen_note_separately(self) -> None:
        order = _order("NOTE-CARD-1", "new")
        order.data = {**order.data, "order_notes": "Sem cebola, por favor"}
        order.save(update_fields=["data", "updated_at"])

        card = build_order_card(order)

        self.assertTrue(card.has_customer_note)
        self.assertFalse(card.has_kitchen_note)

    def test_card_kitchen_note_does_not_masquerade_as_customer_note(self) -> None:
        order = _order("NOTE-CARD-2", "new")
        order.data = {**order.data, "kitchen_note": "Bem assado"}
        order.save(update_fields=["data", "updated_at"])

        card = build_order_card(order)

        self.assertTrue(card.has_kitchen_note)
        self.assertFalse(card.has_customer_note)

    def test_card_blank_customer_note_is_not_presence(self) -> None:
        order = _order("NOTE-CARD-3", "new")
        order.data = {**order.data, "order_notes": "   "}
        order.save(update_fields=["data", "updated_at"])

        self.assertFalse(build_order_card(order).has_customer_note)

    def test_card_flags_gift_and_recipient_presence(self) -> None:
        order = _order("GIFT-CARD-1", "new")
        order.data = {
            **order.data,
            "is_gift": True,
            "recipient": {"name": "Maria Silva", "phone": "+5543988887777"},
        }
        order.save(update_fields=["data", "updated_at"])

        card = build_order_card(order)

        self.assertTrue(card.is_gift)
        self.assertTrue(card.gift_has_recipient)

    def test_card_gift_without_recipient_is_still_a_gift(self) -> None:
        # Retirada: destinatário é opcional (storefront/intents/gift.py) — o
        # selo distingue "entregar a alguém" de "só embalar".
        order = _order("GIFT-CARD-2", "new")
        order.data = {**order.data, "is_gift": True}
        order.save(update_fields=["data", "updated_at"])

        card = build_order_card(order)

        self.assertTrue(card.is_gift)
        self.assertFalse(card.gift_has_recipient)

    def test_card_without_notes_or_gift_stays_clean(self) -> None:
        card = build_order_card(_order("NOTE-CARD-4", "new"))

        self.assertFalse(card.has_customer_note)
        self.assertFalse(card.has_kitchen_note)
        self.assertFalse(card.is_gift)
        self.assertFalse(card.gift_has_recipient)

    def test_detail_reads_customer_note_beside_kitchen_note(self) -> None:
        from shopman.backstage.projections.order_queue import build_operator_order

        order = _order("NOTE-DET-1", "new")
        order.data = {
            **order.data,
            "order_notes": "Sem cebola, por favor",
            "kitchen_note": "Cortar ao meio",
        }
        order.save(update_fields=["data", "updated_at"])

        proj = build_operator_order(order)

        self.assertEqual(proj.customer_note, "Sem cebola, por favor")
        self.assertEqual(proj.kitchen_note, "Cortar ao meio")

    def test_detail_without_customer_note_is_empty_string(self) -> None:
        from shopman.backstage.projections.order_queue import build_operator_order

        self.assertEqual(build_operator_order(_order("NOTE-DET-2", "new")).customer_note, "")


class DeliveryAddressReachesTheOperatorTests(TestCase):
    """Quem despacha precisa saber para onde vai.

    O Gestor não tinha endereço em nenhuma das duas projections nem uma
    ocorrência de "address" no app inteiro, embora o pedido sempre carregasse o
    dado (o PDV já o expunha). Os testes vizinhos afirmavam o RECEBIMENTO
    (retirada × entrega) e paravam ali, que é a asserção mais fraca possível
    sobre uma entrega: verdadeira com e sem destino.
    """

    def _delivery(self, ref: str) -> Order:
        order = _order(ref, "ready", "delivery")
        order.data = {
            **order.data,
            "delivery_address": "Rua das Flores, 123 - Centro - Londrina",
            "delivery_address_structured": {
                "route": "Rua das Flores",
                "street_number": "123",
                "complement": "apto 42",
                "delivery_instructions": "Portão azul, interfone 42",
            },
        }
        order.save(update_fields=["data", "updated_at"])
        return order

    def test_card_carries_address_and_instructions(self) -> None:
        card = build_order_card(self._delivery("END-1"))

        self.assertEqual(
            card.delivery_address,
            "Rua das Flores, 123 - Centro - Londrina - apto 42",
        )
        self.assertEqual(card.delivery_instructions, "Portão azul, interfone 42")

    def test_detail_carries_address_and_instructions(self) -> None:
        from shopman.backstage.projections.order_queue import build_operator_order

        proj = build_operator_order(self._delivery("END-2"))

        self.assertIn("Rua das Flores, 123", proj.delivery_address)
        self.assertEqual(proj.delivery_instructions, "Portão azul, interfone 42")
        self.assertEqual(proj.fulfillment_type, "delivery")

    def test_complement_is_not_repeated_when_already_in_the_formatted_text(self) -> None:
        order = _order("END-3", "ready", "delivery")
        order.data = {
            **order.data,
            "delivery_address": "Rua das Flores, 123, apto 42",
            "delivery_address_structured": {"complement": "apto 42"},
        }
        order.save(update_fields=["data", "updated_at"])

        card = build_order_card(order)

        self.assertEqual(card.delivery_address, "Rua das Flores, 123, apto 42")

    def test_pickup_has_no_address_at_all(self) -> None:
        # Controle positivo: o cartão existe e é de retirada, então o endereço
        # vazio é decisão e não uma projection que não montou.
        card = build_order_card(_order("END-4", "ready", "pickup"))

        self.assertEqual(card.fulfillment_label, "Retirada")
        self.assertEqual(card.delivery_address, "")
        self.assertEqual(card.delivery_instructions, "")


class FulfillmentLabelIsPortugueseTests(TestCase):
    """O rótulo de recebimento é TEXTO de tela, e texto de tela é em português.

    Estava `"Delivery" if is_delivery else "Retirada"` — inglês e português no
    mesmo ternário, em dois lugares. O operador lia "Delivery" no cartão.
    """

    def test_card_and_detail_say_entrega(self) -> None:
        from shopman.backstage.projections.order_queue import build_operator_order

        order = _order("PT-1", "ready", "delivery")

        self.assertEqual(build_order_card(order).fulfillment_label, "Entrega")
        self.assertEqual(build_operator_order(order).fulfillment_label, "Entrega")

    def test_pickup_still_says_retirada(self) -> None:
        self.assertEqual(build_order_card(_order("PT-2", "ready")).fulfillment_label, "Retirada")


class DetailProjectionAnswersWhatIsPossibleTests(TestCase):
    """O detalhe do pedido oferecia ação inválida em posição primária.

    A tela guardava o "Avançar" com `can_settle_delivery_cash !== undefined`
    (sempre verdadeiro) e o "Aceitar" com nada, porque a projection do DETALHE
    nunca respondeu o que é possível. Só o cartão respondia, e o board era o
    único que perguntava. Agora as duas respondem igual, com o mesmo serviço.
    """

    def test_new_order_can_be_confirmed_but_not_advanced(self) -> None:
        from shopman.backstage.projections.order_queue import build_operator_order

        proj = build_operator_order(_order("ACT-1", "new"))

        self.assertTrue(proj.can_confirm)
        self.assertFalse(proj.can_advance)

    def test_detail_agrees_with_the_card_on_every_active_status(self) -> None:
        from shopman.backstage.projections.order_queue import build_operator_order

        for i, status in enumerate(["new", "accepted", "preparing", "ready"]):
            with self.subTest(status=status):
                order = _order(f"ACT-CARD-{i}", status)
                card = build_order_card(order)
                detail = build_operator_order(order)

                self.assertEqual(detail.can_confirm, card.can_confirm)
                self.assertEqual(detail.can_advance, card.can_advance)
                self.assertEqual(detail.next_action_label, card.next_action_label)
                self.assertEqual(detail.advance_block_label, card.advance_block_label)
                self.assertEqual(detail.advance_block_reason, card.advance_block_reason)


class TimelineSpeaksPortugueseTests(TestCase):
    """O histórico do pedido é tela de operador, e fala português.

    Só `status_changed` e três tipos tinham rótulo; o resto caía num
    `event.type.replace("_", " ").title()` e o operador lia "Created". Pior: a
    grafia dominante no banco é `status_change` (sem o "d"), que também não era
    reconhecida. E, sem detalhe legível, o fallback despejava o payload cru ao
    lado do evento: `{"from_session": "SESS-..."}` na tela de quem atende.
    """

    def _with_event(self, ref: str, event_type: str, payload: dict):
        from shopman.backstage.projections.order_queue import build_operator_order

        order = _order(ref, "new")
        order.events.create(seq=99, type=event_type, actor="system", payload=payload)
        return build_operator_order(order).timeline[-1]

    def test_creation_event_is_named_in_portuguese(self) -> None:
        event = self._with_event("TL-1", "created", {"from_session": "SESS-ABC"})

        self.assertEqual(event.label, "Pedido criado")

    def test_internal_payload_is_not_dumped_next_to_the_event(self) -> None:
        event = self._with_event("TL-2", "created", {"from_session": "SESS-ABC"})

        self.assertEqual(event.detail, "")

    def test_a_reason_is_still_shown_because_the_operator_reads_it(self) -> None:
        event = self._with_event("TL-3", "operator_comment", {"note": "Cliente pediu sem cebola"})

        self.assertEqual(event.label, "Comentário")
        self.assertEqual(event.detail, "Cliente pediu sem cebola")

    def test_both_spellings_of_the_status_event_are_recognised(self) -> None:
        # `status_changed` vem do model; `status_change` é a grafia da maioria
        # esmagadora das linhas no banco. Só a primeira era tratada.
        for i, event_type in enumerate(["status_changed", "status_change"]):
            with self.subTest(event_type=event_type):
                event = self._with_event(f"TL-ST-{i}", event_type, {"new_status": "accepted"})

                self.assertEqual(event.label, order_status_label("accepted"))
                self.assertNotIn("Status", event.label)
