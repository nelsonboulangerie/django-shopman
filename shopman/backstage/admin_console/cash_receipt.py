"""Conferir comprovante de caixa — página Admin canônica (Unfold).

O QR do papel aponta para cá. Quem chega tem um comprovante na mão e quer saber
se ele é verdadeiro.

**Exige login de staff.** Isso é decisão, não default herdado: é dinheiro. Uma
página aberta diria a qualquer um, a partir de um papel achado no lixo, quanto a
loja tirou do caixa, quando, e quem autorizou — a planta de um roubo. O custo é
real (o conferente precisa entrar), e é o preço certo.
"""

from __future__ import annotations

from django import forms
from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.utils.html import format_html
from django.views.generic import TemplateView
from shopman.utils import table_badge
from unfold.views import UnfoldModelAdminViewMixin
from unfold.widgets import UnfoldAdminTextInputWidget

from shopman.backstage.projections.cash_receipt import (
    ReceiptVerification,
    build_receipt_verification,
)

#: Quem já pode ver movimentos de caixa pode conferir um. Não inventamos
#: permissão nova: seria uma segunda resposta para a mesma pergunta.
REQUIRED_PERM = "backstage.view_cashmovement"


class ReceiptCodeForm(forms.Form):
    """O campo de digitar, para quando o leitor não pega o QR.

    Papel de bobina amassa, desbota e passa por mão suja. Sem este campo, um
    comprovante com o QR arranhado viraria papel inconferível — e o código
    embaixo dele existe exatamente para esse dia.
    """

    code = forms.CharField(
        label="Código do comprovante",
        required=False,
        widget=UnfoldAdminTextInputWidget(
            attrs={"placeholder": "SG-42-7K3PQR2M", "autocomplete": "off"}
        ),
    )


class CashReceiptVerifyView(UnfoldModelAdminViewMixin, TemplateView):
    title = "Conferir comprovante"
    permission_required = REQUIRED_PERM
    template_name = "admin_console/cash_receipt/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # O código pode vir da URL (QR) ou do campo de digitar (quando o leitor
        # não pega o QR — papel amassado, tinta fraca).
        code = self.kwargs.get("code") or self.request.GET.get("code", "")
        verification = build_receipt_verification(code) if code else None
        context["receipt_form"] = ReceiptCodeForm(initial={"code": code})
        context["verification"] = verification
        if verification and verification.valid:
            context["movement_table"] = _movement_table(verification)
        return context


#: Como o registro de impressão aparece na tela. `pending` não é verde nem
#: vermelho de propósito: ninguém confirmou nada, e pintar de verde seria
#: exatamente a mentira que o status existe para não contar.
_RECEIPT_COLORS = {
    "Impresso": "green",
    "Falhou": "red",
    "Sem impressora": "yellow",
    "Sem confirmação": "gray",
}


def _movement_table(verification: ReceiptVerification) -> dict:
    """O que o movimento diz, lado a lado com o que está no papel."""
    estado = table_badge(
        verification.receipt_status,
        _RECEIPT_COLORS.get(verification.receipt_status, "gray"),
    )
    if verification.receipt_detail:
        estado = format_html(
            '{}<span class="block text-xs text-base-500">{}</span>',
            estado,
            verification.receipt_detail,
        )

    linhas = [
        ["Tipo", verification.movement_type],
        ["Valor", format_html('<span class="font-medium">{}</span>', verification.amount)],
        ["Turno", verification.shift_label],
        ["Operador", verification.created_by],
    ]
    # Só a retirada tem autorizador. Mostrar "Autorizado por: —" num suprimento
    # sugeriria que faltou assinatura onde nunca houve exigência.
    if verification.approved_by:
        linhas.append(["Autorizado por", verification.approved_by])
    linhas += [
        ["Quando", verification.created_at],
        ["Motivo", verification.reason],
        ["Impressão registrada", estado],
    ]
    return {"headers": ["Campo", "Registro no sistema"], "rows": linhas}


def _movement_model_admin():
    from shopman.backstage.models import CashMovement

    return admin.site._registry[CashMovement]


def cash_receipt_verify_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
    """Resolve o ModelAdmin tardiamente (ordem de import do URLConf)."""
    return CashReceiptVerifyView.as_view(model_admin=_movement_model_admin())(
        request, *args, **kwargs
    )
