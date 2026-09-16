from __future__ import annotations

import json
from base64 import b64encode
from unittest.mock import patch

import pytest
from django.test import override_settings

# Bloco fiscal como o Fiscalman entrega (``resolve_fiscal_item``): o adapter não
# adivinha campo tributário nenhum — ausente, ele recusa nominalmente.
FISCAL_OWN_PRODUCTION = {
    "ncm": "19059090",
    "cfop": "5102",
    "icms_origem": "0",
    "icms_situacao_tributaria": "102",
    "pis_situacao_tributaria": "99",
    "cofins_situacao_tributaria": "99",
}

def _settings():
    return {
        "environment": "homologacao",
        "token": "focus-token",
        "cnpj_emitente": "12.345.678/0001-99",
        "serie_nfce": "1",
        "timeout": 10,
    }


def test_focus_nfe_backend_is_the_only_canonical_class_name():
    from shopman.shop.adapters import fiscal_focusnfe

    assert hasattr(fiscal_focusnfe, "FocusNFeBackend")
    assert not hasattr(fiscal_focusnfe, "FocusNFCeBackend")
    assert fiscal_focusnfe.__all__ == ["FocusNFeBackend"]


@override_settings(SHOPMAN_FOCUS_NFE=_settings())
def test_focus_nfe_emit_maps_nfce_payload_to_homologation_endpoint():
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    captured = {}

    def fake_request(method, path, payload, config):
        captured.update(method=method, path=path, payload=payload, config=config)
        return {
            "status": "autorizado",
            "ref": "ORD-1",
            "numero": "123",
            "serie": "1",
            "protocolo": "141240000000000",
            "chave_nfe": "NFC-E-KEY",
            "caminho_danfe": "https://example.test/danfe.pdf",
            "qrcode_url": "https://example.test/qrcode",
        }

    with patch("shopman.shop.adapters.fiscal_focusnfe._request", side_effect=fake_request):
        result = FocusNFeBackend().emit(
            reference="ORD-1",
            items=[{
                "sku": "SKU-1",
                "name": "Pao",
                "qty": "2",
                "unit": "un",
                "unit_price_q": 500,
                "total_q": 1000,
                "fiscal": FISCAL_OWN_PRODUCTION,
            }],
            customer={"name": "Ana", "tax_id": "123.456.789-09"},
            payment={"method": "pix", "amount_q": 1000},
        )

    assert result.success is True
    assert result.access_key == "NFC-E-KEY"
    assert result.protocol_number == "141240000000000"
    assert captured["method"] == "POST"
    assert captured["path"] == "/v2/nfce?ref=ORD-1&completa=1"
    assert captured["payload"]["cnpj_emitente"] == "12345678000199"
    assert captured["payload"]["local_destino"] == "1"
    assert captured["payload"]["valor_produtos"] == "10.00"
    assert captured["payload"]["valor_total"] == "10.00"
    assert captured["payload"]["cpf_destinatario"] == "12345678909"
    assert captured["payload"]["indicador_inscricao_estadual_destinatario"] == "9"
    assert captured["payload"]["items"][0]["codigo_ncm"] == "19059090"
    assert captured["payload"]["formas_pagamento"] == [{
        "forma_pagamento": "17",
        "valor_pagamento": "10.00",
    }]


@override_settings(SHOPMAN_FOCUS_NFE=_settings())
def test_focus_nfe_emit_fails_before_http_when_product_has_no_ncm():
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    with patch("shopman.shop.adapters.fiscal_focusnfe._request") as request:
        result = FocusNFeBackend().emit(
            reference="ORD-2",
            items=[{
                "sku": "SKU-2",
                "name": "Produto sem fiscal",
                "qty": "1",
                "unit_price_q": 1000,
                "total_q": 1000,
                "fiscal": {},
            }],
            customer={},
            payment={"method": "cash", "amount_q": 1000},
        )

    assert result.success is False
    assert result.error_code == "focus_nfe_invalid_payload"
    assert "sem NCM" in result.error_message
    request.assert_not_called()


