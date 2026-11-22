"""O redator da fala de cliente fala português na tela, e o telefone sai inteiro, com o DDD.

A coordenação, na prévia da seção IA do B.I. (21/11/2026): a tela do dono mostrava
"[documento omitido]" ao lado de "[phone]" e "[email]", e "meu zap é ([phone]" deixava o "(" do
DDD para trás. O boundary de telemetria (logs, Sentry) segue com os tokens dele.
"""

from __future__ import annotations

from shopman.shop.telemetry_redaction import redact_text
from shopman.storefront.concierge.observation_privacy import redact_observation_text


def test_contacts_come_out_in_portuguese():
    redacted = redact_observation_text("manda pra maria.silva@gmail.com ou liga 43 99999-8888")
    assert redacted.text == "manda pra [e-mail omitido] ou liga [telefone omitido]"
    assert set(redacted.categories) == {"email", "phone"}


def test_the_phone_with_area_code_in_parentheses_goes_whole():
    for spoken in ("meu zap é (11) 98765-4321", "meu zap é +55 (43) 3025-1234", "meu zap é ( 43 ) 99999 8888"):
        redacted = redact_observation_text(spoken)
        assert redacted.text == "meu zap é [telefone omitido]", spoken
        assert redacted.categories == ("phone",)


def test_no_english_token_and_no_stray_parenthesis():
    text = redact_observation_text("cpf 123.456.789-09, zap (11) 98765-4321, email a@b.com").text
    assert "[phone]" not in text and "[email]" not in text and "(" not in text
    assert "[documento omitido]" in text


def test_times_dates_and_quantities_stay():
    spoken = "quero 2 croissants, dá pra buscar 16h? dia 21/11"
    assert redact_observation_text(spoken).text == spoken


def test_the_telemetry_boundary_keeps_its_own_tokens():
    """Log e Sentry não mudam: quem procura ``[phone]`` no log continua achando."""
    assert redact_text("ligar 43999998888 ou a@b.com") == "ligar [phone] ou [email]"
