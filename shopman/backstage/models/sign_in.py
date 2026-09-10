"""SignInEvent — a trilha de quem entrou no sistema, por qual porta, de onde.

O crachá é a única credencial da casa que se pode perder no chão: é posse pura,
sem segundo fator, e nada além dele é pedido no balcão. Até aqui, usá-lo não
deixava rastro nenhum — o único vestígio era ``PinCredential.last_verified_at``
mudando em silêncio, e um carimbo que sobrescreve o anterior não é trilha, é a
última linha de um livro sem páginas.

**Uma linha por entrada, para sempre** (dentro da retenção). É o que separa este
model dos vizinhos que quase serviriam:

* ``PinCredential`` guarda a credencial, não o uso dela;
* ``TrustedDevice`` guarda o dispositivo, e a estação nem sequer é uma pessoa;
* ``LogEntry`` do Admin guarda mudança de objeto — a EMISSÃO do crachá está lá
  (``backstage/admin/operators.py``), o USO nunca esteve;
* ``OperatorAlert`` é a fila de exceções da loja, e o que é reconhecido sai da
  fila. Trilha não sai.

**Só operador.** Login de cliente (OTP, passkey, link de acesso) não entra aqui:
é o escopo do pedido, é a ordem de grandeza certa (~dezenas por dia, não
milhares), e evita transformar a trilha numa segunda base de PII de cliente.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class SignInMethod(models.TextChoices):
    """Por qual porta a pessoa entrou.

    Não é o backend de autenticação do Django: senha do Admin e senha do app de
    operador são o MESMO backend e a mesma força, enquanto PIN e crachá são o
    mesmo backend com forças opostas — um é conhecimento com bloqueio por
    tentativa, o outro é posse pura. O corte de aviso pergunta por isto, então é
    isto que se guarda.
    """

    PASSWORD = "password", "senha"
    PIN = "pin", "PIN"
    BADGE = "badge", "crachá"
    OTP = "otp", "código de verificação"
    UNKNOWN = "unknown", "desconhecido"


class SignInOutcome(models.TextChoices):
    SUCCESS = "success", "entrou"
    FAILED = "failed", "recusado"
    #: O "não fui eu": a pessoa viu o aviso, não reconheceu o acesso, e as
    #: sessões daquela conta foram derrubadas. É linha da mesma trilha porque
    #: responde à mesma pergunta — o que aconteceu com o acesso a esta conta —
    #: e separá-la numa tabela própria obrigaria a ler duas para contar uma
    #: história só.
    REVOKED = "revoked", "revogado"


class SignInEvent(models.Model):
    """Uma tentativa de entrar no sistema, bem ou mal sucedida."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sign_in_events",
        verbose_name="operador",
    )
    #: Redundante com ``user`` de propósito: apagar a conta não pode apagar a
    #: trilha dela. Numa recusa nem existe conta para apontar, e o nome digitado
    #: é justamente o dado interessante.
    username = models.CharField("usuário", max_length=150, db_index=True)
    method = models.CharField(
        "método", max_length=20, choices=SignInMethod.choices,
        default=SignInMethod.UNKNOWN, db_index=True,
    )
    outcome = models.CharField(
        "resultado", max_length=10, choices=SignInOutcome.choices,
        default=SignInOutcome.SUCCESS, db_index=True,
    )
    #: De que balcão. É o eixo central do corte de aviso ("estação desconhecida"),
    #: e vazio quer dizer "de fora da loja" — um navegador qualquer, o Admin de
    #: casa —, que é uma informação e não uma lacuna.
    station_ref = models.CharField("estação", max_length=80, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField("IP", null=True, blank=True)
    created_at = models.DateTimeField("quando", auto_now_add=True, db_index=True)
    #: Já virou aviso? Guardado no evento e não numa fila à parte para que um
    #: reprocessamento não avise duas vezes pelo mesmo acesso.
    notified = models.BooleanField("avisado", default=False)
    #: Contexto, nunca filtro: ``user_agent``, ``surface``, ``path``, ``reason``.
    #: Chaves registradas em docs/reference/data-schemas.md.
    data = models.JSONField("contexto", default=dict, blank=True)

    class Meta:
        verbose_name = "acesso de operador"
        verbose_name_plural = "acessos de operador"
        ordering = ["-created_at"]
        indexes = [
            # A consulta é sempre "os acessos de fulano, do mais novo pro mais
            # velho" ou "o que entrou hoje". As duas cabem aqui.
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["outcome", "-created_at"]),
        ]

    @property
    def anomalies(self) -> list[str]:
        """Os códigos que fizeram este acesso ser destacado. Vazio = rotina.

        Mora no JSON e não numa coluna porque é resultado de uma REGRA editável:
        virar coluna congelaria no banco a resposta de ontem para uma pergunta
        que o gerente pode mudar hoje. O que se filtra é método, estação e
        resultado — esses sim são fato, não julgamento.
        """
        valores = (self.data or {}).get("anomalies")
        return list(valores) if isinstance(valores, list) else []

    def __str__(self) -> str:  # pragma: no cover - admin/debug only
        return f"{self.username} — {self.get_method_display()} ({self.get_outcome_display()})"