@override_settings(
    SHOPMAN_FOCUS_NFE={
        "environment": "homologacao",
        "token": "focus-token",
        "cnpj_emitente": "",
        "serie_nfce": "1",
        "timeout": 10,
    }
)
def test_focus_nfe_emit_uses_shop_document_as_emitente_fallback():
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    captured = {}

    def fake_request(method, path, payload, config):
        captured.update(method=method, path=path, payload=payload, config=config)
        return {
            "status": "autorizado",
            "ref": "ORD-3",
            "chave_nfe": "NFC-E-KEY",
        }

    with (
        patch("shopman.shop.adapters.fiscal_focusnfe._shop_document", return_value="12.345.678/0001-99"),
        patch("shopman.shop.adapters.fiscal_focusnfe._request", side_effect=fake_request),
    ):
        result = FocusNFeBackend().emit(
            reference="ORD-3",
            items=[{
                "sku": "SKU-3",
                "name": "Pao",
                "qty": "1",
                "unit_price_q": 1000,
                "total_q": 1000,
                "fiscal": FISCAL_OWN_PRODUCTION,
            }],
            customer={},
            payment={"method": "cash", "amount_q": 1000},
        )

    assert result.success is True
    assert captured["payload"]["cnpj_emitente"] == "12345678000199"


@override_settings(SHOPMAN_FOCUS_NFE=_settings())
def test_focus_nfe_query_asks_for_complete_response():
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    captured = {}

    def fake_request(method, path, payload, config):
        captured.update(method=method, path=path, payload=payload, config=config)
        return {
            "status": "autorizado",
            "ref": "ORD-1",
            "chave_nfe": "NFC-E-KEY",
        }

    with patch("shopman.shop.adapters.fiscal_focusnfe._request", side_effect=fake_request):
        result = FocusNFeBackend().query_status(reference="ORD-1")

    assert result.success is True
    assert captured["method"] == "GET"
    assert captured["path"] == "/v2/nfce/ORD-1?completa=1"
    assert captured["payload"] is None


def test_focus_nfe_request_uses_homologation_basic_auth_and_json():
    from shopman.shop.adapters import fiscal_focusnfe

    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"status":"autorizado"}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["authorization"] = request.get_header("Authorization")
        captured["content_type"] = request.get_header("Content-type")
        captured["accept"] = request.get_header("Accept")
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    with patch("shopman.shop.adapters.fiscal_focusnfe.urlopen", side_effect=fake_urlopen):
        response = fiscal_focusnfe._request(
            "POST",
            "/v2/nfce?ref=ORD-1&completa=1",
            {"cnpj_emitente": "12345678000199"},
            _settings(),
        )

    expected_auth = b64encode(b"focus-token:").decode("ascii")
    assert response == {"status": "autorizado"}
    assert captured["url"] == "https://homologacao.focusnfe.com.br/v2/nfce?ref=ORD-1&completa=1"
    assert captured["method"] == "POST"
    assert captured["authorization"] == f"Basic {expected_auth}"
    assert captured["content_type"] == "application/json"
    assert captured["accept"] == "application/json"
    assert captured["payload"] == {"cnpj_emitente": "12345678000199"}
    assert captured["timeout"] == 10


@override_settings(SHOPMAN_FOCUS_NFE=_settings())
def test_focus_nfe_fee_without_delivery_fact_is_rejected():
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    captured = {}

    def fake_request(method, path, payload, config):
        captured.update(payload=payload)
        return {"status": "autorizado", "chave_nfe": "KEY"}

    with patch("shopman.shop.adapters.fiscal_focusnfe._request", side_effect=fake_request):
        result = FocusNFeBackend().emit(
            reference="ORD-2",
            items=[
                {
                    "sku": "SKU-1", "name": "Pao", "qty": "2", "unit": "un",
                    "unit_price_q": 500, "total_q": 1000,
                    "fiscal": FISCAL_OWN_PRODUCTION,
                },
                {
                    # Taxa de entrega do POS/web: sem NCM, não pode virar item.
                    "sku": "__DELIVERY_FEE__", "name": "Taxa de entrega", "qty": "1",
                    "unit": "UN", "unit_price_q": 600, "total_q": 600,
                    "meta": {"type": "delivery_fee"}, "fiscal": {},
                },
            ],
            customer={},
            payment={"method": "pix", "amount_q": 1600},
        )

    assert result.success is False
    assert result.error_code == "focus_nfe_invalid_payload"
    assert "taxa de entrega" in result.error_message
    assert captured == {}  # não reduz pagamento nem envia nota presencial


