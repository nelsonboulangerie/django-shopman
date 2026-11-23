"""Settings do Django servido pelo harness E2E da loja (``run_storefront_e2e.sh``).

É o ``config.settings`` de sempre, com estas diferenças, todas só do harness:

1. **Cartão contra o Stripe falso local** (``fake_stripe.py``). Só o endereço da
   API do SDK muda. Adapter, Checkout Session, webhook assinado e lifecycle são
   os de produção.
2. **Sem limite de taxa por IP.** Todo o E2E sai de 127.0.0.1, como um único
   cliente, e a suíte inteira cabe em menos de um minuto: dois logins por OTP
   (retirada e Dia 1) já estouram o ``request-code`` de 5/min, e as leituras
   públicas encostam no throttle anônimo. Medir o limite aqui seria medir o
   relógio, não o fluxo. Os limites têm teste próprio
   (``shopman/storefront/tests/``), e o throttle anônimo desligado é o mesmo
   botão que o settings já documenta para carga sintética de IP único.
3. **WhatsApp contra o ManyChat falso local** (``fake_manychat.py``, #3272), quando
   ``MANYCHAT_API_BASE`` aponta para 127.0.0.1: o ``notification_manychat`` de
   produção roda inteiro (a resposta do login com "Liberar o Chrome" e "Encerrar
   acesso" sai de verdade), com um token falso e a trava de DEBUG aberta só para
   o ManyChat. O resolvedor de assinantes do Guestman (que acha ou cria o contato
   do telefone antes do aviso do pedido, #3282) também roda inteiro contra o fake:
   o endereço dele é fixo no módulo (``resolver._API_BASE``, sem setting), e é
   trocado aqui como o ``stripe.api_base``, sem mexer no Core. O token falso de
   topo (``MANYCHAT_API_TOKEN``) é o que ele lê; com o endereço trocado, nada sai
   da máquina.
4. **Geocoding contra os mapas falsos locais** (``fake_maps.py``, #2569 item 4),
   quando ``SHOPMAN_E2E_MAPS_API_BASE`` aponta para 127.0.0.1: o ``geocoding`` de
   produção roda inteiro e só o endereço da API muda (``geocoding.GEOCODE_URL``,
   como o ``stripe.api_base`` acima: o serviço não tem setting de endereço, e um só
   para teste não entra no código de produção). Chave de servidor falsa; as de
   navegador ficam vazias, para a loja nunca carregar o Maps JS do Google.

Recusa subir fora do harness: sem DEBUG, sem chave ``sk_test_`` ou com a API
apontada para fora de 127.0.0.1, a importação levanta, para que este módulo
nunca vire "cartão de mentira, sem limite" num ambiente de verdade.
"""

import os
from urllib.parse import urlparse

import stripe

from config.settings import *  # noqa: F403
from config.settings import DEBUG, REST_FRAMEWORK, SHOPMAN_MANYCHAT, SHOPMAN_STRIPE

_FAKE_API_BASE = os.environ.get("SHOPMAN_E2E_STRIPE_API_BASE", "").strip()

if not DEBUG:
    raise RuntimeError("settings_e2e só sobe com DJANGO_DEBUG=true (harness E2E).")
if not str(SHOPMAN_STRIPE.get("secret_key") or "").startswith("sk_test_"):
    raise RuntimeError("settings_e2e exige STRIPE_SECRET_KEY de teste (sk_test_).")
if urlparse(_FAKE_API_BASE).hostname not in {"127.0.0.1", "localhost"}:
    raise RuntimeError("SHOPMAN_E2E_STRIPE_API_BASE precisa apontar para o Stripe falso local.")

stripe.api_base = _FAKE_API_BASE

RATELIMIT_ENABLE = False
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": {**REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "anon": None},
}

_FAKE_MANYCHAT_BASE = os.environ.get("MANYCHAT_API_BASE", "").strip()
if _FAKE_MANYCHAT_BASE:
    if urlparse(_FAKE_MANYCHAT_BASE).hostname not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("MANYCHAT_API_BASE no harness precisa apontar para o ManyChat falso local.")
    from shopman.guestman.contrib.manychat import resolver as _manychat_resolver

    _manychat_resolver._API_BASE = _FAKE_MANYCHAT_BASE.rstrip("/")
    MANYCHAT_API_TOKEN = "e2e-fake-manychat-local-only"
    SHOPMAN_MANYCHAT = {
        **SHOPMAN_MANYCHAT,
        "api_token": MANYCHAT_API_TOKEN,
        "base_url": _FAKE_MANYCHAT_BASE.rstrip("/"),
    }
    SHOPMAN_MANYCHAT_ALLOW_IN_DEBUG = True

_FAKE_MAPS_BASE = os.environ.get("SHOPMAN_E2E_MAPS_API_BASE", "").strip()
if _FAKE_MAPS_BASE:
    if urlparse(_FAKE_MAPS_BASE).hostname not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("SHOPMAN_E2E_MAPS_API_BASE precisa apontar para os mapas falsos locais.")
    from shopman.shop.services import geocoding as _geocoding

    _geocoding.GEOCODE_URL = f"{_FAKE_MAPS_BASE.rstrip('/')}/maps/api/geocode/json"
    GOOGLE_MAPS_SERVER_API_KEY = "e2e-fake-maps-local-only"
    GOOGLE_MAPS_BROWSER_API_KEY = ""
    GOOGLE_MAPS_API_KEY = ""
