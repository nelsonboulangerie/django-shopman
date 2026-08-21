"""Quem fecha a gaveta no fim do expediente.

Este arquivo substitui ``test_pos_close_blocking.py``. Aquele testava um segundo
caminho de fechamento — o "supervisório" — que existia para destravar o beco em
que a segunda pessoa do balcão caía: terminal com turno aberto de outra pessoa.
Com a custódia na gaveta o beco sumiu, o caminho sumiu junto, e sobrou UMA
pergunta: quem pode fechar.

**Resposta (decisão do dono, 21/08/2026): a gerência** (``perform_closing``). A
contagem é cega, então tecnicamente qualquer um poderia contar sem conseguir
burlar; a responsabilidade, ainda assim, começa atribuída a quem fecha o dia.
Não há exceção para "quem abriu": a gaveta não tem dono.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from shopman.cashman.models import Shift

from shopman.backstage.services import pos as pos_service
from shopman.shop.models import Shop

User = get_user_model()
URL = "/api/v1/backstage/pos/cash/close/"


def _grant(user, model, codename):
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    ct = ContentType.objects.get_for_model(model)
    user.user_permissions.add(Permission.objects.get(content_type=ct, codename=codename))
    return User.objects.get(pk=user.pk)  # refresca cache de permissão


@override_settings(SHOPMAN_REQUIRE_ACTIVE_OPERATOR=False)
class POSCashClosePolicyTests(TestCase):
    def setUp(self):
        Shop.objects.create(name="Test", brand_name="Test")
        self.joyce = _grant(
            User.objects.create_user("joyce", password="x", is_staff=True), Shift, "operate_pos"
        )
        self.shift = pos_service.open_cash_shift(operator=self.joyce, opening_amount_raw="50,00")

    def _client(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def _gerente(self, username="marina"):
        from shopman.backstage.models import DayClosing

        return _grant(
            _grant(User.objects.create_user(username, password="x", is_staff=True), Shift, "operate_pos"),
            DayClosing, "perform_closing",
        )

    def test_a_gerencia_fecha_a_gaveta_que_outra_pessoa_abriu(self):
        """O caso NORMAL: a Joyce abriu de manhã, a gerente fecha no fim do dia."""
        resp = self._client(self._gerente()).post(URL, {"closing_amount": "50,00"}, format="json")

        self.assertEqual(resp.status_code, 200, resp.content)
        self.shift.refresh_from_db()
        self.assertEqual(self.shift.status, Shift.Status.CLOSED)
        # Quem abriu continua registrado; quem contou está na linha da contagem.
        self.assertEqual(self.shift.opened_by, self.joyce)
        contagem = self.shift.entries.get(kind="count")
        self.assertEqual(contagem.operator.get_username(), "marina")

    def test_quem_ABRIU_nao_fecha_por_ter_aberto(self):
        """A exceção "dono do turno" morreu junto com o dono do turno.

        Antes a Joyce fechava o próprio turno; agora a gaveta não é dela, e a
        regra é uma só — fechar é da gerência.
        """
        resp = self._client(self.joyce).post(URL, {"closing_amount": "50,00"}, format="json")

        self.assertEqual(resp.status_code, 403, resp.content)
        self.assertEqual(resp.json()["error"]["code"], "cash_close_forbidden")
        self.shift.refresh_from_db()
        self.assertEqual(self.shift.status, Shift.Status.OPEN)

    def test_operador_comum_nao_fecha(self):
        estranho = _grant(
            User.objects.create_user("comum", password="x", is_staff=True), Shift, "operate_pos"
        )

        resp = self._client(estranho).post(URL, {"closing_amount": "50,00"}, format="json")

        self.assertEqual(resp.status_code, 403, resp.content)
        self.shift.refresh_from_db()
        self.assertEqual(self.shift.status, Shift.Status.OPEN)

    def test_sem_gaveta_aberta_o_fechamento_recusa(self):
        gerente = self._gerente()
        self._client(gerente).post(URL, {"closing_amount": "50,00"}, format="json")

        resp = self._client(gerente).post(URL, {"closing_amount": "0"}, format="json")

        self.assertEqual(resp.status_code, 400, resp.content)
