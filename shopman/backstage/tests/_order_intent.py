"""Build a test intention from the actual API projection, like an operator client."""
from uuid import uuid4

from django.urls import reverse


def advance_payload(client, ref, **inputs):
    response = client.get(reverse("api-backstage-order-detail", args=[ref]))
    assert response.status_code == 200
    action = next(action for action in response.json()["order"]["actions"] if action["ref"] == "advance")
    return {**inputs, **action["payload_schema"], "idempotency_key": str(uuid4())}
