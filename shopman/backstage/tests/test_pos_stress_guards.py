"""Guardas do PDV encontradas por teste de estresse (troco, teto, retirada).

Cada teste aqui nasceu de um comportamento observado no PDV rodando, não de um
refinamento teórico: o troco anunciado num cartão digitado a mais, o teto de
desconto que o Admin editava sem efeito, e a sangria que um operador lançava
sozinho e o fechamento cego absolvia.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings
from shopman.cashman import services as cash
from shopman.cashman.models import Entry, Shift, Terminal
from shopman.doorman.models import PinCredential
from shopman.offerman.models import Listing, ListingItem, Product

from shopman.backstage.projections.pos import build_pos
from shopman.backstage.services.exceptions import POSError
from shopman.backstage.services.pos import register_cash_movement
from shopman.shop.models import Channel, Shop
from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import POS_SALE_INTENT_VERSION, PosIntentError


def _grant(user, codename: str) -> None:
    ct = ContentType.objects.get_for_model(Shift)
    user.user_permissions.add(Permission.objects.get(content_type=ct, codename=codename))


class PosGuardsBase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        Shop.objects.create(name="Guard Shop", brand_name="Guard")
        Channel.objects.create(
            ref="pdv",
            name="PDV",
            is_active=True,
            config={
                "payment": {"method": "cash", "timing": "external"},
                "surface_policy": {"fulfillment_types": ["pickup", "delivery"]},
            },
        )
        product = Product.objects.create(
            sku="GUARD-ITEM", name="Item", base_price_q=1000,
            is_published=True, is_sellable=True,
        )
        listing = Listing.objects.create(ref="pdv", name="PDV", is_active=True)
        ListingItem.objects.create(
            listing=listing, product=product, price_q=1000,
            is_published=True, is_sellable=True,
        )
        User = get_user_model()
        self.operator = User.objects.create_user(username="guard-op", password="x", is_staff=True)
        _grant(self.operator, "operate_pos")
        self.manager = User.objects.create_user(username="guard-mgr", password="x", is_staff=True)
        _grant(self.manager, "adjust_shift")
        PinCredential.set_for(self.manager, "4321")
        self.terminal = Terminal.default()

    def _payload(self, **over):
        payload = {
            "intent_version": POS_SALE_INTENT_VERSION,
            "items": [{"sku": "GUARD-ITEM", "name": "Item", "qty": 1, "unit_price_q": 1000}],
            "fulfillment_type": "pickup",
            "payment_method": "cash",
            "payment_collection": "terminal",
        }
        payload.update(over)
        return payload

    def _review(self, **over):
        return pos_service.review_sale(
            channel_ref="pdv",
            payload=self._payload(**over),
            operator_username=self.operator.username,
        )


class ChangeIsCashOnlyTests(PosGuardsBase):
    """Troco sai da gaveta, então só dinheiro recebido a mais vira troco."""

    def test_card_overpay_is_not_change(self) -> None:
        review = self._review(
            payment_method="mixed",
            payment_tenders=[{"method": "card", "amount_q": 500000}],
        )

        self.assertEqual(review.total_q, 1000)
        self.assertEqual(review.tender_total_q, 500000)
        self.assertEqual(review.change_q, 0)
        self.assertIn("tender_overpaid_non_cash", {w["code"] for w in review.warnings})

    def test_cash_overpay_is_change(self) -> None:
        review = self._review(
            payment_method="mixed",
            payment_tenders=[{"method": "cash", "amount_q": 5000}],
        )

        self.assertEqual(review.change_q, 4000)
        self.assertNotIn("tender_overpaid_non_cash", {w["code"] for w in review.warnings})

    def test_mixed_change_limited_to_the_cash_share(self) -> None:
        # Cartão cobre o total e ainda sobra dinheiro: o troco é só a parte em
        # espécie, nunca o excedente do cartão.
        review = self._review(
            payment_method="mixed",
            payment_tenders=[
                {"method": "card", "amount_q": 1000},
                {"method": "cash", "amount_q": 500},
            ],
        )

        self.assertEqual(review.change_q, 500)


class DiscountThresholdHasOneOwnerTests(PosGuardsBase):
    """O teto que a tela mostra é o teto que cobra o PIN."""

    @override_settings(SHOPMAN_POS_DISCOUNT_APPROVAL_THRESHOLD_Q=500)
    def test_admin_threshold_drives_the_gate_and_the_projection(self) -> None:
        shop = Shop.load()
        shop.defaults = {**(shop.defaults or {}), "pos": {"discount_approval_threshold_q": 5000}}
        shop.save(update_fields=["defaults"])

        review = self._review(manual_discount={"type": "fixed", "value": "30,00"})
        exposed = build_pos(operator=self.operator).checkout.capabilities[
            "requires_manager_approval_above_q"
        ]

        self.assertEqual(exposed, 5000)
        self.assertEqual(review.manager_approval_threshold_q, 5000)
        # R$ 30,00 está abaixo do teto de R$ 50,00 que a loja configurou.
        self.assertFalse(review.requires_manager_approval)
        pos_service.validate_manager_approval(
            self._payload(manual_discount={"type": "fixed", "value": "30,00"}),
            operator_username=self.operator.username,
        )

    @override_settings(SHOPMAN_POS_DISCOUNT_APPROVAL_THRESHOLD_Q=500)
    def test_env_is_the_fallback_when_the_shop_says_nothing(self) -> None:
        review = self._review(manual_discount={"type": "fixed", "value": "30,00"})

        self.assertEqual(review.manager_approval_threshold_q, 500)
        self.assertTrue(review.requires_manager_approval)
        self.assertIn("discount_over_threshold", review.approval_reasons)

    @override_settings(SHOPMAN_POS_DISCOUNT_APPROVAL_THRESHOLD_Q=500)
    def test_reasons_name_the_trigger(self) -> None:
        # Sobrou UM gatilho, e é o certo: o desconto acima do teto da loja. O
        # segundo era `price_override` — o operador digitava o preço unitário à
        # mão —, e ele saiu com o mecanismo: preço à mão não passava pela régua
        # do desconto (limite, motivo, "maior desconto ganha") e tinha portão
        # próprio. Uma régua com duas portas não é uma régua.
        review = self._review(manual_discount={"type": "fixed", "value": "30,00"})

        self.assertEqual(review.approval_reasons, ("discount_over_threshold",))

    @override_settings(SHOPMAN_POS_DISCOUNT_APPROVAL_THRESHOLD_Q=500)
    def test_desconto_de_LINHA_em_reais_tambem_passa_pela_regua(self) -> None:
        # O limite mede o desconto SOMADO (linha + pedido). O de linha em R$ é
        # novo, e precisa entrar na mesma conta — senão bastava dar a cortesia
        # por item para escapar do gerente.
        review = self._review(items=[
            {"sku": "GUARD-ITEM", "name": "Item", "qty": 1, "unit_price_q": 3000,
             "list_price_q": 3000,
             "discount": {"type": "fixed", "value": 20.0, "reason": "cortesia"}},
        ])

        self.assertTrue(review.requires_manager_approval)
        self.assertEqual(review.approval_reasons, ("discount_over_threshold",))


class CashRemovalNeedsAManagerTests(PosGuardsBase):
    """Retirada de gaveta é exceção auditada: exige PIN, em qualquer valor."""

    def setUp(self) -> None:
        super().setUp()
        self.shift = cash.open_shift(operator=self.operator, terminal=self.terminal, float_q=10000)

    def test_sangria_without_approval_is_refused(self) -> None:
        with self.assertRaises(PosIntentError) as ctx:
            register_cash_movement(
                operator=self.operator, movement_type="sangria",
                amount_raw="1,00", reason="teste",
            )

        self.assertEqual(ctx.exception.code, "manager_approval_required")
        self.assertFalse(Entry.objects.filter(kind=Entry.Kind.CASH_OUT).exists())

    def test_sangria_with_a_valid_pin_records_both_signatures(self) -> None:
        movement = register_cash_movement(
            operator=self.operator, movement_type="sangria",
            amount_raw="50,00", reason="depósito",
            manager_approval={"username": self.manager.username, "pin": "4321"},
        )

        self.assertEqual(movement.operator, self.operator)
        self.assertEqual(movement.approved_by, self.manager)
        self.assertEqual(movement.amount_q, -5000)

    def test_sangria_with_a_wrong_pin_is_refused(self) -> None:
        with self.assertRaises(PosIntentError) as ctx:
            register_cash_movement(
                operator=self.operator, movement_type="sangria",
                amount_raw="50,00", reason="x",
                manager_approval={"username": self.manager.username, "pin": "0000"},
            )

        self.assertEqual(ctx.exception.code, "manager_approval_invalid")

    def test_a_non_manager_cannot_authorize(self) -> None:
        PinCredential.set_for(self.operator, "1111")

        with self.assertRaises(PosIntentError):
            register_cash_movement(
                operator=self.operator, movement_type="sangria",
                amount_raw="50,00", reason="x",
                manager_approval={"username": self.operator.username, "pin": "1111"},
            )

    def test_valor_negativo_nao_vira_sangria_disfarcada(self) -> None:
        # O `ajuste` com sinal foi aposentado justamente porque era uma segunda
        # porta para o mesmo efeito. Agora valor negativo é recusado: um
        # suprimento de −20 seria uma sangria sem gerente.
        with self.assertRaises(POSError):
            register_cash_movement(
                operator=self.operator, movement_type="suprimento",
                amount_raw="-20,00", reason="Cofre",
            )

    def test_suprimento_needs_no_manager(self) -> None:
        movement = register_cash_movement(
            operator=self.operator, movement_type="suprimento",
            amount_raw="30,00", reason="Reforço de troco",
        )

        self.assertIsNone(movement.approved_by)
        self.assertEqual(movement.kind, Entry.Kind.CASH_IN)
        self.assertEqual(movement.amount_q, 3000)

    def test_tipo_desconhecido_cai_em_sangria_e_exige_gerente(self) -> None:
        # Fail-safe: o que não é suprimento é tratado como retirada. Cair no
        # tipo permissivo deixaria passar dinheiro saindo sem assinatura.
        with self.assertRaises(PosIntentError):
            register_cash_movement(
                operator=self.operator, movement_type="ajuste",
                amount_raw="5,00", reason="sobra",
            )

    def test_movement_still_requires_an_open_shift(self) -> None:
        cash.close_shift(self.shift, counted_q=10000, actor=self.operator)

        with self.assertRaises(POSError):
            register_cash_movement(
                operator=self.operator, movement_type="suprimento",
                amount_raw="10,00", reason="x",
            )


class AbsurdQuantityIsRefusedCleanlyTests(PosGuardsBase):
    def test_quantity_over_the_ceiling_raises_a_domain_error(self) -> None:
        with self.assertRaises(PosIntentError) as ctx:
            pos_service.review_sale(
                channel_ref="pdv",
                payload=self._payload(items=[
                    {"sku": "GUARD-ITEM", "name": "Item", "qty": 10**9, "unit_price_q": 1000},
                ]),
                operator_username=self.operator.username,
            )

        self.assertEqual(ctx.exception.code, "quantity_too_large")


class TerminalHealthOnlyWarnsAboutWhatExistsTests(PosGuardsBase):
    def test_a_terminal_without_declared_hardware_is_ready(self) -> None:
        from shopman.backstage.services.pos_terminal import runtime_profile

        profile = runtime_profile(self.terminal)

        self.assertEqual(profile.status, "ready")
        self.assertEqual({c.status for c in profile.components}, {"absent"})

    def test_a_declared_component_without_adapter_still_warns(self) -> None:
        from shopman.backstage.services.pos_terminal import runtime_profile

        self.terminal.metadata = {"hardware": {"printer": {"enabled": True}}}
        self.terminal.save(update_fields=["metadata"])

        profile = runtime_profile(self.terminal)

        self.assertEqual(profile.status, "warning")

    def test_a_real_adapter_is_ready_not_suspicious(self) -> None:
        from shopman.backstage.services.pos_terminal import runtime_profile

        self.terminal.metadata = {"hardware": {"printer": {"enabled": True, "adapter": "escpos"}}}
        self.terminal.save(update_fields=["metadata"])

        profile = runtime_profile(self.terminal)

        self.assertEqual(profile.status, "ready")
