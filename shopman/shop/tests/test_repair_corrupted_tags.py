"""repair_corrupted_tags: desfaz as etiquetas que o Admin gravou como repr de objeto."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from shopman.guestman.models import Customer
from shopman.guestman.models.tag import CustomerTag
from shopman.offerman.models import Product
from taggit.models import Tag

from shopman.shop.management.commands.repair_corrupted_tags import clean_name, is_corrupted

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("[<Tag: pao>", "pao"),
        ("<Tag: hamburger>", "hamburger"),
        ("<Tag: individual>]", "individual"),
        ("[<Tag: pao>]", "pao"),
        ("[<Tag: [<Tag: pao>>", "pao"),
        ("<Tag: <Tag: hamburger>]>]", "hamburger"),
        ("[<CustomerTag: sem glúten>", "sem glúten"),
        ("[<Tag: pão de queijo>]", "pão de queijo"),
        ("[]", ""),
        ("[<Tag: []>]", ""),
    ],
)
def test_clean_name_tira_as_camadas_de_repr(raw, clean):
    assert is_corrupted(raw)
    assert clean_name(raw) == clean


@pytest.mark.parametrize("name", ["pao", "sem glúten", "pão de queijo", "a>b"])
def test_nome_limpo_nao_e_corrompido(name):
    assert not is_corrupted(name)


def _run(*args) -> str:
    out = StringIO()
    call_command("repair_corrupted_tags", *args, stdout=out, stderr=StringIO())
    return out.getvalue()


def _corrupt_product() -> Product:
    product = Product.objects.create(sku="TRABB", name="Pão de hambúrguer")
    product.keywords.add("levain")  # a limpa já existe: reusa, não duplica
    for name in ["[<Tag: pao>", "<Tag: hamburger>", "<Tag: levain>", "<Tag: individual>]"]:
        product.keywords.add(Tag.objects.create(name=name))
    return product


def test_dry_run_por_padrao_nao_grava():
    product = _corrupt_product()
    out = _run()
    assert "Dry-run" in out
    assert "4 etiqueta(s) corrompida(s), 1 objeto(s) afetado(s)" in out
    assert sorted(product.keywords.names()) == sorted(
        ["[<Tag: pao>", "<Tag: hamburger>", "<Tag: levain>", "<Tag: individual>]", "levain"]
    )


def test_apply_religa_ao_nome_limpo_apaga_as_corrompidas_e_e_idempotente():
    product = _corrupt_product()
    _run("--apply")
    assert sorted(product.keywords.names()) == ["hamburger", "individual", "levain", "pao"]
    assert Tag.objects.filter(name="levain").count() == 1
    assert not [t for t in Tag.objects.values_list("name", flat=True) if is_corrupted(t)]

    again = _run("--apply")
    assert "0 etiqueta(s) corrompida(s)" in again
    assert sorted(product.keywords.names()) == ["hamburger", "individual", "levain", "pao"]


def test_apply_solta_lista_vazia_e_apaga_corrompida_sem_uso():
    product = Product.objects.create(sku="SEMPC", name="Sem palavra-chave")
    product.keywords.add(Tag.objects.create(name="[]"))
    Tag.objects.create(name="[<Tag: orfa>")  # sem uso: só some
    _run("--apply")
    assert list(product.keywords.names()) == []
    assert not Tag.objects.filter(name__in=["[]", "[<Tag: orfa>"]).exists()
    assert not Tag.objects.filter(name="orfa").exists()


def test_apply_cobre_as_etiquetas_do_cliente():
    customer = Customer.objects.create(ref="CLI-T", first_name="Ana", phone="+5543999990009")
    customer.tags.add(CustomerTag.objects.create(name="[<CustomerTag: vizinho>"))
    customer.tags.add(CustomerTag.objects.create(name="<CustomerTag: corredores>]"))
    _run("--apply")
    assert sorted(customer.tags.names()) == ["corredores", "vizinho"]
