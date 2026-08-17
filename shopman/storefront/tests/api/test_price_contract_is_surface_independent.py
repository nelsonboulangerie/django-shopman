"""A promessa de preço não pode depender de por onde o pedido entra.

"Nunca cobrar mais do que foi exibido" é invariante do produto. Enquanto
``expected_total_q`` era opcional, ela valia só para quem lembrasse de mandar o
campo: o app Nuxt manda, então pela interface a proteção existia; qualquer outro
chamador da MESMA API — script, app futuro, integração, um bug no front que
esqueça o campo — commitava sem baseline e recebia o preço recalculado calado.

Medido no staging em 2026-08-11, mesma sessão e mesmo instante: a projeção
mostrava R$ 12,80, o commit sem baseline fechou o pedido `WEB-260811-Z99` em
R$ 13,60. Nenhum erro, HTTP 201.

Experiência pode divergir por superfície; contrato de segurança, não. Estes
testes amarram a invariante no SERVIDOR, onde ela não depende da disciplina de
quem chama.
"""

from __future__ import annotations

import json

import pytest
from django.utils import timezone

from shopman.storefront.tests._checkout_baseline import displayed_total_q
from shopman.storefront.tests.api.test_storefront_surface import _seed_surface

pytestmark = pytest.mark.django_db


def _add_item(client, qty: int = 2) -> None:
    resp = client.put(
        "/api/v1/cart/skus/PAO-FRANCES/",
        data={"qty": qty},
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content


def _payload(**over) -> dict:
    payload = {
        "name": "Ana",
        "phone": "+5543999990001",
        "fulfillment_type": "pickup",
        "delivery_date": timezone.localdate().isoformat(),
        "delivery_time_slot": _last_slot(),
        "payment_method": "cash",
    }
    payload.update(over)
    return payload


def _last_slot() -> str:
    from shopman.storefront.services.pickup_slots import get_slots

    return get_slots()[-1]["ref"]


def _post(client, payload: dict):
    return client.post(
        "/api/v1/checkout/",
        data=json.dumps(payload),
        content_type="application/json",
    )


def test_commit_without_a_baseline_is_refused(client):
    """Sem o total exibido, o servidor não fecha pedido — venha de onde vier.

    Este é o teste que teria pego o furo: o chamador "esquece" o campo e espera
    que passe. Passar significa aceitar cobrar um número que ninguém mostrou.
    """
    _seed_surface()
    _add_item(client)

    payload = _payload()
    assert "expected_total_q" not in payload
    resp = _post(client, payload)

    assert resp.status_code == 400, resp.content
    body = resp.json()
    assert body["field"] == "expected_total_q", body
    assert "expected_total_q" in body["errors"], body


def test_commit_with_a_stale_baseline_is_refused(client):
    """Baseline que não bate com o preço atual → recusa explícita, não cobrança."""
    _seed_surface()
    _add_item(client)

    current = displayed_total_q(client)
    resp = _post(client, _payload(expected_total_q=current - 1))

    assert resp.status_code == 400, resp.content
    body = resp.json()
    assert body.get("error_code") == "total_changed", body
    # O servidor diz o número certo, para a pessoa reconfirmar sobre ele.
    assert body["context"]["new_total_q"] == current, body


def test_commit_with_the_displayed_baseline_goes_through(client):
    """O caminho feliz continua feliz: baseline correta fecha o pedido."""
    _seed_surface()
    _add_item(client)

    current = displayed_total_q(client)
    resp = _post(client, _payload(expected_total_q=current))

    assert resp.status_code == 201, resp.content

    from shopman.orderman.models import Order

    order = Order.objects.get(ref=resp.json()["order_ref"])
    # O que foi cobrado é exatamente o que a tela mostrava.
    assert order.total_q == current


def test_a_low_baseline_cannot_dictate_the_price(client):
    """O campo é COMPARADO, nunca usado como preço — ninguém escolhe quanto paga.

    Se um dia alguém trocar a comparação por atribuição, este teste cai: mandar
    1 centavo passaria a fechar o pedido por 1 centavo.
    """
    _seed_surface()
    _add_item(client)

    current = displayed_total_q(client)
    resp = _post(client, _payload(expected_total_q=1))

    assert resp.status_code == 400, resp.content
    assert resp.json()["context"]["new_total_q"] == current
    from shopman.orderman.models import Order

    assert not Order.objects.exists(), "nenhum pedido pode nascer de uma baseline forjada"
