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
   acesso" sai de verdade), com um token falso só no ``SHOPMAN_MANYCHAT`` e a
   trava de DEBUG aberta só para o ManyChat. O ``MANYCHAT_API_TOKEN`` de topo fica
   VAZIO de propósito: o resolvedor de assinantes do Guestman fala com
   ``api.manychat.com`` por endereço fixo e só chama com esse token. Sem ele, nada
   sai da máquina (o assinante do login vem do próprio ManyChat, por id).

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
    MANYCHAT_API_TOKEN = ""
    SHOPMAN_MANYCHAT = {
        **SHOPMAN_MANYCHAT,
        "api_token": "e2e-fake-manychat-local-only",
        "base_url": _FAKE_MANYCHAT_BASE.rstrip("/"),
    }
    SHOPMAN_MANYCHAT_ALLOW_IN_DEBUG = True
