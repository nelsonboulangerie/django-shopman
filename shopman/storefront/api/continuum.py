"""Endpoint credentialless do snapshot estrutural público Continuum 0.2."""

from __future__ import annotations

from django.http import HttpResponse, HttpResponseNotModified
from django.utils.http import parse_etags
from django.views import View

from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
from shopman.storefront.continuum import (
    candidate_enabled,
    continuum_settings,
    current_or_build_head,
    head_age_ms,
    limits,
    rendered_message,
    validate_message_limits,
)
from shopman.storefront.observability import (
    capture_catalog_timing,
    catalog_stage,
    log_catalog_observation,
)


def _problem(status: int, detail: str) -> HttpResponse:
    response = HttpResponse(
        ('{"detail":"' + detail.replace('"', "") + '"}').encode(),
        status=status,
        content_type="application/problem+json",
    )
    response["Cache-Control"] = "private, no-store"
    return response


def _request_head_bytes(request) -> int:
    total = len(request.get_full_path().encode("utf-8"))
    for name, value in request.headers.items():
        total += len(name.encode("utf-8")) + len(value.encode("utf-8")) + 4
    return total


def _has_credentials(request) -> bool:
    credential_headers = (
        "Cookie",
        "Authorization",
        "Proxy-Authorization",
        "X-SSL-Client-Cert",
    )
    return any(request.headers.get(name) for name in credential_headers) or bool(request.GET)


def _if_none_match_matches(header: str, current_etag: str) -> bool:
    """Aplica a comparação fraca exigida por If-None-Match em GET/HEAD."""
    current_opaque = current_etag.removeprefix("W/")
    return any(
        candidate == "*" or candidate.removeprefix("W/") == current_opaque
        for candidate in parse_etags(header)
    )


def _snapshot_headers(head) -> dict[str, str]:
    config = continuum_settings()
    fresh_ms = int(config.get("fresh_for_ms", 30_000))
    stale_ms = int(config.get("stale_if_error_ms", 120_000))
    return {
        "ETag": head.etag,
        "Continuum-Stream": head.stream_id,
        "Continuum-Epoch": head.epoch,
        "Continuum-Sequence": f"{head.sequence:020d}",
        "Continuum-State-Token": head.state_token,
        "Continuum-State-Digest": head.state_digest,
        "Continuum-Fresh-For-Ms": str(fresh_ms),
        "Continuum-Stale-If-Error-Ms": str(stale_ms),
        "Continuum-Age-Ms": str(head_age_ms(head)),
        "Cache-Control": (
            f"public, max-age={fresh_ms // 1000}, s-maxage={fresh_ms // 1000}, "
            f"stale-if-error={stale_ms // 1000}, stale-while-revalidate={stale_ms // 1000}"
        ),
        "Vary": "Accept",
    }


class CatalogStructureSnapshotView(View):
    """GET público versionado; nunca lê sessão nem define cookie."""

    http_method_names = ["get", "head"]

    def get(self, request):
        if not candidate_enabled():
            return _problem(404, "Snapshot público desativado.")

        configured_limits = limits()
        if _request_head_bytes(request) > int(configured_limits["max_request_head_bytes"]):
            return _problem(431, "Cabeçalhos acima do limite.")
        if _has_credentials(request):
            return _problem(400, "Este endpoint público não aceita credenciais nem parâmetros.")
        if_none_match = request.headers.get("If-None-Match", "")
        if len(if_none_match.encode("utf-8")) > int(configured_limits["max_request_identifier_bytes"]):
            return _problem(431, "Identificador acima do limite.")

        with capture_catalog_timing() as timing:
            with catalog_stage("projection"):
                head, head_status = current_or_build_head(channel_ref=STOREFRONT_CHANNEL_REF)
                body, cache_status = rendered_message(head)
                try:
                    validate_message_limits(head.message, body)
                except ValueError:
                    response = _problem(503, "Snapshot excedeu o limite seguro.")
                    response["Server-Timing"] = timing.server_timing()
                    return response

            headers = _snapshot_headers(head)
            if _if_none_match_matches(if_none_match, head.etag):
                response = HttpResponseNotModified()
                for name, value in headers.items():
                    response[name] = value
                status = 304
                response_bytes = 0
            else:
                response = HttpResponse(
                    body,
                    content_type="application/cloudevents+json; continuum=0.2; schema=1",
                )
                for name, value in headers.items():
                    response[name] = value
                status = 200
                response_bytes = len(body)
            response["Server-Timing"] = timing.server_timing()

        log_catalog_observation(
            path="continuum_catalog_structure",
            mode="snapshot",
            status=status,
            query_count=timing.query_count,
            response_bytes=response_bytes,
            cache_status=f"{head_status}:{cache_status}",
            snapshot_sequence=head.sequence,
            snapshot_age_ms=head_age_ms(head),
            projection_ms=timing.durations_ms.get("projection", 0.0),
            availability_ms=timing.durations_ms.get("availability", 0.0),
            personalization_ms=timing.durations_ms.get("personalization", 0.0),
            db_ms=timing.durations_ms.get("db", 0.0),
        )
        return response

    def head(self, request):
        response = self.get(request)
        response.content = b""
        return response
