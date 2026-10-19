"""
Payman Admin with Unfold theme.

Unfold-styled admin for PaymentIntent and PaymentTransaction. Registered when
'shopman.payman.contrib.admin_unfold' is in INSTALLED_APPS; the core ``payman.admin``
guards against double registration.

Both models are mutated exclusively through ``PaymentService`` (and the immutable
``PaymentTransaction`` contract), so these admins are read-only views for operators.
"""

import json
import logging
from decimal import Decimal

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext_lazy as _
from shopman.payman.models import PaymentIntent, PaymentTransaction
from shopman.payman.service import PaymentService
from shopman.utils.contrib.admin_unfold.badges import unfold_badge, unfold_badge_numeric
from shopman.utils.contrib.admin_unfold.base import BaseModelAdmin, BaseTabularInline
from shopman.utils.monetary import format_money
from unfold.contrib.filters.admin.choice_filters import ChoicesRadioFilter
from unfold.decorators import action, display
from unfold.enums import ActionVariant
from unfold.forms import BaseDialogForm
from unfold.widgets import UnfoldAdminDecimalFieldWidget, UnfoldBooleanWidget

logger = logging.getLogger(__name__)


# Rótulos amigáveis para as chaves de gateway_data (heterogêneas por gateway).
_GATEWAY_LABELS = {
    "txid": _("TXID (PIX)"),
    "location": _("Location (PIX)"),
    "qrcode": _("QR Code (copia e cola)"),
    "imagemQrcode": _("Imagem do QR"),
    "checkout_url": _("URL de checkout"),
    "checkout_session_id": _("Sessão de checkout"),
    "client_secret": _("Client secret"),
    "efi_status": _("Status EFI"),
}


def _gateway_rows(data: dict):
    """Achata gateway_data em (rótulo, valor) legíveis, expandindo o client_secret
    (que pode ser um JSON com qrcode/txid no PIX da EFI) e cortando ruído base64."""
    rows: list[tuple[str, str]] = []
    for key, value in data.items():
        if key == "client_secret" and isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (ValueError, TypeError):
                parsed = None
            if isinstance(parsed, dict):
                for inner_key, inner_value in parsed.items():
                    label = _GATEWAY_LABELS.get(inner_key, inner_key)
                    text = "[imagem base64]" if inner_key == "imagemQrcode" else str(inner_value)
                    rows.append((label, text[:300]))
                continue
        label = _GATEWAY_LABELS.get(key, key)
        text = "[imagem base64]" if key == "imagemQrcode" else str(value)
        rows.append((label, text[:300]))
    return rows

_STATUS_COLORS = {
    PaymentIntent.Status.PENDING: "yellow",
    PaymentIntent.Status.AUTHORIZED: "blue",
    PaymentIntent.Status.CAPTURED: "green",
    PaymentIntent.Status.FAILED: "red",
    PaymentIntent.Status.CANCELLED: "base",
    PaymentIntent.Status.REFUNDED: "orange",
}

_METHOD_COLORS = {
    PaymentIntent.Method.PIX: "green",
    PaymentIntent.Method.CASH: "base",
    # As três leituras de cartão compartilham a cor: quem varre a lista procura
    # "foi cartão?" antes de procurar qual. `card` é o histórico e a loja online;
    # `credit`/`debit` são o balcão, onde prazo e taxa da adquirente diferem.
    PaymentIntent.Method.CARD: "blue",
    PaymentIntent.Method.CREDIT: "blue",
    PaymentIntent.Method.DEBIT: "blue",
    PaymentIntent.Method.EXTERNAL: "base",
}

_TRANSACTION_COLORS = {
    PaymentTransaction.Type.CAPTURE: "green",
    PaymentTransaction.Type.REFUND: "yellow",
    PaymentTransaction.Type.CHARGEBACK: "red",
}


def _format_datetime(dt):
    """Format datetime as DD/MM/AA · HH:MM."""
    return dt.strftime("%d/%m/%y · %H:%M") if dt else "—"


# =============================================================================
# TRANSACTION INLINE
# =============================================================================


class PaymentTransactionInline(BaseTabularInline):
    """Immutable financial movements under a PaymentIntent (read-only)."""

    model = PaymentTransaction
    extra = 0
    fields = ("type_badge", "amount_display", "reason", "gateway_id", "created_at_display")
    readonly_fields = ("type_badge", "amount_display", "reason", "gateway_id", "created_at_display")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @display(description=_("Tipo"))
    def type_badge(self, obj):
        color = _TRANSACTION_COLORS.get(obj.type, "base")
        return unfold_badge(obj.get_type_display().upper(), color)

    @display(description=_("Valor"))
    def amount_display(self, obj):
        return unfold_badge_numeric(f"R$ {format_money(obj.amount_q)}", "base")

    @display(description=_("Data"))
    def created_at_display(self, obj):
        return _format_datetime(obj.created_at)


# =============================================================================
# PAYMENT INTENT ADMIN
# =============================================================================


