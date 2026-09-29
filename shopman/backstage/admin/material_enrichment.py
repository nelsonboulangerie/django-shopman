"""Ação Unfold para revisar a sugestão do GTIN no cadastro do insumo."""

from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from unfold.decorators import action
from unfold.forms import BaseDialogForm
from unfold.widgets import UnfoldAdminTextareaWidget, UnfoldBooleanSwitchWidget

from shopman.shop.services import gtin_enrichment as shared
from shopman.shop.services import material_enrichment as enrichment


def _date(iso: str) -> str:
    moment = parse_datetime(iso or "")
    return moment.strftime("%d/%m/%Y") if moment else "data não registrada"


def _source(entry: dict) -> str:
    source = entry.get("source", "")
    return shared.SOURCE_LABELS.get(source, source)


def _status(block: dict, pending: dict) -> str:
    lines: list[str] = []
    if not block:
        lines.append(
            "Ainda não há sugestão para este insumo. A NF-e pode preparar GTIN, NCM, "
            "CEST e unidade; `manage.py fetch_material_enrichment --stage` pode completar "
            "o rascunho com Cosmos e Open Food Facts."
        )
    lines.extend(block.get("notes") or [])
    photo = block.get("reference_photo")
    if photo:
        lines.append(
            f"Foto de referência: {photo.get('url')} · licença: {photo.get('license')} · "
            f"atribuição: {photo.get('attribution')}. Não vira foto da vitrine."
        )
    accepted = block.get("accepted") or {}
    if accepted:
        lines.append(
            "Já aceitos: "
            + "; ".join(
                f"{enrichment.FIELD_LABELS.get(name, name)} ({_source(record)}, "
                f"{record.get('accepted_by') or 'não registrado'} em "
                f"{_date(record.get('accepted_at', ''))})"
                for name, record in accepted.items()
            )
            + "."
        )
    if block and not pending:
        lines.append("Nenhum campo pendente de aceite.")
    return "\n\n".join(lines)


class MaterialEnrichmentReviewForm(BaseDialogForm):
    """Interruptores oficiais do Unfold, todos desmarcados por padrão."""

    def __init__(self, request: HttpRequest, object_id=None, *args, **kwargs):
        super().__init__(request, object_id, *args, **kwargs)
        from shopman.buyman.models import Material

        self.material = Material.objects.filter(pk=object_id).first() if object_id else None
        self.pending = enrichment.pending_fields(self.material) if self.material else {}
        block = enrichment.draft(self.material) if self.material else {}

        status = _status(block, self.pending)
        if status:
            self.fields["status"] = forms.CharField(
                label="O que as fontes disseram",
                required=False,
                disabled=True,
                initial=status,
                widget=UnfoldAdminTextareaWidget(attrs={"rows": min(10, 2 + status.count("\n"))}),
            )

        for name, entry in self.pending.items():
            label = enrichment.FIELD_LABELS[name]
            value = entry["value"]
            help_parts = [f"Fonte: {_source(entry)}, consultada em {_date(entry.get('fetched_at', ''))}."]
            if entry.get("detail"):
                help_parts.append(entry["detail"])
            for alternative in entry.get("alternatives") or []:
                help_parts.append(
                    f"{_source(alternative)} diz outra coisa: "
                    f"{shared.format_value(name, alternative.get('value'))}."
                )
            if name == "allergens" and block.get("allergens_unmapped"):
                help_parts.append(
                    "Fora da lista da casa: " + ", ".join(block["allergens_unmapped"]) + "."
                )
            self.fields[f"accept_{name}"] = forms.BooleanField(
                label=f"{label}: {shared.format_value(name, value)}",
                required=False,
                help_text=" ".join(help_parts),
                widget=UnfoldBooleanSwitchWidget,
            )
            if self.material is not None and enrichment.needs_replace(self.material, name, value):
                current = enrichment.current_value(self.material, name)
                self.fields[f"replace_{name}"] = forms.BooleanField(
                    label=f"Substituir o {label.lower()} preenchido à mão",
                    required=False,
                    help_text=(
                        f"Hoje: {shared.format_value(name, current)}. Sem esta marcação, "
                        "o valor de hoje fica."
                    ),
                    widget=UnfoldBooleanSwitchWidget,
                )

    def clean(self):
        cleaned = super().clean()
        self.chosen = [
            name
            for name in self.pending
            if cleaned.get(f"accept_{name}") or cleaned.get(f"replace_{name}")
        ]
        self.replace = [name for name in self.pending if cleaned.get(f"replace_{name}")]
        if not self.chosen:
            target = next(
                (f"accept_{name}" for name in self.pending),
                "status" if "status" in self.fields else None,
            )
            message = (
                "Marque ao menos um campo para aplicar."
                if self.pending
                else "Não há campo pendente para aplicar."
            )
            if target:
                self.add_error(target, message)
            else:
                raise forms.ValidationError(message)
        return cleaned


