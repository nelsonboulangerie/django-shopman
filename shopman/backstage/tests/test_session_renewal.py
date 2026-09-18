"""Renovação de sessão: as duas valem enquanto são usadas — operador (7 dias) e Admin (14).

Decisão do dono (17/09/2026). O relógio não é congelado: o teste escreve na própria
sessão o prazo que "sobrou" (``set_expiry``) e observa o que a requisição seguinte
faz com ele — que é exatamente a pergunta que o middleware responde.
"""

from __future__ import annotations

from datetime import timedelta
from importlib import import_module

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.db import connection
from django.http import HttpResponse, StreamingHttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from shopman.doorman.models import PinCredential

from shopman.backstage.middleware import SessionRenewalMiddleware
from shopman.backstage.services import admin_session, operator_session
from shopman.backstage.tests.support import trust_station
from shopman.shop.models import Channel, Shop

User = get_user_model()

LOGIN = "/api/v1/backstage/operator/login/"
UNLOCK = "/api/v1/backstage/operator/unlock/"
LOCK = "/api/v1/backstage/operator/lock/"
ORDERS = "/api/v1/backstage/orders/"
POS_PERM = "cashman.operate_pos"

API_HOST = "api.boulangerie.com.br"
ZONE = ".boulangerie.com.br"
DAY = 24 * 60 * 60
SEVEN_DAYS = 7 * DAY
#: Folga para o tempo que o próprio teste leva entre gravar e medir.
SLACK = 60


def _session_store(key: str):
    return import_module(settings.SESSION_ENGINE).SessionStore(session_key=key)


def _session_writes(queries) -> list[str]:
    return [
        q["sql"]
        for q in queries
        if "django_session" in q["sql"] and q["sql"].lstrip().upper().startswith(("UPDATE", "INSERT"))
    ]


