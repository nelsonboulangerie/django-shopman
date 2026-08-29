"""A trilha de acesso: quem entrou, por qual porta, de onde.

O que estes testes protegem não é o model — é a **cobertura**. A trilha vale
enquanto ninguém consegue entrar sem deixar linha, e o desenho aposta tudo num
ponto só: o ``user_logged_in`` do Django, por onde os quatro caminhos de operador
passam. Se alguém trocar um `login()` por outra coisa, ou esquecer de marcar o
método numa porta nova, é aqui que aparece.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from shopman.doorman.models import PinCredential

from shopman.backstage.models import SignInEvent, SignInMethod, SignInOutcome
from shopman.backstage.services import sign_in_audit
from shopman.backstage.tests.support import trust_station
from shopman.shop.models import Channel, Shop

User = get_user_model()

UNLOCK = "/api/v1/backstage/operator/unlock/"
LOGIN = "/api/v1/backstage/operator/login/"
POS_PERM = "cashman.operate_pos"

_CASHMAN_PERMS = {"operate_pos", "adjust_shift", "audit_shift", "manage_operators"}


def _grant(user, codename):
    app_label = "cashman" if codename in _CASHMAN_PERMS else "backstage"
    user.user_permissions.add(
        Permission.objects.get(content_type__app_label=app_label, codename=codename)
    )
    return User.objects.get(pk=user.pk)


class SignInAuditTests(TestCase):
    def setUp(self):
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="PDV", is_active=True)
        trust_station(self.client, "pdv-main")
        self.op = User.objects.create_user(
            "ana", password="senha-forte-123", is_staff=True, first_name="Ana"
        )
        PinCredential.set_for(self.op, "1234")
        self.op = _grant(self.op, "operate_pos")

    # ── O crachá: o caso que motivou tudo ────────────────────────────────

    def test_badge_unlock_deixa_linha_com_metodo_cracha(self):
        """Um crachá esquecido destravando o balcão passa a ter onde ser visto."""
        token = PinCredential.issue_badge(self.op)

        resp = self.client.post(UNLOCK, {"badge": token, "perm": POS_PERM})

        self.assertEqual(resp.status_code, 200)
        evento = SignInEvent.objects.get()
        self.assertEqual(evento.user, self.op)
        self.assertEqual(evento.method, SignInMethod.BADGE)
        self.assertEqual(evento.outcome, SignInOutcome.SUCCESS)
        # De QUE balcão: é o eixo do corte de aviso ("estação desconhecida").
        self.assertEqual(evento.station_ref, "pdv-main")

    def test_cracha_desconhecido_recusado_tambem_vira_linha(self):
        """Sem conta a nomear, e é justamente esse o fato interessante.

        Alguém passou um crachá que não existe — só a trilha conta isso, porque
        a recusa não passa por ``authenticate()`` e não tem signal do Django.
        """
        resp = self.client.post(UNLOCK, {"badge": "naoexiste", "perm": POS_PERM})

        self.assertEqual(resp.status_code, 403)
        evento = SignInEvent.objects.get()
        self.assertIsNone(evento.user)
        self.assertEqual(evento.username, sign_in_audit.UNKNOWN_SUBJECT)
        self.assertEqual(evento.method, SignInMethod.BADGE)
        self.assertEqual(evento.outcome, SignInOutcome.FAILED)
        self.assertEqual(evento.data["reason"], "operator_unlock_invalid")

    # ── PIN ───────────────────────────────────────────────────────────────

    def test_pin_certo_e_pin_errado_se_distinguem_na_trilha(self):
        self.client.post(UNLOCK, {"operator_id": self.op.pk, "pin": "0000", "perm": POS_PERM})
        self.client.post(UNLOCK, {"operator_id": self.op.pk, "pin": "1234", "perm": POS_PERM})

        eventos = list(SignInEvent.objects.order_by("created_at", "pk"))
        self.assertEqual(len(eventos), 2)
        self.assertEqual(
            [(e.method, e.outcome) for e in eventos],
            [
                (SignInMethod.PIN, SignInOutcome.FAILED),
                (SignInMethod.PIN, SignInOutcome.SUCCESS),
            ],
        )
        # A recusa nomeia a conta-alvo mesmo sem sessão: é dela que se suspeita.
        self.assertEqual(eventos[0].username, "ana")

    # ── Senha ─────────────────────────────────────────────────────────────

    def test_login_por_senha_no_app_de_operador(self):
        resp = self.client.post(
            LOGIN, {"username": "ana", "password": "senha-forte-123"},
            content_type="application/json",
        )

        self.assertEqual(resp.status_code, 200)
        evento = SignInEvent.objects.get()
        self.assertEqual(evento.method, SignInMethod.PASSWORD)
        self.assertEqual(evento.outcome, SignInOutcome.SUCCESS)

    def test_login_no_admin_django_tambem_entra_na_trilha(self):
        """A porta que NÃO foi instrumentada à mão.

        É o teste que prova a aposta do desenho: o receiver está no signal do
        Django, então o Admin — que ninguém tocou — já nasce coberto.
        """
        resp = self.client.post(
            reverse("admin:login"),
            {"username": "ana", "password": "senha-forte-123", "next": "/admin/"},
        )

        self.assertIn(resp.status_code, (200, 302))
        evento = SignInEvent.objects.get(outcome=SignInOutcome.SUCCESS)
        self.assertEqual(evento.user, self.op)
        self.assertEqual(evento.data["path"], reverse("admin:login"))

    def test_senha_errada_de_conta_de_operador_vira_recusa(self):
        self.client.post(
            LOGIN, {"username": "ana", "password": "errada"},
            content_type="application/json",
        )

        evento = SignInEvent.objects.get()
        self.assertEqual(evento.method, SignInMethod.PASSWORD)
        self.assertEqual(evento.outcome, SignInOutcome.FAILED)
        # A conta VAI no evento: "alguém errou a sua senha" é o aviso que mais
        # interessa ao dono, e sem o vínculo não haveria a quem avisar.
        self.assertEqual(evento.user, self.op)

    def test_usuario_inexistente_nao_polui_a_trilha(self):
        """Ruído de internet numa trilha de segurança é o que faz ninguém lê-la."""
        self.client.post(
            LOGIN, {"username": "root", "password": "x"},
            content_type="application/json",
        )

        self.assertEqual(SignInEvent.objects.count(), 0)

    # ── Fronteira: cliente não entra ─────────────────────────────────────

    def test_login_de_cliente_nao_entra_na_trilha_de_operador(self):
        cliente = User.objects.create_user("cliente", password="x")  # is_staff=False
        self.assertIsNone(sign_in_audit.record(user=cliente, method=SignInMethod.OTP))
        self.assertEqual(SignInEvent.objects.count(), 0)

    # ── A trilha nunca derruba o login que observa ────────────────────────

    def test_falha_ao_gravar_nao_quebra_o_login(self):
        """Uma trilha que derruba o login vira negação de serviço: o balcão não
        abriria de manhã por causa do log."""
        from unittest.mock import patch

        with patch.object(
            SignInEvent.objects, "create", side_effect=RuntimeError("banco fora")
        ):
            resp = self.client.post(
                UNLOCK, {"operator_id": self.op.pk, "pin": "1234", "perm": POS_PERM}
            )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(SignInEvent.objects.count(), 0)

    # ── Retenção ──────────────────────────────────────────────────────────

    def test_purge_apaga_so_o_que_passou_do_prazo(self):
        from datetime import timedelta

        from django.utils import timezone

        antigo = SignInEvent.objects.create(username="ana", method=SignInMethod.PIN)
        SignInEvent.objects.filter(pk=antigo.pk).update(
            created_at=timezone.now() - timedelta(days=200)
        )
        recente = SignInEvent.objects.create(username="ana", method=SignInMethod.PIN)

        removidas = sign_in_audit.purge(days=180)

        self.assertEqual(removidas, 1)
        self.assertEqual(list(SignInEvent.objects.values_list("pk", flat=True)), [recente.pk])
