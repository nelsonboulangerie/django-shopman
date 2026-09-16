"""Decisão sobre documento de terceiro, separada de qualquer escrita no CRM."""
from __future__ import annotations

from shopman.shop.services.pos_intent import PosIntentError


class ReceiptIdentityConflict(PosIntentError):
    def __init__(self, *, value="", owner_ref="", customer_ref="", client_request_id="", candidates=(), conflicts=(), **kwargs):
        # Subclasse comum: context managers precisam poder atribuir __traceback__.
        super().__init__(**kwargs)
        self.value = value
        self.owner_ref = owner_ref
        self.customer_ref = customer_ref
        self.client_request_id = client_request_id
        self.candidates = candidates
        self.conflicts = conflicts

    def as_dict(self) -> dict:
        return {
            **super().as_dict(), "value": self.value, "owner_ref": self.owner_ref,
            "client_request_id": self.client_request_id, "customer_ref": self.customer_ref,
            "candidates": list(self.candidates), "conflicts": list(self.conflicts),
        }


def normalize_receipt_value(field: str, value) -> str:
    text = str(value or "").strip()
    return "".join(char for char in text if char.isdigit()) if field == "tax_id" else text.lower()


def receipt_identity_choices(raw) -> list[dict]:
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > 2:
        raise PosIntentError("invalid_receipt_identity_choice", "Revise a decisão sobre o documento.", field="receipt_identity_choices")
    result = []
    for choice in raw:
        if (
            not isinstance(choice, dict) or choice.get("field") not in ("tax_id", "email")
            or choice.get("choice") != "receipt_only"
            or set(choice) != {"field", "value", "customer_ref", "owner_ref", "choice", "client_request_id"}
            or any(not isinstance(choice.get(key), str) for key in choice)
            or any(len(choice[key]) > 254 for key in choice)
            or any(item["field"] == choice["field"] for item in result)
        ):
            raise PosIntentError("invalid_receipt_identity_choice", "Revise a decisão sobre o documento.", field="receipt_identity_choices")
        result.append({**choice, "value": normalize_receipt_value(choice["field"], choice["value"])})
    return result


def receipt_payload_for_channels(payload: dict) -> dict:
    """Campo oculto de e-mail não consulta, envia nem grava cadastro."""
    channels = payload.get("receipt_channels") or []
    if isinstance(channels, (list, tuple)) and "email" in channels:
        return payload
    return {**payload, "receipt_email": "", "save_receipt_contact": False}


def require_receipt_identity_choice(payload: dict) -> None:
    """ACK exato autoriza usar na nota, nunca associar ou modificar cadastro."""
    from shopman.shop.services.pos import _conflict_row, _contact_owner, _identifier_owner

    payload = receipt_payload_for_channels(payload)
    customer_ref = str(payload.get("customer_ref") or "").strip()
    request_id = str(payload.get("client_request_id") or "").strip()
    choices = receipt_identity_choices(payload.get("receipt_identity_choices"))
    fields = (
        ("tax_id", "fiscal_tax_id", "save_receipt_tax_id", "CPF/CNPJ"),
        ("email", "receipt_email", "save_receipt_contact", "e-mail"),
    )
    conflicts = []
    first_message = ""
    first_owner_ref = ""
    for field, payload_key, save_key, label in fields:
        value = normalize_receipt_value(field, payload.get(payload_key))
        if not value:
            continue
        owner = _identifier_owner("cpf", value) if field == "tax_id" else _contact_owner("email", value)
        if (owner is not None and owner.ref == customer_ref) or (owner is None and payload.get(save_key)):
            continue
        expected = {
            "field": field, "value": value, "customer_ref": customer_ref,
            "owner_ref": owner.ref if owner else "", "choice": "receipt_only", "client_request_id": request_id,
        }
        if request_id and not payload.get(save_key) and expected in choices:
            continue
        if not conflicts:
            first_message = (f"Este {label} pertence a {owner.name}. Associe o cliente ou use apenas no documento."
                             if owner else f"Deseja salvar este {label} no cadastro ou usar apenas no documento?")
            first_owner_ref = owner.ref if owner else ""
        conflicts.append({
            "field": payload_key, "value": value,
            "candidates": [_conflict_row(owner, ["cpf" if field == "tax_id" else "email"])] if owner else [],
        })
    if conflicts:
        first = conflicts[0]
        raise ReceiptIdentityConflict(
            code="receipt_identity_conflict", message=first_message,
            field=first["field"], focus="receipt", value=first["value"], owner_ref=first_owner_ref,
            client_request_id=request_id, customer_ref=customer_ref,
            candidates=first["candidates"], conflicts=conflicts,
        )


