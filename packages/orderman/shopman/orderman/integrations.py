"""Optional integration points for host/orchestrator apps.

Orderman must stay installable without django-shopman. The host declares its
sales-channel model in ``ORDERMAN["CHANNEL_MODEL"]`` (``"app_label.Model"``,
like ``AUTH_USER_MODEL``), and Orderman uses it for convenience UI/API surfaces
without importing (or naming) the host.
"""

from __future__ import annotations

from typing import Any

from django.apps import apps
from django.conf import settings


def get_channel_model() -> type[Any] | None:
    """The host's channel model declared in ``ORDERMAN["CHANNEL_MODEL"]``, or ``None``."""
    label = getattr(settings, "ORDERMAN", {}).get("CHANNEL_MODEL")
    return apps.get_model(label) if label else None
