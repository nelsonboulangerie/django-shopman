"""A recusa de cliente chega ESTRUTURADA ao balcão — inclusive ao FECHAR a venda.

O conflito rico (`field` + `candidates`) sempre existiu e sempre foi detectado
no commit. O que não acontecia era ele CHEGAR: `PosCustomerConflict` herda de
`ValueError`, e o `except ValueError` genérico das views de revisão e de
fechamento achatava a recusa numa frase seca. O operador lia "Este WhatsApp já é
de outro cadastro" e não tinha um caminho — nem atender o outro, nem unificar,
nem corrigir. Beco sem saída com o cliente na frente.

Aqui se prova pela porta HTTP, que é por onde o balcão fala:

  1. fechar a venda devolve `field` + `candidates`;
  2. revisar a venda também;
  3. o dono DESATIVADO aparece nomeado, com `owner_inactive`;
  4. `IntegrityError` vira 422 com frase — nunca 500 mudo;
  5. unificar dois cadastros deixa a comanda no alvo, com auditoria;
  6. liberar o contato preso num cadastro desativado.
"""

from __future__ import annotations

import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError
from django.test import TestCase
from shopman.cashman import services as cash
from shopman.cashman.models import Shift, Terminal
from shopman.guestman.contrib.merge.models import MergeAudit
from shopman.guestman.models import ContactPoint, Customer
from shopman.offerman.models import Listing, ListingItem, Product
from shopman.orderman.models import Order

from shopman.backstage.models import POSTab
from shopman.shop.models import Channel, Shop
from shopman.shop.services.pos_intent import POS_SALE_INTENT_VERSION

CLOSE_URL = "/api/v1/backstage/pos/sale/close/"
REVIEW_URL = "/api/v1/backstage/pos/sale/review/"
MERGE_URL = "/api/v1/backstage/pos/customer/merge/"
RELEASE_URL = "/api/v1/backstage/pos/customer/contact/release/"


class POSConflitoComSaidaTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(
            ref="pdv",
            name="PDV",
            is_active=True,
            config={
                "payment": {"method": "cash", "timing": "external"},
                "surface_policy": {"fulfillment_types": ["pickup"]},
            },
        )
        POSTab.objects.create(ref="00002001", label="2001")
        product = Product.objects.create(
            sku="POS-CONFLICT-ITEM",
            name="Pão do Conflito",
            base_price_q=1200,
            is_published=True,
            is_sellable=True,
        )
        listing = Listing.objects.create(ref="pdv", name="PDV", is_active=True)
        ListingItem.objects.create(
            listing=listing, product=product, price_q=1200,
            is_published=True, is_sellable=True,
        )

        User = get_user_model()
        self.operator = User.objects.create_user(username="pos-conflito", password="x", is_staff=True)
        ct = ContentType.objects.get_for_model(Shift)
        self.operator.user_permissions.add(
            Permission.objects.get(content_type=ct, codename="operate_pos"),
        )
        self.client.force_login(self.operator)
        self.terminal = Terminal.default()
        cash.open_shift(operator=self.operator, terminal=self.terminal, float_q=0)

    # ── ferramentas ──────────────────────────────────────────────────────────

    def _intent(self, **overrides) -> dict:
        payload = {
            "intent_version": POS_SALE_INTENT_VERSION,
            "items": [{
                "sku": "POS-CONFLICT-ITEM",
                "name": "Pão do Conflito",
                "qty": 1,
                "unit_price_q": 1200,
            }],
            "fulfillment_type": "pickup",
            "payment_method": "cash",
            "payment_collection": "terminal",
            "client_request_id": "pos-conflito-001",
        }
        payload.update(overrides)
        return payload

    def _post(self, url: str, payload: dict):
        return self.client.post(url, data=json.dumps(payload), content_type="application/json")

    def _customer(self, ref: str, first: str, last: str, **extra) -> Customer:
        return Customer.objects.create(ref=ref, first_name=first, last_name=last, **extra)

    # ── 1 · FECHAR a venda: a recusa chega inteira ───────────────────────────

    def test_conflito_no_fechamento_chega_estruturado_pela_http(self) -> None:
        """A saída existia e era achatada por um `except ValueError`.

        `PosCustomerConflict` é subclasse de `ValueError`; capturar a superclasse
        primeiro jogava fora `field` e `candidates`, que é justamente o que a
        tela precisa para oferecer "Atender Bruno" / "Manter Ana".
        """
        ana = self._customer("CUST-CLOSE-A", "Ana", "Prado", phone="+5543999990011")
        self._customer("CUST-CLOSE-B", "Bruno", "Souza", phone="+5543999990022")
        pedidos_antes = Order.objects.count()

        response = self._post(CLOSE_URL, self._intent(
            customer_ref=ana.ref,
            customer_name="Ana Prado",
            customer_phone="43999990022",  # o telefone é de Bruno
        ))

        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["error"]["code"], "customer_conflict")
        self.assertEqual(body["error"]["field"], "customer_phone")
        self.assertEqual(body["field"], "customer_phone")
        self.assertIn("WhatsApp", body["detail"])

        candidatos = {row["ref"]: row for row in body["error"]["candidates"]}
        self.assertEqual(set(candidatos), {"CUST-CLOSE-A", "CUST-CLOSE-B"})
        self.assertTrue(candidatos["CUST-CLOSE-A"]["is_current"])
        self.assertFalse(candidatos["CUST-CLOSE-B"]["is_current"])
        self.assertEqual(candidatos["CUST-CLOSE-B"]["name"], "Bruno Souza")
        # Recusa é recusa: a venda NÃO fechou.
        self.assertEqual(Order.objects.count(), pedidos_antes)

    # ── 2 · REVISAR a venda: mesma recusa, mesma estrutura ───────────────────

    def test_conflito_na_revisao_chega_estruturado_pela_http(self) -> None:
        """A revisão é a porta gêmea, e não pode achatar o que o fechamento respeita.

        Hoje `review_sale` não persiste cliente e por isso não levanta o
        conflito sozinho — mas a view capturava `ValueError` genérico, e no dia
        em que a revisão passar a resolver o cliente (é o caminho natural: o
        operador quer saber ANTES de fechar) a recusa chegaria achatada sem que
        ninguém percebesse. O que se prova aqui é o CONTRATO da view.
        """
        from shopman.shop.services.pos import PosCustomerConflict

        conflito = PosCustomerConflict(
            "Este WhatsApp já é de outro cadastro.",
            field="customer_phone",
            candidates=[
                {"ref": "CUST-REVIEW-A", "name": "Ana Prado", "is_current": True,
                 "matched_by": ["ref"], "owner_inactive": False},
                {"ref": "CUST-REVIEW-B", "name": "Bruno Souza", "is_current": False,
                 "matched_by": ["phone"], "owner_inactive": False},
            ],
        )
        with mock.patch("shopman.shop.services.pos.review_sale", side_effect=conflito):
            response = self._post(REVIEW_URL, self._intent(customer_name="Ana Prado"))

        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["error"]["code"], "customer_conflict")
        self.assertEqual(body["error"]["field"], "customer_phone")
        self.assertEqual(body["field"], "customer_phone")
        self.assertEqual(
            {row["ref"] for row in body["error"]["candidates"]},
            {"CUST-REVIEW-A", "CUST-REVIEW-B"},
        )

    # ── 3 · O dono INATIVO: o conflito que virava frase seca ─────────────────

    def test_dono_inativo_vira_conflito_rico_e_nomeado(self) -> None:
        """O resolve só enxerga ATIVO; os UNIQUEs do banco enxergam TODOS.

        Com o dono desativado não nascia candidato, não havia conflito rico, e o
        INSERT estourava lá embaixo — frase seca sobre um cadastro que o
        operador não consegue nem achar na busca.
        """
        ana = self._customer("CUST-INACT-A", "Ana", "Prado", phone="+5543999990011")
        antigo = self._customer(
            "CUST-INACT-OLD", "Cadastro", "Antigo", phone="+5543999990022", is_active=False,
        )

        response = self._post(CLOSE_URL, self._intent(
            customer_ref=ana.ref,
            customer_name="Ana Prado",
            customer_phone="43999990022",
        ))

        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["error"]["code"], "customer_conflict")
        self.assertEqual(body["error"]["field"], "customer_phone")
        self.assertIn("desativado", body["detail"])

        candidatos = {row["ref"]: row for row in body["error"]["candidates"]}
        # O dono é NOMEADO — é a informação que faltava por completo.
        self.assertIn(antigo.ref, candidatos)
        self.assertTrue(candidatos[antigo.ref]["owner_inactive"])
        self.assertEqual(candidatos[antigo.ref]["name"], "Cadastro Antigo")
        self.assertFalse(candidatos[antigo.ref]["is_current"])
        self.assertFalse(candidatos[ana.ref]["owner_inactive"])

    def test_cpf_de_dono_inativo_tambem_e_nomeado(self) -> None:
        """O irmão fiscal do caso acima — mesma cegueira, mesma saída."""
        from shopman.guestman.contrib.identifiers.models import CustomerIdentifier

        ana = self._customer("CUST-CPF-A", "Ana", "Prado", phone="+5543999990011")
        antigo = self._customer("CUST-CPF-OLD", "Cadastro", "Antigo", is_active=False)
        CustomerIdentifier.objects.create(
            customer=antigo, identifier_type="cpf", identifier_value="52998224725",
        )

        response = self._post(CLOSE_URL, self._intent(
            customer_ref=ana.ref,
            customer_name="Ana Prado",
            customer_tax_id="529.982.247-25",
        ))

        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["error"]["field"], "customer_tax_id")
        candidatos = {row["ref"]: row for row in body["error"]["candidates"]}
        self.assertTrue(candidatos[antigo.ref]["owner_inactive"])

    # ── 4 · O 500 mudo: o balcão nunca lê uma frase que não existe ───────────

    def test_integrity_error_no_fechamento_vira_422_com_frase(self) -> None:
        """`IntegrityError` não é `ValueError`: escapava da view e virava 500.

        Sem `detail`, o front cai na frase genérica e a venda trava sem que
        ninguém saiba por quê. A blindagem é da view, e continua valendo depois
        de a raiz ser corrigida.
        """
        alvo = "shopman.shop.services.pos.close_sale"
        with mock.patch(alvo, side_effect=IntegrityError("duplicate key")):
            response = self._post(CLOSE_URL, self._intent(customer_name="Alguém"))

        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertTrue(body["detail"])
        self.assertIn("cadastro", body["detail"].lower())

    def test_integrity_error_na_revisao_vira_422_com_frase(self) -> None:
        alvo = "shopman.shop.services.pos.review_sale"
        with mock.patch(alvo, side_effect=IntegrityError("duplicate key")):
            response = self._post(REVIEW_URL, self._intent(customer_name="Alguém"))

        self.assertEqual(response.status_code, 422)
        self.assertTrue(response.json()["detail"])

    # ── 5 · Unificar: a terceira saída, com auditoria ────────────────────────

    def test_unificar_deixa_a_comanda_no_cadastro_alvo_e_deixa_rastro(self) -> None:
        """"É a mesma pessoa" — nem atender o outro, nem manter quem está."""
        duplicado = self._customer("CUST-MERGE-SRC", "Ana", "Prado", phone="+5543999990022")
        alvo = self._customer("CUST-MERGE-DST", "Ana", "Prado", phone="+5543999990011")

        response = self._post(MERGE_URL, {
            "source_ref": duplicado.ref,
            "target_ref": alvo.ref,
        })

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        # A comanda segue no ALVO, e a projeção dele volta pronta.
        self.assertEqual(body["customer"]["ref"], alvo.ref)
        self.assertEqual(body["merge"]["target_ref"], alvo.ref)
        self.assertEqual(body["merge"]["source_ref"], duplicado.ref)

        duplicado.refresh_from_db()
        self.assertFalse(duplicado.is_active)

        # Rastro: auditoria com quem fez, e a janela para desfazer.
        audit = MergeAudit.objects.get(pk=body["merge"]["audit_id"])
        self.assertEqual(audit.target_ref, alvo.ref)
        self.assertEqual(audit.actor, "pos-conflito")
        self.assertTrue(body["merge"]["undo_deadline"])

    def test_unificar_recusa_o_mesmo_cadastro_com_frase_em_portugues(self) -> None:
        alvo = self._customer("CUST-MERGE-SAME", "Ana", "Prado")

        response = self._post(MERGE_URL, {"source_ref": alvo.ref, "target_ref": alvo.ref})

        self.assertEqual(response.status_code, 422)
        self.assertIn("mesmo", response.json()["detail"])

    # ── 6 · Liberar o contato preso num cadastro desativado ──────────────────

    def test_liberar_contato_de_cadastro_desativado_destrava_a_venda(self) -> None:
        """O merge recusa inativo dos dois lados — esta é a saída que sobra."""
        ana = self._customer("CUST-REL-A", "Ana", "Prado", phone="+5543999990011")
        antigo = self._customer(
            "CUST-REL-OLD", "Cadastro", "Antigo", phone="+5543999990022", is_active=False,
        )

        liberado = self._post(RELEASE_URL, {
            "field": "customer_phone", "value": "43999990022",
        })

        self.assertEqual(liberado.status_code, 200)
        self.assertEqual(liberado.json()["released_from"]["ref"], antigo.ref)
        antigo.refresh_from_db()
        self.assertEqual(antigo.phone, "")
        self.assertFalse(
            ContactPoint.objects.filter(value_normalized="+5543999990022").exists(),
        )

        # E agora a venda que estava travada FECHA, com o número em nome de Ana.
        fechada = self._post(CLOSE_URL, self._intent(
            customer_ref=ana.ref,
            customer_name="Ana Prado",
            customer_phone="43999990022",
        ))
        self.assertEqual(fechada.status_code, 200)
        self.assertEqual(
            ContactPoint.objects.get(value_normalized="+5543999990022").customer_id,
            ana.pk,
        )

    def test_liberar_contato_de_cadastro_ATIVO_e_recusado(self) -> None:
        """Liberar contato de cliente ativo seria roubar em silêncio."""
        self._customer("CUST-REL-LIVE", "Bruno", "Souza", phone="+5543999990033")

        response = self._post(RELEASE_URL, {
            "field": "customer_phone", "value": "43999990033",
        })

        self.assertEqual(response.status_code, 422)
        self.assertIn("Bruno", response.json()["detail"])
        self.assertEqual(Customer.objects.get(ref="CUST-REL-LIVE").phone, "+5543999990033")

    # ── 7 · A ORDEM de salvar o contato do comprovante usa a MESMA saída ─────

    def test_ordem_de_salvar_email_do_comprovante_de_outro_cadastro_vira_422_rico(self) -> None:
        """Gravar passou a ser oferecido; a recusa não pode ser um 500 mudo.

        Quando o operador MANDA guardar no cadastro um e-mail que já é de outra
        pessoa, o UNIQUE global de `ContactPoint` recusa. Sem a checagem prévia
        isso subia como `IntegrityError` de dentro do `Customer.save()` — lido
        ali como conflito de TELEFONE, ou escapando da view como HTTP 500 com a
        venda travada. Aqui é a mesma recusa rica das outras portas.
        """
        ana = self._customer("CUST-RCPT-A", "Ana", "Prado", phone="+5543999990011")
        self._customer(
            "CUST-RCPT-B", "Bruno", "Souza", phone="+5543999990022", email="bruno@example.org",
        )
        pedidos_antes = Order.objects.count()

        response = self._post(CLOSE_URL, self._intent(
            customer_ref=ana.ref,
            customer_name="Ana Prado",
            receipt_channels=["email"],
            receipt_email="bruno@example.org",
            save_receipt_contact=True,
        ))

        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["error"]["code"], "customer_conflict")
        self.assertEqual(body["error"]["field"], "customer_email")
        candidatos = {row["ref"]: row for row in body["error"]["candidates"]}
        self.assertEqual(set(candidatos), {"CUST-RCPT-A", "CUST-RCPT-B"})
        self.assertTrue(candidatos["CUST-RCPT-A"]["is_current"])
        # Recusa é recusa: a venda NÃO fechou.
        self.assertEqual(Order.objects.count(), pedidos_antes)

    def test_ordem_de_salvar_cpf_da_nota_de_outro_cadastro_vira_422_rico(self) -> None:
        """O CPF tem a matriz inteira — inclusive esta linha."""
        ana = self._customer("CUST-RCPT-C", "Ana", "Prado", phone="+5543999990011")
        self._customer(
            "CUST-RCPT-D", "Bruno", "Souza", phone="+5543999990022", document="52998224725",
        )

        response = self._post(CLOSE_URL, self._intent(
            customer_ref=ana.ref,
            customer_name="Ana Prado",
            fiscal_tax_id="52998224725",
            save_receipt_tax_id=True,
        ))

        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["error"]["field"], "customer_tax_id")
        self.assertEqual(
            {row["ref"] for row in body["error"]["candidates"]},
            {"CUST-RCPT-C", "CUST-RCPT-D"},
        )

    def test_sem_a_ordem_a_nota_vai_para_o_email_de_outro_e_a_venda_FECHA(self) -> None:
        """"A pessoa pode querer enviar para outro e-mail, por algum motivo."

        Sem ordem de gravar não há posse em disputa: a nota vai para o endereço
        informado, e os dois cadastros ficam como estavam.
        """
        ana = self._customer("CUST-RCPT-E", "Ana", "Prado", phone="+5543999990011")
        bruno = self._customer(
            "CUST-RCPT-F", "Bruno", "Souza", phone="+5543999990022", email="bruno@example.org",
        )

        response = self._post(CLOSE_URL, self._intent(
            customer_ref=ana.ref,
            customer_name="Ana Prado",
            receipt_channels=["email"],
            receipt_email="bruno@example.org",
        ))

        self.assertEqual(response.status_code, 200)
        ana.refresh_from_db()
        bruno.refresh_from_db()
        self.assertEqual(ana.email, "")
        self.assertEqual(bruno.email, "bruno@example.org")
        pedido = Order.objects.get(ref=response.json()["order_ref"])
        self.assertEqual(pedido.data["receipt"]["email"], "bruno@example.org")
