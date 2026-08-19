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
        assert set(FISCAL_PROFILES) == {"own_production", "resale"}

    def test_own_production_is_default(self):
        assert DEFAULT_PROFILE_KEY == "own_production"

    def test_own_production_codes(self):
        p = FISCAL_PROFILES["own_production"]
        assert (p.csosn, p.cfop_internal, p.cfop_interstate, p.requires_cest) == (
            "102",
            "5102",
            "6102",
            False,
        )

    def test_resale_codes_require_cest(self):
        p = FISCAL_PROFILES["resale"]
        assert (p.csosn, p.cfop_internal, p.cfop_interstate, p.requires_cest) == (
            "500",
            "5405",
            "6405",
            True,
        )


class TestValidation:
    def test_valid_own_production(self):
        c = ProductFiscalClassification(profile="own_production", ncm="19059010")
        assert c.is_valid
        assert c.errors() == []

    def test_ncm_must_be_8_digits(self):
        assert "NCM deve ter 8 dígitos." in ProductFiscalClassification(ncm="1905").errors()
        assert "NCM deve ter 8 dígitos." in ProductFiscalClassification(ncm="abcd1234").errors()

    def test_resale_requires_cest(self):
        c = ProductFiscalClassification(profile="resale", ncm="22021000")
        assert not c.is_valid
        assert any("CEST" in e for e in c.errors())

    def test_resale_with_valid_cest(self):
        c = ProductFiscalClassification(profile="resale", ncm="22021000", cest="0300700")
        assert c.is_valid

    def test_own_production_rejects_cest(self):
        c = ProductFiscalClassification(profile="own_production", ncm="19059010", cest="0300700")
        assert not c.is_valid
        assert any("CEST não se aplica" in e for e in c.errors())

    def test_unknown_profile(self):
        assert ProductFiscalClassification(profile="bogus", ncm="19059010").errors() == [
            "Perfil fiscal desconhecido: 'bogus'."
        ]


class TestResolveFiscalItem:
    def test_own_production_intrastate(self):
        c = ProductFiscalClassification(profile="own_production", ncm="19059010")
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

    def test_own_production_interstate_uses_6102(self):
        c = ProductFiscalClassification(profile="own_production", ncm="19059010")
        assert resolve_fiscal_item(c, interstate=True)["cfop"] == "6102"

    def test_resale_intrastate_includes_cest(self):
        c = ProductFiscalClassification(profile="resale", ncm="22021000", cest="0300700")
        item = resolve_fiscal_item(c)
        assert item["cfop"] == "5405"
        assert item["icms_situacao_tributaria"] == "500"
        assert item["cest"] == "0300700"

    def test_resale_interstate_uses_6405(self):
        c = ProductFiscalClassification(profile="resale", ncm="22021000", cest="0300700")
        assert resolve_fiscal_item(c, interstate=True)["cfop"] == "6405"


class TestMetadataRoundTrip:
    def test_from_metadata_defaults(self):
        c = from_metadata(None)
        assert c.profile == "own_production"
        assert c.ncm == ""

    def test_from_metadata_reads_legacy_codigo_ncm(self):
        c = from_metadata({"fiscal": {"codigo_ncm": "19059090", "unidade_comercial": "UN"}})
        assert c.ncm == "19059090"
        assert c.unit == "UN"

    def test_round_trip_own_production(self):
        c = ProductFiscalClassification(profile="own_production", ncm="19059010")
        assert from_metadata({"fiscal": to_metadata_fiscal(c)}) == c

    def test_round_trip_resale_with_cest(self):
        c = ProductFiscalClassification(profile="resale", ncm="22021000", cest="0300700")
        assert from_metadata({"fiscal": to_metadata_fiscal(c)}) == c

    def test_to_metadata_omits_empty_cest(self):
        c = ProductFiscalClassification(profile="own_production", ncm="19059010")
        assert "cest" not in to_metadata_fiscal(c)


class TestValidateForEmission:
    """A pergunta 'este produto pode virar item de nota?' com um dono só."""

    def test_complete_own_production_has_no_errors(self):
        metadata = {"fiscal": {"profile": "own_production", "ncm": "19059010"}}
        assert validate_for_emission(metadata) == []

    def test_unclassified_product_says_so_instead_of_blaming_the_ncm(self):
        # "ninguém preencheu" é diagnóstico diferente de "preencheram torto" —
        # quem audita o catálogo precisa dos dois separados.
        for metadata in (None, {}, {"fiscal": {}}):
            errors = validate_for_emission(metadata)
            assert len(errors) == 1
            assert "Sem classificação fiscal" in errors[0]

    def test_bad_ncm_reports_the_ncm(self):
        errors = validate_for_emission({"fiscal": {"profile": "own_production", "ncm": "1905"}})
        assert errors == ["NCM deve ter 8 dígitos."]

    def test_resale_without_cest_is_incomplete(self):
        errors = validate_for_emission({"fiscal": {"profile": "resale", "ncm": "22021000"}})
        assert any("CEST" in e for e in errors)

    def test_reads_legacy_key_like_the_rest_of_the_schema(self):
        assert validate_for_emission({"fiscal": {"codigo_ncm": "19059010"}}) == []