@override_settings(SHOPMAN_FOCUS_NFE=_settings())
def test_focus_nfe_rejects_invalid_cpf_before_http():
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    with patch("shopman.shop.adapters.fiscal_focusnfe._request") as request:
        result = FocusNFeBackend().emit(
            reference="ORD-3",
            items=[{
                "sku": "SKU-1", "name": "Pao", "qty": "1", "unit": "un",
                "unit_price_q": 500, "total_q": 500,
                "fiscal": FISCAL_OWN_PRODUCTION,
            }],
            customer={"name": "Ana", "tax_id": "123.456.789-00"},  # dígito errado
            payment={"method": "cash", "amount_q": 500},
        )

    assert result.success is False
    assert result.error_code == "focus_nfe_invalid_payload"
    assert "CPF/CNPJ" in (result.error_message or "")
    request.assert_not_called()


def test_document_result_key_without_authorized_status_is_not_success():
    from shopman.shop.adapters.fiscal_focusnfe import _document_result

    processing = _document_result(
        {"status": "processando_autorizacao", "chave_nfe": "KEY"}, None
    )
    assert processing.success is False
    assert processing.error_code == "focus_nfe_processing"

    rejected = _document_result({"status": "erro_autorizacao", "chave_nfe": "KEY"}, None)
    assert rejected.success is False


@override_settings(SHOPMAN_FOCUS_NFE=_settings())
def test_focus_nfe_home_delivery_freight_with_identified_recipient():
    """Com CPF + endereço: entrega a domicílio (indPres=4) com frete documentado.

    Receita do MOC validada em homologação SEFAZ-PR (nota autorizada
    2026-07-02): vFrete no item (I15) e no total (W08), modFrete=3 e grupo
    transportador = emitente. Sem identificação, a emissão deve ser recusada.
    """
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    captured = {}

    def fake_request(method, path, payload, config):
        captured.update(payload=payload)
        return {"status": "autorizado", "chave_nfe": "KEY"}

    with patch("shopman.shop.adapters.fiscal_focusnfe._request", side_effect=fake_request):
        result = FocusNFeBackend().emit(
            reference="ORD-DOM-1",
            items=[
                {"sku": "SKU-1", "name": "Pao", "qty": "2", "unit": "un",
                 "unit_price_q": 500, "total_q": 1000,
                 "fiscal": FISCAL_OWN_PRODUCTION},
                {"sku": "__DELIVERY_FEE__", "name": "Taxa de entrega", "qty": "1",
                 "unit": "UN", "unit_price_q": 600, "total_q": 600,
                 "meta": {"type": "delivery_fee"}, "fiscal": {}},
            ],
            customer={"name": "Ana", "tax_id": "529.982.247-25"},
            payment={"method": "pix", "amount_q": 1600},
            delivery={"address": {"route": "Rua X", "street_number": "1",
                                  "neighborhood": "Centro", "city": "Londrina",
                                  "state_code": "PR", "postal_code": "86010-000"}},
        )

    assert result.success is True
    payload = captured["payload"]
    assert payload["presenca_comprador"] == "4"
    assert payload["modalidade_frete"] == "3"
    assert payload["valor_frete"] == "6.00"
    assert payload["valor_total"] == "16.00"
    assert payload["items"][0]["valor_frete"] == "6.00"
    assert payload["cnpj_transportador"] == "12345678000199"
    assert payload["cep_destinatario"] == "86010000"
    assert payload["formas_pagamento"] == [{"forma_pagamento": "17", "valor_pagamento": "16.00"}]


