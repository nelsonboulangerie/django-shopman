"""Shared helpers for SMS OTP senders (Twilio, Comtele, …).

Keeps message rendering and number normalization in one place so each provider sender
stays thin. Provider choice is swappable via DOORMAN['DELIVERY_SENDERS']['sms'].
"""

from __future__ import annotations

#: O SMS de OTP chega num dispositivo cheio de mensagens de remetente desconhecido,
#: e o que estava aqui não dizia de onde vinha nem para quê: "482913 é o seu
#: código de verificação" podia ser de qualquer serviço do mundo. Quem recebe sem
#: reconhecer ou ignora (e não entra) ou desconfia (e reclama).
#:
#: A MARCA vai na frente porque a pré-visualização do celular corta o resto — é
#: o primeiro fragmento que decide se a pessoa abre. Sobre a promessa de curto:
#: SMS cobra por segmento de 160 caracteres (e 70 se houver acento fora do
#: GSM-7), então cada palavra a mais pode dobrar o custo de cada envio.
#:
#: A marca é a da loja (``Shop.brand_name``, ou o nome), nunca um nome escrito
#: aqui. A casa pode reescrever o texto inteiro por `SHOPMAN_SMS_CODE_MESSAGE`
#: sem tocar em código (``{brand}``, ``{code}`` e ``{ttl}`` são preenchidos).
CODE_MESSAGE_TEMPLATE = "{brand}: {code} e o seu codigo de acesso. Vale {ttl} min. Nao compartilhe."
#: Sem loja cadastrada não há marca a pôr na frente.
CODE_MESSAGE_WITHOUT_BRAND = "{code} e o seu codigo de acesso. Vale {ttl} min. Nao compartilhe."


def _brand() -> str:
    from shopman.shop.models import Shop

    shop = Shop.load()
    if shop is None:
        return ""
    return (shop.brand_name or shop.name or "").strip()


def ttl_minutes() -> int:
    """Verification code validity in minutes (from Doorman config; 10 as fallback)."""
    try:
        from shopman.doorman.conf import doorman_settings

        return int(doorman_settings.ACCESS_CODE_TTL_MINUTES)
    except (ImportError, AttributeError, ValueError, TypeError):
        return 10


def render_message(cfg: dict, code: str) -> str:
    """Build the OTP message text from config (or the default), filling brand + code + ttl."""
    brand = _brand()
    default = CODE_MESSAGE_TEMPLATE if brand else CODE_MESSAGE_WITHOUT_BRAND
    template = str(cfg.get("code_message") or default)
    return template.format(brand=brand, code=code, ttl=ttl_minutes())


def to_digits(target: str) -> str:
    """Digits-only phone number (strips '+', spaces, punctuation)."""
    return "".join(ch for ch in str(target) if ch.isdigit())
