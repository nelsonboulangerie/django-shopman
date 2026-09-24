"""Revisar a sugestão do GTIN — aceite CAMPO A CAMPO, na ficha do produto.

A sugestão (NF-e de compra, Cosmos, Open Food Facts) mora em
``Product.metadata['enrichment']`` como rascunho por campo; o serviço que a
monta e que a aplica é :mod:`shopman.shop.services.product_enrichment`. Esta
tela é só a porta: um diálogo oficial do Unfold (``BaseDialogForm``) com um
interruptor por campo sugerido e, quando o produto já tem outro valor naquele
campo, um segundo interruptor — "substituir" — sem o qual o valor preenchido à
mão fica.

Por que um diálogo por produto, e não mais uma ação em lote: o aceite antigo
era tudo-ou-nada e sobrescrevia alérgeno de dezenas de produtos de uma vez. A
conferência é com a embalagem na mão, uma de cada vez — e a tela agora tem o
formato da conferência.

A base é o Admin que o Core REGISTROU (Offerman + abas fiscal e social),
lida do site no ``ready()`` do backstage — o último app — e não importada: a
superfície herda do que o Core pôs no Admin, sem entrar no contrib dele.
"""

from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from unfold.decorators import action
from unfold.forms import BaseDialogForm
from unfold.widgets import UnfoldAdminTextareaWidget, UnfoldBooleanSwitchWidget

from shopman.shop.services import product_enrichment as enrichment


def _data(iso: str) -> str:
    moment = parse_datetime(iso or "")
    return moment.strftime("%d/%m/%Y") if moment else "data não registrada"


def _fonte(entry: dict) -> str:
    source = entry.get("source", "")
    return enrichment.SOURCE_LABELS.get(source, source)


def _situacao(block: dict, pending: dict) -> str:
    """O que a consulta disse, em texto: notas, foto de referência, aceites."""
    linhas: list[str] = []
    if not block:
        linhas.append(
            "Ainda não há sugestão para este produto. Ela nasce no recebimento com "
            "NF-e (GTIN, NCM, CEST, unidade) e em `manage.py fetch_product_enrichment` "
            "(Cosmos e Open Food Facts)."
        )
    linhas.extend(block.get("notes") or [])
    foto = block.get("reference_photo")
    if foto:
        linhas.append(
            f"Foto de referência — {foto.get('url')} · licença: {foto.get('license')} · "
            f"atribuição: {foto.get('attribution')}. Não vai para a vitrine: a vitrine usa foto da casa."
        )
    aceitos = block.get("accepted") or {}
    if aceitos:
        linhas.append(
            "Já aceitos: "
            + "; ".join(
                f"{enrichment.FIELD_LABELS.get(nome, nome)} ({_fonte(reg)}, {reg.get('accepted_by') or '—'} "
                f"em {_data(reg.get('accepted_at', ''))})"
                for nome, reg in aceitos.items()
            )
            + "."
        )
    if block and not pending:
        linhas.append("Nenhum campo pendente de aceite.")
    return "\n\n".join(linhas)


class EnrichmentReviewForm(BaseDialogForm):
    """Um interruptor por campo sugerido; "substituir" só onde há valor à mão.

    Os campos do form são montados a partir do rascunho do produto — por isso
    o form lê o ``object_id`` que o Unfold lhe entrega. Nada vem marcado: o
    padrão é não aceitar, e aceitar é gesto.
    """

    def __init__(self, request: HttpRequest, object_id=None, *args, **kwargs):
        super().__init__(request, object_id, *args, **kwargs)
        from shopman.offerman.models import Product

        self.product = Product.objects.filter(pk=object_id).first() if object_id else None
        self.pending = enrichment.pending_fields(self.product) if self.product else {}
        block = enrichment.draft(self.product) if self.product else {}

        situacao = _situacao(block, self.pending)
        if situacao:
            self.fields["situacao"] = forms.CharField(
                label="O que a consulta disse",
                required=False,
                disabled=True,
                initial=situacao,
                widget=UnfoldAdminTextareaWidget(attrs={"rows": min(10, 2 + situacao.count("\n"))}),
            )

        for nome, entry in self.pending.items():
            rotulo = enrichment.FIELD_LABELS[nome]
            valor = entry["value"]
            ajuda = [f"Fonte: {_fonte(entry)}, consultada em {_data(entry.get('fetched_at', ''))}."]
            if entry.get("detail"):
                ajuda.append(entry["detail"])
            for alt in entry.get("alternatives") or []:
                ajuda.append(f"{_fonte(alt)} diz outra coisa: {enrichment.format_value(nome, alt.get('value'))}.")
            if nome == "allergens" and block.get("allergens_unmapped"):
                ajuda.append("Fora da lista da casa: " + ", ".join(block["allergens_unmapped"]) + ".")
            self.fields[f"accept_{nome}"] = forms.BooleanField(
                label=f"{rotulo}: {enrichment.format_value(nome, valor)}",
                required=False,
                help_text=" ".join(ajuda),
                widget=UnfoldBooleanSwitchWidget,
            )
            if self.product is not None and enrichment.needs_replace(self.product, nome, valor):
                atual = enrichment.current_value(self.product, nome)
                self.fields[f"replace_{nome}"] = forms.BooleanField(
                    label=f"Substituir o {rotulo.lower()} preenchido à mão",
                    required=False,
                    help_text=(
                        f"Hoje: {enrichment.format_value(nome, atual)}. Sem esta marcação, "
                        "o valor de hoje fica."
                    ),
                    widget=UnfoldBooleanSwitchWidget,
                )

    def clean(self):
        cleaned = super().clean()
        self.chosen = [
            nome
            for nome in self.pending
            if cleaned.get(f"accept_{nome}") or cleaned.get(f"replace_{nome}")
        ]
        self.replace = [nome for nome in self.pending if cleaned.get(f"replace_{nome}")]
        if not self.chosen:
            alvo = next((f"accept_{nome}" for nome in self.pending), "situacao" if "situacao" in self.fields else None)
            mensagem = (
                "Marque ao menos um campo para aplicar."
                if self.pending
                else "Não há campo pendente para aplicar."
            )
            if alvo:
                self.add_error(alvo, mensagem)
            else:
                raise forms.ValidationError(mensagem)
        return cleaned


