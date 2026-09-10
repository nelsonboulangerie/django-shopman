"""A mesma empresa cadastrada duas vezes vira uma só, sem perder histórico."""

from __future__ import annotations

import pytest
from django.core.management import CommandError, call_command
from shopman.buyman.models import Material, MaterialConversion, Supplier, SupplierMaterialCost


@pytest.fixture
def insumo(db):
    return Material.objects.create(sku="FARINHA-T55", name="Farinha T55", unit="kg")


@pytest.fixture
def par(db):
    """O cadastro do dono (sem CNPJ) e o que a NF criou (com CNPJ e histórico)."""
    do_dono = Supplier.objects.create(ref="france-panificacao", name="France Panificação")
    da_nota = Supplier.objects.create(
        ref="france-panificacao-nf",
        name="FRANCE PANIFICACAO LTDA",
        document="11.222.333/0001-81",
        phone="4333445566",
        metadata={"purchase": {"invoice_product_map": {"FAR-25": "FARINHA-T55"}}},
    )
    return do_dono, da_nota


@pytest.mark.django_db
def test_ensaio_nao_grava_nada(par, insumo):
    do_dono, da_nota = par
    SupplierMaterialCost.objects.create(supplier=da_nota, material=insumo, cost_q=15000)

    call_command("merge_suppliers", da_nota.ref, do_dono.ref)

    assert Supplier.objects.filter(ref=da_nota.ref).exists()
    do_dono.refresh_from_db()
    assert do_dono.document == ""


@pytest.mark.django_db
def test_o_destino_herda_cnpj_custo_e_de_para(par, insumo):
    do_dono, da_nota = par
    SupplierMaterialCost.objects.create(supplier=da_nota, material=insumo, cost_q=15000)
    MaterialConversion.objects.create(
        material=insumo, supplier=da_nota, label="Saco 25kg", to_base_factor=25
    )

    call_command("merge_suppliers", da_nota.ref, do_dono.ref, "--apply")

    assert not Supplier.objects.filter(ref=da_nota.ref).exists()
    do_dono.refresh_from_db()
    assert do_dono.name == "France Panificação"  # o nome de boca fica
    assert do_dono.document == "11.222.333/0001-81"
    assert do_dono.phone == "4333445566"
    assert do_dono.metadata["purchase"]["invoice_product_map"] == {"FAR-25": "FARINHA-T55"}
    assert SupplierMaterialCost.objects.get(material=insumo).supplier == do_dono
    assert MaterialConversion.objects.get(material=insumo).supplier == do_dono


@pytest.mark.django_db
def test_o_custo_do_destino_vence_o_da_origem(par, insumo):
    """Dois custos para o mesmo par violariam a unicidade — o do destino fica."""
    do_dono, da_nota = par
    SupplierMaterialCost.objects.create(supplier=do_dono, material=insumo, cost_q=14000)
    SupplierMaterialCost.objects.create(supplier=da_nota, material=insumo, cost_q=15000)

    call_command("merge_suppliers", da_nota.ref, do_dono.ref, "--apply")

    custos = SupplierMaterialCost.objects.filter(material=insumo)
    assert custos.count() == 1
    assert custos.first().cost_q == 14000


@pytest.mark.django_db
def test_o_insumo_passa_a_apontar_para_o_destino(par, insumo):
    do_dono, da_nota = par
    insumo.metadata = {"supplier": da_nota.ref, "alt_suppliers": [do_dono.ref, "anaconda"]}
    insumo.save(update_fields=["metadata"])

    call_command("merge_suppliers", da_nota.ref, do_dono.ref, "--apply")

    insumo.refresh_from_db()
    assert insumo.metadata["supplier"] == do_dono.ref
    # o destino já estava nos alternativos: trocar não pode duplicá-lo nem
    # deixá-lo listado como alternativa de si mesmo
    assert insumo.metadata["alt_suppliers"] == ["anaconda"]


@pytest.mark.django_db
def test_nunca_sobrescreve_cnpj_do_destino(par, insumo):
    do_dono, da_nota = par
    do_dono.document = "99.888.777/0001-66"
    do_dono.save(update_fields=["document"])

    call_command("merge_suppliers", da_nota.ref, do_dono.ref, "--apply")

    do_dono.refresh_from_db()
    assert do_dono.document == "99.888.777/0001-66"


@pytest.mark.django_db
def test_o_de_para_do_destino_vence_em_conflito(par, insumo):
    do_dono, da_nota = par
    do_dono.metadata = {"purchase": {"invoice_product_map": {"FAR-25": "FARINHA-T65"}}}
    do_dono.save(update_fields=["metadata"])

    call_command("merge_suppliers", da_nota.ref, do_dono.ref, "--apply")

    do_dono.refresh_from_db()
    assert do_dono.metadata["purchase"]["invoice_product_map"]["FAR-25"] == "FARINHA-T65"


@pytest.mark.django_db
def test_recusa_ref_desconhecida_e_fusao_consigo_mesmo(par):
    do_dono, da_nota = par
    with pytest.raises(CommandError):
        call_command("merge_suppliers", "nao-existe", do_dono.ref, "--apply")
    with pytest.raises(CommandError):
        call_command("merge_suppliers", do_dono.ref, do_dono.ref, "--apply")
    assert Supplier.objects.filter(ref=do_dono.ref).exists()
