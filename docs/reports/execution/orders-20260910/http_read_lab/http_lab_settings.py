"""Local synthetic HTTP assay only. Never import these settings for deployment."""
from config.settings_test import *  # noqa: F403

DEBUG = False
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False
SHOPMAN_COURIER_ADAPTER = None
SHOPMAN_PAYMENT_ADAPTERS = {"pix": "shopman.shop.adapters.payment_mock", "card": None, "cash": None}
MIDDLEWARE = ["http_lab_metrics.ReadMetrics", *MIDDLEWARE]  # noqa: F405

# Required by Doorman when DEBUG=False; this local database has no real accounts.
DOORMAN = {**DOORMAN, "ACCESS_LINK_API_KEY": "synthetic-local-http-assay-key", "DEFAULT_DOMAIN": "orders-perf.invalid"}  # noqa: F405
