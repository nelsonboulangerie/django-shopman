"""O PDV destrava pela API genérica de operador (``operator/unlock|lock``).

O balcão começa o dia travado: dispositivo reconhecido, ninguém identificado. Quem
digita o PIN VIRA a sessão, e o PDV passa a mostrar essa pessoa — não um
"operador ativo" guardado ao lado da conta da máquina, que era o desenho
anterior e a origem do buraco de permissão (D1 Parte B).
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
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

    def _superuser_with_pin_and_badge(self):
        dono = User.objects.create_user(
            "admin", password="x", is_staff=True, is_superuser=True, first_name="Admin"
        )
        PinCredential.set_for(dono, "1234")
        cred = PinCredential.objects.get(user=dono)
        cred.set_badge("abcdef012345")
        cred.save(update_fields=["badge_hash"])
        return dono

    def test_superuser_destrava_por_pin(self):
        """O superusuário destrava como qualquer operador: o destrave é `login()`
        real como a pessoa, e o PIN é dele, individual. Sem `perm` e com a do PDV."""
        dono = self._superuser_with_pin_and_badge()
        for perm in (POS_PERM, ""):
            self.client.post(LOCK)
            resp = self.client.post(UNLOCK, {"operator_id": dono.pk, "pin": "1234", "perm": perm})
            self.assertEqual(resp.status_code, 200, perm)
            self.assertEqual(resp.json()["operator"]["name"], "Admin")
            self.assertEqual(str(self.client.session["_auth_user_id"]), str(dono.pk))

    def test_superuser_com_pin_errado_nao_destrava(self):
        dono = self._superuser_with_pin_and_badge()
        resp = self.client.post(UNLOCK, {"operator_id": dono.pk, "pin": "0000", "perm": POS_PERM})
        self.assertEqual(resp.status_code, 403)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_superuser_destrava_por_cracha(self):
        dono = self._superuser_with_pin_and_badge()
        resp = self.client.post(UNLOCK, {"badge": "abcdef012345", "perm": POS_PERM})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(str(self.client.session["_auth_user_id"]), str(dono.pk))

    def test_superuser_com_pin_aparece_no_seletor_da_tela_de_bloqueio(self):
        self._superuser_with_pin_and_badge()
        resp = self.client.get("/api/v1/backstage/operator/eligible/", {"perm": POS_PERM})
        self.assertEqual(resp.status_code, 200)
        names = [o["username"] for o in resp.json()["operators"]]
        self.assertEqual(names, ["admin", "ana"])

    def test_superuser_sem_pin_fica_fora_do_seletor(self):
        """O filtro de ter credencial vale para ele também: quem não cadastrou PIN
        não tem o que digitar na tela de bloqueio."""
        User.objects.create_user("admin", password="x", is_staff=True, is_superuser=True)
        resp = self.client.get("/api/v1/backstage/operator/eligible/", {"perm": POS_PERM})
        names = [o["username"] for o in resp.json()["operators"]]
        self.assertEqual(names, ["ana"])

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
        # da Opção C: a sessão do dispositivo decidia, e travar só apagava um nome
        # da tela. Agora a permissão é do operador ativo; sem ele não há quem
        # autorize a leitura, e o gate responde 403 com código estável — que é
        # exatamente o que faz o PDV subir a tela de identificação em vez de
        # desenhar um balcão vazio.
        pos2 = self.client.get("/api/v1/backstage/pos/")
        self.assertEqual(pos2.status_code, 403)
        self.assertEqual(pos2.json()["error"]["code"], "station_locked")


@override_settings(
    ALLOWED_HOSTS=["*"],
    SHOPMAN_OPERATOR_COOKIE_DOMAIN=".boulangerie.com.br",
    SHOPMAN_OPERATOR_API_HOST="api.boulangerie.com.br",
)
class LockIsZoneWideLogoutTests(TestCase):
    """Travar o PDV derruba o Gestor aberto no mesmo navegador — por construção.

    A sessão de operador é UMA para toda a zona `.boulangerie.com.br`, e travar é
    `logout()`. É por isso que o auto-lock do PDV (60 s, só enxerga a atividade do
    próprio PDV) não pode disparar com o PDV fora da vista: ele desligava o Gestor
    em uso ao lado. Este teste fixa a premissa do lado do servidor; o lado do PDV
    está em ``surfaces/pos-nuxt/tests/posAutoLock.test.ts``.
    """

    API_HOST = "api.boulangerie.com.br"

    def setUp(self):
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="PDV", is_active=True)
        trust_station(self.client, "pdv-main")
        op = User.objects.create_user("ana", password="x", is_staff=True, first_name="Ana")
        PinCredential.set_for(op, "1234")
        _grant(op, "operate_pos")
        # A fila do Gestor pede `shop.manage_orders` (a mesma perm do app orders-nuxt).
        op.user_permissions.add(Permission.objects.get(content_type__app_label="shop", codename="manage_orders"))
        self.op = User.objects.get(pk=op.pk)

    def test_pdv_lock_expires_the_session_cookie_for_the_whole_operator_zone(self):
        unlock = self.client.post(
            UNLOCK, {"operator_id": self.op.pk, "pin": "1234", "perm": POS_PERM}, HTTP_HOST=self.API_HOST,
        )
        self.assertEqual(unlock.status_code, 200)
        self.assertEqual(unlock.cookies[settings.SESSION_COOKIE_NAME]["domain"], ".boulangerie.com.br")
        self.assertEqual(self.client.get("/api/v1/backstage/orders/", HTTP_HOST=self.API_HOST).status_code, 200)

        lock = self.client.post(LOCK, HTTP_HOST=self.API_HOST)

        self.assertEqual(lock.status_code, 200)
        deleted = lock.cookies[settings.SESSION_COOKIE_NAME]
        self.assertEqual(deleted.value, "")
        self.assertEqual(deleted["max-age"], 0)
        self.assertEqual(deleted["domain"], ".boulangerie.com.br")
        self.assertEqual(self.client.get("/api/v1/backstage/orders/", HTTP_HOST=self.API_HOST).status_code, 403)
