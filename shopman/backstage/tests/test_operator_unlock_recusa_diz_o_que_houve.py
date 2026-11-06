"""A recusa do destrave diz o que houve (beta test de 05/11/2026, PDV-20).

"Identificação inválida." não dizia se era o PIN, o crachá ou o acesso.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from shopman.doorman.models import PinCredential

from shopman.backstage.tests.support import trust_station
from shopman.backstage.tests.test_sign_in_audit import POS_PERM, UNLOCK, _grant
from shopman.shop.models import Channel, Shop

User = get_user_model()


class UnlockRefusalCopyTests(TestCase):
    def setUp(self):
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="PDV", is_active=True)
        trust_station(self.client, "pdv-main")
        self.op = User.objects.create_user("ana", password="senha-forte-123", is_staff=True)
        PinCredential.set_for(self.op, "1234")
        self.op = _grant(self.op, "operate_pos")

    def test_pin_errado_diz_que_o_pin_nao_confere(self):
        resp = self.client.post(UNLOCK, {"operator_id": self.op.pk, "pin": "0000", "perm": POS_PERM})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"], "PIN não confere. Tente de novo.")

    def test_cracha_desconhecido_diz_cracha(self):
        resp = self.client.post(UNLOCK, {"badge": "naoexiste", "perm": POS_PERM})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"], "Crachá não reconhecido. Passe de novo ou digite o PIN.")

    def test_sem_acesso_ao_app_nao_culpa_o_pin(self):
        sem_acesso = User.objects.create_user("bia", password="senha-forte-123", is_staff=True)
        PinCredential.set_for(sem_acesso, "4321")
        resp = self.client.post(UNLOCK, {"operator_id": sem_acesso.pk, "pin": "4321", "perm": POS_PERM})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"], "Esta pessoa não tem acesso a este app. Fale com o gerente.")
