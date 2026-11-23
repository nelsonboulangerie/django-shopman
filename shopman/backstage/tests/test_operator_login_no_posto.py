"""O login com senha num posto vinculado (#2334).

O ``operator/login/`` aceitava a senha de qualquer staff, inclusive num posto: a
trava do balcão cobra PIN ou crachá (``OperatorUnlockPasswordView``, decisão do dono
de 06/11/2026), mas quem chamasse a API direto com a própria senha abria sessão ali
e pulava o bloqueio progressivo do PIN.

A régua, num posto vinculado: a senha entra só para quem vincula postos (o reparo
do posto é com a senha da Gerente) e para o Dono (a mesma exceção da trava). O resto
entra pelo PIN ou pelo crachá. Fora de posto, nada muda.
"""

import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.test import TestCase
from shopman.doorman.models import PinCredential

from shopman.backstage.models import SignInEvent, SignInMethod, SignInOutcome
from shopman.backstage.tests.support import trust_station
from shopman.shop.models import Channel, Shop

User = get_user_model()

LOGIN = "/api/v1/backstage/operator/login/"
SESSION = "/api/v1/backstage/operator/session/"


def _staff(username: str, *perms: str, pin: str | None = None, superuser: bool = False):
    if superuser:
        user = User.objects.create_superuser(username, password="segredo123")
    else:
        user = User.objects.create_user(username, password="segredo123", is_staff=True)
    for codename in perms:
        user.user_permissions.add(Permission.objects.get(content_type__app_label="cashman", codename=codename))
    if pin:
        PinCredential.set_for(user, pin)
    return User.objects.get(pk=user.pk)


class LoginComSenhaNoPosto(TestCase):
    def setUp(self):
        cache.clear()
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="PDV", is_active=True)

    def _login(self, username: str, password: str = "segredo123"):
        return self.client.post(
            LOGIN, json.dumps({"username": username, "password": password}), content_type="application/json",
        )

    def test_caixa_com_senha_num_posto_e_recusada_sem_abrir_sessao(self):
        _staff("fran", "operate_pos", pin="1234")
        trust_station(self.client)

        resp = self._login("fran")

        self.assertEqual(resp.status_code, 403)
        corpo = resp.json()
        self.assertEqual(corpo["error"]["code"], "operator_password_station_pin_only")
        self.assertEqual(corpo["detail"], "Neste posto, entre pelo PIN ou pelo crachá. Sem PIN, peça um ao gerente.")
        self.assertNotIn("_auth_user_id", self.client.session)
        linha = SignInEvent.objects.get(username="fran")
        self.assertEqual((linha.method, linha.outcome), (SignInMethod.PASSWORD, SignInOutcome.FAILED))
        self.assertEqual(linha.data["reason"], "operator_password_station_pin_only")

    def test_quem_nao_opera_ali_tambem_nao_entra_com_senha(self):
        # A pessoa da Cozinha, com senha, no posto do Caixa: era o furo da #2334.
        _staff("cozinha")
        trust_station(self.client)

        self.assertEqual(self._login("cozinha").json()["error"]["code"], "operator_password_station_pin_only")

    def test_recusa_da_porta_nao_conta_como_senha_errada(self):
        _staff("fran", "operate_pos", pin="1234")
        trust_station(self.client)
        for _ in range(6):
            self.assertEqual(self._login("fran").status_code, 403)
        # Seis recusas da porta e nenhuma vira 429: o balde é de senha errada.
        self.assertEqual(self._login("fran").json()["error"]["code"], "operator_password_station_pin_only")

    def test_quem_vincula_postos_entra_com_senha_no_posto(self):
        _staff("joyce", "operate_pos", "manage_operators", pin="4321")
        trust_station(self.client)

        resp = self._login("joyce")

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(resp.json()["ok"])

    def test_o_dono_entra_com_senha_no_posto(self):
        _staff("dono", superuser=True)
        trust_station(self.client)

        self.assertEqual(self._login("dono").status_code, 200)

    def test_fora_de_posto_nada_muda(self):
        _staff("fran", "operate_pos", pin="1234")

        resp = self._login("fran")

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(self.client.get(SESSION).json().get("operator"))

    def test_senha_errada_no_posto_segue_sendo_senha_errada(self):
        _staff("fran", "operate_pos", pin="1234")
        trust_station(self.client)

        self.assertEqual(self._login("fran", "errada").json()["error"]["code"], "operator_login_invalid")
