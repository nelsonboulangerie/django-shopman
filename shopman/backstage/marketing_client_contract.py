"""Deterministic OpenAPI and TypeScript client artifacts for Marketing v2."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from shopman.backstage.projections.marketing_v2 import schema

OPENAPI_VERSION = "3.1.0"
API_VERSION = "2.0.0"
BOARD_PATH = "/api/v1/backstage/marketing/v2/"
ANNOUNCEMENT_PATH = "/api/v1/backstage/marketing/v2/announcements/{announcement_id}/"
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
    response = {
        "description": "Canonical Marketing v2 projection.",
        "content": {
            "application/json": {
                "schema": {"$ref": f"{_COMPONENT_REF_PREFIX}MarketingEnvelopeV2"}
            }
        },
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
                    "responses": {"200": response},
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
                        }
                    ],
                    "responses": {"200": response},
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
        "}",
        "",
        "export type MarketingV2Transport = <T>(",
        "  href: string,",
        "  options: MarketingV2TransportOptions,",
        ") => Promise<T>;",
        "",
        "export interface MarketingV2Client {",
        "  getMarketingBoard(): Promise<MarketingEnvelopeV2>;",
        "  getMarketingAnnouncement(announcementId: number): Promise<MarketingEnvelopeV2>;",
        "}",
        "",
        f'export const MARKETING_V2_BOARD_PATH = "{BOARD_PATH}" as const;',
        "",
        "export function createMarketingV2Client(",
        "  transport: MarketingV2Transport,",
        "): MarketingV2Client {",
        "  const readOptions: MarketingV2TransportOptions = {",
        '    method: "GET",',
        '    credentials: "same-origin",',
        "  };",
        "  return {",
        "    getMarketingBoard: () =>",
        "      transport<MarketingEnvelopeV2>(MARKETING_V2_BOARD_PATH, readOptions),",
        "    getMarketingAnnouncement: (announcementId: number) => {",
        "      if (!Number.isSafeInteger(announcementId) || announcementId <= 0) {",
        '        throw new RangeError("announcementId must be a positive integer");',
        "      }",
        "      return transport<MarketingEnvelopeV2>(",
        "        `/api/v1/backstage/marketing/v2/announcements/${announcementId}/`,",
        "        readOptions,",
        "      );",
        "    },",
        "  };",
        "}",
        "",
    ])
    return "\n".join(blocks).rstrip() + "\n"


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
