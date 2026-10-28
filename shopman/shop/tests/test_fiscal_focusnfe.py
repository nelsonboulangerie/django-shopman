from __future__ import annotations

import json
from base64 import b64encode
from unittest.mock import patch

import pytest
from django.test import override_settings

# Bloco fiscal como o Fiscalman entrega (``resolve_fiscal_item``): o adapter não
# adivinha campo tributário nenhum — ausente, ele recusa nominalmente.
FISCAL_STANDARD = {
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
                "fiscal": FISCAL_STANDARD,
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
        "tipo_integracao": "2",
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
                "fiscal": FISCAL_STANDARD,
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
                    "fiscal": FISCAL_STANDARD,
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
                "fiscal": FISCAL_STANDARD,
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
                 "fiscal": FISCAL_STANDARD},
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
    assert payload["formas_pagamento"] == [{"forma_pagamento": "17", "valor_pagamento": "16.00", "tipo_integracao": "2"}]


def test_map_item_vuncom_times_qty_equals_vprod_after_distributed_discount():
    """R1 (DISCOUNT-AUDIT): um desconto rateado deixa unit_price_q × qty ≠
    line_total_q. A NFC-e deve derivar vUnCom de vProd/qCom (alta precisão) para
    que vUnCom × qCom == vProd — senão a SEFAZ rejeita."""
    from decimal import ROUND_HALF_UP, Decimal

    from shopman.shop.adapters.fiscal_focusnfe import _map_item

    # qty=2, total cobrado 999 (após desconto), unit_price_q floor = 499 → 499×2=998≠999.
    item = {
        "sku": "PAO", "name": "Pão", "qty": 2, "unit_price_q": 499, "total_q": 999,
        "fiscal": FISCAL_STANDARD,
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
        "fiscal": FISCAL_STANDARD,
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

    fiscal = {k: v for k, v in FISCAL_STANDARD.items() if k != missing_key}

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
        "unit_price_q": 1000, "total_q": 1000, "fiscal": FISCAL_STANDARD,
    }, _settings())

    assert mapped["pis_situacao_tributaria"] == "99"
    assert mapped["cofins_situacao_tributaria"] == "99"
    assert mapped["icms_situacao_tributaria"] == "102"


@pytest.mark.parametrize(
    ("gtin", "expected"),
    [("3006670000187", "3006670000187"), ("", "SEM GTIN"), (None, "SEM GTIN")],
    ids=["gtin-confiavel", "sem-gtin", "chave-ausente"],
)
def test_map_item_sends_the_gtin_in_both_barcode_fields(gtin, expected):
    """cEAN e cEANTrib levam o mesmo GTIN; sem GTIN, o literal do leiaute 4.0."""
    from shopman.shop.adapters.fiscal_focusnfe import _map_item

    item = {
        "sku": "DAL-FIG-284", "name": "Geleia", "qty": "1",
        "unit_price_q": 3000, "total_q": 3000, "fiscal": FISCAL_STANDARD,
    }
    if gtin is not None:
        item["gtin"] = gtin

    mapped = _map_item(1, item, _settings())

    assert mapped["codigo_barras_comercial"] == expected
    assert mapped["codigo_barras_tributavel"] == expected


_DELIVERY_ADDRESS = {"route": "Rua X", "street_number": "1", "neighborhood": "Jardim Real",
                     "city": "Londrina", "state_code": "PR", "postal_code": "86010-000"}


def _delivery_input(fee_q=0):
    items = [{"sku": "SKU-1", "name": "Pao", "qty": "2", "unit": "un",
              "unit_price_q": 500, "total_q": 1000, "fiscal": FISCAL_STANDARD}]
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


def test_payment_code_conta_na_casa_e_credito_loja_e_link_fica_em_outros():
    """tPag: conta na casa → 05 (crédito loja); link → 99 (crédito ou débito só a
    Stripe sabe depois da captura). Códigos a confirmar com o contador (17/09/2026)."""
    from shopman.shop.adapters.fiscal_focusnfe import _payment_code

    assert _payment_code("account") == "05"
    assert _payment_code("house_account") == "05"
    # Cartão pela Stripe (loja `card` e `link`): o funding da cobrança decide.
    assert _payment_code("link") == "99"
    assert _payment_code("card") == "99"
    assert _payment_code("link", "credit") == "03"
    assert _payment_code("card", "debit") == "04"
    assert _payment_code("card", "prepaid") == "99"
    # O balcão já diz crédito/débito por conta própria; funding não interfere.
    assert _payment_code("credit", "debit") == "03"
    assert _payment_code("pix") == "17"
    assert _payment_code("cash") == "01"


# ── Formas de pagamento (F2 do laudo de 23/10/2026) ─────────────────────────
# Nomes dos campos conferidos em https://campos.focusnfe.com.br/nfe/FormaPagamentoXML.html
# (tipo_integracao, descricao_pagamento) e NotaFiscalXML.html (valor_troco).


