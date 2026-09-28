#!/usr/bin/env python3
"""Structural and referential validation for the neutral Continuum 0.2 corpus."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parent
KIND_FRAGMENT = {
    "snapshot": "snapshotData",
    "patch": "patchData",
    "invalidate": "invalidateData",
    "gap": "gapData",
    "commit": "commitData",
}
DATA_BASE_LIMITS = {
    "max_compressed_response_bytes",
    "max_decoded_response_bytes",
    "max_response_head_bytes",
    "max_request_head_bytes",
    "max_request_identifier_bytes",
    "max_json_nodes",
    "max_json_depth",
    "max_result_bytes",
    "max_resident_bytes",
    "max_decompression_ratio_milli",
    "max_decompression_ms",
    "max_repair_attempts",
    "max_retry_ms",
}
COMMAND_BASE_LIMITS = {
    "max_compressed_response_bytes",
    "max_decoded_response_bytes",
    "max_response_head_bytes",
    "max_request_head_bytes",
    "max_request_identifier_bytes",
    "max_json_nodes",
    "max_json_depth",
    "max_result_bytes",
    "max_resident_bytes",
    "max_decompression_ratio_milli",
    "max_decompression_ms",
    "max_pending_commands",
    "max_command_operations_per_minute",
    "max_command_retry_ms",
    "max_accepted_terminal_ms",
    "max_receipt_retention_ms",
}
REALTIME_LIMITS = {
    "max_sse_line_bytes",
    "max_sse_event_data_bytes",
    "max_queue_events",
    "max_queue_bytes",
    "max_dedupe_entries",
    "max_events_per_subscription_generation",
    "max_bytes_per_subscription_generation",
    "max_subscription_generation_ms",
    "max_streams_per_connection",
    "max_connections_per_principal",
    "max_connections_per_tenant",
    "max_connections_per_ip",
    "max_events_per_second",
    "max_reconnects_per_minute",
    "max_backoff_ms",
    "max_canonical_reconcile_interval_ms",
    "max_canonical_reconcile_jitter_ms",
}
PROTECTED_LIMITS = {
    "max_lease_ms",
    "max_revocation_sla_ms",
    "max_active_subscription_lineages_per_context",
    "max_lease_operations_per_minute",
    "max_request_body_bytes",
}
REPLAY_LIMITS = {"max_replay_events", "max_replay_bytes", "max_replay_ms"}


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON member: {key}")
        result[key] = value
    return result


def parse_interoperable_float(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"invalid JSON decimal: {value}") from error
    if not parsed.is_finite() or abs(parsed) > Decimal("1.7976931348623157e308"):
        raise ValueError(f"non-finite or overflowing I-JSON number: {value}")
    return parsed


def parse_interoperable_int(value: str) -> int:
    parsed = int(value)
    if abs(parsed) > 9_007_199_254_740_991:
        raise ValueError(f"integer outside exact interoperable range: {value}")
    return parsed


def reject_lone_surrogates(value: Any, path: str = "$") -> None:
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise ValueError(f"lone Unicode surrogate at {path}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            reject_lone_surrogates(item, f"{path}/{index}")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            reject_lone_surrogates(key, f"{path}/<key>")
            reject_lone_surrogates(item, f"{path}/{key!r}")


def loads_strict(source: str) -> Any:
    def reject_non_finite(value: str) -> None:
        raise ValueError(f"non-I-JSON numeric constant: {value}")

    document = json.loads(
        source,
        object_pairs_hook=reject_duplicate_keys,
        parse_constant=reject_non_finite,
        parse_float=parse_interoperable_float,
        parse_int=parse_interoperable_int,
    )
    reject_lone_surrogates(document)
    return document


def load(name: str) -> Any:
    return loads_strict((ROOT / name).read_text(encoding="utf-8"))


def validator(schema: dict[str, Any]) -> Draft202012Validator:
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate(instance: Any, instance_name: str, check: Draft202012Validator) -> None:
    errors = sorted(check.iter_errors(instance), key=lambda error: list(error.absolute_path))
    if errors:
        rendered = "\n".join(
            f"  {instance_name}{''.join(f'/{part}' for part in error.absolute_path)}: "
            f"{error.message}"
            for error in errors
        )
        raise AssertionError(f"schema validation failed:\n{rendered}")


def assert_invalid(
    instance: Any,
    instance_name: str,
    check: Draft202012Validator,
    expected_error: str | None = None,
) -> None:
    errors = sorted(check.iter_errors(instance), key=lambda error: list(error.absolute_path))
    if not errors:
        raise AssertionError(f"negative fixture unexpectedly validates: {instance_name}")
    if expected_error is not None:
        rendered = "\n".join(
            f"/{'/'.join(str(part) for part in error.absolute_path)}: {error.message}"
            for error in errors
        )
        if expected_error not in rendered:
            raise AssertionError(
                f"{instance_name}: expected schema error containing {expected_error!r}, "
                f"got {rendered!r}"
            )


def pointer_parts(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise AssertionError(f"not an RFC 6901 pointer: {pointer}")
    decoded_parts: list[str] = []
    for encoded_part in pointer[1:].split("/"):
        decoded: list[str] = []
        offset = 0
        while offset < len(encoded_part):
            character = encoded_part[offset]
            if character != "~":
                decoded.append(character)
                offset += 1
                continue
            if offset + 1 >= len(encoded_part) or encoded_part[offset + 1] not in "01":
                raise AssertionError(f"invalid RFC 6901 escape in pointer: {pointer}")
            decoded.append("~" if encoded_part[offset + 1] == "0" else "/")
            offset += 2
        decoded_parts.append("".join(decoded))
    return decoded_parts


def replace_existing(document: Any, pointer: str, value: Any) -> Any:
    parts = pointer_parts(pointer)
    if not parts:
        return copy.deepcopy(value)
    parent = document
    for part in parts[:-1]:
        if isinstance(parent, list):
            parent = parent[int(part)]
        elif isinstance(parent, dict) and part in parent:
            parent = parent[part]
        else:
            raise AssertionError(f"replacement traverses absent member: {pointer}")
    leaf = parts[-1]
    if isinstance(parent, list):
        index = int(leaf)
        if index >= len(parent):
            raise AssertionError(f"replacement index is absent: {pointer}")
        parent[index] = copy.deepcopy(value)
    elif isinstance(parent, dict) and leaf in parent:
        parent[leaf] = copy.deepcopy(value)
    else:
        raise AssertionError(f"replacement member is absent: {pointer}")
    return document


def fixture(ref: str, documents: dict[str, Any]) -> Any:
    try:
        file_name, key = ref.split("#", 1)
    except ValueError as error:
        raise AssertionError(f"fixture reference lacks '#': {ref}") from error
    if file_name not in documents or not key or key not in documents[file_name]:
        raise AssertionError(f"unresolved fixture reference: {ref}")
    return copy.deepcopy(documents[file_name][key])


def validate_action_result_refs(value: Any, path: str = "body") -> None:
    if isinstance(value, list):
        for index, item in enumerate(value):
            validate_action_result_refs(item, f"{path}/{index}")
        return
    if not isinstance(value, dict):
        return
    if "$result_ref" in value:
        if set(value) != {"$result_ref"} or not isinstance(value["$result_ref"], str):
            raise AssertionError(f"{path}: $result_ref must be the only string member")
        pointer_parts(value["$result_ref"])
        return
    for key, item in value.items():
        validate_action_result_refs(item, f"{path}/{key}")


def collect_limit_refs(value: Any, path: str = "$") -> set[str]:
    refs: set[str] = set()
    if isinstance(value, list):
        for index, item in enumerate(value):
            refs |= collect_limit_refs(item, f"{path}/{index}")
        return refs
    if not isinstance(value, dict):
        return refs
    if "$limit_ref" in value:
        if set(value) - {"$limit_ref", "delta"}:
            raise AssertionError(f"{path}: $limit_ref has unknown members")
        if not isinstance(value["$limit_ref"], str):
            raise AssertionError(f"{path}: $limit_ref must be a string")
        if "delta" in value and not isinstance(value["delta"], int):
            raise AssertionError(f"{path}: $limit_ref delta must be an integer")
        refs.add(value["$limit_ref"])
        return refs
    for key, item in value.items():
        refs |= collect_limit_refs(item, f"{path}/{key}")
    return refs


def collect_literal_stream_ids(value: Any) -> set[str]:
    stream_ids: set[str] = set()
    if isinstance(value, list):
        for item in value:
            stream_ids |= collect_literal_stream_ids(item)
        return stream_ids
    if not isinstance(value, dict):
        return stream_ids
    candidate = value.get("stream_ids")
    if isinstance(candidate, list):
        stream_ids |= {item for item in candidate if isinstance(item, str)}
    for item in value.values():
        stream_ids |= collect_literal_stream_ids(item)
    return stream_ids


def iter_limit_expressions(value: Any):
    if isinstance(value, list):
        for item in value:
            yield from iter_limit_expressions(item)
        return
    if not isinstance(value, dict):
        return
    if "$limit_ref" in value:
        yield value
        return
    for item in value.values():
        yield from iter_limit_expressions(item)


def required_limits_for_unit(unit: dict[str, Any]) -> set[str]:
    capabilities = set(unit["capabilities"])
    profiles = set(unit["profiles"])
    layers = set(unit["layers"])
    required: set[str] = set()
    if capabilities - {"continuum.command-receipt.v0.2"}:
        required |= DATA_BASE_LIMITS
    if "continuum.command-receipt.v0.2" in capabilities:
        required |= COMMAND_BASE_LIMITS
    if "sse" in layers:
        required |= REALTIME_LIMITS
    if "continuum.patch.json.v0.2" in capabilities:
        required.add("max_patch_ops")
    if "continuum.replay.v0.2" in capabilities:
        required |= REPLAY_LIMITS
    if "protected-data" in profiles:
        required |= PROTECTED_LIMITS
    return required


def normalize_state_domain_locator(locator: str) -> str:
    parsed = urlsplit(locator)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        return f"{scheme}:{locator.split(':', 1)[1]}"
    hostname = (parsed.hostname or "").lower()
    port = parsed.port
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        hostname = f"{hostname}:{port}"
    path = parsed.path or "/"
    return urlunsplit((scheme, hostname, path, parsed.query, parsed.fragment))


def validate_message_semantics(name: str, message: dict[str, Any]) -> None:
    kind = message["data"]["kind"]
    suffix = f"#/$defs/{KIND_FRAGMENT[kind]}"
    if not message["dataschema"].endswith(suffix):
        raise AssertionError(f"{name}: dataschema does not identify {suffix}")
    if kind == "commit":
        expected_subject = f"command/{message['data']['command']['command_id']}"
    else:
        expected_subject = f"stream/{message['data']['stream']['id']}"
    if message["subject"] != expected_subject:
        raise AssertionError(
            f"{name}: subject {message['subject']!r} != {expected_subject!r}"
        )
    if kind == "commit":
        stream_ids = [
            observation["stream_id"]
            for observation in message["data"]["command"]["observations"]
        ]
        if len(stream_ids) != len(set(stream_ids)):
            raise AssertionError(f"{name}: receipt contains more than one fence for a stream")


def canonical_fixture_state_bytes(value: Any) -> bytes:
    """JCS bytes for the deliberately simple JSON value domain used by state fixtures.

    Fixture state uses strings, booleans, null, arrays, objects, and interoperable
    integers only. Rejecting other numeric forms here prevents Python's serializer
    from silently standing in for RFC 8785 number formatting.
    """
    if value is None or isinstance(value, (str, bool, int)):
        pass
    elif isinstance(value, list):
        for item in value:
            canonical_fixture_state_bytes(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise AssertionError("JCS fixture object key is not a string")
            canonical_fixture_state_bytes(item)
    else:
        raise AssertionError(
            f"state fixture requires a full JCS numeric implementation for {type(value).__name__}"
        )
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def state_digest(value: Any) -> str:
    digest = hashlib.sha256(canonical_fixture_state_bytes(value)).digest()
    encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return f"sha256-{encoded}"


def repair_payload_etag(messages: list[dict[str, Any]]) -> str:
    """Strong ETag for the exact JCS UTF-8 wire body declared by repair vectors."""
    payload: Any = messages[0] if len(messages) == 1 else messages
    digest = hashlib.sha256(canonical_fixture_state_bytes(payload)).digest()
    encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return f'"sha256-{encoded}"'


def apply_json_patch_fixture(state: Any, operations: list[dict[str, Any]]) -> Any:
    result = copy.deepcopy(state)
    for operation in operations:
        if operation["op"] != "replace":
            raise AssertionError("fixture digest chain only supports JSON Patch replace")
        result = replace_existing(result, operation["path"], operation["value"])
    return result


def materialize_limit_expression_for_schema(value: Any) -> Any:
    """Resolve a limit expression to a safe integer for derived-fixture shape checks.

    Deployment-specific resolution is checked separately for every applicable unit.
    This materialization exists only so the post-replacement wire fixture is validated,
    including the exact field selected by its JSON Pointer.
    """
    if isinstance(value, dict) and "$limit_ref" in value:
        return 1_000_000 + value.get("delta", 0)
    return copy.deepcopy(value)


def is_cookie_unsafe_request(action: dict[str, Any]) -> bool:
    if action.get("op") != "request":
        return False
    request_uri = action.get("request_uri", "").split("?", 1)[0]
    if request_uri in {"/continuum/command-ids", "/continuum/auth/lease"}:
        return True
    if request_uri.startswith("/continuum/commands/"):
        return True
    target = action.get("target", "")
    unsafe_markers = (
        "command_id_issue",
        "command_ids",
        "command_issue",
        "command_submit",
        "auth_lease",
        "lease_",
        "_lease",
        "grant_",
        "_grant",
        "renew_",
        "_renew",
    )
    return any(marker in target for marker in unsafe_markers)


def apply_merge_patch_fixture(target: Any, patch: Any) -> Any:
    if not isinstance(patch, dict):
        return copy.deepcopy(patch)
    result = copy.deepcopy(target) if isinstance(target, dict) else {}
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = apply_merge_patch_fixture(result.get(key), value)
    return result


def validate_fixture_digest_chains(
    fixture_documents: list[tuple[str, dict[str, Any]]],
) -> None:
    known_states: dict[tuple[str, str], Any] = {}
    patches: list[tuple[str, dict[str, Any]]] = []
    for document_name, fixtures in fixture_documents:
        for fixture_name, message in fixtures.items():
            data = message.get("data", {})
            kind = data.get("kind")
            if kind == "snapshot":
                computed = state_digest(data["state"])
                declared = data["target"]["state_digest"]
                if declared != computed:
                    raise AssertionError(
                        f"{document_name}#{fixture_name}: snapshot state_digest "
                        f"{declared} != JCS state digest {computed}"
                    )
                known_states[(data["stream"]["id"], declared)] = copy.deepcopy(data["state"])
            elif kind == "patch":
                patches.append((f"{document_name}#{fixture_name}", message))

    pending = patches
    while pending:
        next_pending: list[tuple[str, dict[str, Any]]] = []
        progressed = False
        for fixture_name, message in pending:
            data = message["data"]
            key = (data["stream"]["id"], data["base"]["state_digest"])
            if key not in known_states:
                next_pending.append((fixture_name, message))
                continue
            base_state = known_states[key]
            patch = data["patch"]
            if patch["media_type"] == "application/json-patch+json":
                result = apply_json_patch_fixture(base_state, patch["document"])
            elif patch["media_type"] == "application/merge-patch+json":
                result = apply_merge_patch_fixture(base_state, patch["document"])
            else:
                raise AssertionError(f"{fixture_name}: unsupported patch format")
            computed = state_digest(result)
            declared = data["target"]["state_digest"]
            if declared != computed:
                raise AssertionError(
                    f"{fixture_name}: patch target state_digest {declared} "
                    f"!= computed JCS state digest {computed}"
                )
            known_states[(data["stream"]["id"], declared)] = result
            progressed = True
        if not progressed:
            unresolved = [name for name, _ in next_pending]
            raise AssertionError(f"patch fixtures lack a known base state: {unresolved}")
        pending = next_pending


def validate_control_semantics(name: str, control: dict[str, Any]) -> None:
    if control["kind"] not in {"ready", "caught_up"}:
        return
    stream_ids = [stream["stream_id"] for stream in control["streams"]]
    if len(stream_ids) != len(set(stream_ids)):
        raise AssertionError(f"{name}: manifest contains duplicate stream ids")
    manifest = {
        "protocol_version": "0.2",
        "stream_ids": sorted(stream_ids),
    }
    # The manifest domain is restricted to ASCII opaque ids, so sorted compact JSON is
    # byte-identical to RFC 8785/JCS for this deliberately small structure.
    canonical = json.dumps(
        manifest,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    digest = "sha256-" + base64.urlsafe_b64encode(hashlib.sha256(canonical).digest()).rstrip(b"=").decode("ascii")
    if control["subscription_manifest_digest"] != digest:
        raise AssertionError(
            f"{name}: manifest digest {control['subscription_manifest_digest']} != {digest}"
        )


def validate_conformance_manifest(
    name: str,
    manifest: dict[str, Any],
    binding: dict[str, Any],
) -> None:
    units = manifest["units"]
    by_id = {unit["id"]: unit for unit in units}
    if len(by_id) != len(units):
        raise AssertionError(f"{name}: duplicate conformance unit id")
    result_documents = [unit["result_document"] for unit in units]
    if len(set(result_documents)) != len(result_documents):
        raise AssertionError(f"{name}: result document is shared across conformance units")
    trace_documents = [unit["trace_evidence"] for unit in units]
    if len(set(trace_documents)) != len(trace_documents):
        raise AssertionError(f"{name}: trace evidence is shared across conformance units")

    registry = manifest["state_domain_registry"]
    referenced_domain_ids = {
        domain_id for unit in units for domain_id in unit["state_domains"]
    }
    domain_reference_counts = Counter(
        domain_id for unit in units for domain_id in unit["state_domains"]
    )
    if multiply_referenced_domains := sorted(
        domain_id
        for domain_id, reference_count in domain_reference_counts.items()
        if reference_count != 1
    ):
        raise AssertionError(
            f"{name}: each state domain must belong to exactly one consolidated unit; "
            f"invalid={multiply_referenced_domains}"
        )
    if unknown_domains := referenced_domain_ids - set(registry):
        raise AssertionError(f"{name}: unknown state domain refs {sorted(unknown_domains)}")
    if orphan_domains := set(registry) - referenced_domain_ids:
        raise AssertionError(f"{name}: orphan state domains {sorted(orphan_domains)}")
    identity_to_id: dict[tuple[str, str, str, str], str] = {}
    digest_to_id: dict[str, str] = {}
    domain_identities: dict[str, tuple[str, str, str, str]] = {}
    for domain_id, descriptor in registry.items():
        effective_identity = descriptor["effective_backing_identity"]
        identity_strings = {
            "namespace": descriptor["namespace"],
            "effective.backend_instance": effective_identity["backend_instance"],
            "effective.partition": effective_identity["partition"],
            "effective.namespace": effective_identity["namespace"],
        }
        for field_name, value in identity_strings.items():
            if value != value.strip():
                raise AssertionError(
                    f"{name}: state domain {domain_id!r} {field_name} has edge whitespace"
                )
            if unicodedata.normalize("NFC", value) != value:
                raise AssertionError(
                    f"{name}: state domain {domain_id!r} {field_name} is not NFC"
                )
        computed_identity_digest = state_digest(effective_identity)
        if descriptor["effective_backing_identity_digest"] != computed_identity_digest:
            raise AssertionError(
                f"{name}: state domain {domain_id!r} effective backing identity digest "
                f"{descriptor['effective_backing_identity_digest']!r} != {computed_identity_digest!r}"
            )
        if descriptor["kind"] != effective_identity["kind"]:
            raise AssertionError(
                f"{name}: state domain {domain_id!r} kind differs from effective backing identity"
            )
        if descriptor["namespace"] != effective_identity["namespace"]:
            raise AssertionError(
                f"{name}: state domain {domain_id!r} namespace differs from effective backing identity"
            )
        identity = (
            effective_identity["kind"],
            effective_identity["backend_instance"],
            effective_identity["partition"],
            effective_identity["namespace"],
        )
        if prior_id := identity_to_id.get(identity):
            raise AssertionError(
                f"{name}: state domain aliases {prior_id!r} and {domain_id!r} "
                "identify the same effective backing resource"
            )
        digest = descriptor["effective_backing_identity_digest"]
        if prior_id := digest_to_id.get(digest):
            raise AssertionError(
                f"{name}: state domain aliases {prior_id!r} and {domain_id!r} "
                "declare the same effective backing identity digest"
            )
        identity_to_id[identity] = domain_id
        digest_to_id[digest] = domain_id
        domain_identities[domain_id] = identity

    registry_trace_documents = [
        descriptor["trace_evidence"] for descriptor in registry.values()
    ]
    if len(set(registry_trace_documents)) != len(registry_trace_documents):
        raise AssertionError(f"{name}: state-domain trace evidence is not unique")

    public_domains = {
        domain_identities[domain]
        for unit in units
        if "public-data" in unit["profiles"]
        for domain in unit["state_domains"]
    }
    protected_domains = {
        domain_identities[domain]
        for unit in units
        if "protected-data" in unit["profiles"]
        for domain in unit["state_domains"]
    }
    if shared_domains := public_domains & protected_domains:
        raise AssertionError(
            f"{name}: state domains cross public/protected classification "
            f"{sorted(shared_domains)}"
        )

    for unit in units:
        profiles = set(unit["profiles"])
        capabilities = set(unit["capabilities"])
        layers = set(unit["layers"])
        if {"public-data", "protected-data"} <= profiles:
            raise AssertionError(f"{name}#{unit['id']}: unit cannot be both public and protected")
        auth_profiles = profiles & {"cookie-auth", "non-cookie-auth"}
        if "protected-data" in profiles and len(auth_profiles) != 1:
            raise AssertionError(
                f"{name}#{unit['id']}: protected-data requires exactly one auth profile"
            )
        if auth_profiles and "protected-data" not in profiles:
            raise AssertionError(
                f"{name}#{unit['id']}: auth profile requires protected-data"
            )
        if {"native-eventsource", "fetch-stream"} <= profiles:
            raise AssertionError(f"{name}#{unit['id']}: unit cannot declare two alternative transports")
        if {"snapshot-first", "subscribe-first"} <= profiles:
            raise AssertionError(f"{name}#{unit['id']}: unit cannot declare two alternative cut strategies")
        transport_profiles = profiles & {"native-eventsource", "fetch-stream"}
        cut_profiles = profiles & {"snapshot-first", "subscribe-first"}
        realtime_capabilities = capabilities & {
            "continuum.invalidate.v0.2",
            "continuum.patch.json.v0.2",
            "continuum.patch.merge.v0.2",
            "continuum.replay.v0.2",
        }
        if realtime_capabilities and "sse" not in layers:
            raise AssertionError(
                f"{name}#{unit['id']}: Continuum 0.2 realtime capability requires sse layer"
            )
        if "sse" in layers:
            if len(transport_profiles) != 1:
                raise AssertionError(
                    f"{name}#{unit['id']}: sse layer requires exactly one native/fetch transport"
                )
            if len(cut_profiles) != 1:
                raise AssertionError(
                    f"{name}#{unit['id']}: sse layer requires exactly one cut strategy"
                )
            required_realtime = {
                "continuum.snapshot.v0.2",
                "continuum.invalidate.v0.2",
            }
            if not required_realtime <= capabilities:
                raise AssertionError(
                    f"{name}#{unit['id']}: realtime scope lacks snapshot or invalidate capability"
                )
        if "native-eventsource" in profiles and "subscribe-first" not in profiles:
            raise AssertionError(
                f"{name}#{unit['id']}: native EventSource requires subscribe-first"
            )
        if "native-eventsource" in profiles and capabilities & {
            "continuum.patch.json.v0.2",
            "continuum.patch.merge.v0.2",
        }:
            raise AssertionError(
                f"{name}#{unit['id']}: patch capabilities require fetch-stream"
            )
        if {
            "protected-data",
            "native-eventsource",
            "non-cookie-auth",
        } <= profiles:
            raise AssertionError(
                f"{name}#{unit['id']}: protected native EventSource requires cookie-auth"
            )
        if (
            "snapshot-first" in profiles
            and "continuum.replay.v0.2" not in capabilities
        ):
            raise AssertionError(
                f"{name}#{unit['id']}: snapshot-first realtime requires replay capability"
            )
        if "public-shared-cache" in profiles and "public-data" not in profiles:
            raise AssertionError(f"{name}#{unit['id']}: shared public cache is not public-data")
        if profiles & {"public-shared-cache", "service-worker-present"} and "cache" not in layers:
            raise AssertionError(f"{name}#{unit['id']}: cache profile lacks cache layer")
        if "protected-data" in profiles and "authorization" not in layers:
            raise AssertionError(f"{name}#{unit['id']}: protected-data lacks authorization layer")
        if profiles & {"native-eventsource", "fetch-stream"} and "sse" not in layers:
            raise AssertionError(f"{name}#{unit['id']}: stream profile lacks sse layer")
        if profiles & {"snapshot-first", "subscribe-first"} and "sse" not in layers:
            raise AssertionError(f"{name}#{unit['id']}: cut strategy lacks sse layer")
        if "multiplexed-stream" in profiles and not {"multistream", "sse"} <= layers:
            raise AssertionError(
                f"{name}#{unit['id']}: multiplexed stream lacks multistream or sse layer"
            )
        if "ssr-bootstrap" in profiles and "continuum.snapshot.v0.2" not in capabilities:
            raise AssertionError(f"{name}#{unit['id']}: SSR profile lacks snapshot capability")
        if "ssr-bootstrap" in profiles and "http" not in layers:
            raise AssertionError(f"{name}#{unit['id']}: SSR profile lacks http layer")
        if {"protected-data", "ssr-bootstrap"} <= profiles and (
            "prehydration-purge-guard" not in profiles
        ):
            raise AssertionError(
                f"{name}#{unit['id']}: protected SSR requires a parser-blocking prehydration purge guard"
            )
        if "prehydration-purge-guard" in profiles and not {
            "protected-data",
            "ssr-bootstrap",
        } <= profiles:
            raise AssertionError(
                f"{name}#{unit['id']}: prehydration purge guard requires protected SSR"
            )
        if "continuum.command-receipt.v0.2" in capabilities:
            if profiles & {"public-data", "public-shared-cache"} or "protected-data" not in profiles:
                raise AssertionError(
                    f"{name}#{unit['id']}: command receipt classification must be protected only"
                )
            required_command_layers = {
                "authorization",
                "http",
                "cache",
                "parser",
                "producer",
                "command",
            }
            if not required_command_layers <= layers:
                raise AssertionError(
                    f"{name}#{unit['id']}: command receipt lacks required binding layer"
                )
        if "external-provider" in profiles and (
            "continuum.command-receipt.v0.2" not in capabilities or "command" not in layers
        ):
            raise AssertionError(f"{name}#{unit['id']}: external provider lacks command receipt")
        if ("rollout-candidate" in profiles) != ("rollout" in layers):
            raise AssertionError(
                f"{name}#{unit['id']}: rollout layer and rollout-candidate profile must coincide"
            )
        if ("rollout" in unit) != ("rollout-candidate" in profiles):
            raise AssertionError(
                f"{name}#{unit['id']}: rollout document and rollout-candidate profile must coincide"
            )
        data_capabilities = capabilities - {"continuum.command-receipt.v0.2"}
        if data_capabilities:
            if len(profiles & {"public-data", "protected-data"}) != 1:
                raise AssertionError(
                    f"{name}#{unit['id']}: data scope requires exactly one security classification"
                )
            if "continuum.snapshot.v0.2" not in capabilities:
                raise AssertionError(f"{name}#{unit['id']}: data capability lacks snapshot baseline")
            if not {"http", "cache", "parser", "producer"} <= layers:
                raise AssertionError(
                    f"{name}#{unit['id']}: data capability lacks HTTP/cache/parser/producer"
                )
        if "sse" in layers and len(transport_profiles) != 1:
            raise AssertionError(
                f"{name}#{unit['id']}: sse layer requires exactly one native/fetch transport"
            )

        required_limits = required_limits_for_unit(unit)
        declared_limits = set(unit["limits"])
        if declared_limits != required_limits:
            missing = sorted(required_limits - declared_limits)
            extra = sorted(declared_limits - required_limits)
            raise AssertionError(
                f"{name}#{unit['id']}: limit set mismatch; missing={missing}, extra={extra}"
            )
        limits = unit["limits"]
        if limits["max_result_bytes"] > limits["max_resident_bytes"]:
            raise AssertionError(f"{name}#{unit['id']}: result limit exceeds resident limit")
        if limits["max_compressed_response_bytes"] > limits["max_resident_bytes"]:
            raise AssertionError(f"{name}#{unit['id']}: compressed response exceeds resident limit")
        if limits["max_decoded_response_bytes"] > limits["max_resident_bytes"]:
            raise AssertionError(f"{name}#{unit['id']}: decoded response exceeds resident limit")
        if limits["max_response_head_bytes"] > limits["max_resident_bytes"]:
            raise AssertionError(f"{name}#{unit['id']}: response head exceeds resident limit")
        if limits["max_request_head_bytes"] > limits["max_resident_bytes"]:
            raise AssertionError(f"{name}#{unit['id']}: request head exceeds resident limit")
        if limits["max_request_identifier_bytes"] > limits["max_request_head_bytes"]:
            raise AssertionError(
                f"{name}#{unit['id']}: request identifier exceeds request-head representability"
            )
        if "protected-data" in profiles:
            if limits["max_request_body_bytes"] > limits["max_resident_bytes"]:
                raise AssertionError(f"{name}#{unit['id']}: request body exceeds resident limit")
        if limits["max_json_depth"] > limits["max_json_nodes"]:
            raise AssertionError(f"{name}#{unit['id']}: JSON depth exceeds node limit")
        if limits["max_json_nodes"] > limits["max_decoded_response_bytes"]:
            raise AssertionError(
                f"{name}#{unit['id']}: JSON nodes exceed decoded-byte representability"
            )
        if "continuum.patch.json.v0.2" in capabilities and (
            limits["max_patch_ops"] > limits["max_json_nodes"]
        ):
            raise AssertionError(f"{name}#{unit['id']}: patch operations exceed JSON nodes")
        if "sse" in layers:
            if limits["max_sse_line_bytes"] > limits["max_sse_event_data_bytes"]:
                raise AssertionError(f"{name}#{unit['id']}: SSE line limit exceeds event limit")
            if limits["max_sse_event_data_bytes"] > limits["max_resident_bytes"]:
                raise AssertionError(f"{name}#{unit['id']}: SSE event exceeds resident limit")
            if limits["max_sse_event_data_bytes"] > limits["max_queue_bytes"]:
                raise AssertionError(f"{name}#{unit['id']}: SSE event exceeds queue byte limit")
            if (
                limits["max_sse_event_data_bytes"]
                > limits["max_bytes_per_subscription_generation"]
            ):
                raise AssertionError(
                    f"{name}#{unit['id']}: SSE event exceeds generation byte limit"
                )
            if (
                limits["max_events_per_second"]
                > limits["max_events_per_subscription_generation"]
            ):
                raise AssertionError(
                    f"{name}#{unit['id']}: event-rate limit exceeds generation event limit"
                )
            if limits["max_queue_bytes"] > limits["max_resident_bytes"]:
                raise AssertionError(f"{name}#{unit['id']}: queue limit exceeds resident limit")
            if limits["max_queue_events"] > limits["max_events_per_subscription_generation"]:
                raise AssertionError(
                    f"{name}#{unit['id']}: queue events exceed subscription-generation events"
                )
            if limits["max_queue_bytes"] > limits["max_bytes_per_subscription_generation"]:
                raise AssertionError(
                    f"{name}#{unit['id']}: queue bytes exceed subscription-generation bytes"
                )
            if limits["max_queue_bytes"] < limits["max_queue_events"]:
                raise AssertionError(
                    f"{name}#{unit['id']}: queue byte limit cannot represent one byte per event"
                )
            if (
                limits["max_bytes_per_subscription_generation"]
                < limits["max_events_per_subscription_generation"]
            ):
                raise AssertionError(
                    f"{name}#{unit['id']}: generation byte limit cannot represent one byte per event"
                )
            if "continuum.replay.v0.2" in capabilities:
                if (
                    limits["max_replay_events"]
                    > limits["max_events_per_subscription_generation"]
                ):
                    raise AssertionError(
                        f"{name}#{unit['id']}: replay events exceed subscription-generation events"
                    )
                if (
                    limits["max_replay_bytes"]
                    > limits["max_bytes_per_subscription_generation"]
                ):
                    raise AssertionError(
                        f"{name}#{unit['id']}: replay bytes exceed subscription-generation bytes"
                    )
                if limits["max_replay_bytes"] < limits["max_replay_events"]:
                    raise AssertionError(
                        f"{name}#{unit['id']}: replay byte limit cannot represent one byte per event"
                    )
            if (
                limits["max_canonical_reconcile_interval_ms"]
                + limits["max_canonical_reconcile_jitter_ms"]
                > 9_007_199_254_740_991
            ):
                raise AssertionError(
                    f"{name}#{unit['id']}: reconcile interval plus jitter exceeds I-JSON"
                )
        if "protected-data" in profiles and (
            limits["max_lease_ms"] > limits["max_revocation_sla_ms"]
        ):
            raise AssertionError(
                f"{name}#{unit['id']}: lease duration exceeds revocation SLA"
            )
        if "rollout-candidate" in profiles and (
            unit["rollout"]["thresholds"]["max_resident_bytes"]
            > limits["max_resident_bytes"]
        ):
            raise AssertionError(f"{name}#{unit['id']}: rollout memory threshold exceeds hard limit")

        applicable = [
            vector
            for vector in binding["vectors"]
            if set(vector["capabilities"]) <= capabilities
            and set(vector.get("requires_profiles", [])) <= profiles
            and vector["layer"] in layers
            and not (set(vector.get("excludes_capabilities", [])) & capabilities)
            and not (set(vector.get("excludes_profiles", [])) & profiles)
            and not (set(vector.get("excludes_layers", [])) & layers)
        ]
        exercised_layers = {vector["layer"] for vector in applicable}
        exercised_profiles = {
            profile
            for vector in applicable
            for profile in vector.get("requires_profiles", [])
        }
        exercised_capabilities = {
            capability
            for vector in applicable
            for capability in vector["capabilities"]
        }
        if missing_layers := layers - exercised_layers:
            raise AssertionError(
                f"{name}#{unit['id']}: declared layers lack applicable vectors "
                f"{sorted(missing_layers)}"
            )
        if missing_profiles := profiles - exercised_profiles:
            raise AssertionError(
                f"{name}#{unit['id']}: declared profiles lack explicit applicable vectors "
                f"{sorted(missing_profiles)}"
            )
        if missing_capabilities := capabilities - exercised_capabilities:
            raise AssertionError(
                f"{name}#{unit['id']}: declared capabilities lack applicable vectors "
                f"{sorted(missing_capabilities)}"
            )
        evidenced_limits = {
            limit
            for vector in applicable
            for limit in vector.get("requires_limits", [])
        }
        if missing_evidence := required_limits - evidenced_limits:
            raise AssertionError(
                f"{name}#{unit['id']}: limits lack applicable boundary vectors "
                f"{sorted(missing_evidence)}"
            )
        for vector in applicable:
            for expression in iter_limit_expressions(vector):
                limit_name = expression["$limit_ref"]
                if limit_name not in limits:
                    raise AssertionError(
                        f"{name}#{unit['id']}: {vector['id']} references absent {limit_name}"
                    )
                effective = limits[limit_name] + expression.get("delta", 0)
                if not 0 <= effective <= 9_007_199_254_740_991:
                    raise AssertionError(
                        f"{name}#{unit['id']}: {vector['id']} resolves {limit_name} out of range"
                    )


def main() -> None:
    for invalid_number in ("NaN", "Infinity", "-Infinity", "1e400", "9007199254740992"):
        try:
            loads_strict(invalid_number)
        except ValueError:
            pass
        else:
            raise AssertionError(f"non-interoperable JSON number accepted: {invalid_number}")
    if loads_strict("[0.1,0.10000000000000001]")[0] == loads_strict(
        "[0.1,0.10000000000000001]"
    )[1]:
        raise AssertionError("exact JSON decimal ratios collapsed to binary-float equality")

    for invalid_unicode in (
        '"\\ud800"',
        '{"\\udfff": true}',
        '{"nested": ["\\ud800"]}',
    ):
        try:
            loads_strict(invalid_unicode)
        except ValueError:
            pass
        else:
            raise AssertionError(f"lone Unicode surrogate accepted: {invalid_unicode!r}")

    for invalid_pointer in ("/invalid~2escape", "/dangling~"):
        try:
            pointer_parts(invalid_pointer)
        except AssertionError:
            pass
        else:
            raise AssertionError(f"invalid replacement JSON Pointer accepted: {invalid_pointer}")

    names = [
        "message.schema.json",
        "examples.json",
        "binding-protected-examples.json",
        "conformance-vectors.schema.json",
        "conformance-vectors.json",
        "binding-control.schema.json",
        "binding-control-examples.json",
        "binding-control-negative-examples.json",
        "binding-vectors.schema.json",
        "binding-vectors.json",
        "conformance-manifest.schema.json",
        "conformance-manifest.example.json",
    ]
    documents = {name: load(name) for name in names}

    message_check = validator(documents["message.schema.json"])
    control_check = validator(documents["binding-control.schema.json"])
    core_check = validator(documents["conformance-vectors.schema.json"])
    binding_check = validator(documents["binding-vectors.schema.json"])
    manifest_check = validator(documents["conformance-manifest.schema.json"])

    client_state_check = validator(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$ref": "#/$defs/clientState",
            "$defs": documents["conformance-vectors.schema.json"]["$defs"],
        }
    )
    message_action_check = validator(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$ref": "#/$defs/messageAction",
            "$defs": documents["conformance-vectors.schema.json"]["$defs"],
        }
    )
    for invalid_pointer in ("/invalid~2escape", "/dangling~"):
        assert_invalid(
            {
                "op": "deliver_http",
                "message_ref": "snapshot_10",
                "replace": [{"path": invalid_pointer, "value": None}],
            },
            f"message action with invalid JSON Pointer {invalid_pointer!r}",
            message_action_check,
        )
    for invalid_etag in ('W/"snapshot-10"', "snapshot-10"):
        assert_invalid(
            {
                "op": "deliver_http",
                "message_ref": "snapshot_10",
                "representation_etag": invalid_etag,
            },
            f"HTTP delivery with invalid ETag {invalid_etag!r}",
            message_action_check,
        )
    assert_invalid(
        {
            "security_generation": "g_a",
            "data_state": "absent",
            "transport_state": "idle",
            "reconcile_state": "idle",
            "state": {"leak": True},
        },
        "absent client with state",
        client_state_check,
    )
    assert_invalid(
        {
            "security_generation": "g_a",
            "data_state": "invalid",
            "transport_state": "idle",
            "reconcile_state": "fatal",
        },
        "fatal client with open transport",
        client_state_check,
    )
    assert_invalid(
        {
            "security_generation": "g_a",
            "data_state": "fresh",
            "transport_state": "idle",
            "reconcile_state": "reset_required",
            "stream_id": "s_a",
            "cursor": {"epoch": "e_a", "sequence": "00000000000000000001"},
            "state_token": "t_a",
            "state_digest": "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            "state": {},
        },
        "fresh client requiring reset",
        client_state_check,
    )
    assert_invalid(
        {
            "security_generation": "g_a",
            "data_state": "fresh",
            "transport_state": "idle",
            "reconcile_state": "idle",
            "stream_id": "",
            "cursor": {"epoch": "e_a", "sequence": "00000000000000000001"},
            "state_token": "",
            "state_digest": "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            "state": {},
        },
        "fresh client with empty semantic identity",
        client_state_check,
    )

    for example_file in ("examples.json", "binding-protected-examples.json"):
        for name, message in documents[example_file].items():
            validate(message, f"{example_file}#{name}", message_check)
            validate_message_semantics(f"{example_file}#{name}", message)
            if message.get("continuumreplayed"):
                originals = [
                    candidate
                    for candidate in documents[example_file].values()
                    if candidate["source"] == message["source"]
                    and candidate["id"] == message["continuumoriginalid"]
                ]
                if len(originals) != 1 or originals[0]["data"] != message["data"]:
                    raise AssertionError(
                        f"{example_file}#{name}: replay data is not semantically identical"
                    )
                if originals[0]["id"] == message["id"]:
                    raise AssertionError(
                        f"{example_file}#{name}: replay must use a new CloudEvents id"
                    )
    validate_fixture_digest_chains(
        [
            ("examples.json", documents["examples.json"]),
            (
                "binding-protected-examples.json",
                documents["binding-protected-examples.json"],
            ),
        ]
    )
    incomplete_replay = copy.deepcopy(documents["examples.json"]["patch_10_11_replay"])
    del incomplete_replay["continuumoriginalid"]
    assert_invalid(incomplete_replay, "replay without original id", message_check)
    duplicate_observation = copy.deepcopy(documents["examples.json"]["commit_committed"])
    second_fence = copy.deepcopy(duplicate_observation["data"]["command"]["observations"][0])
    second_fence["cursor"]["sequence"] = "00000000000000000014"
    second_fence["state_token"] = "t_state_14"
    duplicate_observation["data"]["command"]["observations"].append(second_fence)
    validate(duplicate_observation, "receipt with duplicate stream fence shape", message_check)
    try:
        validate_message_semantics("receipt with duplicate stream fence", duplicate_observation)
    except AssertionError:
        pass
    else:
        raise AssertionError("receipt with duplicate stream fence passed semantic validation")
    for name, control in documents["binding-control-examples.json"].items():
        validate(control, f"binding-control-examples.json#{name}", control_check)
        validate_control_semantics(f"binding-control-examples.json#{name}", control)
    for name, control in documents["binding-control-negative-examples.json"].items():
        validate(control, f"binding-control-negative-examples.json#{name}", control_check)

    missing_security_event = copy.deepcopy(
        documents["binding-control-examples.json"]["security_renew_protected"]
    )
    del missing_security_event["event"]
    assert_invalid(
        missing_security_event,
        "security-generation SSE control without its explicit event name",
        control_check,
    )
    wrong_security_event = copy.deepcopy(
        documents["binding-control-examples.json"]["security_renew_protected"]
    )
    wrong_security_event["event"] = "message"
    assert_invalid(
        wrong_security_event,
        "security-generation SSE control disguised as a projection event",
        control_check,
    )

    for forbidden_field in (
        "previous_security_generation_id",
        "next_security_generation_id",
    ):
        invalid_purge = copy.deepcopy(
            documents["binding-control-examples.json"]["security_purge"]
        )
        invalid_purge[forbidden_field] = "g_forbidden"
        assert_invalid(
            invalid_purge,
            f"purge with {forbidden_field}",
            control_check,
        )

    overlong_stream = copy.deepcopy(documents["binding-control-examples.json"]["ready"])
    overlong_stream["streams"][0]["stream_id"] = "s" * 257
    assert_invalid(overlong_stream, "ready with 257-byte stream id", control_check)

    overlong_token = copy.deepcopy(documents["binding-control-examples.json"]["ready"])
    overlong_token["streams"][0]["head"]["state_token"] = "t" * 257
    assert_invalid(overlong_token, "ready with 257-byte state token", control_check)

    overlong_subscription = copy.deepcopy(
        documents["binding-control-examples.json"]["ready"]
    )
    overlong_subscription["subscription_id"] = "s" * 257
    assert_invalid(overlong_subscription, "ready with 257-byte subscription id", control_check)

    overlong_delivery_cursor = copy.deepcopy(
        documents["binding-control-examples.json"]["ready"]
    )
    overlong_delivery_cursor["delivery_cursor"] = "d" * 513
    assert_invalid(
        overlong_delivery_cursor,
        "ready with 513-byte delivery cursor",
        control_check,
    )

    overlong_security_generation = copy.deepcopy(
        documents["binding-control-examples.json"]["security_renew"]
    )
    overlong_security_generation["security_generation_id"] = "g" * 129
    assert_invalid(
        overlong_security_generation,
        "renew with 129-byte security generation id",
        control_check,
    )

    core = documents["conformance-vectors.json"]
    binding = documents["binding-vectors.json"]
    validate(core, "conformance-vectors.json", core_check)
    validate(binding, "binding-vectors.json", binding_check)
    declared_limit_names = set(
        documents["binding-vectors.schema.json"]["$defs"]["limitName"]["enum"]
    )
    manifest_limit_names = set(
        documents["conformance-manifest.schema.json"]["$defs"]["limits"]["properties"]
    )
    if declared_limit_names != manifest_limit_names:
        raise AssertionError("manifest and binding limit catalogs diverge")
    for vector in binding["vectors"]:
        required_profiles = set(vector.get("requires_profiles", []))
        vector_capabilities = set(vector["capabilities"])
        excluded_capabilities = set(vector.get("excludes_capabilities", []))
        excluded_profiles = set(vector.get("excludes_profiles", []))
        excluded_layers = set(vector.get("excludes_layers", []))
        if vector_capabilities & excluded_capabilities:
            raise AssertionError(
                f"{vector['id']}: required and excluded capabilities overlap"
            )
        if required_profiles & excluded_profiles:
            raise AssertionError(f"{vector['id']}: required and excluded profiles overlap")
        if vector["layer"] in excluded_layers:
            raise AssertionError(f"{vector['id']}: vector layer is also excluded")
        actions = vector["actions"]
        for action_index, action in enumerate(actions):
            body = action.get("body")
            if isinstance(body, dict):
                for identifier_name in ("lease_operation_id", "issuance_nonce"):
                    identifier = body.get(identifier_name)
                    if identifier is not None and (
                        not isinstance(identifier, str)
                        or re.fullmatch(r"[0-9a-f]{32}", identifier) is None
                    ):
                        raise AssertionError(
                            f"{vector['id']}: {identifier_name} fixture must encode "
                            "128 client-generated bits as 32 lowercase hex digits"
                        )
            lease_request = action.get("headers", {}).get("Continuum-Lease-Request")
            if lease_request is not None and (
                not isinstance(lease_request, str)
                or re.fullmatch(r"[0-9a-f]{32}", lease_request) is None
            ):
                raise AssertionError(
                    f"{vector['id']}: Continuum-Lease-Request fixture must encode "
                    "128 client-generated bits as 32 lowercase hex digits"
                )
        given_classification = vector.get("given", {}).get("classification")
        if given_classification == "public" and "public-data" not in required_profiles:
            raise AssertionError(
                f"{vector['id']}: public given requires public-data profile"
            )
        if given_classification in {"tenant", "principal"} and "protected-data" not in required_profiles:
            raise AssertionError(
                f"{vector['id']}: protected given requires protected-data profile"
            )
        given_binding = vector.get("given", {}).get("binding")
        binding_profile = {
            "native_eventsource": "native-eventsource",
            "fetch_stream": "fetch-stream",
        }.get(given_binding)
        if binding_profile and binding_profile not in required_profiles:
            raise AssertionError(
                f"{vector['id']}: fixed {given_binding} binding lacks {binding_profile} profile"
            )
        literal_stream_ids = collect_literal_stream_ids(vector.get("actions", []))
        if "protected-data" in required_profiles and any(
            stream_id.startswith("s_example_public_")
            for stream_id in literal_stream_ids
        ):
            raise AssertionError(
                f"{vector['id']}: protected vector contains public stream id"
            )
        if "public-data" in required_profiles and any(
            "_protected_" in stream_id for stream_id in literal_stream_ids
        ):
            raise AssertionError(
                f"{vector['id']}: public vector contains protected stream id"
            )
        if "continuum.command-receipt.v0.2" in vector_capabilities and any(
            stream_id.startswith("s_example_protected_")
            and "_command_" not in stream_id
            for stream_id in literal_stream_ids
        ):
            raise AssertionError(
                f"{vector['id']}: command lease uses a data-stream authority id"
            )
        if "protected-data" in required_profiles and "non-cookie-auth" not in required_profiles:
            for action in vector["actions"]:
                if not is_cookie_unsafe_request(action):
                    continue
                if action.get("csrf_negative_probe"):
                    if "cookie-auth" not in required_profiles:
                        raise AssertionError(
                            f"{vector['id']}: CSRF negative probe must require cookie-auth"
                        )
                    continue
                headers = action.get("headers", {})
                if headers.get("Origin") != "https://app-a.example.test":
                    raise AssertionError(
                        f"{vector['id']}: unsafe cookie-applicable request "
                        f"{action['target']!r} lacks exact trusted Origin"
                    )
                if not headers.get("X-CSRF-Token"):
                    raise AssertionError(
                        f"{vector['id']}: unsafe cookie-applicable request "
                        f"{action['target']!r} lacks session-bound CSRF token"
                    )
        refs = collect_limit_refs(vector, f"binding-vectors.json#{vector['id']}")
        required = set(vector.get("requires_limits", []))
        if refs != required:
            raise AssertionError(
                f"{vector['id']}: limit refs {sorted(refs)} != requires_limits {sorted(required)}"
            )
        if not refs <= declared_limit_names:
            raise AssertionError(f"{vector['id']}: unknown limit ref")
        probes = vector.get("boundary_probes", [])
        probe_names = [probe["limit"] for probe in probes]
        if len(probe_names) != len(set(probe_names)):
            raise AssertionError(f"{vector['id']}: duplicate boundary probe")
        if set(probe_names) != required:
            raise AssertionError(
                f"{vector['id']}: boundary probes {sorted(probe_names)} "
                f"!= requires_limits {sorted(required)}"
            )
    manifest = documents["conformance-manifest.example.json"]
    validate(manifest, "conformance-manifest.example.json", manifest_check)
    validate_conformance_manifest("conformance-manifest.example.json", manifest, binding)

    def synthetic_unit(
        unit_id: str,
        capabilities: list[str],
        profiles: list[str],
        layers: list[str],
    ) -> dict[str, Any]:
        unit: dict[str, Any] = {
            "id": unit_id,
            "capabilities": capabilities,
            "profiles": profiles,
            "layers": layers,
            "targets": {"synthetic_target": {"adapter": "neutral conformance adapter"}},
            "state_domains": [f"synthetic.{unit_id}"],
            "limits": {},
            "result_document": f"urn:continuum-result:matrix.{unit_id}",
            "trace_evidence": f"urn:continuum-trace:matrix.{unit_id}",
        }
        limits = {limit: 1000 for limit in required_limits_for_unit(unit)}
        for limit, value in {
            "max_decompression_ratio_milli": 2000,
            "max_resident_bytes": 1_000_000,
            "max_result_bytes": 100_000,
            "max_queue_bytes": 10_000,
            "max_events_per_subscription_generation": 10_000,
            "max_bytes_per_subscription_generation": 100_000,
            "max_sse_line_bytes": 1000,
            "max_sse_event_data_bytes": 10_000,
            "max_command_retry_ms": 1000,
            "max_accepted_terminal_ms": 5000,
            "max_receipt_retention_ms": 10_000,
            "max_lease_ms": 60_000,
            "max_revocation_sla_ms": 60_000,
        }.items():
            if limit in limits:
                limits[limit] = value
        unit["limits"] = limits
        if "rollout-candidate" in profiles:
            unit["rollout"] = {
                "owner": "synthetic-conformance",
                "observation_window_ms": 60_000,
                "comparison_population": "synthetic operations in the same assigned cohort",
                "latency_metric": "continuum.synthetic.duration_ms",
                "error_event": "continuum.synthetic.error",
                "minimum_candidate_samples": 10,
                "minimum_baseline_samples": 10,
                "thresholds": {
                    "semantic_divergence_ppm": 0,
                    "cross_audience_leaks": 0,
                    "repair_loop_rate": 0,
                    "max_resident_bytes": limits["max_resident_bytes"],
                    "reconnect_storm_rate": 0,
                    "p95_latency_regression_ms": 0,
                    "error_rate_regression": 0,
                },
            }
        return unit

    capability_matrix = {
        "protocol_version": "0.2",
        "implementation_id": "synthetic-capability-matrix",
        "generated_at": "2026-09-28T00:00:00Z",
        "units": [
            synthetic_unit(
                "protected_snapshot",
                ["continuum.snapshot.v0.2"],
                ["protected-data", "non-cookie-auth"],
                ["authorization", "http", "cache", "parser", "producer"],
            ),
            synthetic_unit(
                "plain_public_snapshot",
                ["continuum.snapshot.v0.2"],
                ["public-data"],
                ["http", "cache", "parser", "producer"],
            ),
            synthetic_unit(
                "protected_ssr_snapshot",
                ["continuum.snapshot.v0.2"],
                ["protected-data", "cookie-auth", "ssr-bootstrap", "prehydration-purge-guard"],
                ["authorization", "http", "cache", "parser", "producer"],
            ),
            synthetic_unit(
                "protected_fetch_subscribe",
                ["continuum.snapshot.v0.2", "continuum.invalidate.v0.2"],
                ["protected-data", "non-cookie-auth", "fetch-stream", "subscribe-first"],
                ["authorization", "http", "cache", "sse", "parser", "producer"],
            ),
            synthetic_unit(
                "protected_cookie_native_subscribe",
                ["continuum.snapshot.v0.2", "continuum.invalidate.v0.2"],
                [
                    "protected-data",
                    "cookie-auth",
                    "native-eventsource",
                    "subscribe-first",
                ],
                ["authorization", "http", "cache", "sse", "parser", "producer"],
            ),
            synthetic_unit(
                "protected_cookie_native_multiplexed",
                ["continuum.snapshot.v0.2", "continuum.invalidate.v0.2"],
                [
                    "protected-data",
                    "cookie-auth",
                    "native-eventsource",
                    "subscribe-first",
                    "multiplexed-stream",
                ],
                [
                    "authorization",
                    "http",
                    "cache",
                    "sse",
                    "parser",
                    "producer",
                    "multistream",
                ],
            ),
            synthetic_unit(
                "protected_json_patch_fetch",
                [
                    "continuum.snapshot.v0.2",
                    "continuum.invalidate.v0.2",
                    "continuum.patch.json.v0.2",
                ],
                ["protected-data", "non-cookie-auth", "fetch-stream", "subscribe-first"],
                ["authorization", "http", "cache", "sse", "parser", "producer"],
            ),
            synthetic_unit(
                "protected_merge_patch_fetch",
                [
                    "continuum.snapshot.v0.2",
                    "continuum.invalidate.v0.2",
                    "continuum.patch.merge.v0.2",
                ],
                ["protected-data", "non-cookie-auth", "fetch-stream", "subscribe-first"],
                ["authorization", "http", "cache", "sse", "parser", "producer"],
            ),
            synthetic_unit(
                "protected_multiplexed_subscribe",
                ["continuum.snapshot.v0.2", "continuum.invalidate.v0.2"],
                [
                    "protected-data",
                    "non-cookie-auth",
                    "fetch-stream",
                    "subscribe-first",
                    "multiplexed-stream",
                ],
                ["authorization", "http", "cache", "sse", "parser", "producer", "multistream"],
            ),
            synthetic_unit(
                "protected_multiplexed_snapshot_first",
                [
                    "continuum.snapshot.v0.2",
                    "continuum.invalidate.v0.2",
                    "continuum.replay.v0.2",
                ],
                [
                    "protected-data",
                    "non-cookie-auth",
                    "fetch-stream",
                    "snapshot-first",
                    "multiplexed-stream",
                ],
                ["authorization", "http", "cache", "sse", "parser", "producer", "multistream"],
            ),
            synthetic_unit(
                "protected_snapshot_rollout",
                ["continuum.snapshot.v0.2"],
                ["protected-data", "cookie-auth", "rollout-candidate"],
                ["authorization", "http", "cache", "parser", "producer", "rollout"],
            ),
            synthetic_unit(
                "native_public",
                ["continuum.snapshot.v0.2", "continuum.invalidate.v0.2"],
                ["public-data", "native-eventsource", "subscribe-first"],
                ["http", "cache", "sse", "parser", "producer"],
            ),
            synthetic_unit(
                "json_patch_fetch",
                [
                    "continuum.snapshot.v0.2",
                    "continuum.invalidate.v0.2",
                    "continuum.patch.json.v0.2",
                ],
                ["public-data", "fetch-stream", "subscribe-first"],
                ["http", "cache", "sse", "parser", "producer"],
            ),
            synthetic_unit(
                "merge_patch_fetch",
                [
                    "continuum.snapshot.v0.2",
                    "continuum.invalidate.v0.2",
                    "continuum.patch.merge.v0.2",
                ],
                ["public-data", "fetch-stream", "subscribe-first"],
                ["http", "cache", "sse", "parser", "producer"],
            ),
            synthetic_unit(
                "replay_multiplexed",
                [
                    "continuum.snapshot.v0.2",
                    "continuum.invalidate.v0.2",
                    "continuum.replay.v0.2",
                ],
                [
                    "public-data",
                    "fetch-stream",
                    "snapshot-first",
                    "multiplexed-stream",
                ],
                ["http", "cache", "sse", "parser", "producer", "multistream"],
            ),
            synthetic_unit(
                "subscribe_first_multiplexed",
                ["continuum.snapshot.v0.2", "continuum.invalidate.v0.2"],
                [
                    "public-data",
                    "fetch-stream",
                    "subscribe-first",
                    "multiplexed-stream",
                ],
                ["http", "cache", "sse", "parser", "producer", "multistream"],
            ),
            synthetic_unit(
                "protected_external_command",
                ["continuum.command-receipt.v0.2"],
                [
                    "protected-data",
                    "cookie-auth",
                    "external-provider",
                    "service-worker-present",
                    "rollout-candidate",
                ],
                [
                    "authorization",
                    "http",
                    "cache",
                    "parser",
                    "producer",
                    "command",
                    "rollout",
                ],
            ),
        ],
    }
    capability_matrix["state_domain_registry"] = {}
    for unit in capability_matrix["units"]:
        for domain_id in unit["state_domains"]:
            effective_identity = {
                "kind": "memory",
                "backend_instance": f"synthetic-backend-{domain_id}",
                "partition": "synthetic",
                "namespace": domain_id,
            }
            capability_matrix["state_domain_registry"][domain_id] = {
            "kind": "memory",
            "adapter_locator": f"urn:continuum-state-domain:{domain_id}",
            "namespace": domain_id,
            "canonicalizer": {"id": "continuum.state-domain-jcs", "version": "1"},
            "effective_backing_identity": effective_identity,
            "effective_backing_identity_digest": state_digest(effective_identity),
            "trace_evidence": f"urn:continuum-trace:state-{domain_id}",
        }
    validate(capability_matrix, "synthetic capability matrix", manifest_check)
    validate_conformance_manifest("synthetic capability matrix", capability_matrix, binding)

    invalid_manifests: list[tuple[str, dict[str, Any], str]] = []
    duplicate_unit = copy.deepcopy(manifest)
    duplicate_unit["units"][1]["id"] = duplicate_unit["units"][0]["id"]
    invalid_manifests.append(("duplicate conformance unit", duplicate_unit, "duplicate conformance unit id"))
    shared_result_document = copy.deepcopy(manifest)
    shared_result_document["units"][1]["result_document"] = shared_result_document["units"][0][
        "result_document"
    ]
    invalid_manifests.append(("shared result document", shared_result_document, "result document is shared"))
    shared_trace_evidence = copy.deepcopy(manifest)
    shared_trace_evidence["units"][1]["trace_evidence"] = shared_trace_evidence["units"][0][
        "trace_evidence"
    ]
    invalid_manifests.append(("shared trace evidence", shared_trace_evidence, "trace evidence is shared"))
    shared_without_cache = copy.deepcopy(manifest)
    shared_without_cache["units"][0]["profiles"].remove("service-worker-present")
    shared_without_cache["units"][0]["layers"].remove("cache")
    invalid_manifests.append(("shared cache profile without cache layer", shared_without_cache, "cache profile lacks cache layer"))
    service_worker_without_cache = copy.deepcopy(manifest)
    service_worker_without_cache["units"][0]["profiles"].remove("public-shared-cache")
    service_worker_without_cache["units"][0]["layers"].remove("cache")
    invalid_manifests.append(("service worker profile without cache layer", service_worker_without_cache, "cache profile lacks cache layer"))
    multiplex_without_layer = copy.deepcopy(manifest)
    multiplex_without_layer["units"][1]["profiles"].append("multiplexed-stream")
    invalid_manifests.append(("multiplexed profile without multistream layer", multiplex_without_layer, "multiplexed stream lacks multistream or sse layer"))
    stream_without_cut = copy.deepcopy(manifest)
    stream_without_cut["units"][1]["profiles"].remove("subscribe-first")
    invalid_manifests.append(("realtime transport without cut strategy", stream_without_cut, "sse layer requires exactly one cut strategy"))
    data_without_classification = copy.deepcopy(manifest)
    data_without_classification["units"][1]["profiles"].remove("public-data")
    invalid_manifests.append(("data scope without security classification", data_without_classification, "data scope requires exactly one security classification"))
    sse_without_transport = copy.deepcopy(manifest)
    sse_without_transport["units"][1]["profiles"].remove("fetch-stream")
    invalid_manifests.append(("sse layer without transport profile", sse_without_transport, "sse layer requires exactly one native/fetch transport"))
    realtime_without_snapshot = copy.deepcopy(manifest)
    realtime_without_snapshot["units"][1]["capabilities"].remove("continuum.snapshot.v0.2")
    invalid_manifests.append(("realtime scope without snapshot", realtime_without_snapshot, "realtime scope lacks snapshot or invalidate capability"))
    realtime_without_sse = copy.deepcopy(manifest)
    realtime_without_sse["units"][1]["profiles"] = ["public-data"]
    realtime_without_sse["units"][1]["layers"].remove("sse")
    realtime_without_sse["units"][1]["limits"] = {
        limit: realtime_without_sse["units"][1]["limits"][limit]
        for limit in DATA_BASE_LIMITS
    }
    invalid_manifests.append(("realtime capability without SSE", realtime_without_sse, "realtime capability requires sse layer"))
    sse_without_transport = copy.deepcopy(manifest)
    sse_without_transport["units"][1]["profiles"].remove("fetch-stream")
    invalid_manifests.append(("SSE without native/fetch transport", sse_without_transport, "sse layer requires exactly one native/fetch transport"))
    snapshot_first_without_replay = copy.deepcopy(manifest)
    snapshot_first_without_replay["units"][1]["profiles"].remove("subscribe-first")
    snapshot_first_without_replay["units"][1]["profiles"].append("snapshot-first")
    invalid_manifests.append(("snapshot-first without replay", snapshot_first_without_replay, "snapshot-first realtime requires replay capability"))
    native_snapshot_first = copy.deepcopy(manifest)
    native_snapshot_first["units"][1]["profiles"].remove("fetch-stream")
    native_snapshot_first["units"][1]["profiles"].remove("subscribe-first")
    native_snapshot_first["units"][1]["profiles"].extend(
        ["native-eventsource", "snapshot-first"]
    )
    invalid_manifests.append(("native EventSource with snapshot-first", native_snapshot_first, "native EventSource requires subscribe-first"))
    command_without_protection = copy.deepcopy(manifest)
    command_without_protection["units"][1]["capabilities"] = [
        "continuum.command-receipt.v0.2"
    ]
    command_without_protection["units"][1]["profiles"] = []
    command_without_protection["units"][1]["layers"] = ["command"]
    invalid_manifests.append(("command receipt without protection", command_without_protection, "command receipt classification must be protected only"))
    command_without_cache = copy.deepcopy(manifest)
    command_without_cache["units"][3]["layers"].remove("cache")
    invalid_manifests.append(("command receipt without cache layer", command_without_cache, "command receipt lacks required binding layer"))
    ssr_without_http = copy.deepcopy(manifest)
    ssr_without_http["units"][0]["layers"].remove("http")
    invalid_manifests.append(("SSR profile without HTTP layer", ssr_without_http, "SSR profile lacks http layer"))
    cut_without_sse = copy.deepcopy(manifest)
    cut_without_sse["units"][1]["profiles"].remove("fetch-stream")
    cut_without_sse["units"][1]["layers"].remove("sse")
    invalid_manifests.append(("cut strategy without SSE layer", cut_without_sse, "realtime capability requires sse layer"))
    missing_limit = copy.deepcopy(manifest)
    del missing_limit["units"][0]["limits"]["max_json_depth"]
    invalid_manifests.append(("missing mandatory limit", missing_limit, "limit set mismatch"))
    irrelevant_limit = copy.deepcopy(manifest)
    irrelevant_limit["units"][0]["limits"]["max_patch_ops"] = 10
    invalid_manifests.append(("irrelevant limit outside unit facets", irrelevant_limit, "limit set mismatch"))
    rollout_above_hard_memory = copy.deepcopy(manifest)
    rollout_above_hard_memory["units"][0]["rollout"]["thresholds"][
        "max_resident_bytes"
    ] = rollout_above_hard_memory["units"][0]["limits"]["max_resident_bytes"] + 1
    invalid_manifests.append(("rollout memory threshold above hard limit", rollout_above_hard_memory, "rollout memory threshold exceeds hard limit"))

    unknown_domain_ref = copy.deepcopy(manifest)
    unknown_domain_ref["units"][0]["state_domains"].append("unknown_domain")
    invalid_manifests.append(("unknown state domain ref", unknown_domain_ref, "unknown state domain refs"))

    orphan_domain = copy.deepcopy(manifest)
    orphan_descriptor = copy.deepcopy(orphan_domain["state_domain_registry"]["public_snapshot_http"])
    orphan_descriptor["adapter_locator"] = "urn:continuum-state-domain:orphan-domain"
    orphan_descriptor["namespace"] = "orphan-domain"
    orphan_descriptor["effective_backing_identity"]["namespace"] = "orphan-domain"
    orphan_descriptor["effective_backing_identity_digest"] = state_digest(
        orphan_descriptor["effective_backing_identity"]
    )
    orphan_descriptor["trace_evidence"] = "urn:continuum-trace:state-orphan-domain"
    orphan_domain["state_domain_registry"]["orphan_domain"] = orphan_descriptor
    invalid_manifests.append(("orphan state domain", orphan_domain, "orphan state domains"))

    shared_domain_owner = copy.deepcopy(manifest)
    shared_domain_owner["units"][1]["state_domains"].append("public_snapshot_http")
    invalid_manifests.append((
        "state domain referenced by two same-class units",
        shared_domain_owner,
        "each state domain must belong to exactly one consolidated unit",
    ))

    aliased_effective_identity = copy.deepcopy(manifest)
    alias = aliased_effective_identity["state_domain_registry"]["public_live_fetch"]
    original = aliased_effective_identity["state_domain_registry"]["public_snapshot_http"]
    alias["kind"] = original["kind"]
    alias["namespace"] = original["namespace"]
    alias["canonicalizer"] = {"id": "different.canonicalizer", "version": "99"}
    alias["effective_backing_identity"] = copy.deepcopy(original["effective_backing_identity"])
    alias["effective_backing_identity_digest"] = original[
        "effective_backing_identity_digest"
    ]
    invalid_manifests.append((
        "distinct locators alias one effective backing resource",
        aliased_effective_identity,
        "identify the same effective backing resource",
    ))

    wrong_effective_identity_digest = copy.deepcopy(manifest)
    wrong_effective_identity_digest["state_domain_registry"]["public_snapshot_http"][
        "effective_backing_identity_digest"
    ] = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    invalid_manifests.append((
        "wrong effective backing identity digest",
        wrong_effective_identity_digest,
        "effective backing identity digest",
    ))

    edge_whitespace_identity = copy.deepcopy(manifest)
    edge_descriptor = edge_whitespace_identity["state_domain_registry"][
        "public_snapshot_http"
    ]
    edge_descriptor["namespace"] = " public-snapshot-http"
    edge_descriptor["effective_backing_identity"]["namespace"] = " public-snapshot-http"
    edge_descriptor["effective_backing_identity_digest"] = state_digest(
        edge_descriptor["effective_backing_identity"]
    )
    invalid_manifests.append((
        "state-domain identity with edge whitespace",
        edge_whitespace_identity,
        "has edge whitespace",
    ))

    non_nfc_identity = copy.deepcopy(manifest)
    non_nfc_descriptor = non_nfc_identity["state_domain_registry"]["public_snapshot_http"]
    non_nfc_descriptor["effective_backing_identity"]["backend_instance"] = "cafe\u0301"
    non_nfc_descriptor["effective_backing_identity_digest"] = state_digest(
        non_nfc_descriptor["effective_backing_identity"]
    )
    invalid_manifests.append((
        "state-domain identity without NFC normalization",
        non_nfc_identity,
        "is not NFC",
    ))

    duplicate_domain_trace = copy.deepcopy(manifest)
    duplicate_domain_trace["state_domain_registry"]["public_live_fetch"]["trace_evidence"] = (
        duplicate_domain_trace["state_domain_registry"]["public_snapshot_http"]["trace_evidence"]
    )
    invalid_manifests.append((
        "duplicate state-domain trace evidence",
        duplicate_domain_trace,
        "state-domain trace evidence is not unique",
    ))

    rollout_layer_without_profile = copy.deepcopy(manifest)
    rollout_layer_without_profile["units"][0]["profiles"].remove("rollout-candidate")
    invalid_manifests.append((
        "rollout layer without rollout profile",
        rollout_layer_without_profile,
        "rollout layer and rollout-candidate profile must coincide",
    ))

    rollout_profile_without_layer = copy.deepcopy(manifest)
    rollout_profile_without_layer["units"][0]["layers"].remove("rollout")
    invalid_manifests.append((
        "rollout profile without rollout layer",
        rollout_profile_without_layer,
        "rollout layer and rollout-candidate profile must coincide",
    ))

    dead_declared_layer = copy.deepcopy(manifest)
    dead_declared_layer["units"][0]["layers"].append("authorization")
    invalid_manifests.append((
        "declared layer without applicable vector",
        dead_declared_layer,
        "declared layers lack applicable vectors",
    ))

    native_patch = copy.deepcopy(capability_matrix)
    native_patch_unit = next(unit for unit in native_patch["units"] if unit["id"] == "json_patch_fetch")
    native_patch_unit["profiles"].remove("fetch-stream")
    native_patch_unit["profiles"].append("native-eventsource")
    invalid_manifests.append((
        "native EventSource with patch capability",
        native_patch,
        "patch capabilities require fetch-stream",
    ))

    protected_native_non_cookie = copy.deepcopy(capability_matrix)
    protected_native_unit = next(
        unit
        for unit in protected_native_non_cookie["units"]
        if unit["id"] == "protected_cookie_native_subscribe"
    )
    protected_native_unit["profiles"].remove("cookie-auth")
    protected_native_unit["profiles"].append("non-cookie-auth")
    invalid_manifests.append((
        "protected native EventSource with non-cookie auth",
        protected_native_non_cookie,
        "protected native EventSource requires cookie-auth",
    ))

    protected_ssr_without_guard = copy.deepcopy(capability_matrix)
    protected_ssr_unit = next(
        unit
        for unit in protected_ssr_without_guard["units"]
        if unit["id"] == "protected_ssr_snapshot"
    )
    protected_ssr_unit["profiles"].remove("prehydration-purge-guard")
    invalid_manifests.append((
        "generic protected SSR without prehydration purge guard",
        protected_ssr_without_guard,
        "protected SSR requires a parser-blocking prehydration purge guard",
    ))

    def add_limit_relation_fault(
        label: str,
        unit_id: str,
        updates: dict[str, int],
        expected_error: str,
    ) -> None:
        invalid = copy.deepcopy(capability_matrix)
        unit = next(item for item in invalid["units"] if item["id"] == unit_id)
        unit["limits"].update(updates)
        invalid_manifests.append((label, invalid, expected_error))

    add_limit_relation_fault("result above resident", "plain_public_snapshot", {"max_result_bytes": 1_000_001}, "result limit exceeds resident limit")
    add_limit_relation_fault("compressed above resident", "plain_public_snapshot", {"max_compressed_response_bytes": 1_000_001}, "compressed response exceeds resident limit")
    add_limit_relation_fault("decoded above resident", "plain_public_snapshot", {"max_decoded_response_bytes": 1_000_001}, "decoded response exceeds resident limit")
    add_limit_relation_fault("response head above resident", "plain_public_snapshot", {"max_response_head_bytes": 1_000_001}, "response head exceeds resident limit")
    add_limit_relation_fault("request head above resident", "plain_public_snapshot", {"max_request_head_bytes": 1_000_001}, "request head exceeds resident limit")
    add_limit_relation_fault("request identifier above request head", "plain_public_snapshot", {"max_request_identifier_bytes": 1_001}, "request identifier exceeds request-head representability")
    add_limit_relation_fault("protected request body above resident", "protected_snapshot", {"max_request_body_bytes": 1_000_001}, "request body exceeds resident limit")
    add_limit_relation_fault("JSON depth above nodes", "plain_public_snapshot", {"max_json_depth": 1_001}, "JSON depth exceeds node limit")
    add_limit_relation_fault("JSON nodes above decoded bytes", "plain_public_snapshot", {"max_json_nodes": 1_001}, "JSON nodes exceed decoded-byte representability")
    add_limit_relation_fault("patch operations above JSON nodes", "json_patch_fetch", {"max_patch_ops": 1_001}, "patch operations exceed JSON nodes")
    add_limit_relation_fault("SSE line above event", "protected_fetch_subscribe", {"max_sse_line_bytes": 10_001}, "SSE line limit exceeds event limit")
    add_limit_relation_fault("SSE event above resident", "protected_fetch_subscribe", {"max_result_bytes": 9_999, "max_resident_bytes": 9_999}, "SSE event exceeds resident limit")
    add_limit_relation_fault("SSE event above queue bytes", "protected_fetch_subscribe", {"max_sse_event_data_bytes": 10_001}, "SSE event exceeds queue byte limit")
    add_limit_relation_fault("SSE event above generation bytes", "protected_fetch_subscribe", {"max_bytes_per_subscription_generation": 9_999}, "SSE event exceeds generation byte limit")
    add_limit_relation_fault("event rate above generation events", "protected_fetch_subscribe", {"max_events_per_second": 10_001}, "event-rate limit exceeds generation event limit")
    add_limit_relation_fault("queue bytes above resident", "protected_fetch_subscribe", {"max_queue_bytes": 1_000_001, "max_bytes_per_subscription_generation": 1_000_001}, "queue limit exceeds resident limit")
    add_limit_relation_fault("queue events above generation events", "protected_fetch_subscribe", {"max_queue_events": 10_001, "max_queue_bytes": 10_001}, "queue events exceed subscription-generation events")
    add_limit_relation_fault("queue bytes above generation bytes", "protected_fetch_subscribe", {"max_queue_bytes": 100_001}, "queue bytes exceed subscription-generation bytes")
    add_limit_relation_fault("queue bytes cannot hold one byte per event", "protected_fetch_subscribe", {"max_sse_line_bytes": 999, "max_sse_event_data_bytes": 999, "max_queue_bytes": 999}, "queue byte limit cannot represent one byte per event")
    add_limit_relation_fault("generation bytes cannot hold one byte per event", "protected_fetch_subscribe", {"max_sse_line_bytes": 999, "max_sse_event_data_bytes": 9_999, "max_queue_bytes": 9_999, "max_bytes_per_subscription_generation": 9_999}, "generation byte limit cannot represent one byte per event")
    add_limit_relation_fault("replay events above generation events", "replay_multiplexed", {"max_replay_events": 10_001}, "replay events exceed subscription-generation events")
    add_limit_relation_fault("replay bytes above generation bytes", "replay_multiplexed", {"max_replay_bytes": 100_001}, "replay bytes exceed subscription-generation bytes")
    add_limit_relation_fault("replay bytes cannot hold one byte per event", "replay_multiplexed", {"max_replay_bytes": 999}, "replay byte limit cannot represent one byte per event")
    add_limit_relation_fault("reconcile interval plus jitter above I-JSON", "protected_fetch_subscribe", {"max_canonical_reconcile_interval_ms": 9_007_199_254_740_990, "max_canonical_reconcile_jitter_ms": 2}, "reconcile interval plus jitter exceeds I-JSON")
    add_limit_relation_fault("lease duration above revocation SLA", "protected_snapshot", {"max_lease_ms": 60_001}, "lease duration exceeds revocation SLA")
    for label, invalid_manifest, expected_error in invalid_manifests:
        try:
            validate_conformance_manifest(label, invalid_manifest, binding)
        except AssertionError as error:
            if expected_error not in str(error):
                raise AssertionError(
                    f"{label}: expected semantic error containing {expected_error!r}, got {str(error)!r}"
                ) from error
        else:
            raise AssertionError(f"invalid conformance manifest accepted: {label}")

    single_snapshot_manifest = copy.deepcopy(manifest)
    single_snapshot_manifest["units"] = [single_snapshot_manifest["units"][0]]
    single_snapshot_manifest["state_domain_registry"] = {
        "public_snapshot_http": single_snapshot_manifest["state_domain_registry"][
            "public_snapshot_http"
        ]
    }

    binding_without_ssr_profile_evidence = copy.deepcopy(binding)
    for vector in binding_without_ssr_profile_evidence["vectors"]:
        if "ssr-bootstrap" in vector.get("requires_profiles", []):
            vector["requires_profiles"].remove("ssr-bootstrap")
    try:
        validate_conformance_manifest(
            "profile facet without explicit vector evidence",
            single_snapshot_manifest,
            binding_without_ssr_profile_evidence,
        )
    except AssertionError as error:
        if "declared profiles lack explicit applicable vectors" not in str(error):
            raise AssertionError(
                "profile facet negative fixture failed for the wrong reason: "
                f"{error}"
            ) from error
    else:
        raise AssertionError("profile facet without explicit vector evidence was accepted")

    binding_without_snapshot_capability_evidence = copy.deepcopy(binding)
    for vector in binding_without_snapshot_capability_evidence["vectors"]:
        if "continuum.snapshot.v0.2" in vector["capabilities"]:
            vector["capabilities"].remove("continuum.snapshot.v0.2")
    try:
        validate_conformance_manifest(
            "capability facet without explicit vector evidence",
            single_snapshot_manifest,
            binding_without_snapshot_capability_evidence,
        )
    except AssertionError as error:
        if "declared capabilities lack applicable vectors" not in str(error):
            raise AssertionError(
                "capability facet negative fixture failed for the wrong reason: "
                f"{error}"
            ) from error
    else:
        raise AssertionError("capability facet without explicit vector evidence was accepted")

    incomplete_rollout_thresholds = copy.deepcopy(manifest)
    del incomplete_rollout_thresholds["units"][0]["rollout"]["thresholds"]["error_rate_regression"]
    assert_invalid(
        incomplete_rollout_thresholds,
        "rollout candidate with incomplete thresholds",
        manifest_check,
    )
    nonzero_leak_budget = copy.deepcopy(manifest)
    nonzero_leak_budget["units"][0]["rollout"]["thresholds"]["cross_audience_leaks"] = 1
    assert_invalid(
        nonzero_leak_budget,
        "rollout candidate with nonzero cross-audience leak budget",
        manifest_check,
    )
    unknown_limit = copy.deepcopy(manifest)
    unknown_limit["units"][0]["limits"] = {"foo": 1}
    assert_invalid(unknown_limit, "manifest with unknown-only limits", manifest_check)

    limit_schemas = documents["conformance-manifest.schema.json"]["$defs"]["limits"][
        "properties"
    ]
    for limit_name, limit_schema in limit_schemas.items():
        at_maximum_plus_one = copy.deepcopy(capability_matrix)
        unit = next(
            candidate
            for candidate in at_maximum_plus_one["units"]
            if limit_name in candidate["limits"]
        )
        unit["limits"][limit_name] = limit_schema["maximum"] + 1
        assert_invalid(
            at_maximum_plus_one,
            f"{limit_name} above schema maximum leaves no representable N+1 probe",
            manifest_check,
            "greater than the maximum",
        )

    for threshold_name, invalid_value in (
        ("semantic_divergence_ppm", 1_000_000),
        ("repair_loop_rate", Decimal("1")),
        ("reconnect_storm_rate", Decimal("1")),
        ("p95_latency_regression_ms", 9_007_199_254_740_991),
        ("error_rate_regression", Decimal("1")),
        ("max_resident_bytes", 9_007_199_254_740_991),
    ):
        invalid_rollout_threshold = copy.deepcopy(manifest)
        invalid_rollout_threshold["units"][0]["rollout"]["thresholds"][
            threshold_name
        ] = invalid_value
        assert_invalid(
            invalid_rollout_threshold,
            f"rollout {threshold_name} has no representable above-threshold probe",
            manifest_check,
            "greater than or equal to the maximum"
            if isinstance(invalid_value, Decimal)
            else "greater than the maximum",
        )

    invalid_state_locator = copy.deepcopy(manifest)
    invalid_state_locator["state_domain_registry"]["public_snapshot_http"][
        "adapter_locator"
    ] = "urn:continuum-state-domain:public%2dsnapshot"
    assert_invalid(
        invalid_state_locator,
        "percent-encoded state-domain locator alias",
        manifest_check,
        "does not match",
    )

    invalid_result_document = copy.deepcopy(manifest)
    invalid_result_document["units"][0]["result_document"] = "file:/tmp/result.json"
    assert_invalid(
        invalid_result_document,
        "physical result-document locator",
        manifest_check,
        "does not match",
    )

    invalid_trace_evidence = copy.deepcopy(manifest)
    invalid_trace_evidence["units"][0]["trace_evidence"] = "file:///tmp/trace.json"
    assert_invalid(
        invalid_trace_evidence,
        "physical trace-evidence locator",
        manifest_check,
        "does not match",
    )

    missing_canonicalizer = copy.deepcopy(manifest)
    del missing_canonicalizer["state_domain_registry"]["public_snapshot_http"][
        "canonicalizer"
    ]
    assert_invalid(
        missing_canonicalizer,
        "state domain without canonicalizer",
        manifest_check,
        "canonicalizer",
    )

    incomplete_effective_identity = copy.deepcopy(manifest)
    del incomplete_effective_identity["state_domain_registry"]["public_snapshot_http"][
        "effective_backing_identity"
    ]["partition"]
    assert_invalid(
        incomplete_effective_identity,
        "state domain without effective partition identity",
        manifest_check,
        "partition",
    )

    binding_defs = documents["binding-vectors.schema.json"]["$defs"]
    manifest_defs = documents["conformance-manifest.schema.json"]["$defs"]
    for binding_name, manifest_name in (
        ("capability", "capability"),
        ("deploymentProfile", "profile"),
        ("layer", "layer"),
    ):
        if set(binding_defs[binding_name]["enum"]) != set(manifest_defs[manifest_name]["enum"]):
            raise AssertionError(f"manifest and binding {binding_name} enums diverge")

    declared_profiles = set(
        documents["binding-vectors.schema.json"]["$defs"]["deploymentProfile"]["enum"]
    )
    exercised_profiles = {
        profile
        for vector in binding["vectors"]
        for profile in vector.get("requires_profiles", [])
    }
    if missing_profiles := declared_profiles - exercised_profiles:
        raise AssertionError(
            f"deployment profiles without a binding vector: {sorted(missing_profiles)}"
        )
    declared_layers = set(documents["binding-vectors.schema.json"]["$defs"]["layer"]["enum"])
    exercised_layers = {vector["layer"] for vector in binding["vectors"]}
    if missing_layers := declared_layers - exercised_layers:
        raise AssertionError(f"binding layers without a vector: {sorted(missing_layers)}")

    ids: set[str] = set()
    for corpus_name, corpus in (("core", core), ("binding", binding)):
        for vector in corpus["vectors"]:
            vector_id = vector["id"]
            if vector_id in ids:
                raise AssertionError(f"duplicate vector id across corpora: {vector_id}")
            ids.add(vector_id)
            if corpus_name == "core":
                explicit = set(vector["expected"])
                absent = set(vector["expected"].get("absent_fields", []))
                overlap = {path for path in absent if path[1:] in explicit}
                if overlap:
                    raise AssertionError(f"{vector_id}: field is both present and absent: {overlap}")

    for vector in core["vectors"]:
        for action in vector["actions"]:
            if "message_ref" not in action:
                continue
            message = fixture(f"examples.json#{action['message_ref']}", documents)
            for replacement in action.get("replace", []):
                message = replace_existing(
                    message,
                    replacement["path"],
                    materialize_limit_expression_for_schema(replacement["value"]),
                )
            validate(message, f"{vector['id']} derived message", message_check)
            expected_violation = action.get("expected_semantic_violation")
            if expected_violation is None:
                validate_message_semantics(f"{vector['id']} derived message", message)
            elif expected_violation == "subject_stream_mismatch":
                try:
                    validate_message_semantics(f"{vector['id']} derived message", message)
                except AssertionError as error:
                    if "subject" not in str(error):
                        raise AssertionError(
                            f"{vector['id']}: expected subject mismatch, got {error}"
                        ) from error
                else:
                    raise AssertionError(
                        f"{vector['id']}: expected subject mismatch was not present"
                    )

    for vector in binding["vectors"]:
        given = vector["given"]
        current_security_generation = next(
            (
                given[key]
                for key in (
                    "security_generation",
                    "security_generation_id",
                    "active_generation",
                )
                if isinstance(given.get(key), str)
            ),
            None,
        )
        current_subscription = next(
            (
                given[key]
                for key in ("subscription_id", "active_subscription")
                if isinstance(given.get(key), str)
            ),
            None,
        )
        request_headers_by_target: dict[str, dict[str, Any]] = {}
        actions = vector["actions"]
        for action_index, action in enumerate(actions):
            if action["op"] == "request":
                request_headers_by_target[action["target"]] = action.get("headers", {})
            batch_messages: list[dict[str, Any]] = []
            for batch_descriptor in action.get("fixtures", []):
                if isinstance(batch_descriptor, str):
                    batch_ref = batch_descriptor
                    batch_replacements: list[dict[str, Any]] = []
                else:
                    batch_ref = batch_descriptor["fixture"]
                    batch_replacements = batch_descriptor["replace"]
                if not batch_ref.startswith(
                    ("examples.json#", "binding-protected-examples.json#")
                ):
                    raise AssertionError(
                        f"{vector['id']}: batch fixture must reference a message fixture"
                    )
                batch_message = fixture(batch_ref, documents)
                for replacement in batch_replacements:
                    batch_message = replace_existing(
                        batch_message,
                        replacement["path"],
                        materialize_limit_expression_for_schema(replacement["value"]),
                    )
                validate(
                    batch_message,
                    f"{vector['id']} batch message {batch_ref}",
                    message_check,
                )
                validate_message_semantics(
                    f"{vector['id']} batch message {batch_ref}", batch_message
                )
                stream = batch_message.get("data", {}).get("stream")
                if stream:
                    fixture_profile = (
                        "public-data"
                        if stream["classification"] == "public"
                        else "protected-data"
                    )
                    if (
                        fixture_profile not in set(vector.get("requires_profiles", []))
                        and action.get("expected_batch_violation") != "stream_mismatch"
                    ):
                        raise AssertionError(
                            f"{vector['id']}: {batch_ref} fixes "
                            f"{stream['classification']} classification without "
                            f"{fixture_profile} profile"
                        )
                batch_messages.append(batch_message)
            if batch_messages:
                violations: set[str] = set()
                if any(message.get("data", {}).get("kind") != "patch" for message in batch_messages):
                    raise AssertionError(f"{vector['id']}: repair batch contains non-patch message")
                streams = [message["data"]["stream"] for message in batch_messages]
                stream_identities = {
                    (
                        stream["id"],
                        stream["projection"],
                        stream["partition"],
                        stream["classification"],
                    )
                    for stream in streams
                }
                if len(stream_identities) != 1:
                    violations.add("stream_mismatch")
                authorized_stream = given.get("authorized_stream_descriptor")
                descriptor_keys = {
                    "id",
                    "projection",
                    "partition",
                    "schema",
                    "classification",
                }
                if (
                    not isinstance(authorized_stream, dict)
                    or set(authorized_stream) != descriptor_keys
                ):
                    raise AssertionError(
                        f"{vector['id']}: repair vector must declare exact "
                        "given.authorized_stream_descriptor"
                    )
                authorized_identity = tuple(
                    authorized_stream[key]
                    for key in ("id", "projection", "partition", "classification")
                )
                if any(identity != authorized_identity for identity in stream_identities):
                    violations.add("stream_mismatch")
                if (
                    len({stream["schema"] for stream in streams}) != 1
                    or any(stream["schema"] != authorized_stream["schema"] for stream in streams)
                ):
                    violations.add("schema_mismatch")
                epochs = {
                    cursor["epoch"]
                    for message in batch_messages
                    for cursor in (
                        message["data"]["base"]["cursor"],
                        message["data"]["target"]["cursor"],
                    )
                }
                if len(epochs) != 1:
                    violations.add("epoch_mismatch")

                def patch_tuple(value: dict[str, Any]) -> tuple[Any, ...]:
                    return (
                        value["cursor"]["epoch"],
                        value["cursor"]["sequence"],
                        value["state_token"],
                        value["state_digest"],
                    )

                if "epoch_mismatch" not in violations and any(
                    patch_tuple(previous["data"]["target"])
                    != patch_tuple(current["data"]["base"])
                    for previous, current in zip(batch_messages, batch_messages[1:])
                ):
                    violations.add("noncontiguous_chain")
                final_data = batch_messages[-1]["data"]
                final_target = final_data["target"]
                headers = action.get("headers", {})
                correlated_request_target = action.get("correlates_request_target")
                if not isinstance(correlated_request_target, str):
                    raise AssertionError(
                        f"{vector['id']}: repair response must declare "
                        "correlates_request_target"
                    )
                request_headers = request_headers_by_target.get(correlated_request_target)
                if request_headers is None:
                    raise AssertionError(
                        f"{vector['id']}: repair response correlates unknown or future request "
                        f"{correlated_request_target!r}"
                    )
                request_repair_id = request_headers.get("Continuum-Repair-Id")
                if (
                    not isinstance(request_repair_id, str)
                    or headers.get("Continuum-Repair-Id") != request_repair_id
                ):
                    raise AssertionError(
                        f"{vector['id']}: repair response must echo the exact current "
                        "Continuum-Repair-Id"
                    )
                if action.get("wire_body_encoding") != "jcs-utf8":
                    raise AssertionError(
                        f"{vector['id']}: repair response must declare exact JCS UTF-8 "
                        "wire bytes for ETag validation"
                    )
                expected_etag = repair_payload_etag(batch_messages)
                if headers.get("ETag") != expected_etag:
                    raise AssertionError(
                        f"{vector['id']}: repair ETag {headers.get('ETag')!r} != "
                        f"strong ETag of exact wire bytes {expected_etag!r}"
                    )
                expected_content_type = (
                    "application/cloudevents+json"
                    if len(batch_messages) == 1
                    else "application/cloudevents-batch+json"
                )
                if headers.get("Content-Type") != expected_content_type:
                    raise AssertionError(
                        f"{vector['id']}: repair response with {len(batch_messages)} "
                        f"patch(es) must use {expected_content_type}"
                    )
                expected_version_headers = {
                    "Continuum-Stream": final_data["stream"]["id"],
                    "Continuum-Epoch": final_target["cursor"]["epoch"],
                    "Continuum-Sequence": final_target["cursor"]["sequence"],
                    "Continuum-State-Token": final_target["state_token"],
                    "Continuum-State-Digest": final_target["state_digest"],
                }
                if any(headers.get(name) != value for name, value in expected_version_headers.items()):
                    violations.add("final_version_header_mismatch")
                expected_freshness_headers = {
                    "Continuum-Fresh-For-Ms": final_data["freshness"]["fresh_for_ms"],
                    "Continuum-Stale-If-Error-Ms": final_data["freshness"]["stale_if_error_ms"],
                }
                if any(headers.get(name) != value for name, value in expected_freshness_headers.items()):
                    violations.add("final_freshness_header_mismatch")
                response_age = headers.get("Continuum-Age-Ms")
                http_age_seconds = headers.get("Age")
                if (
                    not isinstance(response_age, int)
                    or isinstance(response_age, bool)
                    or response_age < 0
                    or not isinstance(http_age_seconds, int)
                    or isinstance(http_age_seconds, bool)
                    or http_age_seconds < 0
                    or action.get("authoritative_validation_cut") is not True
                ):
                    violations.add("invalid_age_header")
                expected_violation = action.get("expected_batch_violation")
                if expected_violation is None:
                    if violations:
                        raise AssertionError(
                            f"{vector['id']}: valid repair response has violations "
                            f"{sorted(violations)}"
                        )
                    local_elapsed_ms = action.get("local_elapsed_ms")
                    expected_effective_age_ms = action.get("expected_effective_age_ms")
                    if (
                        not isinstance(local_elapsed_ms, int)
                        or isinstance(local_elapsed_ms, bool)
                        or local_elapsed_ms < 0
                        or not isinstance(expected_effective_age_ms, int)
                        or isinstance(expected_effective_age_ms, bool)
                    ):
                        raise AssertionError(
                            f"{vector['id']}: valid repair response must declare nonnegative "
                            "local_elapsed_ms and expected_effective_age_ms"
                        )
                    if action_index + 1 >= len(actions):
                        raise AssertionError(
                            f"{vector['id']}: valid repair response lacks elapsed advance"
                        )
                    elapsed_action = actions[action_index + 1]
                    if (
                        elapsed_action.get("op") != "advance"
                        or elapsed_action.get("milliseconds") != local_elapsed_ms
                    ):
                        raise AssertionError(
                            f"{vector['id']}: repair local_elapsed_ms must equal the "
                            "immediately following advance"
                        )
                    conservative_http_age_ms = http_age_seconds * 1000 + 999
                    computed_effective_age_ms = (
                        response_age + conservative_http_age_ms + local_elapsed_ms
                    )
                    if expected_effective_age_ms != computed_effective_age_ms:
                        raise AssertionError(
                            f"{vector['id']}: repair effective age "
                            f"{expected_effective_age_ms} != Continuum-Age-Ms "
                            f"{response_age} + HTTP Age {http_age_seconds}s*1000 + "
                            f"999ms quantization + local elapsed {local_elapsed_ms}"
                        )
                elif violations != {expected_violation}:
                    raise AssertionError(
                        f"{vector['id']}: expected isolated {expected_violation}, got "
                        f"{sorted(violations)}"
                    )
            ref = action.get("fixture")
            if ref:
                derived = fixture(ref, documents)
                for replacement in action.get("replace", []):
                    derived = replace_existing(
                        derived,
                        replacement["path"],
                        materialize_limit_expression_for_schema(replacement["value"]),
                    )
                if ref.startswith(("examples.json#", "binding-protected-examples.json#")):
                    validate(derived, f"{vector['id']} derived message", message_check)
                    validate_message_semantics(f"{vector['id']} derived message", derived)
                    stream = derived.get("data", {}).get("stream")
                    if stream:
                        fixture_profile = (
                            "public-data"
                            if stream["classification"] == "public"
                            else "protected-data"
                        )
                        if fixture_profile not in set(vector.get("requires_profiles", [])):
                            raise AssertionError(
                                f"{vector['id']}: {ref} fixes {stream['classification']} "
                                f"classification without {fixture_profile} profile"
                            )
                elif ref.startswith("binding-control-"):
                    validate(derived, f"{vector['id']} derived control", control_check)
                    control_stream_ids = {
                        stream["stream_id"]
                        for stream in derived.get("streams", [])
                        if isinstance(stream, dict) and "stream_id" in stream
                    }
                    required_profiles = set(vector.get("requires_profiles", []))
                    if any(
                        stream_id.startswith("s_example_public_")
                        for stream_id in control_stream_ids
                    ) and "public-data" not in required_profiles:
                        raise AssertionError(
                            f"{vector['id']}: public control fixture lacks public-data profile"
                        )
                    if any(
                        stream_id.startswith("s_example_protected_")
                        for stream_id in control_stream_ids
                    ) and "protected-data" not in required_profiles:
                        raise AssertionError(
                            f"{vector['id']}: protected control fixture lacks protected-data profile"
                        )
                    fixture_key = ref.split("#", 1)[1]
                    if fixture_key.startswith("security_"):
                        if "continuum.command-receipt.v0.2" in vector["capabilities"]:
                            if not fixture_key.endswith("_command"):
                                raise AssertionError(
                                    f"{vector['id']}: command vector uses non-command security control"
                                )
                        elif "protected-data" in vector.get("requires_profiles", []):
                            if not fixture_key.endswith("_protected"):
                                raise AssertionError(
                                    f"{vector['id']}: protected data vector uses public security control"
                                )
                        control_action = derived["action"]
                        control_generation = derived["security_generation_id"]
                        if control_action in {"renew", "reauthorize", "purge"}:
                            if (
                                current_security_generation is not None
                                and control_generation != current_security_generation
                            ):
                                raise AssertionError(
                                    f"{vector['id']}: {fixture_key} generation "
                                    f"{control_generation!r} != current "
                                    f"{current_security_generation!r}"
                                )
                            if (
                                current_subscription is not None
                                and derived["subscription_id"] != current_subscription
                            ):
                                raise AssertionError(
                                    f"{vector['id']}: {fixture_key} subscription "
                                    f"{derived['subscription_id']!r} != current "
                                    f"{current_subscription!r}"
                                )
                        if control_action == "grant":
                            previous = derived.get("previous_security_generation_id")
                            if (
                                previous is not None
                                and current_security_generation is not None
                                and previous != current_security_generation
                            ):
                                raise AssertionError(
                                    f"{vector['id']}: {fixture_key} previous generation "
                                    f"{previous!r} != current {current_security_generation!r}"
                                )
                            request_headers = request_headers_by_target.get(
                                action["target"], {}
                            )
                            requested_generation = request_headers.get(
                                "Continuum-Security-Generation"
                            ) or request_headers.get(
                                "Continuum-Pending-Security-Generation"
                            )
                            requested_previous = request_headers.get(
                                "Continuum-Previous-Security-Generation"
                            )
                            requested_previous_subscription = request_headers.get(
                                "Continuum-Previous-Subscription-Id"
                            )
                            if (
                                requested_generation is not None
                                and requested_generation != control_generation
                            ):
                                raise AssertionError(
                                    f"{vector['id']}: grant response generation does not echo request"
                                )
                            if (
                                requested_previous is not None
                                and requested_previous != previous
                            ):
                                raise AssertionError(
                                    f"{vector['id']}: grant response previous generation does not echo request"
                                )
                            if (
                                requested_previous_subscription is not None
                                and requested_previous_subscription
                                != derived.get("previous_subscription_id")
                            ):
                                raise AssertionError(
                                    f"{vector['id']}: grant response previous subscription does not echo request"
                                )
                            current_security_generation = control_generation
                            current_subscription = derived["subscription_id"]
            if "body" in action:
                validate_action_result_refs(action["body"], f"{vector['id']} action body")
        for assertion in vector["assertions"]:
            value = assertion.get("value")
            if isinstance(value, str) and value.startswith("@"):
                pointer_parts(value[1:])

    print(
        "Continuum 0.2 contracts OK: "
        f"{len(documents['examples.json'])} messages, "
        f"{len(documents['binding-control-examples.json'])} controls, "
        f"{len(core['vectors'])} core vectors, "
        f"{len(binding['vectors'])} binding vectors, "
        f"{len(manifest['units'])} manifest units"
    )


if __name__ == "__main__":
    main()
