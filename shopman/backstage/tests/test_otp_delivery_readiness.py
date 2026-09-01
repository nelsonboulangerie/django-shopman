"""A loja tem porta de entrada?

A tela de prontidão cobria pagamento e fiscal — e ficava VERDE com a cadeia de
OTP vazia, que foi exatamente o estado do alpha. Pagamento e fiscal impecáveis
numa loja em que ninguém consegue entrar.
"""

from __future__ import annotations

import pytest

from shopman.backstage.services.integration_readiness import (
    build_provider_readiness,
    otp_delivery_readiness,
)

pytestmark = pytest.mark.django_db


def _cadeia(settings, *canais):
    settings.DOORMAN = {**(settings.DOORMAN or {}), "DELIVERY_CHAIN": list(canais)}


def _sms(settings, *, ok: bool):
    settings.SHOPMAN_SMS = {"api_key": "k" if ok else "", "route": "17" if ok else ""}


def _email(settings, *, ok: bool):
    if ok:
        settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
        settings.EMAIL_HOST = "smtp.exemplo.test"
    else:
        settings.EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
        settings.EMAIL_HOST = ""


def test_esta_na_lista_de_prontidao(settings):
    """O eixo que faltava: ele agora é conferido junto com Efí, Stripe e Focus."""
    assert any(p.provider == "otp_delivery" for p in build_provider_readiness())


def test_cadeia_VAZIA_e_erro(settings):
    """O estado do alpha. Ficava verde porque ninguém perguntava."""
    _cadeia(settings)

    r = otp_delivery_readiness()

    assert r.status == "error"
    assert "DELIVERY_CHAIN_vazia" in r.missing


def test_sms_e_email_configurados_e_pronto(settings):
    _cadeia(settings, "sms", "email")
    _sms(settings, ok=True)
    _email(settings, ok=True)

    r = otp_delivery_readiness()

    assert r.status == "ready"
    assert r.environment == "sms, email"


def test_UM_canal_que_entrega_ja_e_PRONTO(settings):
    """Decisão da casa: o SMS é o canal de OTP por si.

    ⚠️ Este teste já exigiu "warning", e o "warning" era ruído: um e-mail não
    configurado é o DESENHO, não pendência (o WhatsApp não pode fazer OTP — o
    ManyChat não tem template de Authentication). Painel que fica amarelo por
    escolha deliberada ensina o gestor a ignorar o amarelo, e aí ele ignora o
    amarelo que importa.
    """
    _cadeia(settings, "sms", "email")
    _sms(settings, ok=True)
    _email(settings, ok=False)

    r = otp_delivery_readiness()

    assert r.status == "ready"
    assert r.environment == "sms"


def test_mas_o_gestor_SABE_que_so_tem_uma_perna(settings):
    """Pronto sem alarme, e ainda assim transparente. Se o SMS cair, não há
    segunda via — e isso não pode ser descoberto na hora."""
    _cadeia(settings, "sms", "email")
    _sms(settings, ok=True)
    _email(settings, ok=False)

    r = otp_delivery_readiness()

    assert "Sem segunda via" in r.message
    assert "EMAIL_HOST/EMAIL_BACKEND" in r.missing


def test_com_as_DUAS_pernas_nao_ha_ressalva(settings):
    _cadeia(settings, "sms", "email")
    _sms(settings, ok=True)
    _email(settings, ok=True)

    r = otp_delivery_readiness()

    assert r.status == "ready"
    assert "Sem segunda via" not in r.message


def test_os_DOIS_quebrados_e_ERRO(settings):
    """Loja sem porta de entrada. É o que acontece hoje: Comtele em 401 e o
    e-mail no backend de console."""
    _cadeia(settings, "sms", "email")
    _sms(settings, ok=False)
    _email(settings, ok=False)

    r = otp_delivery_readiness()

    assert r.status == "error"
    assert "nenhum_canal_entrega_OTP" in r.missing


def test_console_fora_de_DEBUG_nao_conta_como_canal(settings):
    """Console entrega para o LOG, não para o cliente."""
    settings.DEBUG = False
    _cadeia(settings, "console")

    r = otp_delivery_readiness()

    assert r.status == "error"
    assert "DELIVERY_CHAIN_console_fora_de_DEBUG" in r.missing


def test_console_em_DEBUG_conta(settings):
    settings.DEBUG = True
    _cadeia(settings, "console")

    assert otp_delivery_readiness().status == "ready"


def test_o_email_INERTE_nao_conta_como_canal(settings):
    """O nó do item 4: o backend de console se dizia disponível e ainda por cima
    curto-circuitava o SMS. Aqui ele não pode contar como porta de entrada."""
    _cadeia(settings, "email")
    _email(settings, ok=False)

    r = otp_delivery_readiness()

    assert r.status == "error"
    assert "EMAIL_HOST/EMAIL_BACKEND" in r.missing
