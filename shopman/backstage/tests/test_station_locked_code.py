"""A recusa por estação travada precisa se identificar.

Um 403 sem código é indistinguível de falta de permissão para a superfície, e o
PDV seguia montado com todas as leituras negadas — desenhando um quadro de
comandas VAZIO, que no balcão se lê como "as comandas sumiram". Com o código, a
tela sobe a identificação em vez de mentir.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings
from shopman.cashman.models import Shift

from shopman.shop.models import Shop

POS_URL = "/api/v1/backstage/pos/"


def _grant(user, codename: str) -> None:
    ct = ContentType.objects.get_for_model(Shift)
    user.user_permissions.add(Permission.objects.get(content_type=ct, codename=codename))


@override_settings(SHOPMAN_REQUIRE_ACTIVE_OPERATOR=True)
class StationLockedCodeTests(TestCase):
    def setUp(self) -> None:
        Shop.objects.create(name="Lock Shop", brand_name="Lock")
        User = get_user_model()
        self.device_user = User.objects.create_user(
            username="estacao", password="x", is_staff=True,
        )
        _grant(self.device_user, "operate_pos")
        self.client.force_login(self.device_user)

    def test_locked_station_names_itself(self) -> None:
        response = self.client.get(POS_URL)

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        # `detail` segue sendo a mensagem humana do dialeto canônico...
        self.assertIn("Estação travada", payload["detail"])
        # ...e o código é o que a tela usa para reagir.
        self.assertEqual(payload["error"]["code"], "station_locked")

    def test_missing_permission_is_not_reported_as_locked(self) -> None:
        """Falta de permissão não se resolve com PIN — não pode virar station_locked."""
        from shopman.backstage.services.operator import ACTIVE_OPERATOR_SESSION_KEY

        User = get_user_model()
        operator = User.objects.create_user(username="sem-pos", password="x", is_staff=True)
        session = self.client.session
        session[ACTIVE_OPERATOR_SESSION_KEY] = {"id": operator.pk, "name": operator.username}
        session.save()

        response = self.client.get(POS_URL)

        self.assertEqual(response.status_code, 403)
        self.assertNotIn("error", response.json())

    def test_unlocked_station_reads_normally(self) -> None:
        from shopman.backstage.services.operator import ACTIVE_OPERATOR_SESSION_KEY

        session = self.client.session
        session[ACTIVE_OPERATOR_SESSION_KEY] = {
            "id": self.device_user.pk, "name": self.device_user.username,
        }
        session.save()

        response = self.client.get(POS_URL)

        self.assertEqual(response.status_code, 200)
        self.assertIn("pos", response.json())
