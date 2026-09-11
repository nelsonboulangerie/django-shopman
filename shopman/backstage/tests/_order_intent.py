"""Build test intentions from actual API projections, like an operator client."""
from uuid import uuid4

from django.urls import reverse


def context_payload(client, ref, operation, **inputs):
    response = client.get(reverse("api-backstage-order-detail", args=[ref]))
    assert response.status_code == 200
    action = next(action for action in response.json()["order"]["actions"] if action["ref"] == operation)
    return {**inputs, **action["payload_schema"], "idempotency_key": str(uuid4())}


def advance_payload(client, ref, **inputs):
    return context_payload(client, ref, "advance", **inputs)
