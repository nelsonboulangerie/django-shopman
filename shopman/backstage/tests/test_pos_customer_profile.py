"""Painel do cliente no PDV: preferências persistentes, alertas e aniversário.

O gravador passivo (`_remember_fiscal_prefs`) só LIGA; o painel liga E desliga
— "hoje não" é desmarcar na venda, "nunca mais" é desligar aqui. E o balcão
passa a ver o que importa com o cliente na frente: restrição alimentar
(segurança), observações, aniversário — com promoção de aniversariante só
quando UMA EXISTE configurada (nunca inventar desconto).
"""

from __future__ import annotations

import json
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils import timezone
from shopman.cashman.models import Shift
from shopman.guestman.models import Customer

from shopman.backstage.projections.pos import build_pos_customer_lookup
from shopman.shop.models import Channel, Promotion, Shop


class POSCustomerProfileTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        Shop.objects.create(name="T", brand_name="T")
        Channel.objects.create(ref="pdv", name="PDV", is_active=True, config={})
        user = get_user_model().objects.create_user("op", password="x", is_staff=True)
        ct = ContentType.objects.get_for_model(Shift)
        user.user_permissions.add(Permission.objects.get(content_type=ct, codename="operate_pos"))
        self.client.force_login(user)
        self.customer = Customer.objects.create(
            ref=Customer.generate_ref(), first_name="Ana", phone="+5543999990010",
            metadata={"fiscal_prefs": {"cpf_na_nota": True}},
        )

    def _post(self, body: dict):
        return self.client.post(
            f"/api/v1/backstage/pos/customer/{self.customer.ref}/profile/",
            data=json.dumps(body),
            content_type="application/json",
        )

    def test_profile_turns_a_preference_OFF(self) -> None:
        """O "nunca mais": desligar é explícito e persiste."""
        response = self._post({"fiscal_prefs": {"cpf_na_nota": False}})

        self.assertEqual(response.status_code, 200)
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.metadata["fiscal_prefs"]["cpf_na_nota"])

    def test_profile_updates_notes_and_restrictions(self) -> None:
        response = self._post({
            "notes": "prefere bem assado",
            "dietary_restrictions": "alérgica a nozes",
        })

        self.assertEqual(response.status_code, 200)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.notes, "prefere bem assado")
        self.assertEqual(self.customer.metadata["preferences"], "alérgica a nozes")
        # ...e a lookup projection devolve os dois para a tela:
        lookup = build_pos_customer_lookup("43999990010")
        self.assertEqual(lookup.notes, "prefere bem assado")
        self.assertEqual(lookup.dietary_restrictions, "alérgica a nozes")

    def test_profile_partial_update_leaves_the_rest_alone(self) -> None:
        self._post({"notes": "só a nota"})

        self.customer.refresh_from_db()
        self.assertTrue(self.customer.metadata["fiscal_prefs"]["cpf_na_nota"])

    def test_birthday_today_with_promo_surfaces_the_label(self) -> None:
        today = timezone.localdate()
        self.customer.birthday = date(1990, today.month, today.day)
        self.customer.save(update_fields=["birthday"])
        Promotion.objects.create(
            ref="aniversario", name="Mimo de aniversário", is_active=True,
            birthday_only=True, type="percent", value=10,
            valid_from=timezone.now() - timezone.timedelta(days=1),
            valid_until=timezone.now() + timezone.timedelta(days=30),
        )

        lookup = build_pos_customer_lookup("43999990010")

        self.assertTrue(lookup.is_birthday_today)
        self.assertEqual(lookup.birthday_promo_label, "Mimo de aniversário")

    def test_birthday_today_without_promo_promises_nothing(self) -> None:
        """Sem promoção configurada (ou vencida), o aviso é só o parabéns."""
        today = timezone.localdate()
        self.customer.birthday = date(1990, today.month, today.day)
        self.customer.save(update_fields=["birthday"])
        # Promo de aniversariante VENCIDA não pode prometer nada:
        Promotion.objects.create(
            ref="vencida", name="Antiga", is_active=True, birthday_only=True,
            type="percent", value=10,
            valid_from=timezone.now() - timezone.timedelta(days=60),
            valid_until=timezone.now() - timezone.timedelta(days=30),
        )

        lookup = build_pos_customer_lookup("43999990010")

        self.assertTrue(lookup.is_birthday_today)
        self.assertEqual(lookup.birthday_promo_label, "")