@override_settings(
    ALLOWED_HOSTS=["*"],
    SHOPMAN_OPERATOR_COOKIE_DOMAIN=ZONE,
    SHOPMAN_OPERATOR_API_HOST=API_HOST,
)
class OperatorSessionRenewalTests(TestCase):
    def setUp(self):
        # O login tem rate-limit por conta (5/min) guardado no cache: sem limpar,
        # estes logins de "ana" esgotam a cota da suíte vizinha que usa a mesma conta.
        cache.clear()
        self.addCleanup(cache.clear)
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="PDV", is_active=True)
        op = User.objects.create_user("ana", password="segredo123", is_staff=True, first_name="Ana")
        PinCredential.set_for(op, "1234")
        op.user_permissions.add(
            Permission.objects.get(content_type__app_label="cashman", codename="operate_pos"),
            Permission.objects.get(content_type__app_label="shop", codename="manage_orders"),
        )
        self.op = User.objects.get(pk=op.pk)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _session_key(self) -> str:
        return self.client.cookies[settings.SESSION_COOKIE_NAME].value

    def _db_remaining(self) -> float:
        row = Session.objects.get(session_key=self._session_key())
        return (row.expire_date - timezone.now()).total_seconds()

    def _set_remaining(self, seconds: int) -> None:
        """A sessão chega à requisição com ``seconds`` de prazo — como se o tempo tivesse passado."""
        store = _session_store(self._session_key())
        store.set_expiry(timedelta(seconds=seconds))
        store.save()

    def _unlock(self):
        trust_station(self.client, "pdv-main")
        resp = self.client.post(
            UNLOCK,
            {"operator_id": self.op.pk, "pin": "1234", "perm": POS_PERM},
            content_type="application/json",
            HTTP_HOST=API_HOST,
        )
        self.assertEqual(resp.status_code, 200)
        return resp

    def _login(self):
        resp = self.client.post(
            LOGIN, {"username": "ana", "password": "segredo123"}, content_type="application/json", HTTP_HOST=API_HOST
        )
        self.assertEqual(resp.status_code, 200)
        return resp

    def _assert_seven_day_cookie(self, resp):
        cookie = resp.cookies[settings.SESSION_COOKIE_NAME]
        self.assertEqual(cookie["domain"], ZONE)
        self.assertGreater(int(cookie["max-age"]), SEVEN_DAYS - SLACK)
        self.assertLessEqual(int(cookie["max-age"]), SEVEN_DAYS)

    # ── nascimento ──────────────────────────────────────────────────────────

    def test_pin_unlock_opens_a_marked_session_with_seven_days(self):
        resp = self._unlock()
        self._assert_seven_day_cookie(resp)
        self.assertTrue(_session_store(self._session_key()).get(operator_session.SESSION_MARKER))
        self.assertGreater(self._db_remaining(), SEVEN_DAYS - SLACK)
        self.assertLessEqual(self._db_remaining(), SEVEN_DAYS)

    def test_password_login_opens_a_marked_session_with_seven_days(self):
        resp = self._login()
        self._assert_seven_day_cookie(resp)
        self.assertTrue(_session_store(self._session_key()).get(operator_session.SESSION_MARKER))
        self.assertGreater(self._db_remaining(), SEVEN_DAYS - SLACK)

    # ── renovação ───────────────────────────────────────────────────────────

    def test_use_within_the_same_day_neither_writes_nor_reemits(self):
        self._login()
        self._set_remaining(6 * DAY + 12 * 60 * 60)  # usou há 12 h
        before = self._db_remaining()

        with CaptureQueriesContext(connection) as queries:
            resp = self.client.get(ORDERS, HTTP_HOST=API_HOST)

        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(settings.SESSION_COOKIE_NAME, resp.cookies)
        self.assertEqual(_session_writes(queries.captured_queries), [])
        self.assertAlmostEqual(self._db_remaining(), before, delta=SLACK)

    def test_use_after_a_day_renews_to_seven_days_and_reemits_the_zone_cookie(self):
        self._login()
        self._set_remaining(2 * DAY)  # parada há 5 dias

        with CaptureQueriesContext(connection) as queries:
            resp = self.client.get(ORDERS, HTTP_HOST=API_HOST)

        self.assertEqual(resp.status_code, 200)
        self._assert_seven_day_cookie(resp)
        self.assertEqual(len(_session_writes(queries.captured_queries)), 1)
        self.assertGreater(self._db_remaining(), SEVEN_DAYS - SLACK)
        # A chave não muda: renovar é empurrar o prazo, não abrir outra sessão.
        self.assertEqual(resp.cookies[settings.SESSION_COOKIE_NAME].value, self._session_key())

        # E no mesmo dia a próxima requisição já não grava de novo.
        with CaptureQueriesContext(connection) as again:
            second = self.client.get(ORDERS, HTTP_HOST=API_HOST)
        self.assertNotIn(settings.SESSION_COOKIE_NAME, second.cookies)
        self.assertEqual(_session_writes(again.captured_queries), [])

    def test_seven_days_stopped_expires_as_not_authenticated(self):
        self._login()
        self._set_remaining(-1)  # os 7 dias passaram sem uso

        resp = self.client.get(ORDERS, HTTP_HOST=API_HOST)

        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"]["code"], "not_authenticated")

    def test_admin_path_never_renews_an_operator_session(self):
        # O BFF bate em `/admin/login/` para buscar CSRF: isso não é uso do app.
        self._login()
        self._set_remaining(2 * DAY)
        before = self._db_remaining()

        resp = self.client.get("/admin/login/", HTTP_HOST=API_HOST)

        self.assertNotIn(settings.SESSION_COOKIE_NAME, resp.cookies)
        self.assertAlmostEqual(self._db_remaining(), before, delta=SLACK)

    # ── lock/unlock ─────────────────────────────────────────────────────────

    def test_lock_then_unlock_still_work_and_the_new_session_is_marked(self):
        self._unlock()
        first_key = self._session_key()

        lock = self.client.post(LOCK, HTTP_HOST=API_HOST)
        self.assertEqual(lock.status_code, 200)
        deleted = lock.cookies[settings.SESSION_COOKIE_NAME]
        self.assertEqual(deleted.value, "")
        self.assertEqual(deleted["max-age"], 0)
        self.assertEqual(self.client.get(ORDERS, HTTP_HOST=API_HOST).status_code, 403)

        resp = self._unlock()
        self._assert_seven_day_cookie(resp)
        self.assertNotEqual(self._session_key(), first_key)
        self.assertTrue(_session_store(self._session_key()).get(operator_session.SESSION_MARKER))
        self.assertEqual(self.client.get(ORDERS, HTTP_HOST=API_HOST).status_code, 200)


