"""O "quando" perguntado na ABERTURA do atendimento, não no pagamento.

O agendamento acontece com o operador no telefone: ele ainda nem lançou tudo, e
já precisa dizer ao cliente "quinta às 10h, pode ser?". A review só responde no
checkout — ficar sem resposta até lá é o que empurrava a data para o fim do
fluxo, onde ela nunca deveria ter morado.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils import timezone
from shopman.cashman.models import Shift
from shopman.offerman.models import Product

from shopman.shop.models import Channel, Shop

URL = "/api/v1/backstage/pos/schedule/"

ABERTO_TODO_DIA = {
    day: {"open": "08:00", "close": "18:00"}
    for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
}


class POSScheduleTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        Shop.objects.create(name="Nelson", brand_name="Nelson", opening_hours=ABERTO_TODO_DIA)
        Channel.objects.create(ref="pdv", name="PDV", is_active=True, config={})
        Product.objects.create(sku="CR", name="Croissant", base_price_q=900)
        Product.objects.create(
            sku="BF",
            name="Baguette de Tradition",
            base_price_q=1600,
            metadata={"ready_from": "12:00"},
        )
        user = get_user_model().objects.create_user("op", password="x", is_staff=True)
        ct = ContentType.objects.get_for_model(Shift)
        user.user_permissions.add(Permission.objects.get(content_type=ct, codename="operate_pos"))
        self.client.force_login(user)
        self.amanha = (timezone.localdate() + timedelta(days=1)).isoformat()

    def test_exige_permissao_de_balcao(self) -> None:
        self.client.logout()
        outro = get_user_model().objects.create_user("visita", password="x", is_staff=True)
        self.client.force_login(outro)

        self.assertEqual(self.client.get(URL).status_code, 403)

    def test_oferece_as_datas_operantes(self) -> None:
        payload = self.client.get(URL).json()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["today"], timezone.localdate().isoformat())
        self.assertIn(self.amanha, payload["available_dates"])

    def test_data_em_branco_e_hoje(self) -> None:
        self.assertEqual(self.client.get(URL).json()["date"], timezone.localdate().isoformat())

    def test_data_ilegivel_cai_em_hoje_em_vez_de_estourar(self) -> None:
        """A tela nunca fica sem resposta por causa de um parâmetro torto."""
        resposta = self.client.get(URL, {"date": "amanhã"})

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["date"], timezone.localdate().isoformat())

    def test_a_ENCOMENDA_sai_nos_slots_canonicos(self) -> None:
        """Data futura = turno, não hora marcada. HOJE é que usa a meia hora."""
        payload = self.client.get(URL, {"date": self.amanha}).json()

        self.assertEqual(
            [w["ref"] for w in payload["windows"]], ["slot-09", "slot-12", "slot-15"]
        )
        self.assertEqual(payload["grid"], "canonical")
        self.assertTrue(all(w["enabled"] for w in payload["windows"]))

    def test_HOJE_sai_na_meia_hora_do_expediente(self) -> None:
        payload = self.client.get(URL).json()

        self.assertEqual(payload["grid"], "half_hour")

    def test_a_baguete_desabilita_a_manha_e_diz_por_que(self) -> None:
        """O carrinho entra na pergunta: a janela oferecível DEPENDE do que tem
        dentro. É a falha que o dono chamou de gravíssima."""
        payload = self.client.get(URL, {"date": self.amanha, "skus": "BF,CR"}).json()

        por_ref = {w["ref"]: w for w in payload["windows"]}
        self.assertFalse(por_ref["slot-09"]["enabled"])
        self.assertEqual(
            por_ref["slot-09"]["reason"], "Baguette de Tradition sai às 12:00."
        )
        self.assertTrue(por_ref["slot-12"]["enabled"])
        self.assertEqual(payload["earliest_window_ref"], "slot-12")
        self.assertEqual(payload["ready_at"], "12:00")
        self.assertEqual(payload["bottleneck_name"], "Baguette de Tradition")

    def test_carrinho_sem_prontidao_nao_restringe(self) -> None:
        payload = self.client.get(URL, {"date": self.amanha, "skus": "CR"}).json()

        self.assertTrue(all(w["enabled"] for w in payload["windows"]))
        self.assertEqual(payload["ready_at"], "")

    def test_skus_em_branco_na_lista_sao_ignorados(self) -> None:
        payload = self.client.get(URL, {"date": self.amanha, "skus": "BF,,  ,CR"}).json()

        self.assertEqual(payload["bottleneck_name"], "Baguette de Tradition")
