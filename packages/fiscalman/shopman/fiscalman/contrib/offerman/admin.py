"""Per-product fiscal segment for Offerman's Product admin.

Extends Offerman's ``ProductAdminForm``/``ProductAdmin`` (which already manage
nutrition and metadata) with the fiscal classification — ``profile`` + ``NCM`` +
``CEST`` + origem — edited as proper form fields and stored in
``Product.metadata['fiscal']``. CFOP/CSOSN/PIS-COFINS are NOT edited here: they come
from the named profile at emission time (see ``shopman.fiscalman.classification``).
"""

from __future__ import annotations

from django import forms
from shopman.fiscalman.classification import (
    DEFAULT_ORIGIN,
    DEFAULT_PROFILE_KEY,
    FISCAL_PROFILES,
    ORIGINS,
    ProductFiscalClassification,
    from_metadata,
    to_metadata_fiscal,
)
from shopman.offerman.contrib.admin_unfold.admin import ProductAdmin
from shopman.offerman.contrib.admin_unfold.nutrition_form import ProductAdminForm
from unfold.widgets import UnfoldAdminSelectWidget, UnfoldAdminTextInputWidget

FISCAL_FORM_FIELDS = ("fiscal_profile", "fiscal_ncm", "fiscal_cest", "fiscal_origin")


class FiscalProductAdminForm(ProductAdminForm):
    """Adds fiscal classification fields, backed by ``metadata['fiscal']``."""

    fiscal_profile = forms.ChoiceField(
        label="Perfil fiscal",
        required=False,
        widget=UnfoldAdminSelectWidget,
        choices=[(key, profile.name) for key, profile in FISCAL_PROFILES.items()],
        help_text=(
            "Define a tributação: sem substituição tributária (5102/102) ou com ST (5405/500)."
        ),
    )
    fiscal_ncm = forms.CharField(
        label="NCM",
        required=False,
        widget=UnfoldAdminTextInputWidget,
        max_length=8,
        help_text="8 dígitos. Ex.: 19059090 (pães, folhados, doces), 19059010 (pão de forma).",
    )
    fiscal_cest = forms.CharField(
        label="CEST",
        required=False,
        widget=UnfoldAdminTextInputWidget,
        max_length=7,
        help_text=(
            "7 dígitos. Identificação da mercadoria no Conv. ICMS 142/2018 — vai na nota "
            "sempre que o item estiver listado; a tributação vem do perfil fiscal."
        ),
    )
    fiscal_origin = forms.ChoiceField(
        label="Origem da mercadoria",
        required=False,
        widget=UnfoldAdminSelectWidget,
        choices=list(ORIGINS.items()),
        help_text="0 = nacional. Importado comprado de distribuidor no Brasil = 2.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            current = from_metadata(self.instance.metadata or {})
            self.fields["fiscal_profile"].initial = current.profile
            self.fields["fiscal_ncm"].initial = current.ncm
            self.fields["fiscal_cest"].initial = current.cest
            self.fields["fiscal_origin"].initial = current.origin
        else:
            self.fields["fiscal_profile"].initial = DEFAULT_PROFILE_KEY
            self.fields["fiscal_origin"].initial = DEFAULT_ORIGIN

    def clean(self):
        cleaned = super().clean()

        classification = ProductFiscalClassification(
            profile=cleaned.get("fiscal_profile") or DEFAULT_PROFILE_KEY,
            ncm=(cleaned.get("fiscal_ncm") or "").strip(),
            cest=(cleaned.get("fiscal_cest") or "").strip(),
            origin=cleaned.get("fiscal_origin") or DEFAULT_ORIGIN,
        )

        # Validate only once any fiscal data is present — a product may be saved
        # without classification yet (pre-go-live). This form is one door among
        # many (seed, catalog sync, scripts write Products by ORM), so it is not
        # where completeness is enforced: the orchestrator's publication gate
        # (``shopman/shop/handlers/fiscal_gate.py``, off by default until the
        # go-live) refuses to publish an unclassified sellable on every door, and
        # the adapter still refuses an item without NCM at issue time
        # (``shop/adapters/fiscal_focusnfe._map_item``).
        if classification.ncm or classification.cest:
            for message in classification.errors():
                self.add_error(None, message)

        metadata = dict(cleaned.get("metadata") or {})
        if classification.ncm or classification.cest:
            metadata["fiscal"] = to_metadata_fiscal(classification)
        cleaned["metadata"] = metadata
        if self.instance is not None:
            self.instance.metadata = metadata
        return cleaned


class FiscalProductAdmin(ProductAdmin):
    """Offerman's ProductAdmin + a "Fiscal" fieldset."""

    form = FiscalProductAdminForm

    def get_fieldsets(self, request, obj=None):
        fieldsets = list(super().get_fieldsets(request, obj))
        fiscal_fieldset = (
            "Fiscal (NFC-e)",
            {
                "fields": FISCAL_FORM_FIELDS,
                "classes": ("tab",),
                "description": (
                    "Classificação fiscal por produto. CFOP/CSOSN/PIS-COFINS vêm do "
                    "perfil; NCM, CEST e origem são por produto."
                ),
            },
        )
        # Insert just before the trailing "Metadados" fieldset when present.
        insert_at = max(len(fieldsets) - 1, 0)
        fieldsets.insert(insert_at, fiscal_fieldset)
        return fieldsets
