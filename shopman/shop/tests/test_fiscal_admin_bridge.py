"""Fiscalman ↔ Offerman admin bridge.

The bridge re-registers Offerman's ``Product`` admin with a subclass that adds
the per-product fiscal segment (profile + NCM + CEST), backed by
``Product.metadata['fiscal']``.
"""

import pytest
from django.contrib import admin
from shopman.fiscalman.contrib.offerman.admin import (
    FiscalProductAdmin,
    FiscalProductAdminForm,
)
from shopman.offerman.models import Product


def test_product_admin_is_the_fiscal_bridge():
    assert isinstance(admin.site._registry[Product], FiscalProductAdmin)


def test_fiscal_fieldset_present():
    instance = admin.site._registry[Product]
    titles = [name for name, _ in instance.get_fieldsets(request=None)]
    assert "Fiscal (NFC-e)" in titles


@pytest.mark.django_db
def test_form_initial_reads_metadata():
    product = Product.objects.create(
        sku="PAO-BRIDGE", name="Pão", base_price_q=500,
        metadata={"fiscal": {"profile": "own_production", "ncm": "19059010"}},
    )
    form = FiscalProductAdminForm(instance=product)
    assert form.fields["fiscal_profile"].initial == "own_production"
    assert form.fields["fiscal_ncm"].initial == "19059010"
    assert form.fields["fiscal_cest"].initial == ""


def test_form_rejects_cest_on_own_production():
    cleaned = {"fiscal_profile": "own_production", "fiscal_ncm": "19059010", "fiscal_cest": "0300700"}
    classification_errors = _classification_errors(cleaned)
    assert any("CEST não se aplica" in e for e in classification_errors)


def _classification_errors(cleaned):
    from shopman.fiscalman.classification import ProductFiscalClassification

    return ProductFiscalClassification(
        profile=cleaned["fiscal_profile"],
        ncm=cleaned["fiscal_ncm"],
        cest=cleaned["fiscal_cest"],
    ).errors()


def test_every_cfop_voice_says_the_same_thing():
    """CFOP da fabricação própria = 5102, decisão do dono em 2026-08-19.

    O código já respondeu essa pergunta de três jeitos ao mesmo tempo: o
    dataclass emitia 5102, o help_text ensinava "5101/102" ao operador e o
    comentário do `FiscalProfile` exemplificava 5101. Este teste é o que impede
    a contradição de voltar — divergiu uma das vozes, quebra aqui.

    Razão e o que fazer se o contador discordar:
    docs/reference/fiscal-cfop-5101-vs-5102.md.
    """
    from django.conf import settings
    from shopman.fiscalman.classification import OWN_PRODUCTION

    decided_internal, decided_interstate = "5102", "6102"

    assert (OWN_PRODUCTION.cfop_internal, OWN_PRODUCTION.cfop_interstate) == (
        decided_internal,
        decided_interstate,
    )

    help_text = str(FiscalProductAdminForm.base_fields["fiscal_profile"].help_text)
    assert decided_internal in help_text
    assert "5101" not in help_text

    assert settings.SHOPMAN_FOCUS_NFE["default_cfop_nfce"] == decided_internal
