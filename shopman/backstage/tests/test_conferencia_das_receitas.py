"""Procedência e conferência das receitas (WP-RECEITAS-DA-CASA F1/F2).

As seis fichas com a massa errada (22/09/2026) passaram porque uma receita
inventada por agente e uma declarada pelo padeiro tinham a mesma cara. Aqui se
trava que a ficha diz de onde veio, que só alguém da casa assina a conferência,
que o carimbo cai quando a fórmula muda, e que a fila do padeiro vem na ordem
do que mais sai, com a massa da peça em destaque.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from shopman.craftsman.models import Recipe, RecipeItem, RecipeVersion
from shopman.craftsman.services import recipe_book as craftsman

from shopman.backstage.projections.recipe_book import build_recipe_book, build_recipe_review_queue
from shopman.backstage.services import recipe_review
from shopman.backstage.services.exceptions import RecipeBookServiceError
from shopman.backstage.tests.production_grants import grant_production_operator

pytestmark = pytest.mark.django_db

FORMULA = {
    "anchor": {"kind": "flour"},
    "items": [
        {"sku": "FARINHA-T55", "name": "Farinha", "role": "flour", "quantity": 1000, "unit": "g"},
        {"sku": "AGUA-FILTRADA", "name": "Água", "role": "liquid", "quantity": 650, "unit": "g"},
    ],
    "parts": [],
}


def _publicar(ref, name, sku, *, source=None, formula=None, yield_quantity="1650", yield_unit="g"):
    entry = craftsman.create_entry(ref=ref, name=name, kind="bread", output_sku=sku)
    version = craftsman.create_version(
        entry, formula=formula or FORMULA, yield_quantity=yield_quantity, yield_unit=yield_unit, source=source,
    )
    craftsman.publish_version(version)
    entry.refresh_from_db()
    return entry, RecipeVersion.objects.get(pk=version.pk)


# ── Procedência ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("source", "kind"),
    [
        ({"kind": "manual"}, "house"),
        ({"kind": "import", "text": "planilha"}, "house"),
        ({"kind": "photo"}, "notebook"),
        ({"kind": "note"}, "notebook"),
        ({"kind": "ficha", "recipe_ref": "x"}, "agent"),
        ({}, "agent"),
    ],
)
def test_a_procedencia_sai_da_origem_da_versao(source, kind):
    _, version = _publicar("massa-p", "Massa P", "MASSA-P", source=source or None)
    if not source:
        version.source = {}
        version.save(update_fields=["source"])
    assert recipe_review.provenance_of(version).kind == kind


def test_cadastro_inicial_nao_se_passa_por_receita_da_casa():
    _, version = _publicar("massa-agente", "Massa Agente", "MASSA-AG", source={"kind": "ficha", "recipe_ref": "x"})
    provenance = recipe_review.provenance_of(version)
    assert provenance.label == "Do cadastro inicial"
    assert "agente" in provenance.detail


# ── Conferência ──────────────────────────────────────────────────────────────


def test_conferir_assina_com_autor_e_data():
    _, version = _publicar("massa-c", "Massa C", "MASSA-C")
    assert recipe_review.review_of(version).status == "pending"

    recipe_review.confirm(version, actor="maysa", actor_name="Maysa")
    version.refresh_from_db()
    review = recipe_review.review_of(version)
    assert review.status == "confirmed"
    assert review.by == "maysa"
    assert review.by_name == "Maysa"
    assert review.at
    assert version.meta["review"]["formula_digest"] == recipe_review.formula_digest(version)


def test_conferencia_anonima_e_recusada():
    _, version = _publicar("massa-a", "Massa A", "MASSA-A")
    with pytest.raises(RecipeBookServiceError) as exc:
        recipe_review.confirm(version, actor="  ")
    assert exc.value.code == "REVIEW_WITHOUT_ACTOR"


def test_so_a_versao_em_uso_se_confere():
    entry, first = _publicar("massa-v", "Massa V", "MASSA-V")
    second = craftsman.create_version(entry, formula=FORMULA, yield_quantity="1650", yield_unit="g")
    craftsman.publish_version(second)
    first.refresh_from_db()
    with pytest.raises(RecipeBookServiceError) as exc:
        recipe_review.confirm(first, actor="maysa")
    assert exc.value.code == "REVIEW_NOT_CURRENT"


def test_formula_mudada_depois_derruba_o_carimbo():
    _, version = _publicar("massa-m", "Massa M", "MASSA-M")
    recipe_review.confirm(version, actor="maysa")
    version.refresh_from_db()
    version.formula = {**version.formula, "items": [{**version.formula["items"][0]}, {**version.formula["items"][1], "quantity": 700}]}
    version.save(update_fields=["formula"])
    assert recipe_review.review_of(version).status == "changed"
    assert recipe_review.review_of(version).label == "Mudou depois da conferência"


# ── Fila do padeiro ──────────────────────────────────────────────────────────


def _peca(ref, name, sku, dough_sku):
    formula = {
        "anchor": {"kind": "total"},
        "items": [{"sku": dough_sku, "name": "massa", "role": "other", "quantity": 80, "unit": "g"}],
        "parts": [],
    }
    return _publicar(ref, name, sku, formula=formula, yield_quantity="1", yield_unit="un")


def test_fila_vem_do_que_mais_sai_e_destaca_a_massa():
    _publicar("massa-brioche", "Massa Brioche", "MASSA-BRIOCHE")
    _publicar("massa-pouco", "Massa Pouco", "MASSA-POUCO")
    _peca("pain-raisins", "Pain aux Raisins", "PAIN-RAISINS", "MASSA-BRIOCHE")
    _peca("coelhinho", "Coelhinho", "COELHINHO", "MASSA-BRIOCHE")
    _, conferida = _publicar("massa-ok", "Massa Ok", "MASSA-OK")
    recipe_review.confirm(conferida, actor="maysa")

    sold = {"PAIN-RAISINS": Decimal("300"), "COELHINHO": Decimal("50"), "MASSA-POUCO": Decimal("5")}
    queue = build_recipe_review_queue(sold=sold)

    refs = [item.ref for item in queue.items]
    # A massa soma o que vendeu cada peça feita dela; a conferida sai da fila.
    assert refs == ["massa-brioche", "pain-raisins", "coelhinho", "massa-pouco"]
    assert "massa-ok" not in refs
    brioche = queue.items[0]
    assert brioche.sold_display == "350 vendidos em 12 meses por 2 produtos"
    raisins = queue.items[1]
    assert (raisins.dough_sku, raisins.dough_name) == ("MASSA-BRIOCHE", "Massa Brioche")
    assert raisins.sold_display == "300 vendidos em 12 meses"
    assert brioche.dough_name == ""  # a massa não tem "massa" a destacar
    assert queue.total == 4
    assert queue.confirmed_total == 1
    assert queue.recipe_total == 5


def test_lista_filtra_nao_conferidas_e_o_cartao_diz_o_estado():
    _, conferida = _publicar("massa-x", "Massa X", "MASSA-X")
    recipe_review.confirm(conferida, actor="maysa")
    _publicar("massa-y", "Massa Y", "MASSA-Y", source={"kind": "ficha", "recipe_ref": "y"})

    book = build_recipe_book(only_unreviewed=True)
    assert [card.ref for card in book.entries] == ["massa-y"]
    card = book.entries[0]
    assert card.review_status == "pending"
    assert card.review_label == "Não conferida"
    assert card.provenance_label == "Do cadastro inicial"


# ── HTTP ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def editor(db):
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Loja Conferência")
    user = User.objects.create_user("padeiro", password="pw", is_staff=True, first_name="Maysa")
    user = grant_production_operator(user)
    user.user_permissions.add(
        Permission.objects.get(content_type=ContentType.objects.get_for_model(Shop), codename="manage_production")
    )
    return User.objects.get(pk=user.pk)


@pytest.fixture
def viewer(db):
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Loja Conferência")
    user = User.objects.create_user("balcao", password="pw", is_staff=True)
    return grant_production_operator(user)


def test_http_fila_e_conferencia(client, editor):
    _publicar("massa-h", "Massa H", "MASSA-H")
    client.force_login(editor)

    queue = client.get("/api/v1/backstage/recipes/review/")
    assert queue.status_code == 200, queue.content
    assert [item["ref"] for item in queue.json()["queue"]["items"]] == ["massa-h"]

    done = client.post("/api/v1/backstage/recipes/massa-h/versions/1/review/")
    assert done.status_code == 200, done.content
    version = done.json()["entry"]["versions"][0]
    assert version["review_status"] == "confirmed"
    assert version["review_by_name"] == "Maysa"
    assert client.get("/api/v1/backstage/recipes/review/").json()["queue"]["items"] == []


def test_http_conferir_pede_a_escrita_do_inventario(client, viewer):
    _publicar("massa-v2", "Massa V2", "MASSA-V2")
    client.force_login(viewer)
    assert client.get("/api/v1/backstage/recipes/review/").status_code == 200
    assert client.post("/api/v1/backstage/recipes/massa-v2/versions/1/review/").status_code == 403


def test_ficha_ativa_de_peca_conta_na_massa_mesmo_sem_inventario():
    """A ficha de execução que consome a massa conta, publicada pelo inventário ou não."""
    _publicar("massa-z", "Massa Z", "MASSA-Z")
    peca = Recipe.objects.create(ref="baguete-z", name="Baguete Z", output_sku="BAGUETE-Z", batch_size=Decimal("1"))
    RecipeItem.objects.create(recipe=peca, input_sku="MASSA-Z", quantity=Decimal("0.28"), unit="kg")
    queue = build_recipe_review_queue(sold={"BAGUETE-Z": Decimal("12")})
    assert queue.items[0].sold_display == "12 vendidos em 12 meses por 1 produto"
