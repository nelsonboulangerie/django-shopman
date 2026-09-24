"""Tests for the fiscal classification domain (pure Python, no DB)."""

from shopman.fiscalman.classification import (
    DEFAULT_PROFILE_KEY,
    FISCAL_PROFILES,
    ProductFiscalClassification,
    from_metadata,
    resolve_fiscal_item,
    to_metadata_fiscal,
    validate_for_emission,
)


class TestProfiles:
    def test_two_named_profiles_exist(self):
        """O perfil responde só à tributação: sem ST ou com ST."""
        assert set(FISCAL_PROFILES) == {"standard", "tax_substitution"}

    def test_standard_is_default(self):
        assert DEFAULT_PROFILE_KEY == "standard"

    def test_standard_codes(self):
        p = FISCAL_PROFILES["standard"]
        assert (p.csosn, p.cfop_internal, p.cfop_interstate, p.requires_cest) == (
            "102",
            "5102",
            "6102",
            False,
        )

    def test_tax_substitution_codes_require_cest(self):
        p = FISCAL_PROFILES["tax_substitution"]
        assert (p.csosn, p.cfop_internal, p.cfop_interstate, p.requires_cest) == (
            "500",
            "5405",
            "6405",
            True,
        )


class TestValidation:
    def test_valid_standard(self):
        c = ProductFiscalClassification(profile="standard", ncm="19059010")
        assert c.is_valid
        assert c.errors() == []

    def test_ncm_must_be_8_digits(self):
        assert "NCM deve ter 8 dígitos." in ProductFiscalClassification(ncm="1905").errors()
        assert "NCM deve ter 8 dígitos." in ProductFiscalClassification(ncm="abcd1234").errors()

    def test_tax_substitution_requires_cest(self):
        c = ProductFiscalClassification(profile="tax_substitution", ncm="22021000")
        assert not c.is_valid
        assert any("CEST" in e for e in c.errors())

    def test_tax_substitution_with_valid_cest(self):
        c = ProductFiscalClassification(profile="tax_substitution", ncm="22021000", cest="0300700")
        assert c.is_valid

    def test_cest_is_accepted_without_st(self):
        """O CEST identifica a mercadoria; não é privilégio do perfil com ST."""
        c = ProductFiscalClassification(profile="standard", ncm="19059090", cest="1706200")
        assert c.is_valid
        assert resolve_fiscal_item(c)["cest"] == "1706200"

    def test_cest_incompatible_with_ncm_is_a_warning_not_an_error(self):
        c = ProductFiscalClassification(profile="standard", ncm="21039099", cest="1709200")
        assert c.is_valid
        assert any("2005" in w for w in c.warnings())

    def test_cest_outside_the_house_table_asks_to_check(self):
        c = ProductFiscalClassification(profile="standard", ncm="19059090", cest="1799999")
        assert c.is_valid
        assert any("confira no Anexo" in w for w in c.warnings())

    def test_compatible_cest_has_no_warning(self):
        assert ProductFiscalClassification(profile="standard", ncm="04069020", cest="1702400").warnings() == []

    def test_malformed_cest_is_an_error(self):
        c = ProductFiscalClassification(profile="standard", ncm="04069020", cest="17.024.00")
        assert "CEST deve ter 7 dígitos." in c.errors()

    def test_unknown_profile(self):
        assert ProductFiscalClassification(profile="bogus", ncm="19059010").errors() == [
            "Perfil fiscal desconhecido: 'bogus'."
        ]


class TestResolveFiscalItem:
    def test_standard_intrastate(self):
        c = ProductFiscalClassification(profile="standard", ncm="19059010")
        item = resolve_fiscal_item(c)
        assert item == {
            "ncm": "19059010",
            "cfop": "5102",
            "unit": "UN",
            "icms_origem": "0",
            "icms_situacao_tributaria": "102",
            "pis_situacao_tributaria": "99",
            "cofins_situacao_tributaria": "99",
        }

    def test_standard_interstate_uses_6102(self):
        c = ProductFiscalClassification(profile="standard", ncm="19059010")
        assert resolve_fiscal_item(c, interstate=True)["cfop"] == "6102"

    def test_tax_substitution_intrastate_includes_cest(self):
        c = ProductFiscalClassification(profile="tax_substitution", ncm="22021000", cest="0300700")
        item = resolve_fiscal_item(c)
        assert item["cfop"] == "5405"
        assert item["icms_situacao_tributaria"] == "500"
        assert item["cest"] == "0300700"

    def test_tax_substitution_interstate_uses_6405(self):
        c = ProductFiscalClassification(profile="tax_substitution", ncm="22021000", cest="0300700")
        assert resolve_fiscal_item(c, interstate=True)["cfop"] == "6405"


class TestMetadataRoundTrip:
    def test_from_metadata_defaults(self):
        c = from_metadata(None)
        assert c.profile == "standard"
        assert c.ncm == ""

    def test_from_metadata_reads_legacy_codigo_ncm(self):
        c = from_metadata({"fiscal": {"codigo_ncm": "19059090", "unidade_comercial": "UN"}})
        assert c.ncm == "19059090"
        assert c.unit == "UN"

    def test_round_trip_standard(self):
        c = ProductFiscalClassification(profile="standard", ncm="19059010")
        assert from_metadata({"fiscal": to_metadata_fiscal(c)}) == c

    def test_round_trip_tax_substitution_with_cest(self):
        c = ProductFiscalClassification(profile="tax_substitution", ncm="22021000", cest="0300700")
        assert from_metadata({"fiscal": to_metadata_fiscal(c)}) == c

    def test_to_metadata_omits_empty_cest(self):
        c = ProductFiscalClassification(profile="standard", ncm="19059010")
        assert "cest" not in to_metadata_fiscal(c)


class TestValidateForEmission:
    """A pergunta 'este produto pode virar item de nota?' com um dono só."""

    def test_complete_standard_has_no_errors(self):
        metadata = {"fiscal": {"profile": "standard", "ncm": "19059010"}}
        assert validate_for_emission(metadata) == []

    def test_unclassified_product_says_so_instead_of_blaming_the_ncm(self):
        # "ninguém preencheu" é diagnóstico diferente de "preencheram torto" —
        # quem audita o catálogo precisa dos dois separados.
        for metadata in (None, {}, {"fiscal": {}}):
            errors = validate_for_emission(metadata)
            assert len(errors) == 1
            assert "Sem classificação fiscal" in errors[0]

    def test_bad_ncm_reports_the_ncm(self):
        errors = validate_for_emission({"fiscal": {"profile": "standard", "ncm": "1905"}})
        assert errors == ["NCM deve ter 8 dígitos."]

    def test_tax_substitution_without_cest_is_incomplete(self):
        errors = validate_for_emission({"fiscal": {"profile": "tax_substitution", "ncm": "22021000"}})
        assert any("CEST" in e for e in errors)

    def test_reads_legacy_key_like_the_rest_of_the_schema(self):
        assert validate_for_emission({"fiscal": {"codigo_ncm": "19059010"}}) == []
