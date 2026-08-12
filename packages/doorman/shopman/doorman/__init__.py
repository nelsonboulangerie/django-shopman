"""
Shopman Doorman — Phone-First Authentication.

Usage:
    from shopman.doorman import get_access_link_service, get_auth_service
"""

__title__ = "Shopman Doorman"
__version__ = "0.1.0"
__author__ = "Pablo Valentini"


def get_access_link_service():
    """Lazy import to avoid circular imports."""
    from .services.access_link import AccessLinkService

    return AccessLinkService


def get_auth_service():
    """Lazy import to avoid circular imports."""
    from .services.verification import AuthService

    return AuthService


def __getattr__(name):
    """Lazy import for public surfaces."""
    if name == 'TrustedDevice':
        from shopman.doorman.models.device_trust import TrustedDevice
        return TrustedDevice
    elif name == 'SubjectType':
        # Sai na superfície pública porque quem consulta dispositivos precisa NOMEAR o
        # sujeito ("customer" ou "display"). Sem isto, o chamador importava o módulo interno
        # — que o `test_import_boundaries` proíbe, e com razão: import profundo é como o
        # `customer_id` de `shop/services/devices.py` sobreviveu a um refactor do model.
        from shopman.doorman.models.device_trust import SubjectType
        return SubjectType
    elif name == 'hash_device_token':
        from shopman.doorman.models.device_trust import _hash_token
        return _hash_token
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "get_access_link_service",
    "get_auth_service",
    "TrustedDevice",
    "SubjectType",
    "hash_device_token",
]
