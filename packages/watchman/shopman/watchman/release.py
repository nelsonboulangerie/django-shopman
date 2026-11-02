"""Release identity: what THIS process was built from, and whether the live one is current.

Two halves of the same contract (``docs/reference/release-contract.md`` in the
Shopman repository):

* the **address**: every deployable component answers ``/health/release`` with
  ``{schema_version, component, release_id, build_sha}``. The values come from
  the image (``SHOPMAN_BUILD_SHA``, ``SHOPMAN_RELEASE_ID`` and
  ``SHOPMAN_RELEASE_COMPONENT``, set as build args in the last layer), never
  from a provider API at request time, and are never secret;
* the **probe**: :class:`ReleaseIdentityCheck` asks each configured address and
  compares the served commit with the commit the host expects (normally the head
  of the main branch).

An image built without identity answers with empty strings instead of
inventing a number: "unidentified" is a fact the probe can fail on, a made-up
version is not.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.http import JsonResponse
from django.utils.module_loading import import_string
from django.views import View

from shopman.watchman.contracts import CheckContext, CheckResult, Scope, Status

SCHEMA_VERSION = 1
BUILD_SHA_ENV = "SHOPMAN_BUILD_SHA"
RELEASE_ID_ENV = "SHOPMAN_RELEASE_ID"
COMPONENT_ENV = "SHOPMAN_RELEASE_COMPONENT"
RELEASE_HEADER = "X-Shopman-Release"

SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
RELEASE_ID_PATTERN = re.compile(r"^\d{8}-\d{4}-[0-9a-f]{7}$")
COMPONENT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")

DEFAULT_TARGET_TIMEOUT_SECONDS = 5.0
MAX_BODY_BYTES = 4096
USER_AGENT = "shopman-watchman-release/1"


class ReleasePayloadError(ValueError):
    """The address answered, but not with a release identity."""


@dataclass(frozen=True, slots=True)
class ReleaseIdentity:
    component: str
    release_id: str
    build_sha: str

    @property
    def identified(self) -> bool:
        return bool(self.build_sha)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "component": self.component,
            "release_id": self.release_id,
            "build_sha": self.build_sha,
        }


def current_release(environ: Mapping[str, str] | None = None, *, default_component: str = "") -> ReleaseIdentity:
    """Identity of this process, read from the image environment.

    A malformed value is reported as empty: the image carries a contract, and a
    value outside it is as unusable as no value at all.
    """

    env = os.environ if environ is None else environ
    build_sha = env.get(BUILD_SHA_ENV, "").strip().lower()
    release_id = env.get(RELEASE_ID_ENV, "").strip().lower()
    component = env.get(COMPONENT_ENV, "").strip() or default_component
    return ReleaseIdentity(
        component=component if COMPONENT_PATTERN.match(component or "") else default_component,
        release_id=release_id if RELEASE_ID_PATTERN.match(release_id) else "",
        build_sha=build_sha if SHA_PATTERN.match(build_sha) else "",
    )


def parse_release_payload(payload: object) -> ReleaseIdentity:
    """Validate what a ``/health/release`` address answered."""

    if not isinstance(payload, Mapping):
        raise ReleasePayloadError("payload is not an object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ReleasePayloadError("unsupported schema_version")
    values: dict[str, str] = {}
    for key in ("component", "release_id", "build_sha"):
        value = payload.get(key)
        if not isinstance(value, str):
            raise ReleasePayloadError(f"{key} must be a string")
        values[key] = value.strip()
    if not COMPONENT_PATTERN.match(values["component"]):
        raise ReleasePayloadError("component is invalid")
    if values["build_sha"] and not SHA_PATTERN.match(values["build_sha"]):
        raise ReleasePayloadError("build_sha is invalid")
    if values["release_id"] and not RELEASE_ID_PATTERN.match(values["release_id"]):
        raise ReleasePayloadError("release_id is invalid")
    return ReleaseIdentity(**values)


class ReleaseIdentityView(View):
    """``GET /health/release/``: constant, cheap, public and never secret."""

    component = "web"

    def get(self, request):
        identity = current_release(default_component=self.component)
        response = JsonResponse(identity.to_dict())
        response["Cache-Control"] = "no-store"
        response["X-Content-Type-Options"] = "nosniff"
        if identity.release_id:
            response[RELEASE_HEADER] = identity.release_id
        return response


# ── Probe ─────────────────────────────────────────────────────────────────────

Fetcher = Callable[[str, float], object]
#: ``(target_id, live_sha, expected_sha) -> True | False | None``: does the live
#: commit already serve everything the expected commit requires of this target?
#: ``None`` means the host cannot tell (no history at hand).
Equivalence = Callable[[str, str, str], bool | None]


def fetch_json(url: str, timeout: float) -> object:
    if not url.startswith(("https://", "http://")):
        raise ValueError("release address must be http(s)")
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - scheme checked above
        body = response.read(MAX_BODY_BYTES + 1)
    if len(body) > MAX_BODY_BYTES:
        raise ReleasePayloadError("payload is too large")
    try:
        return json.loads(body)
    except ValueError as exc:
        raise ReleasePayloadError("payload is not JSON") from exc


_SEVERITY = (Status.FAIL, Status.UNKNOWN, Status.WARN, Status.PASS)


def _worst(statuses: Sequence[Status]) -> Status:
    for candidate in _SEVERITY:
        if candidate in statuses:
            return candidate
    return Status.UNKNOWN


class ReleaseIdentityCheck:
    """Compare the commit each live component serves with the commit the host expects.

    Configuration, in ``WATCHMAN["RELEASE_IDENTITY"]``::

        {
            "expected_sha_env": "WATCHMAN_EXPECTED_RELEASE_SHA",
            "equivalence": "myproject.release.component_unchanged",  # optional
            "targets": [
                {"id": "web", "url_env": "WATCHMAN_RELEASE_URL_WEB"},
            ],
        }

    Only environment variable NAMES live in settings: the addresses and the
    expected commit belong to the environment running the probe (a CI job, an
    operator's shell), not to the observed application.

    Outcomes per target: ``pass`` when the live commit is the expected one, or
    the host's equivalence hook says nothing in between touched the component;
    ``fail`` when the address answers something unusable, an image without
    identity, another component, or a commit that is behind; ``unknown`` when
    the question could not be asked (no address, network error, no expected
    commit). Absence of proof is never reported as proof.
    """

    id = "release_identity"
    description = "Each live component serves the commit the main branch expects."
    scopes = frozenset({Scope.DIAGNOSTIC})
    timeout_seconds = 30.0

    def __init__(self, fetcher: Fetcher | None = None, environ: Mapping[str, str] | None = None):
        self._fetch = fetcher or fetch_json
        self._environ = environ

    def _env(self) -> Mapping[str, str]:
        return os.environ if self._environ is None else self._environ

    def run(self, context: CheckContext) -> CheckResult:
        config = (getattr(settings, "WATCHMAN", {}) or {}).get("RELEASE_IDENTITY")
        if not isinstance(config, Mapping):
            return CheckResult(
                id=self.id,
                status=Status.UNKNOWN,
                summary="release identity probe is not configured",
                remediation="Configure WATCHMAN['RELEASE_IDENTITY'] with targets and expected_sha_env.",
            )
        targets = config.get("targets") or ()
        if not isinstance(targets, Sequence) or isinstance(targets, (str, bytes)) or not targets:
            return CheckResult(
                id=self.id,
                status=Status.FAIL,
                summary="release identity targets are invalid",
                remediation="Declare WATCHMAN['RELEASE_IDENTITY']['targets'] as a non-empty list.",
            )

        env = self._env()
        expected = env.get(str(config.get("expected_sha_env") or ""), "").strip().lower()
        if expected and not SHA_PATTERN.match(expected):
            return CheckResult(
                id=self.id,
                status=Status.FAIL,
                summary="expected commit is not a full SHA",
                remediation="Export the expected commit as a 40-character SHA.",
            )
        equivalence: Equivalence | None = None
        if config.get("equivalence"):
            equivalence = import_string(str(config["equivalence"]))

        components: list[dict[str, Any]] = []
        for target in targets:
            if not isinstance(target, Mapping) or not target.get("id") or not target.get("url_env"):
                return CheckResult(
                    id=self.id,
                    status=Status.FAIL,
                    summary="release identity target needs id and url_env",
                )
            components.append(self._probe_target(target, env, expected, equivalence, context))

        statuses = [Status(item["status"]) for item in components]
        status = _worst(statuses)
        behind = [item["id"] for item in components if item["status"] != Status.PASS.value]
        summary = (
            f"{len(components)} components serve the expected release"
            if not behind
            else f"{len(behind)} of {len(components)} components need attention: {', '.join(behind)}"
        )
        return CheckResult(
            id=self.id,
            status=status,
            summary=summary,
            evidence={"expected_sha": expected, "components": components},
            remediation=(
                "Compare each component's served commit with the deploy run of the expected commit; "
                "a component that stayed behind is republished from the top of main."
                if behind
                else None
            ),
        )

    def _probe_target(
        self,
        target: Mapping[str, Any],
        env: Mapping[str, str],
        expected: str,
        equivalence: Equivalence | None,
        context: CheckContext,
    ) -> dict[str, Any]:
        target_id = str(target["id"])
        url = env.get(str(target["url_env"]), "").strip()
        item: dict[str, Any] = {"id": target_id}
        if not url:
            return {**item, "status": Status.UNKNOWN.value, "reason": "address_not_configured",
                    "required_env": str(target["url_env"])}
        item["url"] = url
        timeout = min(
            float(target.get("timeout_seconds", DEFAULT_TARGET_TIMEOUT_SECONDS)),
            max(0.1, context.remaining_seconds()),
        )
        try:
            identity = parse_release_payload(self._fetch(url, timeout))
        except ReleasePayloadError as exc:
            return {**item, "status": Status.FAIL.value, "reason": "invalid_payload", "detail": str(exc)}
        except (OSError, urllib.error.URLError, ValueError) as exc:
            return {**item, "status": Status.UNKNOWN.value, "reason": "unreachable", "detail": exc.__class__.__name__}

        item.update(live_sha=identity.build_sha, release_id=identity.release_id, component=identity.component)
        if identity.component != target_id:
            return {**item, "status": Status.FAIL.value, "reason": "other_component"}
        if not identity.identified:
            return {**item, "status": Status.FAIL.value, "reason": "unidentified_build"}
        if not expected:
            return {**item, "status": Status.UNKNOWN.value, "reason": "expected_sha_missing"}
        if identity.build_sha == expected:
            return {**item, "status": Status.PASS.value, "reason": "same_commit"}
        if equivalence is None:
            return {**item, "status": Status.FAIL.value, "reason": "different_commit"}
        verdict = equivalence(target_id, identity.build_sha, expected)
        if verdict is True:
            return {**item, "status": Status.PASS.value, "reason": "unchanged_since_live"}
        if verdict is False:
            return {**item, "status": Status.FAIL.value, "reason": "behind_expected"}
        return {**item, "status": Status.UNKNOWN.value, "reason": "history_unavailable"}