def test_map_item_vuncom_times_qty_equals_vprod_after_distributed_discount():
    """R1 (DISCOUNT-AUDIT): um desconto rateado deixa unit_price_q × qty ≠
    line_total_q. A NFC-e deve derivar vUnCom de vProd/qCom (alta precisão) para
    que vUnCom × qCom == vProd — senão a SEFAZ rejeita."""
    from decimal import ROUND_HALF_UP, Decimal

    from shopman.shop.adapters.fiscal_focusnfe import _map_item

    # qty=2, total cobrado 999 (após desconto), unit_price_q floor = 499 → 499×2=998≠999.
    item = {
        "sku": "PAO", "name": "Pão", "qty": 2, "unit_price_q": 499, "total_q": 999,
        "fiscal": FISCAL_OWN_PRODUCTION,
    }
    mapped = _map_item(1, item, {})
    vuncom = Decimal(mapped["valor_unitario_comercial"])
    qcom = Decimal(mapped["quantidade_comercial"])
    vprod = Decimal(mapped["valor_bruto"])
    assert vprod == Decimal("9.99")
    assert (vuncom * qcom).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == vprod


def test_map_item_keeps_two_decimals_when_evenly_divisible():
    """Caminho comum (sem resto): vUnCom mantém 2 casas."""
    from shopman.shop.adapters.fiscal_focusnfe import _map_item

    item = {
        "sku": "PAO", "name": "Pão", "qty": 2, "unit_price_q": 500, "total_q": 1000,
        "fiscal": FISCAL_OWN_PRODUCTION,
    }
    mapped = _map_item(1, item, {})
    assert mapped["valor_unitario_comercial"] == "5.00"
    assert mapped["valor_bruto"] == "10.00"


# ── o adapter não tem segunda opinião fiscal ─────────────────────────────────
#
# Regressão do audit do Fiscalman (F6): `_map_item` carregava defaults próprios
# para bloco fiscal incompleto — CSOSN "102" e PIS/COFINS "07", este último
# DIVERGINDO do "99" que a parametrização do contador manda (e que o perfil
# emite). Política fiscal paralela dormindo no adapter, e errada onde diverge.
# Mesma doutrina do NCM: campo tributário ausente FALHA, não adivinha.


@override_settings(SHOPMAN_FOCUS_NFE=_settings())
@pytest.mark.parametrize(
    ("missing_key", "expected"),
    [
        ("icms_situacao_tributaria", "sem CSOSN"),
        ("pis_situacao_tributaria", "sem CST do PIS"),
        ("cofins_situacao_tributaria", "sem CST da COFINS"),
        ("icms_origem", "sem origem do ICMS"),
    ],
)
def test_focus_nfe_refuses_item_missing_a_tax_field_by_name(missing_key, expected):
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    fiscal = {k: v for k, v in FISCAL_OWN_PRODUCTION.items() if k != missing_key}

    with patch("shopman.shop.adapters.fiscal_focusnfe._request") as request:
        result = FocusNFeBackend().emit(
            reference="ORD-TAX",
            items=[{
                "sku": "PAO", "name": "Pao", "qty": "1",
                "unit_price_q": 1000, "total_q": 1000, "fiscal": fiscal,
            }],
            customer={},
            payment={"method": "cash", "amount_q": 1000},
        )

    assert result.success is False
    assert result.error_code == "focus_nfe_invalid_payload"
    assert expected in result.error_message
    assert "PAO" in result.error_message
    request.assert_not_called()


@override_settings(SHOPMAN_FOCUS_NFE=_settings())
def test_focus_nfe_emits_the_profile_pis_cofins_cst_and_never_07():
    from shopman.shop.adapters.fiscal_focusnfe import _map_item

    mapped = _map_item(1, {
        "sku": "PAO", "name": "Pao", "qty": "1",
        "unit_price_q": 1000, "total_q": 1000, "fiscal": FISCAL_OWN_PRODUCTION,
    }, _settings())

    assert mapped["pis_situacao_tributaria"] == "99"
    assert mapped["cofins_situacao_tributaria"] == "99"
    assert mapped["icms_situacao_tributaria"] == "102"


