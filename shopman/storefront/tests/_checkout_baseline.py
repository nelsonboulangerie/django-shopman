"""Baseline de preço do checkout do cliente, para os testes falarem como o app.

``expected_total_q`` é OBRIGATÓRIO em ``POST /api/v1/checkout/``: é o total que a
pessoa VIU, e o servidor recusa o commit se a reprecificação final divergir.

O número certo NÃO é "a soma dos itens" — é o que a tela mostra depois de o app
gravar as escolhas na sessão. A loja faz isso em dois passos antes de confirmar:

- ``PATCH /api/v1/checkout/draft/`` — recebimento + endereço, para a taxa de
  entrega e a cobertura de zona entrarem no total;
- ``PATCH /api/v1/checkout/loyalty/`` — resgate de pontos, quando ligado.

Ambos devolvem o carrinho já reprecificado. Um teste que pula esses passos e
soma os itens na mão inventa uma baseline que a loja nunca exibiria, e aí testa
um caminho que não existe.
"""

from __future__ import annotations

import json


def _cart_from(resp) -> dict:
    body = resp.json()
    return body.get("cart") or body["checkout"]["cart"]


def displayed_total_q(client, payload: dict | None = None) -> int:
    """O total que a tela mostraria para ``payload`` — a baseline do commit.

    Reproduz a sequência do app: grava as escolhas na sessão e lê o total
    resultante. Sem ``payload``, só lê a projeção como está.
    """
    payload = payload or {}

    if payload.get("use_loyalty"):
        resp = client.patch(
            "/api/v1/checkout/loyalty/",
            data=json.dumps({"enabled": True}),
            content_type="application/json",
        )
        if resp.status_code == 200:
            _cart_from(resp)

    draft = {
        "fulfillment_type": payload.get("fulfillment_type") or "pickup",
        "delivery_address_structured": payload.get("delivery_address_structured") or {},
    }
    resp = client.patch(
        "/api/v1/checkout/draft/",
        data=json.dumps(draft),
        content_type="application/json",
    )
    if resp.status_code == 200:
        return _cart_from(resp)["grand_total_q"]

    date = payload.get("delivery_date")
    qs = f"?delivery_date={date}" if date else ""
    return _cart_from(client.get(f"/api/v1/storefront/checkout/{qs}"))["grand_total_q"]


def with_baseline(client, payload: dict) -> dict:
    """Completa o payload com a baseline lida da projeção, se ele não trouxer uma.

    Passe ``expected_total_q`` explicitamente para simular divergência de preço —
    é assim que se testa a recusa ``total_changed``.
    """
    if "expected_total_q" in payload:
        return payload
    return {**payload, "expected_total_q": displayed_total_q(client, payload)}