def _emit_capturing(payment: dict, total_q: int = 1500) -> dict:
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    captured = {}

    def fake_request(method, path, payload, config):
        captured["payload"] = payload
        return {"status": "autorizado", "chave_nfe": "K"}

    with override_settings(SHOPMAN_FOCUS_NFE=_settings()), patch(
        "shopman.shop.adapters.fiscal_focusnfe._request", side_effect=fake_request
    ):
        result = FocusNFeBackend().emit(
            reference="ORD-PAG",
            items=[{
                "sku": "SKU-1", "name": "Pao", "qty": "1", "unit": "un",
                "unit_price_q": total_q, "total_q": total_q, "fiscal": FISCAL_STANDARD,
            }],
            customer={},
            payment=payment,
        )
    assert result.success is True, result.error_message
    return captured["payload"]


@pytest.mark.parametrize(("method", "funding", "code"), [
    ("credit", None, "03"),
    ("debit", None, "04"),
    ("card", "credit", "03"),
    ("link", "debit", "04"),
])
def test_cartao_credito_e_debito_levam_o_grupo_de_cartao_nao_integrado(method, funding, code):
    """Sem o grupo de cartão a SEFAZ recusa a nota de 03/04 (rejeição 391)."""
    payment = {"method": method, "amount_q": 1500}
    if funding:
        payment["card_funding"] = funding
    payload = _emit_capturing(payment)

    assert payload["formas_pagamento"] == [{
        "forma_pagamento": code,
        "valor_pagamento": "15.00",
        "tipo_integracao": "2",
    }]
    assert "valor_troco" not in payload


def test_pix_da_cobranca_sai_17_com_grupo_de_cartao():
    """A regra YA04-10 (rejeição 391) vale também para Pix: 17 sem o grupo é recusado."""
    payload = _emit_capturing({"method": "pix", "amount_q": 1500})

    assert payload["formas_pagamento"] == [{
        "forma_pagamento": "17",
        "valor_pagamento": "15.00",
        "tipo_integracao": "2",
    }]


def test_pix_atestado_no_balcao_sai_20_estatico_sem_grupo_de_cartao():
    """ "Recebi o Pix" (QR fixo ou chave da loja) não teve cobrança com txid: é 20.

    Sem o grupo ``card``: a SEFAZ recusa o grupo no 20 (rejeição 963, medida em
    homologação em 27/10/2026)."""
    payload = _emit_capturing({
        "method": "mixed",
        "amount_q": 1500,
        "tenders": [
            {"method": "cash", "amount_q": 500},
            {"method": "pix", "amount_q": 1000, "pix_confirmed_by": "ana", "pix_confirmed_at": "2026-10-24T10:00:00-03:00"},
        ],
    })

    assert payload["formas_pagamento"] == [
        {"forma_pagamento": "01", "valor_pagamento": "5.00"},
        {"forma_pagamento": "20", "valor_pagamento": "10.00"},
    ]


def test_pix_numa_venda_mista_sem_atestado_segue_17():
    payload = _emit_capturing({
        "method": "mixed",
        "amount_q": 1500,
        "tenders": [{"method": "cash", "amount_q": 500}, {"method": "pix", "amount_q": 1000}],
    })

    assert payload["formas_pagamento"][1] == {
        "forma_pagamento": "17", "valor_pagamento": "10.00", "tipo_integracao": "2",
    }


@pytest.mark.parametrize(("method", "code"), [
    ("account", "05"),
    ("house_account", "05"),
    ("store_credit", "21"),
])
def test_conta_na_casa_e_crediario_05_e_saldo_na_casa_21(method, code):
    """05 "Cartão da Loja (Private Label)", na forma de crediário: o fiado.
    21 "Crédito em Loja": saldo pago antes ou vale de devolução."""
    payload = _emit_capturing({"method": method, "amount_q": 1500})

    form = payload["formas_pagamento"][0]
    assert form["forma_pagamento"] == code
    assert "tipo_integracao" not in form


@pytest.mark.parametrize(("payment", "description"), [
    ({"method": "external"}, "Pagamento pelo intermediador da venda"),
    ({"method": "card"}, "Cartão sem tipo informado pelo gateway"),
    ({"method": "link", "card_funding": "unknown"}, "Cartão sem tipo informado pelo gateway"),
    ({"method": "card", "card_funding": "prepaid"}, "Cartão pré-pago"),
    ({"method": "voucher_x"}, "Outro meio: voucher_x"),
])
def test_outros_99_sempre_leva_descricao_do_meio(payment, description):
    """O leiaute exige xPag quando tPag = 99 (todo pedido do iFood cai aqui)."""
    payload = _emit_capturing({**payment, "amount_q": 1500})

    form = payload["formas_pagamento"][0]
    assert form["forma_pagamento"] == "99"
    assert form["descricao_pagamento"] == description
    assert 2 <= len(form["descricao_pagamento"]) <= 60
    assert "tipo_integracao" not in form


def test_dinheiro_com_troco_declara_o_entregue_e_o_troco():
    """Σ vPag − vTroco = vNF: o dinheiro entregue e o troco que voltou."""
    payload = _emit_capturing({
        "method": "cash", "amount_q": 1500, "tendered_q": 2000, "change_q": 500,
    })

    assert payload["formas_pagamento"] == [{"forma_pagamento": "01", "valor_pagamento": "20.00"}]
    assert payload["valor_troco"] == "5.00"
    assert payload["valor_total"] == "15.00"
    assert "valor_desconto" not in payload


