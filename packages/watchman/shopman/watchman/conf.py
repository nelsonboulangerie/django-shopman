"""Settings parsing kept separate from registry construction."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from django.conf import settings

from shopman.watchman.exceptions import WatchmanConfigurationError

DEFAULT_CHECKS = ("shopman.watchman.checks.ProcessCheck",)
DEFAULT_PROFILES = {
    "liveness": ("process",),
    "readiness": ("process",),
    "diagnostic": ("process",),
}


def get_watchman_config() -> dict[str, Any]:
    raw = getattr(settings, "WATCHMAN", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping):
        raise WatchmanConfigurationError("WATCHMAN must be a mapping")

    checks = raw.get("CHECKS", DEFAULT_CHECKS)
    profiles = raw.get("PROFILES", DEFAULT_PROFILES)
    if not _is_sequence(checks):
        raise WatchmanConfigurationError("WATCHMAN['CHECKS'] must be a sequence")
    if not isinstance(profiles, Mapping):
        raise WatchmanConfigurationError("WATCHMAN['PROFILES'] must be a mapping")

    normalized_profiles: dict[str, tuple[str, ...]] = {}
    for name, check_ids in profiles.items():
        if not isinstance(name, str) or not name.strip():
            raise WatchmanConfigurationError("profile names must be non-empty strings")
        if not _is_sequence(check_ids) or not all(isinstance(value, str) for value in check_ids):
            raise WatchmanConfigurationError(f"WATCHMAN profile {name!r} must be a sequence of check IDs")
        normalized_profiles[name] = tuple(check_ids)

    return {"CHECKS": tuple(checks), "PROFILES": normalized_profiles}


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
