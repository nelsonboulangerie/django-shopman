"""Resolve configured checks and profiles without global mutable state."""

from __future__ import annotations

import inspect
from dataclasses import dataclass

from django.utils.module_loading import import_string

from shopman.watchman.conf import get_watchman_config
from shopman.watchman.contracts import Check, Scope
from shopman.watchman.exceptions import WatchmanConfigurationError


@dataclass(frozen=True, slots=True)
class Registry:
    checks: tuple[Check, ...]
    profiles: dict[str, tuple[str, ...]]

    def __post_init__(self) -> None:
        ids = [check.id for check in self.checks]
        duplicates = sorted({check_id for check_id in ids if ids.count(check_id) > 1})
        if duplicates:
            raise WatchmanConfigurationError(f"duplicate Watchman check IDs: {', '.join(duplicates)}")
        known = set(ids)
        for profile, check_ids in self.profiles.items():
            missing = sorted(set(check_ids) - known)
            if missing:
                raise WatchmanConfigurationError(
                    f"Watchman profile {profile!r} references unknown checks: {', '.join(missing)}"
                )

    def for_profile(self, profile: str) -> tuple[Check, ...]:
        try:
            selected = self.profiles[profile]
        except KeyError as exc:
            raise WatchmanConfigurationError(f"unknown Watchman profile: {profile}") from exc
        by_id = {check.id: check for check in self.checks}
        return tuple(by_id[check_id] for check_id in selected)

    def by_id(self, check_id: str) -> Check:
        for check in self.checks:
            if check.id == check_id:
                return check
        raise WatchmanConfigurationError(f"unknown Watchman check: {check_id}")


def build_registry() -> Registry:
    config = get_watchman_config()
    checks = tuple(_load_check(entry) for entry in config["CHECKS"])
    return Registry(checks=checks, profiles=config["PROFILES"])


def _load_check(entry) -> Check:
    candidate = import_string(entry) if isinstance(entry, str) else entry
    if inspect.isclass(candidate):
        candidate = candidate()
    if not isinstance(candidate, Check):
        raise WatchmanConfigurationError(f"{entry!r} does not implement the Watchman Check contract")
    if not candidate.id or not isinstance(candidate.id, str):
        raise WatchmanConfigurationError(f"{entry!r} has an invalid check id")
    if candidate.timeout_seconds <= 0:
        raise WatchmanConfigurationError(f"Watchman check {candidate.id!r} must declare a positive timeout")
    try:
        scopes = frozenset(Scope(scope) for scope in candidate.scopes)
    except (TypeError, ValueError) as exc:
        raise WatchmanConfigurationError(f"Watchman check {candidate.id!r} has invalid scopes") from exc
    if not scopes:
        raise WatchmanConfigurationError(f"Watchman check {candidate.id!r} must declare at least one scope")
    return candidate