def test_venda_mista_com_troco_soma_o_troco_so_na_linha_de_dinheiro():
    # Crédito 10,00 + dinheiro 5,00 entregue numa venda de 13,00: o serviço
    # fiscal já tirou o troco da linha de dinheiro (3,00 líquido).
    payload = _emit_capturing({
        "method": "mixed", "amount_q": 1300, "tendered_q": 500, "change_q": 200,
        "tenders": [
            {"method": "credit", "amount_q": 1000},
            {"method": "cash", "amount_q": 300},
        ],
    }, total_q=1300)

    assert payload["formas_pagamento"] == [
        {"forma_pagamento": "03", "valor_pagamento": "10.00", "tipo_integracao": "2"},
        {"forma_pagamento": "01", "valor_pagamento": "5.00"},
    ]
    assert payload["valor_troco"] == "2.00"
    assert payload["valor_total"] == "13.00"


@pytest.mark.parametrize("payment", [
    {"method": "cash", "amount_q": 1500},
    {"method": "cash", "amount_q": 1500, "tendered_q": 1500, "change_q": 0},
    # Troco que não fecha com o entregue não se inventa: vPag líquido é válido.
    {"method": "cash", "amount_q": 1500, "tendered_q": 3000, "change_q": 500},
    {"method": "cash", "amount_q": 1500, "change_q": 500},
    # Troco sem dinheiro na nota não é troco.
    {"method": "pix", "amount_q": 1500, "tendered_q": 2000, "change_q": 500},
])
def test_sem_troco_provado_a_nota_declara_o_liquido(payment):
    payload = _emit_capturing(payment)

    assert payload["formas_pagamento"][0]["valor_pagamento"] == "15.00"
    assert "valor_troco" not in payload


# ── Hora da Autorização de Uso (prazo de cancelamento) ─────────────────────
#
# Medido em 28/10/2026 no alpha: a Focus responde a NFC-e sem `data_autorizacao`,
# o pedido gravava `nfce_authorized_at` vazio, e o cancelamento 4 h depois foi à
# SEFAZ e voltou "autorizada há mais de 30 minutos" em vez de abrir a nota de
# estorno. A hora oficial é o `dhRecbto` do XML autorizado.

_AUTHORIZED_XML = (
    b'<nfeProc><NFe/><protNFe><infProt><tpAmb>2</tpAmb>'
    b"<dhRecbto>2026-10-28T06:22:16-03:00</dhRecbto><nProt>141260001773024</nProt>"
    b"<cStat>100</cStat></infProt></protNFe></nfeProc>"
)


def _authorized_response(**extra):
    return {
        "status": "autorizado",
        "ref": "ORD-1",
        "numero": "723",
        "serie": "1",
        "protocolo": "141260001773024",
        "chave_nfe": "NFC-E-KEY",
        "caminho_xml_nota_fiscal": "https://example.test/nota.xml",
        **extra,
    }


class _XmlResponse:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.body


def test_query_without_authorization_date_reads_dhRecbto_from_the_xml():
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    opened = []

    def fake_urlopen(request, timeout):
        opened.append(request.full_url)
        return _XmlResponse(_AUTHORIZED_XML)

    with (
        patch("shopman.shop.adapters.fiscal_focusnfe._request", return_value=_authorized_response()),
        patch("shopman.shop.adapters.fiscal_focusnfe.urlopen", side_effect=fake_urlopen),
        override_settings(SHOPMAN_FOCUS_NFE=_settings()),
    ):
        result = FocusNFeBackend().query_status(reference="ORD-1")

    assert result.success is True
    assert result.authorization_date == "2026-10-28T06:22:16-03:00"
    assert opened == ["https://example.test/nota.xml"]


def test_authorization_date_from_the_response_skips_the_xml():
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    response = _authorized_response(data_autorizacao="2026-10-28T06:22:16-03:00")
    with (
        patch("shopman.shop.adapters.fiscal_focusnfe._request", return_value=response),
        patch("shopman.shop.adapters.fiscal_focusnfe.urlopen") as xml_open,
        override_settings(SHOPMAN_FOCUS_NFE=_settings()),
    ):
        result = FocusNFeBackend().query_status(reference="ORD-1")

    assert result.authorization_date == "2026-10-28T06:22:16-03:00"
    xml_open.assert_not_called()


def test_unreadable_xml_keeps_the_note_authorized_without_the_date():
    from urllib.error import URLError

    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    with (
        patch("shopman.shop.adapters.fiscal_focusnfe._request", return_value=_authorized_response()),
        patch("shopman.shop.adapters.fiscal_focusnfe.urlopen", side_effect=URLError("down")),
        override_settings(SHOPMAN_FOCUS_NFE=_settings()),
    ):
        result = FocusNFeBackend().query_status(reference="ORD-1")

    assert result.success is True
    assert result.authorization_date is None
