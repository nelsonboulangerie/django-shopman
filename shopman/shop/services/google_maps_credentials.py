"""Single source of truth for the Google Maps credential split.

``GOOGLE_MAPS_API_KEY`` is a rollout-only compatibility seam. Keeping the
fallback here (instead of at settings import time) also lets tests and runtime
overrides behave predictably.
"""

from django.conf import settings


def browser_api_key() -> str:
    """Return the public, browser-restricted Maps key."""

    return (
        getattr(settings, "GOOGLE_MAPS_BROWSER_API_KEY", "")
        or getattr(settings, "GOOGLE_MAPS_API_KEY", "")
        or ""
    )


def server_api_key() -> str:
    """Return the private, Geocoding-only server key."""

    return (
        getattr(settings, "GOOGLE_MAPS_SERVER_API_KEY", "")
        or getattr(settings, "GOOGLE_MAPS_API_KEY", "")
        or ""
    )