#: A permissão que estorna. Pontuada de propósito: o Unfold confere a forma com
#: ponto direto com ``request.user.has_perm``; a forma curta chamaria
#: ``has_change_permission``, que aqui é sempre ``False`` (a cobrança não se
#: edita à mão) e mataria a ação até para superusuário.
REFUND_PERMISSION = "payman.refund_paymentintent"


class RefundConfirmForm(BaseDialogForm):
    """Segunda confirmação do estorno, dentro do diálogo oficial do Unfold.

    O primeiro gesto é escolher a ação; o segundo é marcar a confirmação e
    enviar. Sem a marca o formulário não valida e nada é estornado. O
    `BaseDialogForm` ainda carrega o `_form_submitted` obrigatório, que é o que
    torna o GET incapaz de validar: GET só desenha o diálogo, o estorno é POST com
    CSRF.
    """

    confirm = forms.BooleanField(
        label=_("Confirmo o estorno, que não tem desfazer"),
        required=True,
        widget=UnfoldBooleanWidget,
        error_messages={"required": _("Marque a confirmação para estornar.")},
    )


class RefundAmountForm(RefundConfirmForm):
    """Estorno de um valor (ou do disponível inteiro, em branco), com a mesma confirmação."""

    amount_reais = forms.DecimalField(
        label=_("Valor a estornar (R$)"),
        required=False,
        min_value=Decimal("0.01"),
        max_digits=10,
        decimal_places=2,
        widget=UnfoldAdminDecimalFieldWidget,
    )

    field_order = ["amount_reais", "confirm"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.available_q = _available_q(self.object_id)
        self.fields["amount_reais"].help_text = _(
            "Disponível para estorno: R$ %(v)s. Em branco, estorna todo o disponível."
        ) % {"v": format_money(self.available_q)}

    def clean_amount_reais(self):
        amount = self.cleaned_data.get("amount_reais")
        if amount is None:
            return None
        amount_q = int((amount * 100).to_integral_value())
        if amount_q > self.available_q:
            raise forms.ValidationError(
                _("Valor acima do disponível (R$ %(v)s).") % {"v": format_money(self.available_q)}
            )
        return amount_q


def _available_q(object_id) -> int:
    """Capturado menos o já estornado; zero se a cobrança não existe."""
    intent = PaymentIntent.objects.filter(pk=object_id).first() if object_id else None
    if intent is None:
        return 0
    return max(intent.amount_q - PaymentService.refunded_total(intent.ref), 0)


@admin.register(PaymentIntent)
class PaymentIntentAdmin(BaseModelAdmin):
    """Read-only view of payment intents (mutated via PaymentService)."""

    list_display = (
        "ref",
        "order_ref",
        "method_badge",
        "status_badge",
        "amount_display",
        "currency",
        "created_at_display",
    )
    list_filter = (("status", ChoicesRadioFilter), "method", "currency")
    search_fields = ("ref", "order_ref", "gateway_id")
    readonly_fields = (
        "ref",
        "order_ref",
        "method",
        "status",
        "amount_q",
        "currency",
        "gateway",
        "gateway_id",
        "gateway_data_display",
        "idempotency_key",
        "created_at",
        "authorized_at",
        "captured_at",
        "cancelled_at",
        "expires_at",
        "cancel_reason",
    )
    fieldsets = (
        (_("Identificação"), {"fields": ("ref", "order_ref", "idempotency_key")}),
        (_("Pagamento"), {"fields": ("method", "status", "amount_q", "currency")}),
        (_("Gateway"), {"fields": ("gateway", "gateway_id", "gateway_data_display")}),
        (
            _("Datas"),
            {
                "fields": (
                    "created_at", "authorized_at", "captured_at",
                    "cancelled_at", "expires_at", "cancel_reason",
                ),
            },
        ),
    )
    inlines = [PaymentTransactionInline]
    ordering = ("-created_at",)
    compressed_fields = True
    actions_row = ["refund_row"]
    actions_detail = ["refund_detail"]

    # ⚠️ `dialog` não é enfeite de UX: é o que faz esta ação exigir POST.
    #
    # O Unfold monta a URL de `actions_row` embrulhada só em `admin_site.admin_view`
    # (`is_active and is_staff`, zero permissão de modelo) e a renderiza como um
    # `<a href>`. Sem `dialog`, o corpo executava em GET. Com `SESSION_COOKIE_SAMESITE
    # = "Lax"` o cookie VAI em navegação top-level GET, então um link mandado num
    # WhatsApp e clicado pelo gestor logado estornava.
    #
    # Com `dialog`, o GET só renderiza o diálogo (o form nasce inválido, sem
    # `_form_submitted` e sem a confirmação marcada); o estorno acontece no POST,
    # com CSRF. Ver `unfold/decorators.py`.
    #
    # A permissão é a dedicada (`payman.refund_paymentintent`), não `view`: ver a
    # cobrança não dá direito a devolver o dinheiro dela.
    @action(
        description=_("Estornar o total"),
        url_path="refund",
        icon="undo",
        variant=ActionVariant.DANGER,
        permissions=[REFUND_PERMISSION],
        dialog={
            "title": _("Estornar o total?"),
            "description": _(
                "Registra nesta cobrança o estorno de todo o valor disponível. "
                "Daqui o dinheiro não sai: a devolução pelo Pix ou cartão é feita no gateway. "
                "Não há desfazer."
            ),
            "form_class": RefundConfirmForm,
            "form_submit_text": _("Estornar"),
        },
    )
    def refund_row(self, request, form, object_id):
        intent = self.get_object(request, object_id)
        if intent is None:
            messages.error(request, _("Cobrança não encontrada."))
            return HttpResponseRedirect(reverse("admin:payman_paymentintent_changelist"))
        self._refund_one(request, intent)
        return HttpResponseRedirect(reverse("admin:payman_paymentintent_change", args=[intent.pk]))

    @action(
        description=_("Estornar um valor"),
        url_path="refund-amount",
        icon="undo",
        variant=ActionVariant.DANGER,
        permissions=[REFUND_PERMISSION],
        dialog={
            "title": _("Estornar um valor?"),
            "description": _(
                "Registra nesta cobrança o estorno do valor informado. "
                "Daqui o dinheiro não sai: a devolução pelo Pix ou cartão é feita no gateway. "
                "Não há desfazer."
            ),
            "form_class": RefundAmountForm,
            "form_submit_text": _("Estornar"),
        },
    )
    def refund_detail(self, request, form, object_id):
        intent = self.get_object(request, object_id)
        if intent is None:
            messages.error(request, _("Cobrança não encontrada."))
            return HttpResponseRedirect(reverse("admin:payman_paymentintent_changelist"))
        self._refund_one(request, intent, amount_q=form.cleaned_data.get("amount_reais"))
        return HttpResponseRedirect(reverse("admin:payman_paymentintent_change", args=[intent.pk]))

    # Estorno em LOTE não existe: ação de lote do Django roda direto no POST do
    # changelist, sem diálogo nem confirmação (laudo 01/09, 06-admin P0-1). Estorno
    # é um por vez, pelas duas ações acima.

    def _refund_one(self, request, intent, *, amount_q: int | None = None) -> bool:
        """Estorna ``amount_q`` (ou todo o disponível, se None). True se gravou."""
        try:
            transaction = PaymentService.refund(
                intent.ref, amount_q=amount_q, reason="Reembolso via admin"
            )
        except Exception as exc:  # PaymentService valida elegibilidade e levanta
            logger.warning("refund failed for %s: %s", intent.ref, exc)
            messages.error(request, str(exc))
            return False
        messages.success(
            request,
            _("Estorno de R$ %(v)s registrado em %(ref)s.")
            % {"v": format_money(transaction.amount_q), "ref": intent.ref},
        )
        return True

    @display(description=_("Dados do gateway"))
    def gateway_data_display(self, obj):
        data = obj.gateway_data or {}
        if not data:
            return "—"
        rows = format_html_join(
            "",
            '<div class="flex gap-3 py-1 border-b border-base-100 dark:border-base-800">'
            '<dt class="font-medium text-base-500 dark:text-base-400 w-48 shrink-0">{}</dt>'
            '<dd class="font-mono text-sm break-all">{}</dd></div>',
            _gateway_rows(data),
        )
        return format_html('<dl class="flex flex-col">{}</dl>', rows)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @display(description=_("Método"))
    def method_badge(self, obj):
        color = _METHOD_COLORS.get(obj.method, "base")
        return unfold_badge(obj.get_method_display().upper(), color)

    @display(description=_("Status"))
    def status_badge(self, obj):
        color = _STATUS_COLORS.get(obj.status, "base")
        return unfold_badge(obj.get_status_display().upper(), color)

    @display(description=_("Valor"))
    def amount_display(self, obj):
        return unfold_badge_numeric(f"R$ {format_money(obj.amount_q)}", "base")

    @display(description=_("Criado"))
    def created_at_display(self, obj):
        return _format_datetime(obj.created_at)


# =============================================================================
# PAYMENT TRANSACTION ADMIN
# =============================================================================


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(BaseModelAdmin):
    """Read-only audit trail of financial movements (immutable model)."""

    list_display = ("intent", "type_badge", "amount_display", "reason", "gateway_id", "created_at_display")
    list_filter = (("type", ChoicesRadioFilter),)
    search_fields = ("intent__ref", "gateway_id", "reason")
    readonly_fields = ("intent", "type", "amount_q", "reason", "gateway_id", "created_at")
    ordering = ("-created_at",)
    compressed_fields = True

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @display(description=_("Tipo"))
    def type_badge(self, obj):
        color = _TRANSACTION_COLORS.get(obj.type, "base")
        return unfold_badge(obj.get_type_display().upper(), color)

    @display(description=_("Valor"))
    def amount_display(self, obj):
        return unfold_badge_numeric(f"R$ {format_money(obj.amount_q)}", "base")

    @display(description=_("Data"))
    def created_at_display(self, obj):
        return _format_datetime(obj.created_at)
