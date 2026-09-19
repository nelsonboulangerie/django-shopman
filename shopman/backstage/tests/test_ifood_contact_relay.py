"""O Gestor não oferece WhatsApp para a central do iFood.

O pedido do iFood chega com ``phone.number`` = o 0800 da central deles e um
``localizer``: o código que se digita nesse 0800 para cair na linha do cliente.
A ingestão sempre soube disso — o comentário está em ``_map_customer`` desde o
WP-3 — e a apresentação não sabia: o detalhe do pedido montava
``https://wa.me/558007003050`` (``normalize_phone("0800 700 3050")``) e o
operador que clicasse mandava recado para o atendimento do marketplace.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.backstage.projections.order_queue import build_operator_order

CENTRAL = "0800 705 3040"
LOCALIZADOR = "89338721"


def _order(ref: str, *, channel_ref: str, customer: dict) -> Order:
    order = Order.objects.create(
        ref=ref,
        channel_ref=channel_ref,
        session_key=f"session-{ref}",
        status="new",
        total_q=1000,
        data={
            "customer": customer,
            "fulfillment_type": "pickup",
            "payment": {"method": "external"},
            "availability_decision": {"approved": True, "decisions": []},
        },
    )
    return order


def _stamp(delta: timedelta) -> str:
    return (timezone.now() + delta).isoformat()


class IFoodContactIsARelayNotAPersonTests(TestCase):
    def test_relay_replaces_whatsapp_with_the_code_that_actually_reaches_the_customer(self) -> None:
        order = _order(
            "IFOOD-RELAY-1",
            channel_ref="ifood",
            customer={
                "name": "Cliente iFood",
                "phone": CENTRAL,
                "phone_localizer": LOCALIZADOR,
                "phone_localizer_expires_at": _stamp(timedelta(hours=3)),
            },
        )

        proj = build_operator_order(order)

        self.assertEqual(proj.customer_whatsapp_url, "")
        self.assertEqual(proj.customer_phone_label, "Central de atendimento do iFood")
        self.assertEqual(proj.customer_phone_code, LOCALIZADOR)
        self.assertIn("Não é o telefone do cliente", proj.customer_phone_note)
        self.assertIn("digite o código", proj.customer_phone_note)
        self.assertIn("O código vale até", proj.customer_phone_note)

    def test_relay_number_is_not_dressed_up_as_a_mobile(self) -> None:
        """O 0800 saía da régua de celular como "(80) 0705-3040" — DDD que não existe."""
        order = _order(
            "IFOOD-RELAY-2",
            channel_ref="ifood",
            customer={"phone": CENTRAL, "phone_localizer": LOCALIZADOR},
        )

        proj = build_operator_order(order)

        self.assertEqual(proj.customer_phone, CENTRAL)
        self.assertEqual(proj.customer_phone_uri, "tel:08007053040")

    def test_expired_localizer_is_not_offered_as_if_it_worked(self) -> None:
        order = _order(
            "IFOOD-RELAY-3",
            channel_ref="ifood",
            customer={
                "phone": CENTRAL,
                "phone_localizer": LOCALIZADOR,
                "phone_localizer_expires_at": _stamp(timedelta(days=-80)),
            },
        )

        proj = build_operator_order(order)

        self.assertEqual(proj.customer_whatsapp_url, "")
        self.assertEqual(proj.customer_phone_code, "")
        self.assertIn("venceu em", proj.customer_phone_note)
        self.assertIn("chat do pedido no iFood", proj.customer_phone_note)

    def test_localizer_without_a_deadline_is_still_offered(self) -> None:
        """Sem prazo informado, recusar o código calaria a única forma de falar."""
        order = _order(
            "IFOOD-RELAY-4",
            channel_ref="ifood",
            customer={"phone": CENTRAL, "phone_localizer": LOCALIZADOR},
        )

        proj = build_operator_order(order)

        self.assertEqual(proj.customer_phone_code, LOCALIZADOR)
        self.assertNotIn("vale até", proj.customer_phone_note)

    def test_ifood_without_localizer_still_offers_no_direct_message(self) -> None:
        """O iFood não garante que o número seja o do cliente; mensagem fica fora."""
        order = _order(
            "IFOOD-RELAY-5",
            channel_ref="ifood",
            customer={"phone": "+5543984049009"},
        )

        proj = build_operator_order(order)

        self.assertEqual(proj.customer_whatsapp_url, "")
        self.assertEqual(proj.customer_phone_uri, "tel:+5543984049009")
        self.assertEqual(proj.customer_phone_label, "")
        self.assertEqual(proj.customer_phone_note, "")


class OwnChannelContactIsUntouchedTests(TestCase):
    """O caminho do canal próprio não muda em nada."""

    def test_web_order_keeps_whatsapp_and_gains_no_explanation(self) -> None:
        order = _order(
            "WEB-CONTACT-1",
            channel_ref="web",
            customer={"name": "Cristiane", "phone": "+5543984049009"},
        )

        proj = build_operator_order(order)

        self.assertEqual(proj.customer_phone, "(43) 98404-9009")
        self.assertEqual(proj.customer_phone_uri, "tel:+5543984049009")
        self.assertEqual(proj.customer_whatsapp_url, "https://wa.me/5543984049009")
        self.assertEqual(proj.customer_phone_label, "")
        self.assertEqual(proj.customer_phone_code, "")
        self.assertEqual(proj.customer_phone_note, "")

    def test_web_order_ignores_a_localizer_it_should_never_have(self) -> None:
        """O relé é do canal intermediado; chave solta em pedido próprio não vale."""
        order = _order(
            "WEB-CONTACT-2",
            channel_ref="web",
            customer={"phone": "+5543984049009", "phone_localizer": LOCALIZADOR},
        )

        proj = build_operator_order(order)

        self.assertEqual(proj.customer_whatsapp_url, "https://wa.me/5543984049009")
        self.assertEqual(proj.customer_phone_label, "")
