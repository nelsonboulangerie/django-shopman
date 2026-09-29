"""Configuração pública e conservadora da conferência de localização.

O recurso é consultivo: esta projeção nunca calcula cobertura, taxa ou promessa.
Configuração ausente, incompleta, fora dos limites ou sem o mapa canônico cai
para ``off``. Assim um deploy não cria leitura de GPS nem UI por acidente.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


DEFAULT_THRESHOLD_M = 500
DEFAULT_MAX_ACCURACY_M = 250
DEFAULT_MAXIMUM_AGE_MS = 30_000
DEFAULT_POLICY_VERSION = "v1"


@dataclass(frozen=True)
class AddressLocationDivergenceProjection:
    mode: str
    threshold_m: int
    max_accuracy_m: int
    maximum_age_ms: int
    policy_version: str


def _off() -> AddressLocationDivergenceProjection:
    return AddressLocationDivergenceProjection(
        mode="off",
        threshold_m=DEFAULT_THRESHOLD_M,
        max_accuracy_m=DEFAULT_MAX_ACCURACY_M,
        maximum_age_ms=DEFAULT_MAXIMUM_AGE_MS,
        policy_version=DEFAULT_POLICY_VERSION,
    )


def _bounded_int(value: Any, *, minimum: int, maximum: int) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if minimum <= parsed <= maximum else None


def build_address_location_divergence(
    raw: Any,
    *,
    map_enabled: bool,
) -> AddressLocationDivergenceProjection:
    """Validate tenant config and fail closed.

    ``measure`` and ``visible`` depend on the canonical map experience. The
    client therefore never receives an active mode while that kill switch is
    off, even if stale tenant JSON says otherwise.
    """

    if not map_enabled or not isinstance(raw, Mapping):
        return _off()

    mode = raw.get("mode")
    if mode == "off":
        return _off()
    if mode not in {"measure", "visible"}:
        return _off()

    threshold_m = _bounded_int(raw.get("threshold_m"), minimum=100, maximum=10_000)
    max_accuracy_m = _bounded_int(raw.get("max_accuracy_m"), minimum=20, maximum=2_000)
    maximum_age_ms = _bounded_int(raw.get("maximum_age_ms"), minimum=0, maximum=300_000)
    policy_version = raw.get("policy_version")
    if (
        threshold_m is None
        or max_accuracy_m is None
        or maximum_age_ms is None
        or not isinstance(policy_version, str)
        or not policy_version.strip()
        or len(policy_version.strip()) > 40
    ):
        return _off()

    return AddressLocationDivergenceProjection(
        mode=mode,
        threshold_m=threshold_m,
        max_accuracy_m=max_accuracy_m,
        maximum_age_ms=maximum_age_ms,
        policy_version=policy_version.strip(),
    )
