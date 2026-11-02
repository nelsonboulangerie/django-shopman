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
#: A última linha é a do WebOTP (decisão do dono de 23/10, escada sem fricção, item 5):
#: o navegador lê ``@<host> #<código>`` e oferece o código no campo, sem a pessoa trocar
#: de app. Só funciona quando o host é EXATAMENTE o da página aberta, por isso vem da
#: ``Shop.storefront_host`` e nunca de um nome escrito aqui. ``@`` e ``#`` são do
#: alfabeto GSM-7 básico (1 caractere cada): a linha não troca a codificação, e a
#: mensagem da Nelson cabe num segmento só (``tests/test_otp_sms_webotp.py``).
#: Ela é acrescentada também ao texto que a casa escreve em ``code_message``.
WEB_OTP_LINE = "@{host} #{code}"


def _host() -> str:
    """O host da loja para a linha do WebOTP; vazio quando não está cadastrado."""
    from shopman.shop.models import Shop

    shop = Shop.load()
    if shop is None:
        return ""
    return (shop.storefront_host or "").strip().lower()


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
    """Texto do SMS de código: o template (da casa ou o padrão) e, quando a loja tem
    host, a linha do WebOTP no fim."""
    brand = _brand()
    default = CODE_MESSAGE_TEMPLATE if brand else CODE_MESSAGE_WITHOUT_BRAND
    template = str(cfg.get("code_message") or default)
    message = template.format(brand=brand, code=code, ttl=ttl_minutes())
    host = _host()
    if not host:
        # Sem host o SMS segue valendo: o cliente digita o código como sempre. O que
        # se perde é só o preenchimento automático.
        return message
    return f"{message}\n{WEB_OTP_LINE.format(host=host, code=code)}"


def to_digits(target: str) -> str:
    """Digits-only phone number (strips '+', spaces, punctuation)."""
    return "".join(ch for ch in str(target) if ch.isdigit())
