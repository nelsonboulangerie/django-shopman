"""Opt-in local Marketing demo profile; hermetic by construction.

This module is intentionally separate from both normal development and the test
suite.  It lets an operator exercise the real approval/outbox/directive/ledger
path while the final provider boundary is replaced by the local simulator.
Importing it never enables any external transport.
"""

from config.settings_test import *  # noqa: F403

SHOPMAN_ENVIRONMENT = "development"
# Cookies ignoram porta: dois backends locais em 127.0.0.1 usam o mesmo pote do
# navegador. O ensaio não pode perder a sessão porque outro app Django local leu,
# substituiu ou removeu o `sessionid` genérico. O nome exclusivo vale somente neste
# perfil descartável; produção mantém o contrato cross-subdomínio canônico.
SESSION_COOKIE_NAME = "marketing_demo_sessionid"
SHOPMAN_MARKETING_OUTBOX_CONSUMER_ENABLED = True
SHOPMAN_MARKETING_DELIVERY_CONSUMER_ENABLED = True
SHOPMAN_MARKETING_SIMULATION_ENABLED = True
SHOPMAN_MARKETING_DELIVERY_ADAPTERS = dict.fromkeys(
    ("instagram", "facebook", "google_business", "whatsapp"),
    "shopman.shop.adapters.marketing_delivery_console",
)
SHOPMAN_MARKETING_SIMULATION_IGNORE_QUIET_HOURS = True
SHOPMAN_MARKETING_SIMULATION_FLOWS = (
    ("local_marketing_e2e", "Fluxo local — sem envio externo"),
)
# Exact host already used by the canonical seed product images.  Validation is
# still fail-closed (no wildcard); the simulator itself never fetches the URL.
SHOPMAN_MARKETING_MEDIA_HOSTS = ("menu.nelsonboulangerie.com.br",)

# These repetitions are deliberate fail-safe documentation.  The adapter checks
# them again immediately before its (local-only) boundary.
SHOPMAN_ALLOW_EXTERNAL_IN_DEBUG = False
SHOPMAN_SMS_ALLOW_IN_DEBUG = False
SHOPMAN_MANYCHAT_ALLOW_IN_DEBUG = False
SHOPMAN_WHATSAPP_ALLOW_IN_DEBUG = False
SHOPMAN_MACHINE_ALLOW_IN_DEBUG = False
