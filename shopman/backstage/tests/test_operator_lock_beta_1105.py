"""Trava, PIN e login do operador: os achados do beta de 05/11/2026.

- CEN-01: PIN bloqueado por tentativas respondia "Identificação inválida.", a
  mesma cara do PIN errado, até para o PIN certo. A pessoa seguia tentando e o
  bloqueio (progressivo) crescia; ninguém era avisado de que a conta travou.
- BI-08 / MKT-19: o limite de login por usuário contava o login CERTO. A Gerente
  que abria seis dispositivos de manhã travava a própria conta.
- PDV-26: a troca de PIN aceitava o mesmo PIN ("PIN atualizado" e nada mudou).
- CEN-07: não havia como sair do dispositivo, só bloquear.
"""

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.test import TestCase, override_settings
from shopman.doorman.models import PinCredential

from shopman.backstage.models import SignInEvent
from shopman.backstage.tests.support import trust_station
from shopman.shop.models import Channel, Shop, UserNotification

User = get_user_model()

LOGIN = "/api/v1/backstage/operator/login/"
LOGOUT = "/api/v1/backstage/operator/logout/"
SESSION = "/api/v1/backstage/operator/session/"
UNLOCK = "/api/v1/backstage/operator/unlock/"
CHANGE = "/api/v1/backstage/operator/pin/change/"
BADGE_LOST = "/api/v1/backstage/operator/badge/lost/"
POS_PERM = "cashman.operate_pos"


def _perm(codename: str) -> Permission:
    return Permission.objects.get(content_type__app_label="cashman", codename=codename)


def _operator(username: str, pin: str, *perms: str):
    user = User.objects.create_user(username, password="segredo123", is_staff=True, first_name=username.title())
    PinCredential.set_for(user, pin)
    for codename in ("operate_pos", *perms):
        user.user_permissions.add(_perm(codename))
    return User.objects.get(pk=user.pk)


@override_settings(RATELIMIT_ENABLE=False)
class PinLockedTests(TestCase):
    """CEN-01: bloqueado tem resposta própria, com hora, e um aviso só.

    O freio por conta (5/min) fica desligado aqui: o assunto é o bloqueio do PIN.
    A precedência entre os dois tem a classe dela, abaixo.
    """

    def setUp(self):
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="PDV", is_active=True)
        trust_station(self.client, "pdv-main")
        self.ana = _operator("ana", "1234")
        self.gerente = _operator("joyce", "9999", "manage_operators")

    def _unlock(self, pin: str):
        return self.client.post(
            UNLOCK,
            json.dumps({"operator_id": self.ana.pk, "pin": pin, "perm": POS_PERM}),
            content_type="application/json",
        )

    def _max(self) -> int:
        return PinCredential.objects.get(user=self.ana).max_attempts

    def test_a_falha_que_trava_ja_responde_bloqueado(self):
        for _ in range(self._max() - 1):
            self.assertEqual(self._unlock("0000").status_code, 403)

        resp = self._unlock("0000")

        self.assertEqual(resp.status_code, 423)
        self.assertEqual(resp.json()["error"]["code"], "pin_locked")
        self.assertIn("PIN bloqueado por tentativas até", resp.json()["detail"])
        self.assertIn("Peça a um gerente para desbloquear", resp.json()["detail"])
        self.assertTrue(resp.json()["error"]["locked_until"])

    def test_pin_certo_de_quem_esta_bloqueado_diz_bloqueado_e_nao_invalido(self):
        for _ in range(self._max()):
            self._unlock("0000")

        resp = self._unlock("1234")

        self.assertEqual(resp.status_code, 423)
        self.assertEqual(resp.json()["error"]["code"], "pin_locked")
        self.assertNotIn("Identificação inválida", resp.json()["detail"])

    def test_tentar_com_o_pin_bloqueado_nao_estende_o_bloqueio(self):
        for _ in range(self._max()):
            self._unlock("0000")
        cred = PinCredential.objects.get(user=self.ana)
        antes = (cred.attempts, cred.locked_until)

        self._unlock("0000")
        self._unlock("1234")

        cred.refresh_from_db()
        self.assertEqual((cred.attempts, cred.locked_until), antes)

    def test_o_bloqueio_avisa_uma_vez_o_dono_e_o_gerente(self):
        for _ in range(self._max() + 3):
            self._unlock("0000")

        dono = UserNotification.objects.filter(user=self.ana, title="Seu PIN foi bloqueado por tentativas")
        gerente = UserNotification.objects.filter(user=self.gerente, title__startswith="PIN de Ana bloqueado")
        self.assertEqual(dono.count(), 1)
        self.assertEqual(gerente.count(), 1)
        self.assertIn("Desbloquear PIN", gerente.get().message)
        # As tentativas depois do bloqueio ficam na trilha, sem novo aviso ao dono.
        self.assertEqual(
            UserNotification.objects.filter(user=self.ana, title__startswith="Tentativa recusada").count(),
            self._max() - 1,
        )
        self.assertTrue(SignInEvent.objects.filter(user=self.ana, data__reason="operator_pin_locked").exists())

    def test_quem_nao_pode_usar_a_tela_nao_ganha_resposta_de_bloqueio(self):
        """O 423 só diz algo sobre quem a lista da trava já mostra."""
        de_fora = User.objects.create_user("zeca", password="x", is_staff=True)
        PinCredential.set_for(de_fora, "1234")
        cred = PinCredential.objects.get(user=de_fora)
        for _ in range(cred.max_attempts):
            cred.verify("0000")

        resp = self.client.post(
            UNLOCK,
            json.dumps({"operator_id": de_fora.pk, "pin": "1234", "perm": POS_PERM}),
            content_type="application/json",
        )

        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"]["code"], "operator_unlock_invalid")

    def test_perdi_meu_cracha_com_pin_bloqueado_diz_bloqueado(self):
        for _ in range(self._max()):
            self._unlock("0000")

        resp = self.client.post(
            BADGE_LOST,
            json.dumps({"operator_id": self.ana.pk, "pin": "1234", "confirm": True}),
            content_type="application/json",
        )

        self.assertEqual(resp.status_code, 423)
        self.assertEqual(resp.json()["error"]["code"], "pin_locked")

    def test_troca_de_pin_que_trava_responde_bloqueado(self):
        for _ in range(self._max() - 1):
            self._unlock("0000")

        resp = self.client.post(
            CHANGE,
            json.dumps({"operator_id": self.ana.pk, "current_pin": "0000", "new_pin": "5678"}),
            content_type="application/json",
        )

        self.assertEqual(resp.status_code, 423)
        self.assertEqual(resp.json()["error"]["code"], "pin_locked")


