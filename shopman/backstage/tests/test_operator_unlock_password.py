"""A Dona sem PIN destrava o balcão com a senha dela (decisão do dono, 06/11/2026).

Beta de 05/11, PDV-21: a trava do balcão lista só quem tem PIN, e o Dono, que
não tem, não entrava. A porta "Entrar com senha" da trava é dele, e só dele:

- num posto da loja, só o Dono (superusuário ou quem audita o caixa);
- quem tem PIN entra pelo PIN, nunca pela senha (Caixa e Gerente incluídos);
- a mesma trilha (``SignInEvent`` com método ``password``) e o mesmo balde de
  senhas erradas do login com senha.
"""

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.test import TestCase, override_settings
from shopman.doorman.models import PinCredential

from shopman.backstage.models import SignInEvent, SignInMethod, SignInOutcome
from shopman.backstage.tests.support import trust_station
from shopman.shop.models import Channel, Shop

User = get_user_model()

URL = "/api/v1/backstage/operator/unlock/password/"
LOGIN = "/api/v1/backstage/operator/login/"
SESSION = "/api/v1/backstage/operator/session/"
POS_PERM = "cashman.operate_pos"


def _perm(codename: str) -> Permission:
    return Permission.objects.get(content_type__app_label="cashman", codename=codename)


def _staff(username: str, *perms: str, pin: str | None = None, superuser: bool = False):
    if superuser:
        user = User.objects.create_superuser(username, password="segredo123", first_name=username.title())
    else:
        user = User.objects.create_user(username, password="segredo123", is_staff=True, first_name=username.title())
    for codename in perms:
        user.user_permissions.add(_perm(codename))
    if pin:
        PinCredential.set_for(user, pin)
    return User.objects.get(pk=user.pk)


class _Base(TestCase):
    def setUp(self):
        cache.clear()
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="PDV", is_active=True)

    def _post(self, username: str, password: str = "segredo123", perm: str = POS_PERM):
        return self.client.post(
            URL,
            json.dumps({"username": username, "password": password, "perm": perm}),
            content_type="application/json",
        )


@override_settings(RATELIMIT_ENABLE=False)
class NoBalcaoTests(_Base):
    def setUp(self):
        super().setUp()
        trust_station(self.client, "pdv-main")

    def test_a_dona_sem_pin_destrava_o_balcao_com_a_senha(self):
        dona = _staff("dona", superuser=True)

        resp = self._post("dona")

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["operator"]["username"], "dona")
        sessao = self.client.get(SESSION, {"perm": POS_PERM}).json()
        self.assertEqual(sessao["operator"]["username"], "dona")
        self.assertFalse(sessao["locked"])
        self.assertTrue(sessao["authorized"])
        self.assertEqual(sessao["station"], "pdv-main")
        evento = SignInEvent.objects.get(user=dona, outcome=SignInOutcome.SUCCESS)
        self.assertEqual(evento.method, SignInMethod.PASSWORD)
        self.assertEqual(evento.station_ref, "pdv-main")

    def test_quem_audita_o_caixa_sem_ser_superusuario_tambem_entra(self):
        _staff("socia", "operate_pos", "audit_shift")

        self.assertEqual(self._post("socia").status_code, 200)

    def test_o_dono_que_tem_pin_entra_pelo_pin(self):
        _staff("dona", superuser=True, pin="4321")

        resp = self._post("dona")

        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"]["code"], "operator_password_has_pin")
        self.assertIn("digite o PIN", resp.json()["detail"])
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_gerente_com_pin_nao_entra_pela_senha(self):
        gerente = _staff("joyce", "operate_pos", "manage_operators", pin="9999")

        resp = self._post("joyce")

        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"]["code"], "operator_password_has_pin")
        recusa = SignInEvent.objects.get(user=gerente)
        self.assertEqual((recusa.method, recusa.outcome), (SignInMethod.PASSWORD, SignInOutcome.FAILED))
        self.assertEqual(recusa.data["reason"], "operator_password_has_pin")

    def test_caixa_sem_pin_nao_entra_pela_senha_no_posto(self):
        _staff("fran", "operate_pos")

        resp = self._post("fran")

        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"]["code"], "operator_password_owner_only")
        self.assertIn("só o Dono", resp.json()["detail"])
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_quem_nao_pode_usar_o_app_nao_entra(self):
        _staff("diofer", "audit_shift")

        resp = self._post("diofer")

        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"]["code"], "operator_unlock_invalid")

    def test_senha_errada_vira_linha_de_senha_recusada(self):
        dona = _staff("dona", superuser=True)

        resp = self._post("dona", password="errada")

        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"]["code"], "operator_login_invalid")
        recusa = SignInEvent.objects.get(user=dona)
        self.assertEqual((recusa.method, recusa.outcome), (SignInMethod.PASSWORD, SignInOutcome.FAILED))

    def test_a_senha_da_dona_derruba_a_trava_de_quem_estava_operando(self):
        caixa = _staff("fran", "operate_pos", pin="1234")
        _staff("dona", superuser=True)
        self.client.force_login(caixa)
        self.client.post(
            "/api/v1/backstage/operator/lock/", json.dumps({"perm": POS_PERM}), content_type="application/json"
        )
        self.assertTrue(self.client.get(SESSION, {"perm": POS_PERM}).json()["locked"])

        self.assertEqual(self._post("dona").status_code, 200)

        sessao = self.client.get(SESSION, {"perm": POS_PERM}).json()
        self.assertEqual(sessao["operator"]["username"], "dona")
        self.assertFalse(sessao["locked"])


@override_settings(RATELIMIT_ENABLE=False)
class ForaDePostoTests(_Base):
    """Fora de posto (dispositivo pessoal, beta BI-09), basta não ter PIN."""

    def test_quem_travou_o_proprio_dispositivo_sem_pin_volta_com_a_senha(self):
        gerente = _staff("marina", "operate_pos")
        self.client.force_login(gerente)

        self.assertEqual(self._post("marina").status_code, 200)

    def test_quem_tem_pin_continua_pelo_pin(self):
        gerente = _staff("joyce", "operate_pos", pin="9999")
        self.client.force_login(gerente)

        resp = self._post("joyce")

        self.assertEqual(resp.json()["error"]["code"], "operator_password_has_pin")

    def test_sem_estacao_e_sem_sessao_a_porta_nao_existe(self):
        _staff("dona", superuser=True)

        self.assertEqual(self._post("dona").status_code, 403)
        self.assertFalse(SignInEvent.objects.exists())


@override_settings(RATELIMIT_ENABLE=True)
class FreioTests(_Base):
    """O balde de senhas erradas é o MESMO do login com senha."""

    def setUp(self):
        super().setUp()
        trust_station(self.client, "pdv-main")
        _staff("dona", superuser=True)
        # Janela fixa: o balde não vira no meio do teste.
        self._win = patch("django_ratelimit.core._get_window", return_value=2_000_000_000)
        self._win.start()

    def tearDown(self):
        self._win.stop()
        cache.clear()

    def test_erros_no_login_e_na_trava_somam_no_mesmo_balde(self):
        for _ in range(3):
            self.client.post(LOGIN, {"username": "dona", "password": "errada"})
        for _ in range(3):
            self._post("dona", password="errada")

        resp = self._post("dona")

        self.assertEqual(resp.status_code, 429)
        self.assertEqual(resp.json()["error"]["code"], "operator_login_rate_limited")