def _de_volta_para_a_ficha(request: HttpRequest, url: str) -> HttpResponse:
    """Volta para a ficha de um jeito que a MENSAGEM chegue junto.

    O diálogo envia por HTMX; um redirect comum seria seguido pelo próprio
    HTMX, que não acharia ``#dialog-form`` na ficha e esvaziaria o modal.
    ``HX-Redirect`` manda o navegador navegar (mesma lição de ``operators.py``).
    """
    if request.headers.get("HX-Request"):
        resposta = HttpResponse(status=204)
        resposta["HX-Redirect"] = url
        return resposta
    return HttpResponseRedirect(url)


class EnrichmentReviewMixin:
    """A ação de detalhe "Revisar sugestão do GTIN" para o Admin de Produto."""

    _enrichment_review = True

    @action(
        description="Revisar sugestão do GTIN",
        url_path="gtin-suggestion",
        icon="barcode",
        # ⚠️ `permissions=` é obrigatório: esta ação ESCREVE no produto (nome,
        # fiscal, alérgeno). Sem ele, a URL rodaria para quem só tem `view`.
        permissions=["change"],
        dialog={
            "title": "Revisar a sugestão do GTIN",
            "description": (
                "Marque só o que confere com a embalagem. Nada é aplicado sem marcação, "
                "e valor preenchido à mão só é trocado com “substituir” marcado. "
                "Alérgeno que a fonte não marcou é “não curado”, não “não contém”."
            ),
            "form_class": EnrichmentReviewForm,
            "form_submit_text": "Aplicar os campos marcados",
        },
    )
    def review_enrichment_detail(self, request, form, object_id):
        product = form.product
        url = reverse(
            f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_change",
            args=[object_id],
        )
        if product is None:
            messages.error(request, "Produto não encontrado.")
            return _de_volta_para_a_ficha(request, url)

        result = enrichment.accept_fields(
            product, form.chosen, replace=form.replace, user=request.user
        )
        rotulo = enrichment.FIELD_LABELS
        if result.applied:
            aplicados = ", ".join(rotulo[n] for n in result.applied)
            self.log_change(request, product, f"Sugestão do GTIN aceita: {aplicados}.")
            messages.success(request, f"Aplicado ao produto: {aplicados}.")
        for nome, atual in result.conflicts.items():
            messages.warning(
                request,
                f"{rotulo[nome]} não mudou: já tinha “{enrichment.format_value(nome, atual)}”, "
                "e substituir não foi marcado.",
            )
        for nome, motivo in result.refused.items():
            messages.error(request, f"{rotulo[nome]} não foi aplicado: {motivo}")
        return _de_volta_para_a_ficha(request, url)


def install_enrichment_review() -> None:
    """Compõe a revisão sobre o Admin de Produto registrado. Idempotente."""
    from shopman.offerman.models import Product

    current = admin.site._registry.get(Product)
    if current is None or getattr(current, "_enrichment_review", False):
        return
    base = type(current)

    class ProductEnrichmentAdmin(EnrichmentReviewMixin, base):
        actions_detail = [*(base.actions_detail or ()), "review_enrichment_detail"]

    ProductEnrichmentAdmin.__name__ = base.__name__
    ProductEnrichmentAdmin.__qualname__ = base.__qualname__
    admin.site.unregister(Product)
    admin.site.register(Product, ProductEnrichmentAdmin)
