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
from shopman.guestman.contrib.identifiers import IdentifierService
from shopman.guestman.contrib.merge.models import MergeAudit
from shopman.guestman.models import ContactPoint, Customer
from shopman.offerman.models import Listing, ListingItem, Product
from shopman.orderman.models import Order

from shopman.backstage.models import POSTab
from shopman.shop.models import Channel, ContactRelease, ReleasedContactKind, Shop
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
            "field": "customer_phone", "value": "43999990022", "confirmed": True,
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

    def test_liberar_SEM_reconfirmar_nao_acontece(self) -> None:
        """A gêmea, no servidor, da segunda pergunta da tela.

        Liberar apaga um ``ContactPoint`` e não tem desfazer. A fricção mora no
        ato destrutivo, não num passo seguinte — e ela não pode viver só no
        JavaScript: uma tela é uma cortesia, o service é a trava.
        """
        antigo = self._customer(
            "CUST-REL-NOCONF", "Cadastro", "Antigo",
            phone="+5543999990044", is_active=False,
        )

        response = self._post(RELEASE_URL, {
            "field": "customer_phone", "value": "43999990044",
        })

        self.assertEqual(response.status_code, 422)
        self.assertIn("Confirme", response.json()["detail"])
        # E o contato continua exatamente onde estava.
        antigo.refresh_from_db()
        self.assertEqual(antigo.phone, "+5543999990044")
        self.assertTrue(ContactPoint.objects.filter(value_normalized="+5543999990044").exists())
        self.assertEqual(ContactRelease.objects.count(), 0)

    def test_liberar_deixa_RASTRO_do_que_era_e_de_qual_ficha_saiu(self) -> None:
        """Um ``.delete()`` sem rastro é uma perda que ninguém consegue narrar.

        A unificação já resolveu isto do jeito certo (``MergeAudit``: quem,
        quando, o que saiu de onde, e um retrato para desfazer). A liberação
        seguia com uma linha de log — que ninguém lê e que não reconstrói
        cadastro nenhum. É este registro que dá lastro à promessa da tela: "fica
        registrado, dá para refazer depois".
        """
        antigo = self._customer(
            "CUST-REL-TRAIL", "Cadastro", "Antigo",
            phone="+5543999990055", is_active=False,
        )
        ponto = ContactPoint.objects.get(value_normalized="+5543999990055")
        pk_apagado = str(ponto.pk)
        era_principal = ponto.is_primary

        response = self._post(RELEASE_URL, {
            "field": "customer_phone", "value": "43999990055", "confirmed": True,
        })
        self.assertEqual(response.status_code, 200)

        rastro = ContactRelease.objects.get(pk=response.json()["release_id"])
        # O VALOR e o TIPO — o que foi solto.
        self.assertEqual(rastro.value, "+5543999990055")
        self.assertEqual(rastro.kind, ReleasedContactKind.PHONE)
        # DE QUAL FICHA saiu — pelo ref, que é a chave que não muda.
        self.assertEqual(rastro.released_from_ref, antigo.ref)
        self.assertIn("Antigo", rastro.released_from_name)
        # QUEM liberou e QUANDO.
        self.assertEqual(rastro.actor, "pos-conflito")
        self.assertIsNotNone(rastro.released_at)
        # E o bastante para RECONSTRUIR: o PK que sumiu e o posto que ele ocupava.
        self.assertEqual(rastro.released_pk, pk_apagado)
        self.assertEqual(rastro.was_primary, era_principal)

        # E o contato foi de fato solto — rastro não é substituto de efeito.
        self.assertFalse(ContactPoint.objects.filter(value_normalized="+5543999990055").exists())

    def test_liberar_CPF_tambem_deixa_rastro(self) -> None:
        """O documento sai por outra porta (``CustomerIdentifier``), não por um atalho."""
        # Nasce ATIVO para o identificador poder ser criado (o Core só enxerga
        # cliente ativo ali) e é desativado depois — que é a ordem em que a
        # realidade acontece: primeiro o cadastro existe, depois ele morre.
        antigo = self._customer("CUST-REL-CPF", "Cadastro", "Antigo", document="52998224725")
        IdentifierService.ensure_identifier(
            customer_ref=antigo.ref,
            identifier_type="cpf",
            identifier_value="52998224725",
            is_primary=True,
            source_system="teste",
        )
        Customer.objects.filter(pk=antigo.pk).update(is_active=False)

        response = self._post(RELEASE_URL, {
            "field": "customer_tax_id", "value": "529.982.247-25", "confirmed": True,
        })
        self.assertEqual(response.status_code, 200)

        rastro = ContactRelease.objects.get(pk=response.json()["release_id"])
        self.assertEqual(rastro.kind, ReleasedContactKind.CPF)
        self.assertEqual(rastro.value, "52998224725")
        self.assertEqual(rastro.released_from_ref, antigo.ref)
        self.assertTrue(rastro.released_pk)
        antigo.refresh_from_db()
        self.assertEqual(antigo.document, "")

    def test_liberar_contato_QUE_VEIO_DE_UMA_UNIFICACAO_marca_o_desfazer(self) -> None:
        """A interação que ninguém tinha mapeado — e que falha em SILÊNCIO.

        O ``MergeService.undo`` devolve os registros migrados pelos **PKs
        guardados no snapshot**. Um PK apagado não volta: a unificação desfeita
        nasce incompleta e ninguém é avisado — o gestor clica "desfazer", lê
        "desfeita", e o cadastro que voltou tem um contato a menos que ele nunca
        vai procurar.

        Aqui se prova o caminho inteiro: a unificação move o contato, o cadastro
        que ficou é desativado depois, o balcão libera o contato — e o rastro
        aponta a unificação afetada, que é o que permite AVISAR quem desfizer.
        """
        absorvido = self._customer("CUST-UNDO-SRC", "Ana", "Antiga")
        sobrevivente = self._customer("CUST-UNDO-TGT", "Ana", "Prado")
        ContactPoint.objects.create(
            customer=absorvido,
            type=ContactPoint.Type.EMAIL,
            value_normalized="ana@example.org",
            value_display="ana@example.org",
            is_primary=True,
        )

        unificado = self._post(MERGE_URL, {
            "source_ref": absorvido.ref, "target_ref": sobrevivente.ref,
        })
        self.assertEqual(unificado.status_code, 200)
        audit_id = unificado.json()["merge"]["audit_id"]
        # O contato mudou de dono e o PK dele ficou no retrato do desfazer.
        movido = ContactPoint.objects.get(value_normalized="ana@example.org")
        self.assertEqual(movido.customer_id, sobrevivente.pk)
        self.assertIn(str(movido.pk), MergeAudit.objects.get(pk=audit_id).snapshot["contact_points"])

        # Mais tarde o cadastro que ficou também é desativado, e aí o e-mail
        # está preso num cadastro morto — o beco que a liberação resolve.
        Customer.objects.filter(pk=sobrevivente.pk).update(is_active=False)

        liberado = self._post(RELEASE_URL, {
            "field": "customer_email", "value": "ana@example.org", "confirmed": True,
        })
        self.assertEqual(liberado.status_code, 200)

        # O rastro AMARRA a liberação à unificação cujo desfazer ela degrada.
        self.assertEqual(liberado.json()["merge_audit_id"], audit_id)
        rastro = ContactRelease.objects.get(pk=liberado.json()["release_id"])
        self.assertEqual(str(rastro.merge_audit_id), audit_id)
        # E guarda o que é preciso para reconstruir o que o `undo` não devolve.
        self.assertEqual(rastro.released_pk, str(movido.pk))
        self.assertEqual(rastro.value, "ana@example.org")
        self.assertEqual(rastro.released_from_ref, sobrevivente.ref)

    def test_liberar_contato_SEM_unificacao_por_tras_nao_inventa_vinculo(self) -> None:
        """O vínculo é achado, não presumido: sem unificação, ele fica vazio."""
        self._customer(
            "CUST-REL-SOLO", "Cadastro", "Antigo",
            phone="+5543999990066", is_active=False,
        )

        liberado = self._post(RELEASE_URL, {
            "field": "customer_phone", "value": "43999990066", "confirmed": True,
        })

        self.assertEqual(liberado.status_code, 200)
        self.assertEqual(liberado.json()["merge_audit_id"], "")
        self.assertIsNone(ContactRelease.objects.get(value="+5543999990066").merge_audit_id)

    def test_liberar_contato_de_cadastro_ATIVO_e_recusado(self) -> None:
        """Liberar contato de cliente ativo seria roubar em silêncio."""
        self._customer("CUST-REL-LIVE", "Bruno", "Souza", phone="+5543999990033")

        response = self._post(RELEASE_URL, {
            "field": "customer_phone", "value": "43999990033", "confirmed": True,
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

    # ── 8 · Sobrescrever o CPF do cadastro tem GÊMEA no servidor ─────────────

    def test_sobrescrever_cpf_sem_a_segunda_palavra_vira_422_com_frase(self) -> None:
        """A fricção da tela não pode morar só na tela.

        A tela cobra a reconfirmação antes de deixar a ordem viajar. Mas trava
        que existe só no front não é trava: um tablet com JS velho, um script,
        a próxima superfície — qualquer um mandaria `save_receipt_tax_id`
        sozinho e a identidade fiscal do cadastro trocaria calada. Aqui a ordem
        sem a segunda palavra é RECUSADA, e a frase diz o que sai e o que entra.
        """
        ana = self._customer(
            "CUST-CPF-A", "Ana", "Prado", phone="+5543999990011", document="52998224725",
        )
        pedidos_antes = Order.objects.count()

        response = self._post(CLOSE_URL, self._intent(
            customer_ref=ana.ref,
            customer_name="Ana Prado",
            fiscal_tax_id="11144477735",
            save_receipt_tax_id=True,
        ))

        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["field"], "customer_tax_id")
        self.assertEqual(body["error"]["code"], "tax_id_overwrite_unconfirmed")
        self.assertIn("52998224725", body["detail"])
        self.assertIn("11144477735", body["detail"])
        self.assertIn("customer_tax_id", body["errors"])
        # O cadastro fica como estava, e a venda não fecha.
        ana.refresh_from_db()
        self.assertEqual(ana.document, "52998224725")
        self.assertEqual(Order.objects.count(), pedidos_antes)

    def test_sobrescrever_cpf_COM_a_segunda_palavra_grava_como_hoje(self) -> None:
        ana = self._customer(
            "CUST-CPF-B", "Ana", "Prado", phone="+5543999990011", document="52998224725",
        )

        response = self._post(CLOSE_URL, self._intent(
            customer_ref=ana.ref,
            customer_name="Ana Prado",
            fiscal_tax_id="11144477735",
            save_receipt_tax_id=True,
            save_receipt_tax_id_confirmed=True,
        ))

        self.assertEqual(response.status_code, 200)
        ana.refresh_from_db()
        self.assertEqual(ana.document, "11144477735")

    def test_preencher_lacuna_de_cpf_segue_de_UM_toque(self) -> None:
        """Atrito no caminho comum vira clique de reflexo — por isso não há."""
        ana = self._customer("CUST-CPF-C", "Ana", "Prado", phone="+5543999990011")

        response = self._post(CLOSE_URL, self._intent(
            customer_ref=ana.ref,
            customer_name="Ana Prado",
            fiscal_tax_id="11144477735",
            save_receipt_tax_id=True,
        ))

        self.assertEqual(response.status_code, 200)
        ana.refresh_from_db()
        self.assertEqual(ana.document, "11144477735")

    def test_email_divergente_NAO_paga_o_pedagio_do_cpf(self) -> None:
        """A assimetria entre CPF e e-mail é o alvo, não um descuido."""
        ana = self._customer(
            "CUST-CPF-D", "Ana", "Prado", phone="+5543999990011", email="ana@example.org",
        )

        response = self._post(CLOSE_URL, self._intent(
            customer_ref=ana.ref,
            customer_name="Ana Prado",
            receipt_channels=["email"],
            receipt_email="ana.nova@example.org",
            save_receipt_contact=True,
        ))

        self.assertEqual(response.status_code, 200)
        ana.refresh_from_db()
        self.assertEqual(ana.email, "ana.nova@example.org")