def _back_to_change(request: HttpRequest, url: str) -> HttpResponse:
    if request.headers.get("HX-Request"):
        response = HttpResponse(status=204)
        response["HX-Redirect"] = url
        return response
    return HttpResponseRedirect(url)


class MaterialEnrichmentReviewMixin:
    _material_enrichment_review = True

    @action(
        description="Revisar sugestão do GTIN",
        url_path="gtin-suggestion",
        icon="barcode",
        permissions=["change"],
        dialog={
            "title": "Revisar a sugestão do GTIN",
            "description": (
                "Marque só o que confere com a embalagem. Nada é aplicado sem marcação, "
                "e valor preenchido à mão só é trocado com “substituir” marcado. "
                "Alérgeno ausente na fonte significa “não curado”, não “não contém”."
            ),
            "form_class": MaterialEnrichmentReviewForm,
            "form_submit_text": "Aplicar os campos marcados",
        },
    )
    def review_material_enrichment_detail(self, request, form, object_id):
        material = form.material
        url = reverse(
            f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_change",
            args=[object_id],
        )
        if material is None:
            messages.error(request, "Insumo não encontrado.")
            return _back_to_change(request, url)

        result = enrichment.accept_fields(
            material, form.chosen, replace=form.replace, user=request.user
        )
        labels = enrichment.FIELD_LABELS
        if result.applied:
            applied = ", ".join(labels[name] for name in result.applied)
            self.log_change(request, material, f"Sugestão do GTIN aceita: {applied}.")
            messages.success(request, f"Aplicado ao insumo: {applied}.")
        if result.recalculated_products:
            messages.success(
                request,
                "Rótulo recalculado a partir das fichas: "
                + ", ".join(result.recalculated_products)
                + ".",
            )
        for name, current in result.conflicts.items():
            messages.warning(
                request,
                f"{labels[name]} não mudou: já tinha “{shared.format_value(name, current)}”, "
                "e substituir não foi marcado.",
            )
        for name, reason in result.refused.items():
            messages.error(request, f"{labels[name]} não foi aplicado: {reason}")
        return _back_to_change(request, url)


def install_material_enrichment_review() -> None:
    """Compõe a ação sobre o MaterialAdmin já registrado. Idempotente."""
    from shopman.buyman.models import Material

    current = admin.site._registry.get(Material)
    if current is None or getattr(current, "_material_enrichment_review", False):
        return
    base = type(current)

    class MaterialEnrichmentAdmin(MaterialEnrichmentReviewMixin, base):
        actions_detail = [*(base.actions_detail or ()), "review_material_enrichment_detail"]

    MaterialEnrichmentAdmin.__name__ = base.__name__
    MaterialEnrichmentAdmin.__qualname__ = base.__qualname__
    admin.site.unregister(Material)
    admin.site.register(Material, MaterialEnrichmentAdmin)