@override_settings(ALLOWED_HOSTS=["*"], SHOPMAN_ADMIN_REQUIRE_2FA=False)
class AdminSessionRenewsWithUseTests(TestCase):
    """A sessão do Admin também vale enquanto é usada.

    Esta classe afirmava o CONTRÁRIO: que usar o Admin um dia antes do
    vencimento não mudava nada. Era a queixa do dono escrita como garantia — a
    decisão de 17/09 tratou a zona de operador e deixou o Admin com o default do
    Django (14 dias do login, sem renovação), que é justamente o corte seco de
    duas em duas semanas de que ele reclamava. O NÚMERO segue 14 dias; o que
    muda é o ponto de partida, que passa a ser o último uso.
    """

    def setUp(self):
        Shop.objects.create(name="Test Shop", brand_name="Test")
        User.objects.create_superuser("dono", "dono@example.com", "segredo123")

    def _login(self) -> str:
        resp = self.client.post("/admin/login/", {"username": "dono", "password": "segredo123", "next": "/admin/"})
        self.assertEqual(resp.status_code, 302)
        return self.client.cookies[settings.SESSION_COOKIE_NAME].value

    def _set_remaining(self, key: str, seconds: int) -> None:
        """A sessão chega à requisição com ``seconds`` de prazo — como se o tempo tivesse passado."""
        store = _session_store(key)
        store.set_expiry(timedelta(seconds=seconds))
        store.save()

    # ── nascimento ──────────────────────────────────────────────────────────

    def test_admin_login_still_starts_with_the_django_default(self):
        # O login continua sendo o do Django: não marca e não escreve prazo.
        store = _session_store(self._login())
        self.assertIsNone(store.get(operator_session.SESSION_MARKER))
        self.assertIsNone(store.get(admin_session.SESSION_EXPIRY_KEY))

    def test_the_first_admin_request_plants_the_clock(self):
        # Sem a chave `_session_expiry`, `get_expiry_age()` devolveria o número
        # do settings para sempre e a renovação seria letra morta. A primeira
        # requisição planta o relógio — inclusive em sessão aberta antes disto.
        key = self._login()

        resp = self.client.get("/admin/")

        self.assertIn(settings.SESSION_COOKIE_NAME, resp.cookies)
        store = _session_store(key)
        self.assertIsNotNone(store.get(admin_session.SESSION_EXPIRY_KEY))
        self.assertAlmostEqual(
            store.get_expiry_age(), settings.SHOPMAN_ADMIN_SESSION_IDLE_SECONDS, delta=SLACK
        )

    # ── renovação ───────────────────────────────────────────────────────────

    def test_using_the_admin_near_the_deadline_pushes_it_back(self):
        key = self._login()
        self.client.get("/admin/")          # planta
        self._set_remaining(key, 1 * DAY)   # um dia para vencer

        resp = self.client.get("/admin/")

        self.assertIn(settings.SESSION_COOKIE_NAME, resp.cookies)
        self.assertAlmostEqual(
            _session_store(key).get_expiry_age(),
            settings.SHOPMAN_ADMIN_SESSION_IDLE_SECONDS,
            delta=SLACK,
        )

    def test_use_within_the_same_day_neither_writes_nor_reemits(self):
        # Mesma economia da gêmea: no máximo uma gravação por dia.
        key = self._login()
        self.client.get("/admin/")
        self._set_remaining(key, 13 * DAY + 12 * 60 * 60)  # usou há 12 h
        before = Session.objects.get(session_key=key).expire_date

        resp = self.client.get("/admin/")

        self.assertNotIn(settings.SESSION_COOKIE_NAME, resp.cookies)
        self.assertEqual(Session.objects.get(session_key=key).expire_date, before)

    # ── quem NÃO renova ─────────────────────────────────────────────────────

    def test_the_api_does_not_renew_an_admin_session(self):
        # Fora de `/admin/` vale a regra de operador, e esta sessão não tem a
        # marca: ninguém renova. O Admin se identifica pelo CAMINHO.
        key = self._login()
        self.client.get("/admin/")
        self._set_remaining(key, 1 * DAY)
        almost_gone = Session.objects.get(session_key=key).expire_date

        resp = self.client.get(ORDERS)

        self.assertNotIn(settings.SESSION_COOKIE_NAME, resp.cookies)
        self.assertEqual(Session.objects.get(session_key=key).expire_date, almost_gone)

    def test_an_anonymous_visitor_renews_nothing(self):
        resp = self.client.get("/admin/login/")
        self.assertNotIn(settings.SESSION_COOKIE_NAME, resp.cookies)


class RenewalMiddlewareGuardTests(TestCase):
    """O que o middleware recusa antes mesmo de olhar a regra."""

    def _marked_request(self, path="/api/v1/backstage/orders/"):
        user = User.objects.create_user("bia", password="x", is_staff=True)
        request = RequestFactory().get(path)
        request.COOKIES[settings.SESSION_COOKIE_NAME] = "qualquer"
        request.session = _session_store(None)
        request.session[operator_session.SESSION_MARKER] = True
        request.session.set_expiry(timedelta(days=2))
        request.session.modified = False
        request.user = user
        return request

    def test_streaming_response_is_not_a_renewal_point(self):
        # O proxy de SSE do BFF não repassa Set-Cookie: renovar ali adiantaria o
        # banco e deixaria o cookie do navegador morrer antes da sessão.
        request = self._marked_request("/events/backstage/")
        SessionRenewalMiddleware(lambda r: StreamingHttpResponse(iter(["data: x\n\n"])))(request)
        self.assertFalse(request.session.modified)

    def test_plain_response_on_the_same_session_renews(self):
        request = self._marked_request()
        SessionRenewalMiddleware(lambda r: HttpResponse())(request)
        self.assertTrue(request.session.modified)
        self.assertGreater(request.session.get_expiry_age(), SEVEN_DAYS - SLACK)

    def test_request_without_session_cookie_does_not_touch_the_session(self):
        request = RequestFactory().get("/api/v1/backstage/orders/")
        request.session = _session_store(None)
        SessionRenewalMiddleware(lambda r: HttpResponse())(request)
        self.assertFalse(request.session.accessed)
