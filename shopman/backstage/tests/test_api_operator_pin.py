"""O PDV destrava pela API genérica de operador (``operator/unlock|lock``).

O balcão começa o dia travado: aparelho reconhecido, ninguém identificado. Quem
digita o PIN VIRA a sessão, e o PDV passa a mostrar essa pessoa — não um
"operador ativo" guardado ao lado da conta da máquina, que era o desenho
anterior e a origem do buraco de permissão (D1 Parte B).
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from shopman.doorman.models import PinCredential

from shopman.backstage.tests.support import trust_station
from shopman.shop.models import Channel, Shop

User = get_user_model()

UNLOCK = "/api/v1/backstage/operator/unlock/"
LOCK = "/api/v1/backstage/operator/lock/"
POS_PERM = "cashman.operate_pos"


# As permissões do caixa moram no ``cashman`` (ADR-022); as demais seguem no ``backstage``.
_CASHMAN_PERMS = {"operate_pos", "adjust_shift", "audit_shift", "manage_operators"}


def _grant(user, codename):
    app_label = "cashman" if codename in _CASHMAN_PERMS else "backstage"
    user.user_permissions.add(Permission.objects.get(content_type__app_label=app_label, codename=codename))
    return User.objects.get(pk=user.pk)


class POSOperatorApiTests(TestCase):
    def setUp(self):
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="PDV", is_active=True)
        trust_station(self.client, "pdv-main")
        self.op = User.objects.create_user("ana", password="x", is_staff=True, first_name="Ana")
        PinCredential.set_for(self.op, "1234")
        self.op = _grant(self.op, "operate_pos")

    def test_unlock_valid_pin(self):
        resp = self.client.post(UNLOCK, {"operator_id": self.op.pk, "pin": "1234", "perm": POS_PERM})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        self.assertEqual(resp.json()["operator"]["name"], "Ana")

    def test_unlock_wrong_pin(self):
        resp = self.client.post(UNLOCK, {"operator_id": self.op.pk, "pin": "0000", "perm": POS_PERM})
        self.assertEqual(resp.status_code, 403)

    def test_unlock_rejects_operator_without_pos_perm(self):
        baker = User.objects.create_user("bia", password="x", is_staff=True)
        PinCredential.set_for(baker, "5555")
        baker = _grant(baker, "operate_production")  # not operate_pos
        resp = self.client.post(UNLOCK, {"operator_id": baker.pk, "pin": "5555", "perm": POS_PERM})
        self.assertEqual(resp.status_code, 403)

    def test_projection_reflects_active_operator_then_lock(self):
        self.client.post(UNLOCK, {"operator_id": self.op.pk, "pin": "1234", "perm": POS_PERM})
        pos = self.client.get("/api/v1/backstage/pos/")
        self.assertEqual(pos.json()["operator"]["name"], "Ana")
        self.assertIn("operators", pos.json()["pos"])
        self.assertEqual(pos.json()["pos"]["auto_lock_seconds"], 60)

        lock = self.client.post(LOCK)
        self.assertEqual(lock.status_code, 200)

        # Depois de travar, a estação NÃO lê mais — e isso mudou de verdade.
        # Este teste afirmava 200 com `operator: null`, que era o mundo de antes
        # da Opção C: a sessão do aparelho decidia, e travar só apagava um nome
        # da tela. Agora a permissão é do operador ativo; sem ele não há quem
        # autorize a leitura, e o gate responde 403 com código estável — que é
        # exatamente o que faz o PDV subir a tela de identificação em vez de
        # desenhar um balcão vazio.
        pos2 = self.client.get("/api/v1/backstage/pos/")
        self.assertEqual(pos2.status_code, 403)
        self.assertEqual(pos2.json()["error"]["code"], "station_locked")
