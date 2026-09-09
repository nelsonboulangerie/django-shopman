"""HTTP semantics shared by the canonical Marketing v2 endpoints."""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from dataclasses import dataclass

from django.utils.cache import patch_vary_headers
from django.utils.http import parse_etags
from rest_framework import exceptions
from rest_framework.response import Response

from shopman.backstage.api.projections import projection_data
from shopman.backstage.projections.marketing_v2 import (
    CONTRACT,
    MarketingActionProjectionV2,
    MarketingEnvelopeV2,
    MarketingErrorEnvelopeV2,
    MarketingErrorV2,
)

_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$")
_CACHE_CONTROL = "private, no-cache, must-revalidate"
_VOLATILE_ETAG_FIELDS = frozenset({"age_seconds", "as_of", "expires_in_seconds", "generated_at"})


@dataclass(frozen=True, slots=True)
class MarketingV2Problem(Exception):
    """A safe, presentation-keyed problem exposed by the v2 HTTP boundary."""

    status_code: int
    code: str
    detail: str
    retryable: bool = False
    field_errors: dict[str, tuple[str, ...]] | None = None
    current_version: int | None = None
    actions: tuple[MarketingActionProjectionV2, ...] = ()
    retry_after: int | None = None


def marketing_v2_response(request, envelope: MarketingEnvelopeV2) -> Response:
    """Return one private conditional response with safe correlation metadata."""

    payload = projection_data(envelope)
    etag = _weak_etag(payload)
    if _etag_matches(request.headers.get("If-None-Match", ""), etag):
        response = Response(status=304)
    else:
        response = Response(payload)
    return _attach_headers(
        response,
        request=request,
        resource_version=envelope.resource_version,
        etag=etag,
    )


def marketing_v2_error_response(
    request,
    *,
    status_code: int,
    code: str,
    detail: str,
    retryable: bool = False,
    field_errors: dict[str, tuple[str, ...]] | None = None,
    current_version: int | None = None,
    actions: tuple[MarketingActionProjectionV2, ...] = (),
    retry_after: int | float | None = None,
) -> Response:
    """Render the strict v2 problem envelope without leaking exception text."""

    request_id = request_id_for(request)
    error = MarketingErrorEnvelopeV2(
        error=MarketingErrorV2(
            code=code,
            detail=detail,
            retryable=retryable,
            field_errors=field_errors or {},
            request_id=request_id,
            current_version=current_version,
            actions=actions,
        )
    )
    response = Response(projection_data(error), status=status_code)
    if retry_after is not None:
        response["Retry-After"] = str(max(1, math.ceil(float(retry_after))))
    return _attach_headers(response, request=request)


def response_for_exception(request, exc: Exception) -> Response | None:
    """Map the status classes promised by Marketing v2; unknown errors propagate."""

    if isinstance(exc, MarketingV2Problem):
        return marketing_v2_error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            detail=exc.detail,
            retryable=exc.retryable,
            field_errors=exc.field_errors,
            current_version=exc.current_version,
            actions=exc.actions,
            retry_after=exc.retry_after,
        )
    if isinstance(exc, (exceptions.NotAuthenticated, exceptions.AuthenticationFailed)):
        return marketing_v2_error_response(
            request,
            status_code=401,
            code="authentication_required",
            detail="presentation.authentication_required",
        )
    if isinstance(exc, exceptions.PermissionDenied):
        return marketing_v2_error_response(
            request,
            status_code=403,
            code="capability_required",
            detail="presentation.capability_required",
        )
    if isinstance(exc, exceptions.NotFound):
        return marketing_v2_error_response(
            request,
            status_code=404,
            code="resource_not_found",
            detail="presentation.resource_not_found",
        )
    if isinstance(exc, exceptions.Throttled):
        return marketing_v2_error_response(
            request,
            status_code=429,
            code="rate_limited",
            detail="presentation.rate_limited",
            retryable=True,
            retry_after=exc.wait,
        )
    return None


def request_id_for(request) -> str:
    existing = getattr(request, "_marketing_v2_request_id", "")
    if existing:
        return existing
    supplied = str(request.headers.get("X-Request-ID") or "").strip()
    request_id = supplied if _REQUEST_ID.fullmatch(supplied) else f"req_{uuid.uuid4().hex}"
    request._marketing_v2_request_id = request_id
    return request_id


def _attach_headers(
    response: Response,
    *,
    request,
    resource_version: int | None = None,
    etag: str = "",
) -> Response:
    response["Cache-Control"] = _CACHE_CONTROL
    response["X-Request-ID"] = request_id_for(request)
    response["X-Contract-Version"] = CONTRACT
    if resource_version is not None:
        response["X-Resource-Version"] = str(resource_version)
    if etag:
        response["ETag"] = etag
    patch_vary_headers(response, ("Cookie",))
    return response


def _weak_etag(payload: dict) -> str:
    canonical = json.dumps(
        _without_volatile_fields(payload),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    return f'W/"marketing-v2-{digest}"'


def _without_volatile_fields(value):
    if isinstance(value, dict):
        return {
            key: _without_volatile_fields(item)
            for key, item in value.items()
            if key not in _VOLATILE_ETAG_FIELDS
        }
    if isinstance(value, list):
        return [_without_volatile_fields(item) for item in value]
    return value


def _etag_matches(header: str, etag: str) -> bool:
    candidates = parse_etags(header)
    return "*" in candidates or etag in candidates
