"""Decisão sobre documento de terceiro, separada de qualquer escrita no CRM."""
from __future__ import annotations

from shopman.shop.services.pos_intent import PosIntentError


class ReceiptIdentityConflict(PosIntentError):
    def __init__(self, *, value="", owner_ref="", customer_ref="", client_request_id="", candidates=(), **kwargs):
        # Subclasse comum: context managers precisam poder atribuir __traceback__.
        super().__init__(**kwargs)
        self.value = value
        self.owner_ref = owner_ref
        self.customer_ref = customer_ref
        self.client_request_id = client_request_id
        self.candidates = candidates

    def as_dict(self) -> dict:
        return {
            **super().as_dict(), "value": self.value, "owner_ref": self.owner_ref,
            "client_request_id": self.client_request_id, "customer_ref": self.customer_ref,
            "candidates": list(self.candidates),
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


def require_receipt_identity_choice(payload: dict) -> None:
    """ACK exato autoriza usar na nota, nunca associar ou modificar cadastro."""
    from shopman.shop.services.pos import _conflict_row, _contact_owner, _identifier_owner

    customer_ref = str(payload.get("customer_ref") or "").strip()
    request_id = str(payload.get("client_request_id") or "").strip()
    choices = receipt_identity_choices(payload.get("receipt_identity_choices"))
    fields = (
        ("tax_id", "fiscal_tax_id", "save_receipt_tax_id", "CPF/CNPJ"),
        ("email", "receipt_email", "save_receipt_contact", "e-mail"),
    )
    for field, payload_key, save_key, label in fields:
        value = normalize_receipt_value(field, payload.get(payload_key))
        if not value:
            continue
        owner = _identifier_owner("cpf", value) if field == "tax_id" else _contact_owner("email", value)
        if owner is None or owner.ref == customer_ref:
            continue
        expected = {
            "field": field, "value": value, "customer_ref": customer_ref,
            "owner_ref": owner.ref, "choice": "receipt_only", "client_request_id": request_id,
        }
        if request_id and not payload.get(save_key) and expected in choices:
            continue
        raise ReceiptIdentityConflict(
            code="receipt_identity_conflict",
            message=f"Este {label} pertence a {owner.name}. Associe o cliente ou use apenas no documento.",
            field=payload_key, focus="receipt", value=value, owner_ref=owner.ref,
            client_request_id=request_id, customer_ref=customer_ref,
            candidates=(_conflict_row(owner, ["cpf" if field == "tax_id" else "email"]),),
        )