@override_settings(RATELIMIT_ENABLE=True)
class PinLockedOverRateLimitTests(TestCase):
    """O freio e o bloqueio disparam juntos na quinta falha. Vence o bloqueio:
    "aguarde um minuto" venceria antes dele e mandaria tentar de novo."""

    def setUp(self):
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="PDV", is_active=True)
        trust_station(self.client, "pdv-main")
        self.ana = _operator("ana", "1234")
        cache.clear()
        self._win = patch("django_ratelimit.core._get_window", return_value=2_000_000_000)
        self._win.start()

    def tearDown(self):
        self._win.stop()
        cache.clear()

    def test_com_o_freio_estourado_o_pin_bloqueado_ainda_diz_bloqueado(self):
        body = json.dumps({"operator_id": self.ana.pk, "pin": "0000", "perm": POS_PERM})
        for _ in range(8):
            resp = self.client.post(UNLOCK, body, content_type="application/json")

        self.assertEqual(resp.status_code, 423)
        self.assertEqual(resp.json()["error"]["code"], "pin_locked")


class SamePinTests(TestCase):
    """PDV-26: trocar pelo mesmo PIN não é troca."""

    def setUp(self):
        Shop.objects.create(name="Test Shop", brand_name="Test")
        self.ana = _operator("ana", "1234")
        self.client.force_login(self.ana)

    def test_recusa_o_mesmo_pin(self):
        resp = self.client.post(
            CHANGE, {"current_pin": "1234", "new_pin": "1234"}, content_type="application/json"
        )

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"]["code"], "same_pin")
        self.assertEqual(resp.json()["detail"], "Escolha um PIN diferente do atual.")

    def test_pin_atual_errado_diz_errado_mesmo_que_o_novo_seja_igual(self):
        """A recusa do PIN igual vem DEPOIS de provar o atual: não vira oráculo."""
        resp = self.client.post(
            CHANGE, {"current_pin": "0000", "new_pin": "0000"}, content_type="application/json"
        )

        self.assertEqual(resp.json()["error"]["code"], "invalid_current")


@override_settings(RATELIMIT_ENABLE=True)
class LoginCountsOnlyFailuresTests(TestCase):
    """BI-08 / MKT-19: o freio por usuário conta a senha ERRADA, não o login."""

    def setUp(self):
        Shop.objects.create(name="Test Shop", brand_name="Test")
        User.objects.create_user("joyce", password="segredo123", is_staff=True)
        cache.clear()
        self._win = patch("django_ratelimit.core._get_window", return_value=2_000_000_000)
        self._win.start()

    def tearDown(self):
        self._win.stop()
        cache.clear()

    def _login(self, password: str):
        return self.client.post(
            LOGIN, json.dumps({"username": "joyce", "password": password}), content_type="application/json"
        )

    def test_seis_dispositivos_seguidos_com_a_senha_certa_entram_todos(self):
        for _ in range(8):
            self.client.logout()
            self.assertEqual(self._login("segredo123").status_code, 200)

    def test_um_erro_depois_de_varios_acertos_nao_trava(self):
        for _ in range(5):
            self._login("segredo123")
        self.assertEqual(self._login("errada").status_code, 403)
        self.assertEqual(self._login("segredo123").status_code, 200)

    def test_o_429_diz_quanto_falta(self):
        for _ in range(6):
            self._login("errada")

        resp = self._login("segredo123")

        self.assertEqual(resp.status_code, 429)
        self.assertEqual(resp.json()["error"]["code"], "operator_login_rate_limited")
        self.assertIn("Tente de novo em", resp.json()["detail"])
        self.assertGreater(resp.json()["error"]["retry_after"], 0)
        self.assertEqual(resp["Retry-After"], str(resp.json()["error"]["retry_after"]))


class LogoutTests(TestCase):
    """CEN-07: sair deste dispositivo encerra a sessão; o posto fica."""

    def setUp(self):
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="PDV", is_active=True)
        self.ana = _operator("ana", "1234")

    def test_sem_posto_volta_a_pedir_senha(self):
        self.client.post(LOGIN, {"username": "ana", "password": "segredo123"})
        self.assertEqual(self.client.get(SESSION).status_code, 200)

        resp = self.client.post(LOGOUT)

        self.assertEqual(resp.status_code, 200)
        # Sem sessão e sem posto, a antessala recusa: a única saída é a senha.
        self.assertEqual(self.client.get(SESSION).status_code, 403)

    def test_no_posto_a_estacao_continua_reconhecida(self):
        trust_station(self.client, "pdv-main")
        self.client.post(LOGIN, {"username": "ana", "password": "segredo123"})

        self.client.post(LOGOUT)

        sessao = self.client.get(SESSION)
        self.assertEqual(sessao.status_code, 200)
        self.assertIsNone(sessao.json()["operator"])
        self.assertTrue(sessao.json()["locked"])
