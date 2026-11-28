"""SMS de código com a linha do WebOTP: ``@<host da loja> #<código>`` no fim.

Decisão do dono de 23/10 (escada sem fricção, item 5). O host vem da ``Shop`` (ADR-042),
e a mensagem tem de seguir num segmento GSM-7: ``@`` e ``#`` são do alfabeto básico,
mas um caractere fora dele derrubaria o limite de 160 para 70 e dobraria o custo.
"""

from __future__ import annotations

import importlib

import pytest
from django.core.exceptions import ValidationError
from django.test import override_settings

from shopman.shop.adapters import _sms
from shopman.shop.models import Shop

#: GSM 03.38, alfabeto básico (1 septeto por caractere).
_GSM7_BASIC = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
#: Extensão: vale, mas custa 2 septetos (escape + caractere).
_GSM7_EXTENSION = set("^{}\\[~]|€\f")


def _gsm7_septets(text: str) -> int | None:
    """Septetos que o texto ocupa em GSM-7, ou ``None`` se ele força UCS-2."""
    total = 0
    for char in text:
        if char in _GSM7_BASIC:
            total += 1
        elif char in _GSM7_EXTENSION:
            total += 2
        else:
            return None
    return total


def _nelson(**extra) -> Shop:
    return Shop.objects.create(
        name="Nelson Boulangerie",
        brand_name="Nelson Boulangerie",
        storefront_host="www.nelsonboulangerie.com.br",
        **extra,
    )


@pytest.mark.django_db
def test_a_ultima_linha_e_o_host_da_loja_e_o_codigo():
    _nelson()

    message = _sms.render_message({}, "482913")

    assert message.splitlines()[-1] == "@www.nelsonboulangerie.com.br #482913"
    assert message.startswith("Nelson Boulangerie: 482913 e o seu codigo de acesso.")


@pytest.mark.django_db
def test_a_mensagem_da_nelson_cabe_num_segmento_gsm7():
    _nelson()

    message = _sms.render_message({}, "482913")
    septets = _gsm7_septets(message)

    assert septets is not None, f"caractere fora do GSM-7 em {message!r}"
    assert septets <= 160, f"{septets} septetos: mais de um segmento"


@pytest.mark.django_db
def test_sem_host_o_sms_sai_sem_a_linha_e_continua_valendo():
    Shop.objects.create(name="Padaria do Bairro", brand_name="Bairro")

    message = _sms.render_message({}, "482913")

    assert "\n" not in message
    assert "#482913" not in message
    assert message.startswith("Bairro: 482913 e o seu codigo")


@pytest.mark.django_db
def test_o_texto_da_casa_tambem_ganha_a_linha():
    _nelson()

    message = _sms.render_message({"code_message": "Codigo {code}"}, "111222")

    assert message == "Codigo 111222\n@www.nelsonboulangerie.com.br #111222"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "valor",
    ["https://www.loja.com.br", "www.loja.com.br/", "WWW.LOJA.COM.BR", "localhost", "loja com.br"],
)
def test_o_host_da_loja_e_so_o_dominio(valor):
    shop = Shop(name="Loja", storefront_host=valor)

    with pytest.raises(ValidationError) as exc:
        shop.full_clean()
    assert "storefront_host" in exc.value.message_dict


@pytest.mark.django_db
def test_a_migracao_herda_o_host_do_deploy_uma_vez():
    from django.apps import apps

    migration = importlib.import_module("shopman.shop.migrations.0106_storefront_host")
    shop = Shop.objects.create(name="Loja")

    with override_settings(SHOPMAN_STOREFRONT_BASE_URL="https://www.loja.com.br"):
        migration._host_from_deploy(apps, None)
    shop.refresh_from_db()
    assert shop.storefront_host == "www.loja.com.br"

    with override_settings(SHOPMAN_STOREFRONT_BASE_URL="https://outra.com.br"):
        migration._host_from_deploy(apps, None)
    shop.refresh_from_db()
    assert shop.storefront_host == "www.loja.com.br"  # não sobrescreve o que a loja já tem


@pytest.mark.django_db
def test_a_migracao_ignora_base_sem_dominio():
    from django.apps import apps

    migration = importlib.import_module("shopman.shop.migrations.0106_storefront_host")
    shop = Shop.objects.create(name="Loja")

    with override_settings(SHOPMAN_STOREFRONT_BASE_URL="http://localhost:3000"):
        migration._host_from_deploy(apps, None)
    shop.refresh_from_db()
    assert shop.storefront_host == ""
