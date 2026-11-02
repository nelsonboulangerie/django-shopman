"""Settings do Django servido pelo harness E2E da loja (``run_storefront_e2e.sh``).

É o ``config.settings`` de sempre, com duas diferenças, as duas só do harness:

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

Recusa subir fora do harness: sem DEBUG, sem chave ``sk_test_`` ou com a API
apontada para fora de 127.0.0.1, a importação levanta, para que este módulo
nunca vire "cartão de mentira, sem limite" num ambiente de verdade.
"""

import os
from urllib.parse import urlparse

import stripe

from config.settings import *  # noqa: F403
from config.settings import DEBUG, REST_FRAMEWORK, SHOPMAN_STRIPE

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
