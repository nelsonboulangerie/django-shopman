"""Google Maps keys: production never exposes or consumes the shared legacy key."""
from django.conf import settings

from shopman.shop.environment import is_production


def browser_api_key() -> str:
    """Only the explicitly separated browser key may enter public projections."""
    browser = str(getattr(settings, "GOOGLE_MAPS_BROWSER_API_KEY", "") or "").strip()
    server = str(getattr(settings, "GOOGLE_MAPS_SERVER_API_KEY", "") or "").strip()
    legacy = str(getattr(settings, "GOOGLE_MAPS_API_KEY", "") or "").strip()
    if is_production():
        return browser if browser and browser not in {server, legacy} else ""
    return browser or legacy


def server_api_key() -> str:
    """Production requires the explicitly provisioned private server credential."""
    server = str(getattr(settings, "GOOGLE_MAPS_SERVER_API_KEY", "") or "").strip()
    if is_production():
        browser = str(getattr(settings, "GOOGLE_MAPS_BROWSER_API_KEY", "") or "").strip()
        return server if server != browser else ""
    return server or str(getattr(settings, "GOOGLE_MAPS_API_KEY", "") or "").strip()
