"""Entry — o livro-caixa do turno. Append-only, um só, em ordem.

Uma linha por coisa que aconteceu na gaveta de um turno. ``amount_q`` é o
**efeito no saldo**, assinado: positivo entra, negativo sai, **zero quando o
acontecimento não mexe em dinheiro** (abrir a gaveta sem venda, pedir troco,
liberar a trava). Assim o mesmo livro responde as duas perguntas do gerente
sem união de tabelas: "quanto era para ter" é ``Σ amount_q``; "o que aconteceu,
em ordem" é a lista.

Segue o padrão do ``stockman.Move`` e da ``payman.PaymentTransaction``: nunca
``update()``, nunca ``delete()``; correção é lançamento novo apontando para o
que corrige (``parent``). O fechamento cego é um lançamento (``count``): o
ajuste que faz o livro bater com a gaveta física. Esperado, contado e diferença
são provados pelo livro, não guardados em coluna.

⚠️ Limite honesto de "imutável": a guarda vale no app. Quem tem acesso ao banco
edita o que quiser; imutabilidade real exigiria trigger no Postgres, e nem o
``Move`` tem. Não prometa mais do que isto entrega.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

_IMMUTABLE = "Lançamentos de caixa são imutáveis. Para corrigir, registre um novo lançamento apontando para este."


class EntryQuerySet(models.QuerySet):
    """Guarda do livro: protege do acidente e do descuido, não do DBA."""

    def update(self, **kwargs):
        raise ValueError(_IMMUTABLE)

    def delete(self):
        raise ValueError(_IMMUTABLE)


class Entry(models.Model):
    class Kind(models.TextChoices):
        # Dinheiro entra
        FLOAT_IN = "float_in", _("Fundo de troco")
        SALE = "sale", _("Venda")
        COD_SETTLED = "cod_settled", _("Acerto de entrega")
        CASH_IN = "cash_in", _("Entrada de caixa")
        # Dinheiro sai
        REFUND = "refund", _("Devolução")
        CASH_OUT = "cash_out", _("Saída de caixa")
        # Custódia temporária do entregador: o troco sai com ele no despacho e
        # volta (o que sobrou) no acerto. Não é pagamento; é dinheiro da gaveta
        # na rua, e o livro precisa saber disso para a contagem não acusar falta.
        COURIER_OUT = "courier_out", _("Troco levado pelo entregador")
        COURIER_IN = "courier_in", _("Troco de volta do entregador")
        # Contagem: o ajuste que faz o livro bater com a gaveta
        COUNT = "count", _("Contagem de fechamento")
        COUNT_CORRECTION = "count_correction", _("Correção da contagem")
        # Sem dinheiro
        DRAWER_OPEN = "drawer_open", _("Gaveta aberta sem venda")
        DRAWER_UNLOCK = "drawer_unlock", _("Trava da gaveta liberada")
        CHANGE_REQUESTED = "change_requested", _("Troco pedido")
        CHANGE_SERVED = "change_served", _("Troco atendido")
        CHANGE_CANCELLED = "change_cancelled", _("Pedido de troco cancelado")
        RECEIPT_RESULT = "receipt_result", _("Resultado do comprovante")
        NOTE = "note", _("Anotação")

    #: O sinal que cada tipo admite. É a única tabela; o CheckConstraint e o
    #: service leem daqui. ``"+"`` > 0, ``"-"`` < 0, ``"0"`` = 0, ``"±"`` livre,
    #: ``"+0"`` >= 0 (venda sem dinheiro: pix/cartão passam pelo turno sem tocar
    #: na gaveta; troco de volta zero: o entregador usou tudo, e o acerto diz isso).
    SIGN_BY_KIND: dict[str, str] = {
        Kind.FLOAT_IN: "+",
        Kind.SALE: "+0",
        Kind.COD_SETTLED: "+",
        Kind.CASH_IN: "+",
        Kind.REFUND: "-",
        Kind.CASH_OUT: "-",
        Kind.COURIER_OUT: "-",
        Kind.COURIER_IN: "+0",
        Kind.COUNT: "±",
        Kind.COUNT_CORRECTION: "±",
        Kind.DRAWER_OPEN: "0",
        Kind.DRAWER_UNLOCK: "0",
        Kind.CHANGE_REQUESTED: "0",
        Kind.CHANGE_SERVED: "0",
        Kind.CHANGE_CANCELLED: "0",
        Kind.RECEIPT_RESULT: "0",
        Kind.NOTE: "0",
    }

    #: Tipos que só existem respondendo a outro lançamento, e de que tipo.
    PARENT_KIND_BY_KIND: dict[str, tuple[str, ...]] = {
        Kind.COUNT_CORRECTION: (Kind.COUNT,),
        Kind.CHANGE_SERVED: (Kind.CHANGE_REQUESTED,),
        Kind.CHANGE_CANCELLED: (Kind.CHANGE_REQUESTED,),
        Kind.RECEIPT_RESULT: (Kind.CASH_OUT, Kind.CASH_IN),
    }

    #: O que o balcão pode dizer sobre o papel de um comprovante
    #: (``receipt_result.payload["status"]``).
    #:
    #: ``pending`` NÃO entra: é o estado de quem ainda não disse nada, e "dizer
    #: que não disse" seria linha vazia no livro. A ausência de filho
    #: ``receipt_result`` já é "sem confirmação".
    #:
    #: ⚠️ Esta é a FONTE. O ``backstage`` valida antes, para a mensagem ser do
    #: dialeto do balcão, mas lê a lista daqui — o schema do payload é do único
    #: escritor, e duas listas divergiriam no dia em que um estado novo entrasse.
    RECEIPT_STATUSES: frozenset[str] = frozenset({"printed", "failed", "skipped"})

    #: Tipos que exigem a segunda assinatura (``approved_by``): a exceção do
    #: caixa tem sempre duas pessoas, quem faz e quem autoriza.
    APPROVAL_REQUIRED: frozenset[str] = frozenset(
        {Kind.CASH_OUT, Kind.DRAWER_UNLOCK, Kind.CHANGE_SERVED, Kind.COUNT_CORRECTION}
    )

    shift = models.ForeignKey(
        "cashman.Shift",
        on_delete=models.PROTECT,
        related_name="entries",
        verbose_name=_("turno"),
    )
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cash_entries",
        verbose_name=_("operador"),
        help_text=_("Quem agiu: o do turno, ou o gerente num fechamento supervisório."),
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cash_entries_approved",
        verbose_name=_("autorizado por"),
        help_text=_("A segunda assinatura: sangria, destrave, troco atendido, correção."),
    )
    at = models.DateTimeField(_("quando"), default=timezone.now)
    kind = models.CharField(_("tipo"), max_length=24, choices=Kind.choices)
    amount_q = models.BigIntegerField(
        _("efeito (centavos)"),
        default=0,
        help_text=_("Efeito no saldo da gaveta, assinado. Zero quando o evento não mexe em dinheiro."),
    )
    order_ref = models.CharField(_("ref do pedido"), max_length=50, blank=True, default="", db_index=True)
    payment_ref = models.CharField(
        _("ref do pagamento"),
        max_length=64,
        blank=True,
        default="",
        help_text=_("Ref do PaymentIntent no payman (venda, devolução, acerto de entrega)."),
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
        verbose_name=_("responde a"),
        help_text=_("O lançamento que este atende, resolve ou corrige."),
    )
    reason = models.CharField(_("motivo"), max_length=200, blank=True, default="")
    payload = models.JSONField(
        _("detalhe"),
        default=dict,
        blank=True,
        help_text=_("O específico de cada tipo. Schema em docs/reference/data-schemas.md."),
    )

    objects = EntryQuerySet.as_manager()

    class Meta:
        app_label = "cashman"
        verbose_name = _("lançamento de caixa")
        verbose_name_plural = _("lançamentos de caixa")
        # `id` desempata dois lançamentos no mesmo instante: a ordem em que
        # foram gravados é a ordem em que aconteceram.
        ordering = ["at", "id"]
        indexes = [
            models.Index(fields=["shift", "id"], name="cashman_entry_shift_id_idx"),
            models.Index(fields=["operator", "at"], name="cashman_entry_op_at_idx"),
            models.Index(fields=["kind", "at"], name="cashman_entry_kind_at_idx"),
            models.Index(fields=["at"], name="cashman_entry_at_idx"),
        ]
        constraints = [
            # O sinal mora no TIPO, e o banco confere. Uma sangria positiva ou
            # uma abertura de gaveta com valor seriam um segundo jeito de dizer
            # a mesma coisa; dois jeitos é como um lançamento se disfarça de outro.
            models.CheckConstraint(
                condition=(
                    models.Q(kind__in=["float_in", "cod_settled", "cash_in"], amount_q__gt=0)
                    | models.Q(kind__in=["sale", "courier_in"], amount_q__gte=0)
                    | models.Q(kind__in=["refund", "cash_out", "courier_out"], amount_q__lt=0)
                    | models.Q(kind__in=["count", "count_correction"])
                    | models.Q(
                        kind__in=[
                            "drawer_open",
                            "drawer_unlock",
                            "change_requested",
                            "change_served",
                            "change_cancelled",
                            "receipt_result",
                            "note",
                        ],
                        amount_q=0,
                    )
                ),
                name="cashman_entry_sign_by_kind",
            ),
            # Um pedido entra UMA vez no livro de um turno, por tipo. Dois
            # submits do mesmo fechamento (retry de rede do PDV) dobrariam o
            # dinheiro esperado do turno, e um `exists()` antes do insert é
            # TOCTOU: entre a leitura e a gravação cabe o segundo submit. A
            # unicidade é do banco, como a do turno aberto; a mensagem continua
            # sendo da casa (``services.record`` traduz o IntegrityError).
            #
            # `order_ref` vazio fica de fora porque não há pedido a que amarrar
            # (venda de balcão sem ref), e o par é por TIPO: a devolução do mesmo
            # pedido convive com a venda, e o mesmo pedido pode voltar noutro
            # turno (o acerto de entrega de ontem).
            models.UniqueConstraint(
                fields=["shift", "order_ref"],
                condition=models.Q(kind="sale") & ~models.Q(order_ref=""),
                name="cashman_entry_one_sale_per_order_uq",
            ),
            models.UniqueConstraint(
                fields=["shift", "order_ref"],
                condition=models.Q(kind="cod_settled") & ~models.Q(order_ref=""),
                name="cashman_entry_one_cod_settled_per_order_uq",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError(_IMMUTABLE)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError(_IMMUTABLE)

    def __str__(self) -> str:
        return f"{self.at:%d/%m %H:%M} {self.get_kind_display()} {self.amount_q:+d}"

    @classmethod
    def sign_allows(cls, kind: str, amount_q: int) -> bool:
        """O ``amount_q`` respeita o sinal do tipo? Mesma tabela do CheckConstraint."""
        rule = cls.SIGN_BY_KIND.get(kind)
        if rule is None:
            return False
        if rule == "+":
            return amount_q > 0
        if rule == "+0":
            return amount_q >= 0
        if rule == "-":
            return amount_q < 0
        if rule == "0":
            return amount_q == 0
        return True
