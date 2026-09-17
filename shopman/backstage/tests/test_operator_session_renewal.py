"""Sessão de operador: renova com o uso, expira após 7 dias parada, Admin intocado.

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

from shopman.backstage.middleware import OperatorSessionRenewalMiddleware
from shopman.backstage.services import operator_session
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
class AdminSessionIsUntouchedTests(TestCase):
    def setUp(self):
        Shop.objects.create(name="Test Shop", brand_name="Test")
        User.objects.create_superuser("dono", "dono@example.com", "segredo123")

    def test_admin_login_keeps_the_django_default_and_is_never_renewed(self):
        resp = self.client.post("/admin/login/", {"username": "dono", "password": "segredo123", "next": "/admin/"})
        self.assertEqual(resp.status_code, 302)
        key = self.client.cookies[settings.SESSION_COOKIE_NAME].value

        store = _session_store(key)
        self.assertIsNone(store.get(operator_session.SESSION_MARKER))
        self.assertIsNone(store.get("_session_expiry"))
        self.assertEqual(store.get_expiry_age(), settings.SESSION_COOKIE_AGE)

        # Um dia antes de a sessão do Admin vencer, ela é usada — no Admin e na API.
        almost_gone = timezone.now() + timedelta(days=1)
        Session.objects.filter(session_key=key).update(expire_date=almost_gone)

        for path in ("/admin/", ORDERS):
            used = self.client.get(path)
            self.assertNotIn(settings.SESSION_COOKIE_NAME, used.cookies, path)
            self.assertEqual(Session.objects.get(session_key=key).expire_date, almost_gone, path)


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
        OperatorSessionRenewalMiddleware(lambda r: StreamingHttpResponse(iter(["data: x\n\n"])))(request)
        self.assertFalse(request.session.modified)

    def test_plain_response_on_the_same_session_renews(self):
        request = self._marked_request()
        OperatorSessionRenewalMiddleware(lambda r: HttpResponse())(request)
        self.assertTrue(request.session.modified)
        self.assertGreater(request.session.get_expiry_age(), SEVEN_DAYS - SLACK)

    def test_request_without_session_cookie_does_not_touch_the_session(self):
        request = RequestFactory().get("/api/v1/backstage/orders/")
        request.session = _session_store(None)
        OperatorSessionRenewalMiddleware(lambda r: HttpResponse())(request)
        self.assertFalse(request.session.accessed)
