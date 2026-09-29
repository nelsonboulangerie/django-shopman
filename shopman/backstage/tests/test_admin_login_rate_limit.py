"""O login do Admin tem o mesmo freio de tentativas do login de operador.

A mesma senha de staff tinha 5/min por conta e 30/min por IP em
``operator/login/``, e nenhum limite em ``/admin/login/`` — o caminho sem freio
para chutar a senha, inclusive a do superusuário.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

User = get_user_model()

LOGIN = "/admin/login/"
# Borda da plataforma escreve à DIREITA; com depth=2 o cliente é o penúltimo.
EDGE = "10.0.0.1"


def _xff(client_ip: str, forged: str = "") -> str:
    return ", ".join(p for p in (forged, client_ip, EDGE) if p)


class AdminLoginRateLimitTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            "owner", password="segredo-forte-123", is_staff=True, is_superuser=True
        )
        cache.clear()
        self._win = patch("django_ratelimit.core._get_window", return_value=2_000_000_000)
        self._win.start()
        self._depth = self.settings(DOORMAN={"TRUSTED_PROXY_DEPTH": 2}, SHOPMAN_BFF_PROXY_SECRET="")
        self._depth.enable()

    def tearDown(self):
        self._depth.disable()
        self._win.stop()
        cache.clear()

    def _post(self, username, password, *, ip="203.0.113.7", forged=""):
        return self.client.post(
            LOGIN,
            {"username": username, "password": password, "next": "/admin/"},
            HTTP_X_FORWARDED_FOR=_xff(ip, forged),
        )

    def test_sexta_tentativa_contra_a_mesma_conta_e_429_mesmo_trocando_de_ip(self):
        for i in range(5):
            resp = self._post("owner", "errada", ip=f"198.51.100.{i + 1}")
            self.assertEqual(resp.status_code, 200)  # formulário de novo, com erro
        resp = self._post("OWNER", "errada", ip="198.51.100.99")
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(resp["Retry-After"], "60")

    def test_estourado_o_limite_nem_a_senha_certa_abre_sessao(self):
        for _ in range(5):
            self._post("owner", "errada")
        with patch("django.contrib.auth.forms.authenticate") as authenticate:
            resp = self._post("owner", "segredo-forte-123")
        self.assertEqual(resp.status_code, 429)
        authenticate.assert_not_called()
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_varredura_de_usernames_pelo_mesmo_ip_bate_no_teto_de_30(self):
        for i in range(30):
            # O valor forjado na ponta esquerda muda a cada tentativa e não
            # escolhe bucket: quem conta é a borda, pela direita.
            resp = self._post(f"u{i}", "errada", forged=f"192.0.2.{i + 1}")
            self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._post("u31", "errada", forged="192.0.2.200").status_code, 429)
        # Outro cliente (outro IP da borda) segue entrando.
        self.assertEqual(self._post("u32", "errada", ip="203.0.113.8").status_code, 200)

    def test_senha_certa_dentro_do_limite_entra(self):
        resp = self._post("owner", "segredo-forte-123")
        self.assertEqual(resp.status_code, 302)

    def test_get_do_login_nao_conta(self):
        """O BFF bate em GET /admin/login/ para buscar CSRF: isso não é tentativa."""
        for _ in range(40):
            self.assertEqual(self.client.get(LOGIN).status_code, 200)
        self.assertEqual(self._post("owner", "segredo-forte-123").status_code, 302)
