"""O diálogo "Revisar sugestão do GTIN" na ficha do produto.

- **quem**: staff que só VÊ produto leva 403 — a ação escreve no produto;
- **como**: GET só desenha o diálogo (um interruptor por campo, e "substituir"
  só onde já há valor à mão); o efeito acontece no POST;
- **o quê**: só os campos marcados entram, e a foto de terceiro não vira a
  foto da vitrine.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from shopman.offerman.models import Product

from shopman.shop.models import Shop
from shopman.shop.services import product_enrichment as pe


def _url(pk) -> str:
    return f"/admin/offerman/product/{pk}/gtin-suggestion/"


def _staff(username: str, *codenames: str) -> User:
    user = User.objects.create_user(username, password="pw", is_staff=True)
    for codename in codenames:
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label="offerman", codename=codename)
        )
    return User.objects.get(pk=user.pk)


@pytest.fixture
def geleia(db):
    Shop.objects.create(name="Loja")
    produto = Product.objects.create(
        sku="GELEIA", name="Geleia de framboesa", base_price_q=3900,
        metadata={},
    )
    s = pe.EnrichmentSuggestion(gtin="5014271390420")
    s.add("name", "GELEIA ST DALFOUR 284G", pe.SOURCE_COSMOS)
    s.add("ncm", "20079990", pe.SOURCE_COSMOS)
    s.add("brand", "ST DALFOUR", pe.SOURCE_COSMOS)
    s.consulted = ["cosmos"]
    s.reference_photo = {
        "url": "https://images.openfoodfacts.org/x.jpg", "source": "openfoodfacts",
        "license": pe.OFF_PHOTO_LICENSE, "attribution": "Open Food Facts contributors",
    }
    s.notes = [pe.ALLERGENS_NOT_CURATED]
    produto.metadata = pe.merge_into_metadata(produto.metadata, s)
    produto.save()
    return produto


@pytest.mark.django_db
def test_quem_so_ve_produto_nao_alcanca_a_acao(client, geleia):
    client.force_login(_staff("so-ve", "view_product"))
    assert client.get(_url(geleia.pk)).status_code == 403


@pytest.mark.django_db
def test_GET_desenha_um_interruptor_por_campo_e_nao_aplica_nada(client, geleia):
    client.force_login(_staff("editor", "view_product", "change_product"))

    resposta = client.get(_url(geleia.pk))

    html = resposta.content.decode()
    assert resposta.status_code == 200
    for campo in ("accept_name", "accept_ncm", "accept_brand", "replace_name"):
        assert f'name="{campo}"' in html
    # marca e NCM estão vazios no produto: não há o que substituir
    assert 'name="replace_ncm"' not in html
    assert "não curado" in html
    assert "CC BY-SA 3.0" in html
    geleia.refresh_from_db()
    assert geleia.name == "Geleia de framboesa"
    assert set(pe.pending_fields(geleia)) == {"name", "brand", "ncm"}


@pytest.mark.django_db
def test_POST_aplica_so_o_marcado(client, geleia):
    client.force_login(_staff("editor2", "view_product", "change_product"))

    resposta = client.post(
        _url(geleia.pk), {"_form_submitted": "true", "accept_ncm": "on", "accept_name": "on"}
    )

    assert resposta.status_code in (204, 302)
    geleia.refresh_from_db()
    assert geleia.metadata["fiscal"]["ncm"] == "20079990"
    # nome à mão não foi trocado: "substituir" não veio marcado
    assert geleia.name == "Geleia de framboesa"
    assert "brand" not in (geleia.metadata.get("social") or {})
    assert geleia.image_url == ""
    assert geleia.metadata["enrichment"]["accepted"]["ncm"]["accepted_by"] == "editor2"


@pytest.mark.django_db
def test_POST_com_substituir_troca_o_valor_a_mao(client, geleia):
    client.force_login(_staff("editor3", "view_product", "change_product"))

    client.post(_url(geleia.pk), {"_form_submitted": "true", "replace_name": "on"})

    geleia.refresh_from_db()
    assert geleia.name == "GELEIA ST DALFOUR 284G"


@pytest.mark.django_db
def test_POST_sem_nada_marcado_nao_aplica(client, geleia):
    client.force_login(_staff("editor4", "view_product", "change_product"))

    resposta = client.post(_url(geleia.pk), {"_form_submitted": "true"})

    assert resposta.status_code == 200
    assert "Marque ao menos um campo" in resposta.content.decode()
    geleia.refresh_from_db()
    assert "accepted" not in geleia.metadata["enrichment"]
