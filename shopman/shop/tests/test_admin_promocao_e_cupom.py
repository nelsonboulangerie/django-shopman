"""Cadastro de promoção e cupom no Admin (beta test 05/11/2026, ADM-01, ADM-02, ADM-09).

- ADM-01: o cupom "natal10" salvo em minúsculas nunca casava, porque a loja
  procura em maiúsculas. O código passa a ser guardado como a loja procura, e o
  que não dá para digitar no balcão (espaço, acento, emoji) é recusado.
- ADM-02: 150% e término antes do início eram aceitos; o 150 virava 100% na venda.
- ADM-09: dinheiro se digita em reais; o modelo continua em centavos.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from shopman.shop.admin.promotion import PromotionAdminForm
from shopman.shop.models import Coupon, Promotion
from shopman.shop.services.cart import CouponRejected, validate_and_apply_coupon

pytestmark = pytest.mark.django_db


def _promotion(**overrides) -> Promotion:
    now = timezone.now()
    fields = {
        "ref": "desconto-teste",
        "name": "Desconto teste",
        "type": Promotion.PERCENT,
        "value": 10,
        "valid_from": now - timedelta(days=1),
        "valid_until": now + timedelta(days=1),
    }
    fields.update(overrides)
    return Promotion(**fields)


# ── ADM-01 · cupom ──────────────────────────────────────────────────


def test_cupom_digitado_em_minusculas_e_guardado_como_a_loja_procura():
    promotion = _promotion()
    promotion.save()
    coupon = Coupon(code="  natal10 ", promotion=promotion)
    coupon.full_clean()
    coupon.save()
    assert Coupon.objects.get(pk=coupon.pk).code == "NATAL10"


@pytest.mark.parametrize("code", ["mg teste ção 🥐", "NATAL 10", "PÃO10", "-X"])
def test_cupom_que_nao_se_digita_no_balcao_e_recusado(code):
    promotion = _promotion()
    promotion.save()
    with pytest.raises(ValidationError) as exc:
        Coupon(code=code, promotion=promotion).full_clean()
    assert "code" in exc.value.message_dict


def test_cupom_gravado_em_minusculas_e_encontrado_pela_loja():
    promotion = _promotion()
    promotion.save()
    Coupon.objects.create(code="natal10", promotion=promotion)
    try:
        validate_and_apply_coupon(session_key="nenhuma", channel_ref="web", code="natal10")
    except CouponRejected as rejected:
        # O cupom existe e foi achado: a recusa, se houver, é de outra regra
        # (sem carrinho neste teste), nunca "cupom inválido".
        assert rejected.code != "invalid_coupon"


# ── ADM-02 · promoção ───────────────────────────────────────────────


def test_percentual_acima_de_100_e_recusado():
    with pytest.raises(ValidationError) as exc:
        _promotion(value=150).full_clean()
    assert exc.value.message_dict["value"] == ["Percentual entre 1 e 100."]


def test_termino_antes_do_inicio_e_recusado():
    now = timezone.now()
    with pytest.raises(ValidationError) as exc:
        _promotion(valid_from=now + timedelta(days=5), valid_until=now - timedelta(days=4)).full_clean()
    assert "valid_until" in exc.value.message_dict


def test_valor_fixo_precisa_ser_maior_que_zero():
    with pytest.raises(ValidationError) as exc:
        _promotion(type=Promotion.FIXED, value=0).full_clean()
    assert "value" in exc.value.message_dict


def test_entrega_gratis_com_teto_zero_continua_valendo():
    _promotion(type=Promotion.FREE_DELIVERY, value=0).full_clean()


# ── ADM-09 · reais na tela ──────────────────────────────────────────


def _form_data(**overrides) -> dict:
    now = timezone.localtime()
    data = {
        "ref": "fixa-reais",
        "name": "Fixa em reais",
        "type": Promotion.FIXED,
        "value": "15,00",
        "valid_from": (now - timedelta(days=1)).strftime("%d/%m/%Y 00:00"),
        "valid_until": (now + timedelta(days=10)).strftime("%d/%m/%Y 00:00"),
        "min_order_q": "50,00",
        "skus": "[]",
        "collections": "[]",
        "fulfillment_types": "[]",
        "customer_segments": "[]",
        "is_active": "on",
    }
    data.update(overrides)
    return data


def test_promocao_de_valor_fixo_digitada_em_reais_grava_centavos():
    form = PromotionAdminForm(data=_form_data())
    assert form.is_valid(), form.errors
    promotion = form.save()
    assert promotion.value == 1500
    assert promotion.min_order_q == 5000


def test_percentual_continua_numero_inteiro():
    form = PromotionAdminForm(data=_form_data(type=Promotion.PERCENT, value="15"))
    assert form.is_valid(), form.errors
    assert form.save().value == 15


def test_percentual_150_e_recusado_pelo_form_do_admin():
    form = PromotionAdminForm(data=_form_data(type=Promotion.PERCENT, value="150"))
    assert not form.is_valid()
    assert "value" in form.errors


def test_promocao_existente_aparece_em_reais():
    promotion = _promotion(type=Promotion.FIXED, value=1500, min_order_q=5000)
    promotion.save()
    form = PromotionAdminForm(instance=promotion)
    assert form.initial["value"] == "15,00"
    assert form["min_order_q"].value() == "50,00"
