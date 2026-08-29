"""A política de aviso: todo login avisa o dono, o suspeito chega destacado.

Três coisas aqui não são detalhe e cada teste existe por causa de uma delas:

1. **Nada é suprimido.** O corte governa DESTAQUE, não silêncio (decisão do dono,
   29/08/2026). Um teste que aceitasse "não avisou porque era rotina" deixaria a
   regressão passar exatamente onde ela machuca.
2. **Cada um sobre a própria conta.** A lista filtra por ``request.user`` e não
   existe porta que mude isso — um balconista que lesse a trilha da loja saberia
   quem estava no balcão a cada hora do mês.
3. **"Não fui eu" confirma antes de destruir**, e diz o que NÃO alcançou.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.sessions.models import Session
from django.test import TestCase
from shopman.doorman.models import PinCredential

from shopman.backstage.models import SignInEvent, SignInMethod, SignInOutcome
from shopman.backstage.tests.support import trust_station
from shopman.shop.models import Channel, NotificationCategory, Shop, UserNotification

User = get_user_model()

UNLOCK = "/api/v1/backstage/operator/unlock/"
SIGN_INS = "/api/v1/backstage/sign-ins/"
POS_PERM = "cashman.operate_pos"

_CASHMAN_PERMS = {"operate_pos", "adjust_shift", "audit_shift", "manage_operators"}


def _grant(user, codename):
    app_label = "cashman" if codename in _CASHMAN_PERMS else "backstage"
    user.user_permissions.add(
        Permission.objects.get(content_type__app_label=app_label, codename=codename)
    )
    return User.objects.get(pk=user.pk)


class SignInNotificationTests(TestCase):
    def setUp(self):
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="PDV", is_active=True)
        trust_station(self.client, "pdv-main")
        self.op = User.objects.create_user(
            "ana", password="senha-forte-123", is_staff=True, first_name="Ana"
        )
        PinCredential.set_for(self.op, "1234")
        self.op = _grant(self.op, "operate_pos")

    def _unlock_pin(self, pin="1234"):
        return self.client.post(
            UNLOCK, {"operator_id": self.op.pk, "pin": pin, "perm": POS_PERM}
        )

    # ── Todo login avisa ─────────────────────────────────────────────────

    def test_login_de_rotina_tambem_avisa(self):
        """O dono pediu "tudo". Rotina NÃO é motivo para não avisar."""
        self._unlock_pin()

        aviso = UserNotification.objects.get(user=self.op)
        self.assertEqual(aviso.category, NotificationCategory.SIGN_IN)
        self.assertTrue(SignInEvent.objects.get().notified)

    def test_aviso_de_rotina_nao_vem_destacado(self):
        """Avisar todos só funciona se o olho puder pular o que é rotina.

        A segunda entrada na MESMA estação é o dia normal: a primeira é sempre
        "estação nunca usada", que é o que o destaque deve pegar.
        """
        self._unlock_pin()
        self.client.post("/api/v1/backstage/operator/lock/")
        self._unlock_pin()

        ultimo = UserNotification.objects.order_by("-pk").first()
        self.assertFalse(ultimo.action_data["highlight"])
        self.assertEqual(ultimo.action_data["anomalies"], [])

    def test_cracha_chega_destacado_sem_ser_separado(self):
        """Destaque, não silo: o aviso é da mesma lista, com um sinal a mais."""
        token = PinCredential.issue_badge(self.op)

        self.client.post(UNLOCK, {"badge": token, "perm": POS_PERM})

        aviso = UserNotification.objects.get(user=self.op)
        self.assertTrue(aviso.action_data["highlight"])
        self.assertIn("badge", aviso.action_data["anomalies"])
        self.assertIn("crachá", aviso.message)

    def test_estacao_nunca_usada_por_esta_conta_destaca(self):
        self._unlock_pin()

        evento = SignInEvent.objects.get()
        self.assertIn("unknown_station", evento.anomalies)

    def test_pin_errado_avisa_o_dono_da_conta(self):
        """"Alguém errou a sua senha" é o aviso que mais interessa ao dono."""
        self._unlock_pin(pin="0000")

        aviso = UserNotification.objects.get(user=self.op)
        self.assertIn("Tentativa recusada", aviso.title)
        # Recusa não tem sessão para derrubar — não oferece o "não fui eu".
        self.assertFalse(aviso.is_actionable)

    def test_cracha_desconhecido_fica_so_no_log(self):
        """Sem dono, não há caixa. A linha existe; o aviso não tem destinatário."""
        self.client.post(UNLOCK, {"badge": "naoexiste", "perm": POS_PERM})

        self.assertEqual(SignInEvent.objects.count(), 1)
        self.assertEqual(UserNotification.objects.count(), 0)

    def test_fora_do_expediente_destaca_pelo_calendario_da_casa(self):
        """Quem responde "a loja estava aberta?" é o ``business_calendar``.

        Uma segunda leitura de ``opening_hours`` aqui divergiria da primeira no
        primeiro feriado — e marcaria como anômalo o acesso de um dia em que a
        casa de fato abriu.
        """
        from django.utils import timezone

        loja = Shop.objects.first()
        loja.opening_hours = {
            dia: {"open": "09:00", "close": "18:00"}
            for dia in ("monday", "tuesday", "wednesday", "thursday", "friday",
                        "saturday", "sunday")
        }
        loja.save(update_fields=["opening_hours"])

        self._unlock_pin()
        evento = SignInEvent.objects.get()
        # Às 03h de um dia com expediente 09-18: fora da janela.
        madrugada = timezone.localtime(evento.created_at).replace(hour=3, minute=0)
        SignInEvent.objects.filter(pk=evento.pk).update(created_at=madrugada)
        evento.refresh_from_db()

        from shopman.backstage.services.sign_in_audit import detect_anomalies

        self.assertIn("outside_hours", detect_anomalies(evento))

        # E dentro da janela, não destaca por horário.
        meio_dia = madrugada.replace(hour=12)
        SignInEvent.objects.filter(pk=evento.pk).update(created_at=meio_dia)
        evento.refresh_from_db()
        self.assertNotIn("outside_hours", detect_anomalies(evento))

    # ── A regra de destaque é configurável, e falha para os defaults ──────

    def test_chave_desconhecida_ignora_a_configuracao_e_mantem_o_destaque(self):
        """Regra roda como configurada ou não roda — e aqui "não roda" seria pior.

        Uma chave escrita errada não pode virar "parou de sinalizar em silêncio",
        que é exatamente a falha que este trabalho existe para evitar. A
        configuração quebrada é ignorada; os defaults são o piso.
        """
        from shopman.shop.models import RuleConfig
        from shopman.shop.rules.security import params_or_defaults

        RuleConfig.objects.create(
            ref="sign_in_highlight",
            rule_path="shopman.shop.rules.security.SignInHighlightRule",
            label="Destaque de acessos",
            enabled=True,
            params={"crachá": False},  # chave que não existe
        )

        self.assertTrue(params_or_defaults()["badge"])

    def test_desligar_um_sinal_pela_configuracao(self):
        from shopman.shop.models import RuleConfig
        from shopman.shop.rules.security import params_or_defaults

        RuleConfig.objects.create(
            ref="sign_in_highlight",
            rule_path="shopman.shop.rules.security.SignInHighlightRule",
            label="Destaque de acessos",
            enabled=True,
            params={"badge": False},
        )

        params = params_or_defaults()
        self.assertFalse(params["badge"])
        # O resto do default continua de pé — desligar um sinal não desliga todos.
        self.assertTrue(params["unknown_station"])

    # ── Cada um sobre a própria conta ────────────────────────────────────

    def test_lista_traz_so_os_acessos_de_quem_pede(self):
        outro = User.objects.create_user("bia", password="x", is_staff=True)
        outro = _grant(outro, "operate_pos")
        SignInEvent.objects.create(user=outro, username="bia", method=SignInMethod.PIN)
        self._unlock_pin()

        resp = self.client.get(SIGN_INS)

        self.assertEqual(resp.status_code, 200)
        usuarios = {item["station_display"] for item in resp.json()["sign_ins"]}
        self.assertEqual(len(resp.json()["sign_ins"]), 1)
        self.assertEqual(usuarios, {"pdv-main"})

    def test_nao_existe_parametro_que_leia_a_conta_alheia(self):
        """A porta que não existe não vaza — nem por query string."""
        outro = User.objects.create_user("bia", password="x", is_staff=True)
        SignInEvent.objects.create(user=outro, username="bia", method=SignInMethod.PIN)
        self._unlock_pin()

        resp = self.client.get(SIGN_INS, {"user": outro.pk, "user_id": outro.pk})

        self.assertEqual(len(resp.json()["sign_ins"]), 1)

    def test_caixa_de_notificacao_alheia_nao_abre(self):
        outro = User.objects.create_user("bia", password="x", is_staff=True)
        alheia = UserNotification.objects.create(
            user=outro, category=NotificationCategory.SIGN_IN, title="acesso da bia"
        )
        self._unlock_pin()

        resp = self.client.post(f"/api/v1/backstage/notifications/{alheia.pk}/read/")

        self.assertEqual(resp.status_code, 404)


class NotMeTests(TestCase):
    """"Não fui eu" derruba as sessões — depois de confirmar, e dizendo o resto."""

    def setUp(self):
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="PDV", is_active=True)
        trust_station(self.client, "pdv-main")
        self.op = User.objects.create_user("ana", password="x", is_staff=True)
        PinCredential.set_for(self.op, "1234")
        self.op = _grant(self.op, "operate_pos")
        self.client.post(UNLOCK, {"operator_id": self.op.pk, "pin": "1234", "perm": POS_PERM})
        self.aviso = UserNotification.objects.get(user=self.op)

    def _act(self, **body):
        return self.client.post(
            f"/api/v1/backstage/notifications/{self.aviso.pk}/action/",
            data={"action": "not_me", **body},
            content_type="application/json",
        )

    def test_sem_confirmacao_nao_destroi_nada(self):
        """Ação destrutiva descreve o estrago antes de causá-lo."""
        antes = Session.objects.count()

        resp = self._act()

        self.assertEqual(resp.status_code, 409)
        self.assertTrue(resp.json()["needs_confirmation"])
        self.assertIn("venda em andamento", resp.json()["detail"])
        self.assertEqual(Session.objects.count(), antes)

    def test_confirmado_derruba_a_sessao_do_outro_dispositivo(self):
        outro_dispositivo = self.client_class()
        trust_station(outro_dispositivo, "pdv-main")
        outro_dispositivo.post(
            UNLOCK, {"operator_id": self.op.pk, "pin": "1234", "perm": POS_PERM}
        )
        self.assertEqual(
            outro_dispositivo.get("/api/v1/backstage/pos/").status_code, 200
        )

        resp = self._act(confirm=True)

        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(resp.json()["sessions_revoked"], 1)
        # O outro dispositivo perdeu a identidade: o PDV recusa quem não é
        # operador. A ESTAÇÃO continua confiável — o cookie é do balcão, não da
        # pessoa —, então ele cai na tela de identificação e não numa de login.
        self.assertEqual(outro_dispositivo.get("/api/v1/backstage/pos/").status_code, 403)
        self.assertEqual(
            outro_dispositivo.get("/api/v1/backstage/operator/session/").json()["locked"],
            True,
        )

    def test_a_propria_sessao_de_quem_pede_sobrevive(self):
        """Quem está lendo o aviso acabou de se autenticar: derrubá-lo seria um
        logout confuso no meio do expediente."""
        resp = self._act(confirm=True)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.client.get("/api/v1/backstage/pos/").status_code, 200)

    def test_o_cracha_morre_junto_com_a_sessao(self):
        """Antes, o crachá clonado reentrava em 0,02s. Este teste é aquela porta.

        Derrubar a sessão sem matar o crachá era teatro: o atacante voltava numa
        requisição. Decisão do dono em 29/08/2026 — o crachá cai junto.
        """
        token = PinCredential.issue_badge(self.op)

        resp = self._act(confirm=True)

        self.assertTrue(resp.json()["badge_revoked"])
        self.assertIsNone(PinCredential.objects.get(user=self.op).badge_hash)
        # E a prova que importa: o mesmo crachá não abre mais a porta.
        atacante = self.client_class()
        trust_station(atacante, "pdv-main")
        volta = atacante.post(UNLOCK, {"badge": token, "perm": POS_PERM})
        self.assertEqual(volta.status_code, 403)

    def test_o_pin_continua_valendo(self):
        """Ninguém para de trabalhar: PIN é conhecimento, não se acha no chão."""
        PinCredential.issue_badge(self.op)

        resp = self._act(confirm=True)

        self.assertTrue(resp.json()["pin_still_valid"])
        outro = self.client_class()
        trust_station(outro, "pdv-main")
        entra = outro.post(UNLOCK, {"operator_id": self.op.pk, "pin": "1234", "perm": POS_PERM})
        self.assertEqual(entra.status_code, 200)

    def test_quem_reemite_e_avisado(self):
        """Crachá que morre calado vira fila no balcão às 6h."""
        gerente = User.objects.create_user("gina", password="x", is_staff=True)
        gerente = _grant(gerente, "manage_operators")
        PinCredential.issue_badge(self.op)

        self._act(confirm=True)

        aviso = UserNotification.objects.filter(user=gerente).first()
        self.assertIsNotNone(aviso)
        self.assertIn("Crachá de", aviso.title)
        self.assertIn("Reemita", aviso.message)

    def test_a_revogacao_vira_linha_no_log_com_quem_pediu(self):
        self._act(confirm=True)

        linha = SignInEvent.objects.get(outcome=SignInOutcome.REVOKED)
        self.assertEqual(linha.user, self.op)
        self.assertEqual(linha.data["requested_by"], "ana")
        self.assertEqual(linha.data["reason"], "not_me")

    def test_a_revogacao_e_ela_propria_notificavel(self):
        self._act(confirm=True)

        titulos = list(UserNotification.objects.values_list("title", flat=True))
        self.assertTrue(any("revogados" in t for t in titulos), titulos)

    def test_nao_revoga_a_conta_alheia(self):
        """Um id de acesso alheio não vira revogação alheia por adivinhação."""
        outro = User.objects.create_user("bia", password="x", is_staff=True)
        alheio = SignInEvent.objects.create(
            user=outro, username="bia", method=SignInMethod.PIN
        )
        self.aviso.action_data = {"sign_in_event_id": alheio.pk}
        self.aviso.save(update_fields=["action_data"])

        resp = self._act(confirm=True)

        self.assertEqual(resp.status_code, 404)


class BadgeLostTests(TestCase):
    """"Perdi meu crachá": na trava, provando o PIN, sem esperar uso indevido."""

    URL = "/api/v1/backstage/operator/badge/lost/"

    def setUp(self):
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="PDV", is_active=True)
        trust_station(self.client, "pdv-main")
        self.op = User.objects.create_user("ana", password="x", is_staff=True)
        PinCredential.set_for(self.op, "1234")
        self.op = _grant(self.op, "operate_pos")
        self.token = PinCredential.issue_badge(self.op)

    def _post(self, **body):
        import json

        return self.client.post(
            self.URL, data=json.dumps(body), content_type="application/json"
        )

    def _badge_ainda_abre(self) -> bool:
        outro = self.client_class()
        trust_station(outro, "pdv-main")
        return outro.post(UNLOCK, {"badge": self.token, "perm": POS_PERM}).status_code == 200

    def test_funciona_sem_sessao_na_tela_de_destrave(self):
        """O cenário real: chega às 6h sem o crachá, o balcão está travado."""
        resp = self._post(operator_id=self.op.pk, pin="1234", confirm=True)

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["badge_revoked"])
        self.assertFalse(self._badge_ainda_abre())

    def test_sem_confirmacao_nao_destroi_nada(self):
        resp = self._post(operator_id=self.op.pk, pin="1234")

        self.assertEqual(resp.status_code, 409)
        self.assertTrue(resp.json()["needs_confirmation"])
        self.assertTrue(self._badge_ainda_abre())

    def test_sem_confirmacao_nao_gasta_tentativa_do_lockout(self):
        """Cliente que esqueceu a flag não pode queimar o PIN de quem não pediu."""
        self._post(operator_id=self.op.pk, pin="0000")

        self.assertEqual(PinCredential.objects.get(user=self.op).attempts, 0)

    def test_pin_errado_recusa_e_vira_linha(self):
        """Errar o PIN aqui é tentar matar o crachá de alguém."""
        resp = self._post(operator_id=self.op.pk, pin="0000", confirm=True)

        self.assertEqual(resp.status_code, 403)
        self.assertTrue(self._badge_ainda_abre())
        linha = SignInEvent.objects.get(outcome=SignInOutcome.FAILED)
        self.assertEqual(linha.data["reason"], "badge_lost_invalid")
        self.assertEqual(linha.user, self.op)

    def test_o_pin_sobrevive(self):
        self._post(operator_id=self.op.pk, pin="1234", confirm=True)

        outro = self.client_class()
        trust_station(outro, "pdv-main")
        self.assertEqual(
            outro.post(
                UNLOCK, {"operator_id": self.op.pk, "pin": "1234", "perm": POS_PERM}
            ).status_code,
            200,
        )

    def test_vira_linha_no_log_com_o_motivo(self):
        self._post(operator_id=self.op.pk, pin="1234", confirm=True)

        linha = SignInEvent.objects.get(outcome=SignInOutcome.REVOKED)
        self.assertEqual(linha.data["reason"], "lost")
        self.assertTrue(linha.data["badge_revoked"])

    def test_nao_mata_o_cracha_do_colega_sem_o_PIN_dele(self):
        """O alvo vem no corpo, mas a autorização é provar o PIN DAQUELA conta."""
        colega = User.objects.create_user("bia", password="x", is_staff=True)
        PinCredential.set_for(colega, "5555")
        PinCredential.issue_badge(colega)

        resp = self._post(operator_id=colega.pk, pin="1234", confirm=True)

        self.assertEqual(resp.status_code, 403)
        self.assertIsNotNone(PinCredential.objects.get(user=colega).badge_hash)

    def test_dispositivo_sem_estacao_nao_alcanca(self):
        forasteiro = self.client_class()  # sem trust_station

        resp = forasteiro.post(
            self.URL,
            data=f'{{"operator_id":{self.op.pk},"pin":"1234","confirm":true}}',
            content_type="application/json",
        )

        self.assertIn(resp.status_code, (401, 403))
        self.assertTrue(self._badge_ainda_abre())
