"""Destrave por PIN tem freio contra adivinhação, como o login de senha.

PIN de 4 dígitos são 10 mil combinações, e até 19/10 o ``operator/unlock`` não
tinha limite nenhum: a estação confiável era o único portão. Agora vale o mesmo
par do ``operator/login``: 5/min por conta-alvo e 30/min por IP.
"""

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.test import TestCase, override_settings
from shopman.doorman.models import PinCredential

from shopman.backstage.tests.support import trust_station
from shopman.shop.models import Channel, Shop

User = get_user_model()

UNLOCK = "/api/v1/backstage/operator/unlock/"
POS_PERM = "cashman.operate_pos"


def _operator(username: str, pin: str):
    user = User.objects.create_user(username, password="x", is_staff=True, first_name=username.title())
    PinCredential.set_for(user, pin)
    user.user_permissions.add(Permission.objects.get(content_type__app_label="cashman", codename="operate_pos"))
    return User.objects.get(pk=user.pk)


@override_settings(RATELIMIT_ENABLE=True)
class OperatorUnlockRateLimitTests(TestCase):
    def setUp(self):
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="PDV", is_active=True)
        trust_station(self.client, "pdv-main")
        self.ana = _operator("ana", "1234")
        cache.clear()
        # Fixa a janela do ratelimit para todas as tentativas caírem no mesmo bucket.
        self._win = patch("django_ratelimit.core._get_window", return_value=2_000_000_000)
        self._win.start()

    def tearDown(self):
        self._win.stop()
        cache.clear()

    def _try(self, operator, pin, **extra):
        return self.client.post(UNLOCK, {"operator_id": operator.pk, "pin": pin, "perm": POS_PERM}, **extra)

    def test_guessing_one_operators_pin_is_stopped_at_the_sixth_try(self):
        for _ in range(5):
            self.assertEqual(self._try(self.ana, "0000").status_code, 403)
        resp = self._try(self.ana, "0001")
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(resp.json()["error"]["code"], "operator_unlock_rate_limited")

    def test_lockout_shields_even_the_right_pin(self):
        for _ in range(6):
            self._try(self.ana, "0000")
        self.assertEqual(self._try(self.ana, "1234").status_code, 429)

    def test_lockout_works_over_json_body(self):
        # O caminho de produção é JSON (BFF): a chave por conta tem de valer nele.
        body = json.dumps({"operator_id": self.ana.pk, "pin": "0000", "perm": POS_PERM})
        for _ in range(5):
            resp = self.client.post(UNLOCK, body, content_type="application/json")
            self.assertEqual(resp.status_code, 403)
        resp = self.client.post(UNLOCK, body, content_type="application/json")
        self.assertEqual(resp.status_code, 429)

    def test_other_operator_is_not_locked_by_someone_elses_mistakes(self):
        bia = _operator("bia", "5678")
        for _ in range(6):
            self._try(self.ana, "0000")
        self.assertEqual(self._try(bia, "5678").status_code, 200)

    def test_ip_ceiling_stops_spraying_across_operators(self):
        # Cinco tentativas em cada um de seis operadores = 30, o teto do IP. A
        # 31ª, num sétimo operador ainda limpo, já é recusada.
        alvos = [_operator(f"op{i}", "9999") for i in range(7)]
        for alvo in alvos[:6]:
            for _ in range(5):
                self.assertEqual(self._try(alvo, "0000").status_code, 403)
        self.assertEqual(self._try(alvos[6], "0000").status_code, 429)
