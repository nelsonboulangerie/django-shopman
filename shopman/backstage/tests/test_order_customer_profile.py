"""O detalhe do pedido diz QUEM é o cliente (WP-360).

Uma cliente real fez pedido no alpha e o operador abriu o detalhe no Gestor sem
uma linha sobre ela: nem recorrência, nem recência, nem "é de casa ou é a
primeira vez". O dado já existia — materializado em ``CustomerInsight``, no
cadastro do Guestman e no histórico do Orderman — e não chegava à tela de quem
atende.

Estes testes fixam as três coisas que fazem o bloco ser verdadeiro:

* o insight AUSENTE é estado normal (não há cron de ``recalculate_all``), e o
  vazio precisa sair vazio, nunca como zero;
* "última compra" é o pedido ANTERIOR, nunca o que está aberto na tela;
* selo de segmento só nos segmentos que mudam o atendimento.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from shopman.guestman.contrib.insights.models import CustomerInsight
from shopman.guestman.models import Customer
from shopman.orderman.models import Order

from shopman.backstage.projections.order_queue import build_operator_order


def _order(ref: str, *, customer_ref: str = "", created_at=None, total_q: int = 4200) -> Order:
    data = {
        "customer": {"name": "Cristiane"},
        "fulfillment_type": "pickup",
        "payment": {"method": "cash"},
    }
    if customer_ref:
        data["customer_ref"] = customer_ref
    order = Order.objects.create(
        ref=ref,
        channel_ref="web",
        session_key=f"session-{ref}",
        status="new",
        total_q=total_q,
        data=data,
        snapshot={"pricing": {"total_q": total_q}, "items": []},
    )
    if created_at is not None:
        # ``created_at`` é auto_now_add: só um update direto move o relógio.
        Order.objects.filter(pk=order.pk).update(created_at=created_at)
        order.refresh_from_db()
    return order


class CustomerProfileTests(TestCase):
    def test_pedido_sem_cliente_identificado_nao_tem_bloco(self) -> None:
        """Venda anônima: a tela omite o bloco em vez de desenhar perfil vazio."""
        proj = build_operator_order(_order("W-ANON"))

        self.assertIsNone(proj.customer_profile)

    def test_primeira_compra_e_dita_com_todas_as_letras(self) -> None:
        """Cliente novo: sem pedido anterior, o rótulo é "Primeira compra" — e o
        ticket médio some, porque o insight recém-criado ainda não é fato sobre
        hábito nenhum."""
        Customer.objects.create(ref="CLI-1", first_name="Cristiane")
        order = _order("W-1", customer_ref="CLI-1")

        perfil = build_operator_order(order).customer_profile

        assert perfil is not None
        self.assertTrue(perfil.is_first_order)
        self.assertEqual(perfil.orders_label, "Primeira compra")
        self.assertEqual(perfil.last_order_display, "")

    def test_sem_insight_o_vazio_sai_vazio_e_nunca_zero(self) -> None:
        """Cliente importado/semeado não tem insight, e isso é estado NORMAL.

        "R$ 0,00" em ticket médio afirmaria que o cliente não gasta nada — o
        oposto de "ainda não sabemos".
        """
        Customer.objects.create(ref="CLI-2", first_name="Cristiane")
        _order("W-OLD", customer_ref="CLI-2", created_at=timezone.now() - timedelta(days=12))
        order = _order("W-NEW", customer_ref="CLI-2")

        perfil = build_operator_order(order).customer_profile

        assert perfil is not None
        self.assertEqual(perfil.average_ticket_display, "")
        self.assertEqual(perfil.favorite_product, "")
        self.assertEqual(perfil.segment_label, "")
        # Há pedido anterior: dizer "Primeira compra" seria falso, e "0 pedidos"
        # seria pior — sem contagem confiável, a linha da contagem some...
        self.assertFalse(perfil.is_first_order)
        self.assertEqual(perfil.orders_label, "")
        # ...mas a recência continua verdadeira, porque não depende do insight.
        self.assertEqual(perfil.last_order_display, "há 12 dias")

    def test_ultima_compra_e_o_pedido_ANTERIOR_nunca_o_que_esta_na_tela(self) -> None:
        """A armadilha central: ``CustomerInsight.last_order_at`` é recalculado no
        ``customer.ensure`` deste mesmo pedido. Lê-lo diria "última compra hoje"
        no detalhe do pedido de hoje — verdade sobre o pedido aberto, ruído sobre
        a relação com o cliente."""
        customer = Customer.objects.create(ref="CLI-3", first_name="Cristiane")
        agora = timezone.now()
        CustomerInsight.objects.create(
            customer=customer,
            total_orders=5,
            average_ticket_q=4200,
            last_order_at=agora,  # = este pedido
        )
        _order("W-P1", customer_ref="CLI-3", created_at=agora - timedelta(days=30))
        atual = _order("W-P2", customer_ref="CLI-3", created_at=agora)

        perfil = build_operator_order(atual).customer_profile

        assert perfil is not None
        self.assertEqual(perfil.last_order_display, "há 30 dias")
        self.assertEqual(perfil.orders_label, "5 pedidos")
        self.assertEqual(perfil.average_ticket_display, "R$ 42,00")

    def test_ontem_e_hoje_sao_ditos_em_gente(self) -> None:
        customer = Customer.objects.create(ref="CLI-4", first_name="Cristiane")
        CustomerInsight.objects.create(customer=customer, total_orders=2)
        agora = timezone.now()
        _order("W-ONTEM", customer_ref="CLI-4", created_at=agora - timedelta(days=1))
        atual = _order("W-HOJE", customer_ref="CLI-4", created_at=agora)

        perfil = build_operator_order(atual).customer_profile

        assert perfil is not None
        self.assertEqual(perfil.last_order_display, "ontem")
        self.assertEqual(perfil.orders_label, "2 pedidos")

    def test_selo_so_nos_segmentos_que_mudam_o_atendimento(self) -> None:
        """"Regular" não ganha selo: badge que aparece em todo pedido vira
        moldura, e o operador para de lê-la."""
        for i, (segmento, esperado_label, esperado_tom) in enumerate((
            ("loyal_customer", "Cliente fiel", "success"),
            ("at_risk", "Em risco", "warning"),
            ("regular", "", ""),
            ("", "", ""),
        )):
            with self.subTest(segmento=segmento):
                ref = f"CLI-SEG-{i}"
                customer = Customer.objects.create(ref=ref, first_name="Cristiane")
                CustomerInsight.objects.create(
                    customer=customer, total_orders=9, rfm_segment=segmento
                )
                order = _order(f"W-SEG-{i}", customer_ref=ref)

                perfil = build_operator_order(order).customer_profile

                assert perfil is not None
                self.assertEqual(perfil.segment_label, esperado_label)
                self.assertEqual(perfil.segment_tone, esperado_tom)

    def test_historico_vazio_nao_transforma_cliente_de_casa_em_novato(self) -> None:
        """O histórico é indexado por ``data.customer_ref``, o vínculo canônico.

        Um pedido que carregue só ``customer.ref`` devolve histórico vazio — e
        chamar de "Primeira compra" quem tem nove pedidos é mentira na cara do
        operador. O insight desempata: sabe QUANTOS, mesmo sem saber quando foi
        a compra anterior.
        """
        customer = Customer.objects.create(ref="CLI-LEG", first_name="Cristiane")
        CustomerInsight.objects.create(customer=customer, total_orders=9)
        order = Order.objects.create(
            ref="W-LEG",
            channel_ref="web",
            session_key="session-W-LEG",
            status="new",
            total_q=4200,
            data={
                "customer": {"name": "Cristiane", "ref": "CLI-LEG"},
                "fulfillment_type": "pickup",
                "payment": {"method": "cash"},
            },
        )

        perfil = build_operator_order(order).customer_profile

        assert perfil is not None
        self.assertFalse(perfil.is_first_order)
        self.assertEqual(perfil.orders_label, "9 pedidos")
        # Não sabemos QUANDO foi a anterior — e calar é a resposta certa.
        self.assertEqual(perfil.last_order_display, "")

    def test_favorito_vem_do_insight_ja_agregado(self) -> None:
        customer = Customer.objects.create(ref="CLI-5", first_name="Cristiane")
        CustomerInsight.objects.create(
            customer=customer,
            total_orders=7,
            favorite_products=[
                {"sku": "PAO-FRA", "name": "Pão francês", "qty": 40},
                {"sku": "CROIS", "name": "Croissant", "qty": 8},
            ],
        )

        perfil = build_operator_order(_order("W-FAV", customer_ref="CLI-5")).customer_profile

        assert perfil is not None
        self.assertEqual(perfil.favorite_product, "Pão francês")

    def test_cadastro_que_muda_o_atendimento_chega_junto(self) -> None:
        """Nota, restrição alimentar e aniversário — as mesmas três coisas que o
        PDV já mostra ao balcão, lidas pelos mesmos helpers."""
        hoje = timezone.localdate()
        Customer.objects.create(
            ref="CLI-6",
            first_name="Cristiane",
            notes="Prefere retirar no fim da tarde",
            birthday=hoje.replace(year=1990),
            metadata={"preferences": "sem lactose"},
        )

        perfil = build_operator_order(_order("W-CAD", customer_ref="CLI-6")).customer_profile

        assert perfil is not None
        self.assertEqual(perfil.notes, "Prefere retirar no fim da tarde")
        self.assertEqual(perfil.dietary_restrictions, "sem lactose")
        self.assertEqual(perfil.birthday_display, hoje.strftime("%d/%m"))
        self.assertTrue(perfil.is_birthday_today)

    def test_cliente_do_cadastro_apagado_nao_derruba_a_tela(self) -> None:
        """``customer_ref`` órfão (cadastro removido) é ausência, não erro."""
        proj = build_operator_order(_order("W-ORF", customer_ref="CLI-SUMIU"))

        self.assertIsNone(proj.customer_profile)
