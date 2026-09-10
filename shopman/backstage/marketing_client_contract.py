"""Deterministic OpenAPI and TypeScript client artifacts for Marketing v2."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from shopman.backstage.marketing_history import (
    HISTORY_ACTORS,
    HISTORY_OUTCOMES,
    HISTORY_PERIODS,
    HISTORY_PLATFORMS,
)
from shopman.backstage.projections.marketing_v2 import error_schema, schema

OPENAPI_VERSION = "3.1.0"
API_VERSION = "2.0.0"
BOARD_PATH = "/api/v1/backstage/marketing/v2/"
ANNOUNCEMENT_PATH = "/api/v1/backstage/marketing/v2/announcements/{announcement_id}/"
HISTORY_PATH = "/api/v1/backstage/marketing/v2/history/"
_REF_PREFIX = "#/$defs/"
_COMPONENT_REF_PREFIX = "#/components/schemas/"
_SAFE_TS_NAME = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


def marketing_openapi() -> dict[str, Any]:
    """Build the narrow OpenAPI boundary currently supported by Marketing v2."""

    projection_schema = deepcopy(schema())
    definitions = projection_schema.pop("$defs", {})
    components = {
        name: _rewrite_refs(definition)
        for name, definition in definitions.items()
    }
    components["MarketingEnvelopeV2"] = _rewrite_refs(projection_schema)
    error_contract = deepcopy(error_schema())
    error_definitions = error_contract.pop("$defs", {})
    for name, definition in error_definitions.items():
        rewritten = _rewrite_refs(definition)
        existing = components.get(name)
        if existing is not None and existing != rewritten:
            raise ValueError(f"Conflicting Marketing schema definition: {name}")
        components[name] = rewritten
    components["MarketingErrorEnvelopeV2"] = _rewrite_refs(error_contract)
    response_headers = {
        "ETag": {"schema": {"type": "string"}},
        "X-Request-ID": {"schema": {"type": "string"}},
        "X-Resource-Version": {"schema": {"type": "integer", "minimum": 1}},
        "X-Contract-Version": {"schema": {"type": "string", "const": "marketing.v2"}},
    }
    response = {
        "description": "Canonical Marketing v2 projection.",
        "headers": response_headers,
        "content": {
            "application/json": {
                "schema": {"$ref": f"{_COMPONENT_REF_PREFIX}MarketingEnvelopeV2"}
            }
        },
    }
    not_modified = {
        "description": "The caller already has the current semantic representation.",
        "headers": response_headers,
    }
    error_response = {
        "description": "Canonical Marketing v2 error.",
        "headers": {
            "X-Request-ID": {"schema": {"type": "string"}},
            "X-Contract-Version": {"schema": {"type": "string", "const": "marketing.v2"}},
        },
        "content": {
            "application/json": {
                "schema": {"$ref": f"{_COMPONENT_REF_PREFIX}MarketingErrorEnvelopeV2"}
            }
        },
    }
    conditional_parameter = {
        "name": "If-None-Match",
        "in": "header",
        "required": False,
        "schema": {"type": "string"},
    }
    return {
        "openapi": OPENAPI_VERSION,
        "info": {
            "title": "Shopman Marketing Projection API",
            "version": API_VERSION,
        },
        "paths": {
            BOARD_PATH: {
                "get": {
                    "operationId": "getMarketingBoard",
                    "summary": "Read the canonical Marketing board",
                    "tags": ["marketing-v2"],
                    "parameters": [conditional_parameter],
                    "responses": {
                        "200": response,
                        "304": not_modified,
                        "401": error_response,
                        "403": error_response,
                        "429": {
                            **error_response,
                            "headers": {
                                **error_response["headers"],
                                "Retry-After": {"schema": {"type": "integer", "minimum": 1}},
                            },
                        },
                        "503": error_response,
                    },
                }
            },
            ANNOUNCEMENT_PATH: {
                "get": {
                    "operationId": "getMarketingAnnouncement",
                    "summary": "Read one canonical Marketing announcement",
                    "tags": ["marketing-v2"],
                    "parameters": [
                        {
                            "name": "announcement_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer", "minimum": 1},
                        },
                        conditional_parameter,
                    ],
                    "responses": {
                        "200": response,
                        "304": not_modified,
                        "401": error_response,
                        "403": error_response,
                        "404": error_response,
                        "429": error_response,
                        "503": error_response,
                    },
                }
            },
            HISTORY_PATH: {
                "get": {
                    "operationId": "getMarketingHistory",
                    "summary": "Read a stable cursor page of Marketing history",
                    "tags": ["marketing-v2"],
                    "parameters": [
                        {
                            "name": "cursor",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "schema": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 100,
                                "default": 50,
                            },
                        },
                        {
                            "name": "outcome",
                            "in": "query",
                            "required": False,
                            "schema": {
                                "type": "string",
                                "enum": HISTORY_OUTCOMES,
                            },
                        },
                        {
                            "name": "platform",
                            "in": "query",
                            "required": False,
                            "schema": {
                                "type": "string",
                                "enum": HISTORY_PLATFORMS,
                            },
                        },
                        {
                            "name": "actor",
                            "in": "query",
                            "required": False,
                            "schema": {
                                "type": "string",
                                "enum": HISTORY_ACTORS,
                            },
                        },
                        {
                            "name": "period",
                            "in": "query",
                            "required": False,
                            "schema": {
                                "type": "string",
                                "enum": HISTORY_PERIODS,
                                "default": "all",
                            },
                        },
                        conditional_parameter,
                    ],
                    "responses": {
                        "200": response,
                        "304": not_modified,
                        "401": error_response,
                        "403": error_response,
                        "422": error_response,
                        "429": error_response,
                        "503": error_response,
                    },
                }
            },
        },
        "components": {
            "securitySchemes": {
                "sessionCookie": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": "sessionid",
                }
            },
            "schemas": components,
        },
        "security": [{"sessionCookie": []}],
    }


def render_marketing_openapi_json() -> str:
    return json.dumps(marketing_openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_marketing_client_ts() -> str:
    """Render types and GET operations from the same in-memory OpenAPI document."""

    document = marketing_openapi()
    schemas = document["components"]["schemas"]
    blocks = [
        "// AUTO-GENERATED — do not edit by hand.",
        "// Source of truth: contracts/openapi/marketing_v2.openapi.json",
        "// Regenerate with: python manage.py export_marketing_client",
        "",
    ]
    blocks.extend(
        _render_component(name, component)
        for name, component in sorted(schemas.items())
    )
    blocks.extend([
        'export type MarketingActionKind = MarketingActionProjectionV2["kind"];',
        'export type MarketingActionMethod = MarketingActionProjectionV2["method"];',
        'export type MarketingActionPriority = MarketingActionProjectionV2["priority"];',
        'export type MarketingFreshnessState = FreshnessProjectionV2["state"];',
        "",
        "export interface MarketingV2TransportOptions {",
        '  method: "GET";',
        '  credentials: "same-origin";',
        "  headers?: Record<string, string>;",
        "}",
        "",
        "export interface MarketingV2ReadOptions {",
        "  etag?: string;",
        "  requestId?: string;",
        "}",
        "",
        _typescript_union("MarketingHistoryOutcome", HISTORY_OUTCOMES),
        _typescript_union("MarketingHistoryPlatform", HISTORY_PLATFORMS),
        _typescript_union("MarketingHistoryActor", HISTORY_ACTORS),
        _typescript_union("MarketingHistoryPeriod", HISTORY_PERIODS),
        "",
        "export interface MarketingV2HistoryOptions extends MarketingV2ReadOptions {",
        "  cursor?: string;",
        "  limit?: number;",
        "  outcome?: MarketingHistoryOutcome;",
        "  platform?: MarketingHistoryPlatform;",
        "  actor?: MarketingHistoryActor;",
        "  period?: MarketingHistoryPeriod;",
        "}",
        "",
        "export type MarketingV2Transport = <T>(",
        "  href: string,",
        "  options: MarketingV2TransportOptions,",
        ") => Promise<T>;",
        "",
        "export interface MarketingV2Client {",
        "  getMarketingBoard(options?: MarketingV2ReadOptions): Promise<MarketingEnvelopeV2>;",
        "  getMarketingAnnouncement(announcementId: number, options?: MarketingV2ReadOptions): Promise<MarketingEnvelopeV2>;",
        "  getMarketingHistory(options?: MarketingV2HistoryOptions): Promise<MarketingEnvelopeV2>;",
        "}",
        "",
        f'export const MARKETING_V2_BOARD_PATH = "{BOARD_PATH}" as const;',
        f'export const MARKETING_V2_HISTORY_PATH = "{HISTORY_PATH}" as const;',
        "",
        "function marketingReadOptions(options: MarketingV2ReadOptions = {}): MarketingV2TransportOptions {",
        "  const headers: Record<string, string> = {};",
        '  if (options.etag) headers["If-None-Match"] = options.etag;',
        '  if (options.requestId) headers["X-Request-ID"] = options.requestId;',
        "  return {",
        '    method: "GET",',
        '    credentials: "same-origin",',
        "    ...(Object.keys(headers).length ? { headers } : {}),",
        "  };",
        "}",
        "",
        "export function marketingHistoryHref(options: MarketingV2HistoryOptions = {}): string {",
        "  if (options.limit != null && (!Number.isSafeInteger(options.limit) || options.limit < 1 || options.limit > 100)) {",
        '    throw new RangeError("limit must be an integer between 1 and 100");',
        "  }",
        "  const query = new URLSearchParams();",
        '  if (options.cursor) query.set("cursor", options.cursor);',
        '  if (options.limit != null) query.set("limit", String(options.limit));',
        '  if (options.outcome) query.set("outcome", options.outcome);',
        '  if (options.platform) query.set("platform", options.platform);',
        '  if (options.actor) query.set("actor", options.actor);',
        '  if (options.period && options.period !== "all") query.set("period", options.period);',
        "  const suffix = query.size ? `?${query.toString()}` : \"\";",
        "  return `${MARKETING_V2_HISTORY_PATH}${suffix}`;",
        "}",
        "",
        "export function createMarketingV2Client(",
        "  transport: MarketingV2Transport,",
        "): MarketingV2Client {",
        "  return {",
        "    getMarketingBoard: (options) =>",
        "      transport<MarketingEnvelopeV2>(MARKETING_V2_BOARD_PATH, marketingReadOptions(options)),",
        "    getMarketingAnnouncement: (announcementId: number, options) => {",
        "      if (!Number.isSafeInteger(announcementId) || announcementId <= 0) {",
        '        throw new RangeError("announcementId must be a positive integer");',
        "      }",
        "      return transport<MarketingEnvelopeV2>(",
        "        `/api/v1/backstage/marketing/v2/announcements/${announcementId}/`,",
        "        marketingReadOptions(options),",
        "      );",
        "    },",
        "    getMarketingHistory: (options = {}) => {",
        "      return transport<MarketingEnvelopeV2>(",
        "        marketingHistoryHref(options),",
        "        marketingReadOptions(options),",
        "      );",
        "    },",
        "  };",
        "}",
        "",
    ])
    return "\n".join(blocks).rstrip() + "\n"


def _typescript_union(name: str, values: tuple[str, ...]) -> str:
    options = " | ".join(json.dumps(value) for value in values)
    return f"export type {name} = {options};"


def _rewrite_refs(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                f"{_COMPONENT_REF_PREFIX}{item.removeprefix(_REF_PREFIX)}"
                if key == "$ref" and isinstance(item, str) and item.startswith(_REF_PREFIX)
                else _rewrite_refs(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_rewrite_refs(item) for item in value]
    return value


def _render_component(name: str, component: dict[str, Any]) -> str:
    if component.get("type") != "object" or "properties" not in component:
        return f"export type {name} = {_ts_type(component)};\n"
    required = frozenset(component.get("required", ()))
    lines = [f"export interface {name} {{"]
    for property_name, property_schema in component["properties"].items():
        rendered_name = (
            property_name
            if _SAFE_TS_NAME.fullmatch(property_name)
            else json.dumps(property_name)
        )
        optional = "" if property_name in required else "?"
        lines.append(
            f"  {rendered_name}{optional}: {_ts_type(property_schema)};"
        )
    lines.append("}")
    return "\n".join(lines) + "\n"


def _ts_type(value: dict[str, Any]) -> str:
    reference = value.get("$ref")
    if isinstance(reference, str):
        return reference.rsplit("/", 1)[-1]
    if "const" in value:
        return json.dumps(value["const"], ensure_ascii=False)
    if "enum" in value:
        return " | ".join(
            json.dumps(item, ensure_ascii=False) for item in value["enum"]
        )
    variants = value.get("anyOf") or value.get("oneOf")
    if variants:
        return " | ".join(_ts_type(item) for item in variants)

    kind = value.get("type")
    if kind == "array":
        return f"Array<{_ts_type(value.get('items', {}))}>"
    if kind == "object":
        additional = value.get("additionalProperties")
        if isinstance(additional, dict):
            return f"Record<string, {_ts_type(additional)}>"
        properties = value.get("properties")
        if isinstance(properties, dict):
            required = frozenset(value.get("required", ()))
            fields = []
            for name, field_schema in properties.items():
                optional = "" if name in required else "?"
                fields.append(f"{name}{optional}: {_ts_type(field_schema)}")
            return "{ " + "; ".join(fields) + " }"
        return "Record<string, unknown>"
    if kind in {"integer", "number"}:
        return "number"
    if kind == "boolean":
        return "boolean"
    if kind == "null":
        return "null"
    if kind == "string":
        return "string"
    raise TypeError(f"Unsupported Marketing OpenAPI schema node: {value!r}")