_DELIVERY_ADDRESS = {"route": "Rua X", "street_number": "1", "neighborhood": "Jardim Real",
                     "city": "Londrina", "state_code": "PR", "postal_code": "86010-000"}


def _delivery_input(fee_q=0):
    items = [{"sku": "SKU-1", "name": "Pao", "qty": "2", "unit": "un",
              "unit_price_q": 500, "total_q": 1000, "fiscal": FISCAL_OWN_PRODUCTION}]
    if fee_q:
        items.append({"sku": "__DELIVERY_FEE__", "name": "Taxa de entrega", "qty": "1", "unit": "UN",
                      "unit_price_q": fee_q, "total_q": fee_q, "meta": {"type": "delivery_fee"}, "fiscal": {}})
    return {"reference": "ORD-DELIVERY", "items": items, "customer": {"name": "Ana", "tax_id": "52998224725"},
            "payment": {"method": "pix", "amount_q": 1000 + fee_q}, "delivery": {"address": dict(_DELIVERY_ADDRESS)}}


@override_settings(SHOPMAN_FOCUS_NFE=_settings())
@pytest.mark.parametrize("fee_q", [0, 600])
def test_free_and_paid_delivery_keep_the_actual_fiscal_operation(fee_q):
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    with patch("shopman.shop.adapters.fiscal_focusnfe._request", return_value={"status": "autorizado", "chave_nfe": "KEY"}) as send:
        result = FocusNFeBackend().emit(**_delivery_input(fee_q))
    assert result.success
    payload = send.call_args.args[2]
    assert payload["presenca_comprador"] == "4"
    assert payload["modalidade_frete"] == "3"
    assert payload["valor_frete"] == ("6.00" if fee_q else "0.00")
    assert payload["valor_total"] == ("16.00" if fee_q else "10.00")
    assert payload["bairro_destinatario"] == "Jardim Real"
    assert payload["formas_pagamento"][0]["valor_pagamento"] == payload["valor_total"]


@override_settings(SHOPMAN_FOCUS_NFE=_settings())
@pytest.mark.parametrize("missing", ["tax_id", "route", "street_number", "neighborhood", "city", "state_code", "postal_code"])
@pytest.mark.parametrize("fee_q", [0, 600])
def test_incomplete_delivery_fails_before_http_instead_of_inventing_data(missing, fee_q):
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    request = _delivery_input(fee_q)
    if missing == "tax_id":
        request["customer"].pop(missing)
    else:
        request["delivery"]["address"].pop(missing)
    with patch("shopman.shop.adapters.fiscal_focusnfe._request") as send:
        result = FocusNFeBackend().emit(**request)
    assert not result.success
    assert result.error_code == "focus_nfe_invalid_payload"
    assert "Entrega a domicílio: confira" in result.error_message
    send.assert_not_called()
    assert request["payment"]["amount_q"] == 1000 + fee_q


@override_settings(SHOPMAN_FOCUS_NFE=_settings())
def test_immediate_pickup_remains_presential_and_accepts_anonymous_customer():
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    request = _delivery_input()
    request.update(delivery=None, customer={})
    with patch("shopman.shop.adapters.fiscal_focusnfe._request", return_value={"status": "autorizado", "chave_nfe": "KEY"}) as send:
        assert FocusNFeBackend().emit(**request).success
    payload = send.call_args.args[2]
    assert payload["presenca_comprador"] == "1"
    assert payload["modalidade_frete"] == "9"
    assert "logradouro_destinatario" not in payload
    assert "valor_frete" not in payload


@override_settings(SHOPMAN_FOCUS_NFE=_settings())
@pytest.mark.parametrize("field,value", [("state_code", "XX"), ("postal_code", "123"), ("street_number", " ")])
def test_invalid_delivery_address_values_are_not_guessed(field, value):
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    request = _delivery_input()
    request["delivery"]["address"][field] = value
    with patch("shopman.shop.adapters.fiscal_focusnfe._request") as send:
        result = FocusNFeBackend().emit(**request)
    assert not result.success
    assert result.error_code == "focus_nfe_invalid_payload"
    send.assert_not_called()
