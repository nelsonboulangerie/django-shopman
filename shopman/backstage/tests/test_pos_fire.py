"""POS kitchen handoff — progressive (course-by-course) fire from a comanda."""

from __future__ import annotations

from django.test import TestCase
from shopman.orderman.models import Session

from shopman.backstage.models import KDSInstance, KDSTicket, POSTab
from shopman.backstage.projections.pos import build_open_tab
from shopman.shop.models import Channel, Shop
from shopman.shop.services import pos as pos_service


class POSFireTabTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="Balcão", is_active=True)
        POSTab.objects.create(ref="00002001", label="2001")
        # Catch-all picking station (no collections) keeps routing trivial.
        KDSInstance.objects.create(ref="cozinha", name="Cozinha", type="picking")
        from shopman.offerman.models import Product

        for sku in ("FIRE-A", "FIRE-B"):
            Product.objects.create(
                sku=sku, name=sku, base_price_q=1000,
                is_published=True, is_sellable=True,
            )

    def _open_tab(self) -> str:
        opened = build_open_tab(pos_service.open_pos_tab(
            channel_ref="pdv", tab_ref="2001",
            actor="pos:alice", operator_username="alice",
        ))
        return opened["tab_session_key"]

    def _save(self, session_key: str, items: list[dict]) -> Session:
        """Salva a comanda como o PDV salva: com o ``line_id`` de cada linha.

        A identidade nasce no cliente e volta em todo save — é ela que faz duas
        linhas do mesmo SKU serem duas, e é ela que impede o fechamento de
        re-disparar para a cozinha.
        """
        pos_service.save_pos_tab(
            channel_ref="pdv",
            payload={
                "items": items,
                "customer_name": "Ana",
                "payment_method": "cash",
                "manual_discount": None,
                "tab_ref": "2001",
                "tab_session_key": session_key,
            },
            actor="pos:alice", operator_username="alice",
        )
        return Session.objects.get(session_key=session_key)

    def _open_tab_with_two_items(self) -> Session:
        return self._save(self._open_tab(), [
            {"line_id": "L-A", "sku": "FIRE-A", "name": "Fire A", "qty": 1, "unit_price_q": 1000},
            {"line_id": "L-B", "sku": "FIRE-B", "name": "Fire B", "qty": 1, "unit_price_q": 1000},
        ])

    def test_line_notes_and_order_notes_reach_the_kds_ticket(self) -> None:
        """A observação da linha (POS 'Obs.') e a do pedido chegam à cozinha.

        O PDV agora edita ``items[].notes`` e ``order_notes``; o caminho até o
        KDS já existia (meta.notes → fire lines → ticket → projection) e este
        teste o trava de ponta a ponta.
        """
        opened = build_open_tab(pos_service.open_pos_tab(
            channel_ref="pdv", tab_ref="2001",
            actor="pos:alice", operator_username="alice",
        ))
        skey = opened["tab_session_key"]
        pos_service.save_pos_tab(
            channel_ref="pdv",
            payload={
                "items": [
                    {
                        "sku": "FIRE-A", "name": "Fire A", "qty": 1,
                        "unit_price_q": 1000, "notes": "sem cebola",
                    },
                ],
                "order_notes": "cliente com pressa",
                "payment_method": "cash",
                "manual_discount": None,
                "tab_ref": "2001",
                "tab_session_key": skey,
            },
            actor="pos:alice", operator_username="alice",
        )
        # O payload da comanda devolve a observação para a tela do PDV.
        session = Session.objects.get(session_key=skey)
        payload = build_open_tab(session)
        self.assertEqual(payload["items"][0]["notes"], "sem cebola")
        self.assertEqual(payload["order_notes"], "cliente com pressa")

        pos_service.fire_pos_tab(
            channel_ref="pdv", session_key=skey,
            actor="pos:alice", operator_username="alice",
        )
        ticket = KDSTicket.objects.get(session_key=skey)
        self.assertEqual(ticket.items[0]["notes"], "sem cebola")

        from shopman.backstage.projections.kds import build_kds_ticket

        projection = build_kds_ticket(ticket.pk)
        self.assertEqual(projection.items[0].notes, "sem cebola")
        self.assertEqual(projection.customer_note, "cliente com pressa")

    def test_fire_whole_tab_creates_tickets_and_marks_fired(self) -> None:
        session = self._open_tab_with_two_items()
        line_ids = {it["line_id"] for it in session.items}

        result = pos_service.fire_pos_tab(
            channel_ref="pdv", session_key=session.session_key,
            actor="pos:alice", operator_username="alice",
        )

        # Both lines route to the one picking station → a single ticket.
        self.assertEqual(result.fired_count, 1)
        self.assertEqual(set(result.fired_lines), line_ids)
        tickets = KDSTicket.objects.filter(session_key=session.session_key)
        self.assertEqual(tickets.count(), 1)
        self.assertEqual({it["line_id"] for it in tickets.first().items}, line_ids)
        # Comanda marker persisted and the cart payload annotates each line fired.
        session.refresh_from_db()
        self.assertEqual(set(session.data["fired_lines"]), line_ids)
        self.assertTrue(all(it["fired"] for it in build_open_tab(result.session)["items"]))

    def test_progressive_fire_sends_only_the_delta(self) -> None:
        session = self._open_tab_with_two_items()
        line_ids = sorted(it["line_id"] for it in session.items)
        first_line, second_line = line_ids[0], line_ids[1]

        # Fire course 1 only.
        first = pos_service.fire_pos_tab(
            channel_ref="pdv", session_key=session.session_key,
            line_ids=[first_line], actor="pos:alice", operator_username="alice",
        )
        self.assertEqual(first.fired_count, 1)
        self.assertEqual(list(first.fired_lines), [first_line])

        # Fire the whole tab → only the still-unfired course 2 is dispatched.
        second = pos_service.fire_pos_tab(
            channel_ref="pdv", session_key=session.session_key,
            actor="pos:alice", operator_username="alice",
        )
        self.assertEqual(second.fired_count, 1)
        self.assertEqual(list(second.fired_lines), line_ids)
        ticket_lines = set()
        for ticket in KDSTicket.objects.filter(session_key=session.session_key):
            ticket_lines.update(it["line_id"] for it in ticket.items)
        self.assertEqual(ticket_lines, {first_line, second_line})

        # Re-firing once everything is out is a no-op.
        third = pos_service.fire_pos_tab(
            channel_ref="pdv", session_key=session.session_key,
            actor="pos:alice", operator_username="alice",
        )
        self.assertEqual(third.fired_count, 0)
        self.assertEqual(KDSTicket.objects.filter(session_key=session.session_key).count(), 2)

    def test_pedir_mais_do_mesmo_item_vira_uma_linha_nova_na_cozinha(self) -> None:
        """O segundo chá. Ele é uma LINHA, não uma unidade a mais na primeira.

        O defeito que abriu o assunto: com uma linha por SKU, "mais um chá" virava
        `qty: 2` numa linha que já tinha ido para a cozinha — e o ledger do KDS
        deduplica por `line_id`. O fire virava no-op e o segundo chá nunca era
        feito, sem erro e sem aviso, com o cliente esperando. Agora a linha tem
        identidade própria: a nova nasce com id novo e é ela que o fire encontra
        por fazer.
        """
        session = self._open_tab_with_two_items()
        pos_service.fire_pos_tab(
            channel_ref="pdv", session_key=session.session_key,
            actor="pos:alice", operator_username="alice",
        )
        session.refresh_from_db()
        self.assertEqual(session.data["fired_qty"]["L-A"], 1)

        # O operador toca no mesmo produto de novo — depois do envio, o PDV cria
        # uma SEGUNDA linha do mesmo SKU em vez de engordar a que já foi.
        session = self._save(session.session_key, [
            {"line_id": "L-A", "sku": "FIRE-A", "name": "Fire A", "qty": 1, "unit_price_q": 1000},
            {"line_id": "L-B", "sku": "FIRE-B", "name": "Fire B", "qty": 1, "unit_price_q": 1000},
            {"line_id": "L-C", "sku": "FIRE-A", "name": "Fire A", "qty": 1, "unit_price_q": 1000},
        ])
        self.assertEqual([it["line_id"] for it in session.items], ["L-A", "L-B", "L-C"])

        again = pos_service.fire_pos_tab(
            channel_ref="pdv", session_key=session.session_key,
            actor="pos:alice", operator_username="alice",
        )

        # A cozinha recebe UM ticket novo, com a linha nova e só ela — nunca a
        # primeira de novo, que reimprimiria o chá já feito.
        self.assertEqual(again.fired_count, 1)
        novo_ticket = KDSTicket.objects.filter(session_key=session.session_key).order_by("-id").first()
        self.assertEqual([(it["line_id"], it["qty"]) for it in novo_ticket.items], [("L-C", 1)])
        session.refresh_from_db()
        self.assertEqual(session.data["fired_qty"], {"L-A": 1, "L-B": 1, "L-C": 1})

        # E agora não há mais o que enviar.
        self.assertEqual(
            pos_service.fire_pos_tab(
                channel_ref="pdv", session_key=session.session_key,
                actor="pos:alice", operator_username="alice",
            ).fired_count,
            0,
        )

    def test_duas_linhas_do_mesmo_sku_sobrevivem_ao_save_com_os_ids(self) -> None:
        """Save/reload não funde nem embaralha duas linhas do mesmo produto.

        A identidade vem do payload; enquanto ela era deduzida do SKU, o
        remove+readd do save casava as linhas pelo produto — com duas do mesmo
        SKU, a segunda perdia o id e a comanda voltava do banco trocada.
        """
        skey = self._open_tab()
        itens = [
            {"line_id": "L-1", "sku": "FIRE-A", "name": "Fire A", "qty": 1, "unit_price_q": 1000,
             "notes": "sem açúcar"},
            {"line_id": "L-2", "sku": "FIRE-A", "name": "Fire A", "qty": 2, "unit_price_q": 1000,
             "discount": {"type": "percent", "value": 10, "reason": "cortesia"}},
        ]
        session = self._save(skey, itens)
        session = self._save(session.session_key, itens)  # o segundo save é o que provava o defeito

        payload = build_open_tab(session)
        por_linha = {it["line_id"]: it for it in payload["items"]}
        self.assertEqual(set(por_linha), {"L-1", "L-2"})
        # A observação fica na linha que a recebeu…
        self.assertEqual(por_linha["L-1"]["notes"], "sem açúcar")
        self.assertEqual(por_linha["L-2"]["notes"], "")
        # …e o desconto também: a linha cheia volta pelo preço cheio, a linha com
        # cortesia volta pelo preço PRÉ-desconto (para o reenvio não aplicá-lo
        # duas vezes) e carregando o descritor.
        self.assertIsNone(por_linha["L-1"]["discount"])
        self.assertEqual(por_linha["L-2"]["discount"]["value"], 10)
        self.assertEqual(por_linha["L-2"]["discount"]["reason"], "cortesia")

    def test_o_desconto_manual_nao_vaza_entre_duas_linhas_do_mesmo_sku(self) -> None:
        """A cortesia é DESTA linha; a irmã do mesmo produto segue pelo preço dela.

        O registro que sobrevive ao save é ``session.pricing["discount"]["items"]``
        (a linha perde campos extras no ``update_items``), e ele nomeava só o SKU:
        com duas linhas do mesmo produto, o registro de uma respondia pela outra.
        Agora cada registro diz de QUE LINHA é.
        """
        from django.utils import timezone as _tz

        from shopman.shop.models import Promotion

        # O motor de desconto só roda quando há promoção/cupom ativos, e é ele
        # quem escreve o registro que este teste lê.
        Promotion.objects.create(
            ref="semana", name="Semana do Pão", is_active=True, type="percent", value=5,
            valid_from=_tz.now() - _tz.timedelta(days=1),
            valid_until=_tz.now() + _tz.timedelta(days=30),
        )
        session = self._save(self._open_tab(), [
            {"line_id": "L-1", "sku": "FIRE-A", "name": "Fire A", "qty": 1, "unit_price_q": 1000,
             "discount": {"type": "percent", "value": 10, "reason": "cortesia"}},
            {"line_id": "L-2", "sku": "FIRE-A", "name": "Fire A", "qty": 1, "unit_price_q": 1000},
        ])

        registros = {r["line_id"]: r for r in session.pricing["discount"]["items"]}
        self.assertEqual(registros["L-1"]["type"], "manual")
        self.assertEqual(registros["L-1"]["original_price_q"], 1000)
        # A outra linha do MESMO SKU não ganhou a cortesia: ela levou a promoção.
        self.assertEqual(registros["L-2"]["type"], "promotion")

        por_linha = {it["line_id"]: it for it in build_open_tab(session)["items"]}
        # A linha da cortesia volta pelo preço PRÉ-desconto (para o reenvio não o
        # aplicar duas vezes) e cobra 10% a menos.
        self.assertEqual(por_linha["L-1"]["price_q"], 1000)
        self.assertEqual(por_linha["L-1"]["charged_price_q"], 900)
        self.assertEqual(por_linha["L-1"]["discount"]["reason"], "cortesia")
        # A irmã cobra os 5% da promoção — e não tem descritor de cortesia nenhum.
        self.assertIsNone(por_linha["L-2"]["discount"])
        self.assertEqual(por_linha["L-2"]["charged_price_q"], 950)

    def test_o_estado_da_cozinha_e_por_linha_nao_por_produto(self) -> None:
        """Uma linha "Pronto" e outra "A enviar", ao mesmo tempo, no mesmo SKU."""
        session = self._save(self._open_tab(), [
            {"line_id": "L-1", "sku": "FIRE-A", "name": "Fire A", "qty": 1, "unit_price_q": 1000},
        ])
        pos_service.fire_pos_tab(
            channel_ref="pdv", session_key=session.session_key,
            actor="pos:alice", operator_username="alice",
        )
        ticket = KDSTicket.objects.get(session_key=session.session_key)
        ticket.status = "done"
        ticket.save(update_fields=["status"])

        session = self._save(session.session_key, [
            {"line_id": "L-1", "sku": "FIRE-A", "name": "Fire A", "qty": 1, "unit_price_q": 1000},
            {"line_id": "L-2", "sku": "FIRE-A", "name": "Fire A", "qty": 1, "unit_price_q": 1000},
        ])

        por_linha = {it["line_id"]: it for it in build_open_tab(session)["items"]}
        self.assertEqual(por_linha["L-1"]["kitchen_status"], "done")
        self.assertTrue(por_linha["L-1"]["fired"])
        # A linha nova não herda nada da irmã: ninguém começou a fazê-la.
        self.assertEqual(por_linha["L-2"]["kitchen_status"], "")
        self.assertFalse(por_linha["L-2"]["fired"])

    def test_salvar_de_novo_a_comanda_disparada_nao_redispara(self) -> None:
        """Reenviar a mesma comanda é no-op — o ledger é por `line_id`.

        É a mesma identidade que atravessa o save: se ela fosse regerada, o fire
        seguinte veria linhas "novas" e a cozinha prepararia tudo em dobro.
        """
        session = self._open_tab_with_two_items()
        pos_service.fire_pos_tab(
            channel_ref="pdv", session_key=session.session_key,
            actor="pos:alice", operator_username="alice",
        )
        session = self._save(session.session_key, [
            {"line_id": "L-A", "sku": "FIRE-A", "name": "Fire A", "qty": 1, "unit_price_q": 1000},
            {"line_id": "L-B", "sku": "FIRE-B", "name": "Fire B", "qty": 1, "unit_price_q": 1000},
        ])

        de_novo = pos_service.fire_pos_tab(
            channel_ref="pdv", session_key=session.session_key,
            actor="pos:alice", operator_username="alice",
        )

        self.assertEqual(de_novo.fired_count, 0)
        self.assertEqual(KDSTicket.objects.filter(session_key=session.session_key).count(), 1)

    def test_a_linha_enviada_que_encolhe_deixa_sobra_na_cozinha(self) -> None:
        """`fired_qty` existe para UMA pergunta: a linha enviada encolheu?

        Reduzir de 2 para 1 algo que a cozinha já está fazendo não desfaz o
        trabalho dela. O balcão precisa ver a sobra antes de fechar a venda.
        """
        session = self._save(self._open_tab(), [
            {"line_id": "L-1", "sku": "FIRE-A", "name": "Fire A", "qty": 2, "unit_price_q": 1000},
        ])
        pos_service.fire_pos_tab(
            channel_ref="pdv", session_key=session.session_key,
            actor="pos:alice", operator_username="alice",
        )
        session = self._save(session.session_key, [
            {"line_id": "L-1", "sku": "FIRE-A", "name": "Fire A", "qty": 1, "unit_price_q": 1000},
        ])

        linha = build_open_tab(session)["items"][0]
        self.assertEqual(linha["qty"], 1)
        self.assertEqual(linha["fired_qty"], 2)

    def test_cancelar_o_envio_de_uma_linha_nao_toca_a_irma_do_mesmo_sku(self) -> None:
        """Duas linhas do mesmo produto se cancelam separadamente.

        O alvo é o `line_id`, e é só ele: cancelar "o chá" cancelava o chá dos
        dois clientes da mesa enquanto a identidade da linha era o produto.
        """
        session = self._save(self._open_tab(), [
            {"line_id": "L-1", "sku": "FIRE-A", "name": "Fire A", "qty": 1, "unit_price_q": 1000},
            {"line_id": "L-2", "sku": "FIRE-A", "name": "Fire A", "qty": 1, "unit_price_q": 1000},
        ])
        pos_service.fire_pos_tab(
            channel_ref="pdv", session_key=session.session_key,
            actor="pos:alice", operator_username="alice",
        )

        pos_service.cancel_fired_pos_tab_lines(
            channel_ref="pdv", session_key=session.session_key,
            line_ids=["L-1"], actor="pos:alice", operator_username="alice",
        )

        session.refresh_from_db()
        vivos = set()
        for ticket in KDSTicket.objects.filter(session_key=session.session_key).exclude(status="cancelled"):
            vivos.update(it["line_id"] for it in ticket.items)
        self.assertEqual(vivos, {"L-2"})
        self.assertEqual(session.data["fired_qty"], {"L-2": 1})
        por_linha = {it["line_id"]: it for it in build_open_tab(session)["items"]}
        self.assertFalse(por_linha["L-1"]["fired"])
        self.assertTrue(por_linha["L-2"]["fired"])

    def test_close_after_fire_does_not_refire_to_kitchen(self) -> None:
        """Regressão: comanda disparada e DEPOIS fechada não pode re-disparar.

        Antes, o fechamento reconstruía as linhas com line_ids NOVOS, então o
        dispatch do pedido committado via lifecycle disparava tudo de novo —
        comanda preparada em dobro. O line_id vem no payload e atravessa o
        remove+readd: o pedido herda o mesmo id e o ledger de fire casa.
        """
        from shopman.orderman.models import Order

        session = self._open_tab_with_two_items()
        fired_line_ids = {it["line_id"] for it in session.items}

        pos_service.fire_pos_tab(
            channel_ref="pdv", session_key=session.session_key,
            actor="pos:alice", operator_username="alice",
        )
        tickets_after_fire = KDSTicket.objects.filter(session_key=session.session_key).exclude(status="cancelled").count()
        self.assertEqual(tickets_after_fire, 1)

        # A venda do terminal acontece dentro de um turno do cashman (a linha
        # `sale` nasce no livro dele); sem turno o shop recusa antes do commit.
        from django.contrib.auth import get_user_model
        from shopman.cashman import services as cash

        alice = get_user_model().objects.create_user(username="alice", password="x")
        shift = cash.open_shift(operator=alice, float_q=0)
        pos_service.close_sale(
            channel_ref="pdv",
            payload={
                "intent_version": pos_service.POS_SALE_INTENT_VERSION,
                "cash_shift_id": shift.pk,
                "tab_ref": "2001",
                "tab_session_key": session.session_key,
                "items": [
                    {"line_id": "L-A", "sku": "FIRE-A", "name": "Fire A", "qty": 1, "unit_price_q": 1000},
                    {"line_id": "L-B", "sku": "FIRE-B", "name": "Fire B", "qty": 1, "unit_price_q": 1000},
                ],
                "fulfillment_type": "pickup",
                "payment_method": "cash",
                "payment_collection": "terminal",
                "tendered_q": 2000,
                "client_request_id": "pos-fire-then-close-001",
            },
            actor="pos:alice", operator_username="alice",
        )

        order = Order.objects.get(session_key=session.session_key)
        order_line_ids = {item.line_id for item in order.items.all()}
        # As linhas do pedido herdaram os line_ids disparados (não foram regeradas)…
        self.assertEqual(order_line_ids, fired_line_ids)
        # …então NÃO houve re-disparo: continua 1 ticket vivo (não dobrou).
        tickets_after_close = KDSTicket.objects.filter(session_key=session.session_key).exclude(status="cancelled").count()
        self.assertEqual(tickets_after_close, 1)

    def test_tab_board_flags_fired_unpaid_tab(self) -> None:
        from shopman.backstage.projections.pos import build_pos_tabs

        session = self._open_tab_with_two_items()
        before = {t.ref: t for t in build_pos_tabs(channel_ref="pdv")}
        assert before["00002001"].fired is False

        pos_service.fire_pos_tab(
            channel_ref="pdv", session_key=session.session_key,
            actor="pos:alice", operator_username="alice",
        )

        after = {t.ref: t for t in build_pos_tabs(channel_ref="pdv")}
        assert after["00002001"].fired is True

    def test_fire_unknown_tab_raises(self) -> None:
        from shopman.shop.services.pos_intent import PosIntentError

        with self.assertRaises(PosIntentError):
            pos_service.fire_pos_tab(
                channel_ref="pdv", session_key="does-not-exist",
                actor="pos:alice", operator_username="alice",
            )

    def test_unfire_trims_then_cancels_and_frees_line_to_refire(self) -> None:
        session = self._open_tab_with_two_items()
        line_ids = sorted(it["line_id"] for it in session.items)
        first_line, second_line = line_ids[0], line_ids[1]

        # Fire the whole tab → one ticket holding both lines.
        pos_service.fire_pos_tab(
            channel_ref="pdv", session_key=session.session_key,
            actor="pos:alice", operator_username="alice",
        )
        ticket = KDSTicket.objects.get(session_key=session.session_key)
        self.assertEqual(len(ticket.items), 2)

        # Cancel one line → ticket is trimmed (still live), line drops from fired.
        trim = pos_service.cancel_fired_pos_tab_lines(
            channel_ref="pdv", session_key=session.session_key,
            line_ids=[first_line], actor="pos:alice", operator_username="alice",
        )
        self.assertEqual(trim.trimmed, 1)
        self.assertEqual(trim.cancelled, 0)
        self.assertEqual(list(trim.fired_lines), [second_line])
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, "pending")
        self.assertEqual({it["line_id"] for it in ticket.items}, {second_line})
        # The cart shows the cancelled line as fireable again.
        fired_flags = {it["line_id"]: it["fired"] for it in build_open_tab(trim.session)["items"]}
        self.assertFalse(fired_flags[first_line])
        self.assertTrue(fired_flags[second_line])

        # The freed line re-fires (reprint = un-fire + fire).
        refire = pos_service.fire_pos_tab(
            channel_ref="pdv", session_key=session.session_key,
            line_ids=[first_line], actor="pos:alice", operator_username="alice",
        )
        self.assertEqual(refire.fired_count, 1)
        self.assertEqual(set(refire.fired_lines), {first_line, second_line})

        # Cancel the last line on the original ticket → it empties → cancelled.
        cancel = pos_service.cancel_fired_pos_tab_lines(
            channel_ref="pdv", session_key=session.session_key,
            line_ids=[second_line], actor="pos:alice", operator_username="alice",
        )
        self.assertEqual(cancel.cancelled, 1)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, "cancelled")
        self.assertIsNotNone(ticket.cancelled_at)
        self.assertEqual(list(cancel.fired_lines), [first_line])

    def test_unfire_only_touches_targeted_progressive_ticket(self) -> None:
        session = self._open_tab_with_two_items()
        line_ids = sorted(it["line_id"] for it in session.items)
        first_line, second_line = line_ids[0], line_ids[1]

        # Fire course by course → two separate tickets.
        pos_service.fire_pos_tab(
            channel_ref="pdv", session_key=session.session_key,
            line_ids=[first_line], actor="pos:alice", operator_username="alice",
        )
        pos_service.fire_pos_tab(
            channel_ref="pdv", session_key=session.session_key,
            line_ids=[second_line], actor="pos:alice", operator_username="alice",
        )
        self.assertEqual(KDSTicket.objects.filter(session_key=session.session_key).count(), 2)

        # Cancel course 1 → only its ticket is cancelled, course 2 untouched.
        pos_service.cancel_fired_pos_tab_lines(
            channel_ref="pdv", session_key=session.session_key,
            line_ids=[first_line], actor="pos:alice", operator_username="alice",
        )
        live = KDSTicket.objects.filter(session_key=session.session_key).exclude(status="cancelled")
        self.assertEqual(live.count(), 1)
        self.assertEqual({it["line_id"] for it in live.first().items}, {second_line})
