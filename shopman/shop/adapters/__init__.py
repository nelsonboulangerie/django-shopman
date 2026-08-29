"""
Shopman adapters — swappable backends resolved at runtime.

Resolution order for get_adapter():
  1. Shop.integrations (DB — Admin-configurável, sobreescreve tudo)
  2. Settings (SHOPMAN_<TYPE>_ADAPTERS — deploy-level config)
  3. Built-in defaults

Usage:
    from shopman.shop.adapters import get_adapter

    adapter = get_adapter("payment", method="pix")
    adapter = get_adapter("notification")
    adapter = get_adapter("stock")
    adapter = get_adapter("fiscal")
"""

import logging
from importlib import import_module

from django.conf import settings

logger = logging.getLogger(__name__)

# Mapping from adapter type → settings key
_SETTINGS_MAP = {
    "payment": "SHOPMAN_PAYMENT_ADAPTERS",
    "notification": "SHOPMAN_NOTIFICATION_ADAPTERS",
    "stock": "SHOPMAN_STOCK_ADAPTER",
    "fiscal": "SHOPMAN_FISCAL_ADAPTER",
    "catalog": "SHOPMAN_CATALOG_ADAPTER",
    "production": "SHOPMAN_PRODUCTION_ADAPTER",
    "customer": "SHOPMAN_CUSTOMER_ADAPTER",
    "courier": "SHOPMAN_COURIER_ADAPTER",
}

# Defaults when settings are absent
_DEFAULTS = {
    # ⚠️ Pagamento não tem default. "Ninguém configurou gateway" não pode
    # resolver silenciosamente para o simulador: era assim que um deploy sem
    # SHOPMAN_CARD_ADAPTER caía no payment_mock e dava pedido por pago sem
    # cobrar. Sem adapter, `payment.initiate` grava o erro e o pedido para —
    # que é o comportamento certo de um sistema de dinheiro sem gateway.
    "payment": {
        "pix": None,
        "card": None,
        "cash": None,
        "external": None,
    },
    "notification": {
        "console": "shopman.shop.adapters.notification_console",
    },
    "stock": "shopman.shop.adapters.stock",
    "fiscal": None,
    "catalog": "shopman.shop.adapters.catalog",
    "production": "shopman.shop.adapters.production",
    "customer": "shopman.shop.adapters.customer",
    "courier": None,
}


def _resolve_module(dotted_path):
    """Import and return a module from a dotted path string."""
    if dotted_path is None:
        return None
    return import_module(dotted_path)


def _from_shop_integrations(adapter_type: str, method=None):
    """Read adapter config from Shop.integrations (Admin-configurable, highest priority)."""
    try:
        from shopman.shop.models import Shop
        shop = Shop.load()
        if not shop or not shop.integrations:
            return None, False
        integrations = shop.integrations
        value = integrations.get(adapter_type)
        if value is None:
            return None, False
        # Found a value — now resolve it
        if isinstance(value, dict):
            path, _ = _method_value(value, adapter_type, method)
            return _resolve_module(path), True
        else:
            return _resolve_module(value), True
    except Exception:
        logger.debug("_from_shop_integrations: DB lookup failed for %s", adapter_type, exc_info=True)
        return None, False


# Tipos em que pedir um método que não está configurado NÃO pode cair no
# primeiro adapter disponível do dicionário. Pagamento é o caso óbvio: pedir
# "card" numa config que só define "pix" devolvia o adapter do Pix, calado —
# e um operador editando `Shop.integrations["payment"]` no Admin (JSON livre,
# prioridade máxima) consegue exatamente isso. Método não configurado é None.
_NO_METHOD_FALLBACK = {"payment"}


def _method_value(mapping: dict, adapter_type: str, method):
    """Escolhe o caminho do método dentro de um dict de configuração.

    Devolve ``(path, resolved)``. ``resolved=False`` significa "esta camada não
    respondeu" — quem chama decide se desce para a próxima.
    """
    if method and method in mapping:
        return mapping[method], True
    if method and adapter_type in _NO_METHOD_FALLBACK:
        # Método desconhecido num tipo sensível: ausência é ausência.
        logger.warning(
            "get_adapter: método %r não configurado para %r — sem adapter.",
            method, adapter_type,
        )
        return None, True
    if "default" in mapping:
        return mapping["default"], True
    for path in mapping.values():
        if path is not None:
            return path, True
    return None, True


def get_adapter(adapter_type, method=None, channel=None):
    """
    Resolve an adapter module by type and optional method.

    Resolution order:
      1. Shop.integrations (DB — Admin-configurável)
      2. Settings (SHOPMAN_<TYPE>_ADAPTERS)
      3. Built-in defaults

    Returns the imported module, or None if the adapter is explicitly disabled.
    """
    # 1. Shop.integrations (Admin-configurable, overrides everything)
    adapter, found = _from_shop_integrations(adapter_type, method)
    if found:
        return adapter

    # 2. Settings
    settings_key = _SETTINGS_MAP.get(adapter_type)
    setting_value = getattr(settings, settings_key, None) if settings_key else None

    if setting_value is not None:
        if isinstance(setting_value, dict):
            path, _ = _method_value(setting_value, adapter_type, method)
            return _resolve_module(path)
        else:
            return _resolve_module(setting_value)

    # 3. Defaults
    default = _DEFAULTS.get(adapter_type)
    if default is None:
        return None
    if isinstance(default, dict):
        path, _ = _method_value(default, adapter_type, method)
        return _resolve_module(path)
    return _resolve_module(default)