def resolve_receipt_identity(action: dict, *, operator_username: str) -> dict:
    """Apply the displayed receipt decision after rechecking every owner."""
    import hashlib
    import json

    from django.db import transaction

    from shopman.shop.services.pos import _contact_owner, _identifier_owner, _persist_customer_from_payload

    if not isinstance(action, dict):
        raise PosIntentError("invalid_receipt_identity_choice", "Revise a decisão sobre o documento.")
    fields = action.get("fields")
    kind = action.get("action")
    target = action.get("target_ref", "")
    current = action.get("customer_ref", "")
    request_id = action.get("client_request_id", "")
    if (kind not in ("create", "save") or not isinstance(target, str) or not isinstance(current, str)
            or not isinstance(request_id, str) or not request_id.strip()
            or not isinstance(fields, list) or not 1 <= len(fields) <= 2
            or (kind == "create" and (target or current)) or (kind == "save" and not target)
            or not isinstance(action.get("tax_id_overwrite_confirmed", False), bool)):
        raise PosIntentError("invalid_receipt_identity_choice", "Revise a decisão sobre o documento.")
    seen = set()
    for item in fields:
        if (not isinstance(item, dict) or set(item) != {"field", "value", "owner_ref"}
                or item.get("field") not in ("tax_id", "email") or item["field"] in seen
                or not isinstance(item.get("value"), str) or not isinstance(item.get("owner_ref"), str)
                or not normalize_receipt_value(item["field"], item["value"])):
            raise PosIntentError("invalid_receipt_identity_choice", "Revise os dados do documento.")
        seen.add(item["field"])
    fingerprint = hashlib.sha256(json.dumps(
        {"operator": operator_username, "action": action}, sort_keys=True, ensure_ascii=True,
    ).encode()).hexdigest()
    with transaction.atomic():
        replay = False
        if target:
            from shopman.guestman.models import Customer
            selected = Customer.objects.select_for_update().filter(ref=target, is_active=True).first()
            if selected is None:
                raise PosIntentError("receipt_identity_changed", "O cadastro selecionado não está disponível.", focus="receipt")
            replay = (selected.metadata or {}).get("pos", {}).get("last_receipt_action") == fingerprint
        payload = {"customer_ref": target, "client_request_id": request_id, "receipt_channels": ["email"],
                   "_receipt_registration": True,
                   "save_receipt_tax_id_confirmed": action.get("tax_id_overwrite_confirmed", False)}
        stale = False
        for item in fields:
            field = item["field"]
            value = normalize_receipt_value(field, item["value"])
            owner = _identifier_owner("cpf", value) if field == "tax_id" else _contact_owner("email", value)
            owner_ref = owner.ref if owner else ""
            owns_saved_field = not item["owner_ref"] or item["owner_ref"] == target
            replay_field_matches = (
                owner_ref == target
                and normalize_receipt_value(field, selected.document if field == "tax_id" else selected.email) == value
            ) if target and owns_saved_field else owner_ref == item["owner_ref"]
            replay = replay and replay_field_matches
            stale |= owner_ref != item["owner_ref"] or bool(owner_ref and kind == "create")
            payload["fiscal_tax_id" if field == "tax_id" else "receipt_email"] = value
        if replay:
            # Exact completed command and unchanged results: return without writing or re-confirming.
            return {"ref": target, "created": False}
        if target and action.get("tax_id_overwrite_confirmed") and (
                    not isinstance(action.get("tax_id_before"), str)
                    or normalize_receipt_value("tax_id", action["tax_id_before"]) != normalize_receipt_value("tax_id", selected.document)):
            raise PosIntentError("receipt_identity_changed", "O CPF do cadastro mudou. Revise a alteração novamente.", focus="receipt")
        if stale:
            # No write has happened. Show current ownership again, including after a lost create response.
            require_receipt_identity_choice({**payload, "customer_ref": current})
            raise PosIntentError("receipt_identity_changed", "O cadastro mudou. Revise os dados do documento.", focus="receipt")
        for item in fields:
            if item["owner_ref"] and item["owner_ref"] != target:
                # Validate the whole displayed snapshot, but never copy a third party's field.
                payload.pop("fiscal_tax_id" if item["field"] == "tax_id" else "receipt_email", None)
                continue
            payload["save_receipt_tax_id" if item["field"] == "tax_id" else "save_receipt_contact"] = True
        result = _persist_customer_from_payload(payload, operator_username=operator_username)
        if target:
            selected.refresh_from_db()
            metadata = dict(selected.metadata or {})
            metadata["pos"] = {**metadata.get("pos", {}), "last_receipt_action": fingerprint}
            selected.metadata = metadata
            selected.save(update_fields=["metadata"])
        return result
