"""O `next_url` do checkout precisa ser uma rota que o app do cliente tem.

Regressão do smoke de alpha (2026-08-11, staging): o checkout devolvia
``next_url = "/tracking/{ref}"``, o `finalizar.vue` faz
``navigateTo(response.next_url)`` — e o fallback ``/pedido/{ref}`` ao lado
**nunca dispara**, porque o campo vem sempre preenchido. Observado ao vivo: o
pedido `WEB-260811-N78` foi criado (R$ 26,00) e o cliente terminou na tela
"Não encontramos esta página".

`/tracking/{ref}` é o ENDPOINT (`/api/v1/tracking/{ref}/`). A rota de tela é
`pages/pedido/[ref]/index.vue` → `/pedido/{ref}`. Confundir as duas custa o
pedido inteiro do ponto de vista do cliente.

O teste amarra o contrato nos DOIS lados: o prefixo que a API promete e a
página que existe no repo do Nuxt.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.utils import timezone

from shopman.storefront.tests._checkout_baseline import with_baseline
from shopman.storefront.tests.api.test_storefront_surface import _seed_surface

pytestmark = pytest.mark.django_db

# shopman/storefront/tests/api/ → raiz do repo
_REPO_ROOT = Path(__file__).resolve().parents[4]
_TRACKING_PAGE = (
    _REPO_ROOT / "surfaces" / "storefront-nuxt" / "app" / "pages" / "pedido" / "[ref]" / "index.vue"
)


def _checkout(client):
    return client.post(
        "/api/v1/checkout/",
        data=with_baseline(client, {
            "name": "Ana",
            "phone": "+5543999990001",
            "fulfillment_type": "delivery",
            "delivery_address": "Rua das Flores, 1",
            "delivery_address_structured": {
                "formatted_address": "Rua das Flores, 1 - Centro, Londrina - PR",
                "route": "Rua das Flores",
                "street_number": "1",
                "city": "Londrina",
                "state_code": "PR",
                "postal_code": "86050-270",
                "neighborhood": "Centro",
            },
            "delivery_date": timezone.localdate().isoformat(),
        }),
        content_type="application/json",
    )


def test_next_url_points_at_the_customer_tracking_route(client):
    from shopman.shop.models import DeliveryZone, Shop

    _seed_surface()
    DeliveryZone.objects.create(
        shop=Shop.objects.first(),
        name="Centro",
        zone_type=DeliveryZone.ZONE_TYPE_CEP_PREFIX,
        match_value="860",
        fee_q=600,
    )
    resp = client.put(
        "/api/v1/cart/skus/PAO-FRANCES/",
        data={"qty": 1},
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content

    created = _checkout(client)
    assert created.status_code == 201, created.content
    body = created.json()

    next_url = body["next_url"]
    assert next_url == f"/pedido/{body['order_ref']}", next_url
    # O endpoint da API nunca pode vazar como rota de navegação.
    assert not next_url.startswith("/tracking/"), next_url


def test_the_tracking_page_actually_exists_in_the_nuxt_app():
    """Se a página for renomeada, este teste cai junto com o contrato acima."""
    assert _TRACKING_PAGE.is_file(), (
        f"A rota do acompanhamento sumiu de {_TRACKING_PAGE.relative_to(_REPO_ROOT)}. "
        "Se ela mudou de lugar, o `next_url` do checkout precisa mudar junto."
    )
