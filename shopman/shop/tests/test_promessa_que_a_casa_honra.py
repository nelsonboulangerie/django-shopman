"""A casa só afirma o que consegue honrar.

Medido no cardápio VIVO em 06/09/2026: **11 produtos** carregavam afirmação de
ausência derivada da ficha — um Espresso "sem glúten", nove pães "sem lactose".
Verdade sobre a receita, mentira sobre o produto: farinha no ar, forno e bancada
compartilhados.

Afirmação de ausência é a única da família em que um celíaco pode agir, e é
justamente a que uma padaria não consegue cumprir.

O que estes testes guardam:

- a derivação **não volta a inventar** "sem glúten", "sem lactose" nem
  "vegetariano" — nem quando a ficha não tem o insumo;
- ``100% vegetal`` **fica**: é afirmação sobre o que o produto É, não sobre o
  que falta nele, e essa a ficha honra;
- o vocabulário de alérgeno cobre os cereais **nomeados** e a pimenta-do-reino,
  porque lista que não cabe a realidade vira alérgeno descartado em silêncio;
- alérgeno vindo da FICHA amplia o vocabulário em vez de derrubar a derivação —
  o defeito que deixava o produto SEM alérgeno nenhum.

⚠️ A limpeza do que já estava gravado é feita pela migração `0035`, e **dado de
migração não sobrevive a teste transacional** — por isso o que se testa aqui é a
REGRA que impede o valor de voltar, não a linha do banco.
"""

from __future__ import annotations

import pytest

from shopman.shop.attribute_defaults import ALERGENOS_CANONICOS, DIETA_CANONICA


def test_a_casa_nao_afirma_mais_ausencia():
    """"sem glúten" e "sem lactose" saíram do vocabulário — os dois lados."""
    assert DIETA_CANONICA == ["100% vegetal"], (
        "Afirmação de ausência não pode voltar ao vocabulário: uma padaria "
        "não honra 'sem glúten' com farinha no ar."
    )
    for proibida in ("sem glúten", "sem lactose", "vegetariano"):
        assert proibida not in DIETA_CANONICA


def test_a_afirmacao_positiva_fica():
    """`100% vegetal` diz o que o produto É, e disso a ficha dá conta."""
    assert "100% vegetal" in DIETA_CANONICA


@pytest.mark.parametrize("cereal", ["trigo", "centeio", "cevada", "aveia"])
def test_os_cereais_da_norma_sao_nomeados(cereal):
    """"glúten" sozinho não distingue centeio de trigo, e quem evita um não evita o outro."""
    assert cereal in ALERGENOS_CANONICOS


def test_pinoli_estava_faltando_e_a_norma_o_nomeia():
    assert "pinoli" in ALERGENOS_CANONICOS


def test_a_pimenta_entra_mesmo_sem_norma():
    """Decisão do dono (06/09/2026): a casa usa e já viu reação.

    O rótulo protege quem come; não existe para cumprir a lista mínima. E o
    termo é o que a casa já escreve no aviso de cozinha compartilhada.
    """
    assert "pimenta-do-reino" in ALERGENOS_CANONICOS


def test_a_derivacao_nao_reintroduz_ausencia():
    """A regra, não o dado: mesmo sem leite na ficha, nada de "sem lactose"."""
    from shopman.craftsman.dietary import DIET_VEGAN, IngredientDietary

    from shopman.shop.services.dietary_from_recipe import _derive_dietary_info

    só_vegetal = [IngredientDietary(diet=DIET_VEGAN, allergens=["glúten"])]
    info = _derive_dietary_info(só_vegetal, ["glúten"])

    assert "sem lactose" not in info
    assert "sem glúten" not in info
    assert "vegetariano" not in info
    assert info == ["100% vegetal"]


@pytest.mark.django_db
def test_alergeno_da_ficha_amplia_em_vez_de_derrubar():
    """O defeito que deixava o produto SEM alérgeno nenhum.

    Com vocabulário fechado, um insumo que declarasse alérgeno de fora fazia a
    escrita levantar — e a derivação inteira ia embora no `except` do signal,
    deixando o rótulo anterior de pé, calada.
    """
    from shopman.offerman.models import Product

    from shopman.shop.models.attributes import AttributeDefinition
    from shopman.shop.services import attributes

    d = AttributeDefinition.objects.get(ref="alergenos")
    assert d.extends_from_source, "o vocabulário de alérgeno precisa poder crescer pela ficha"

    produto = Product.objects.create(sku="TESTE-AMPLIA", name="Teste")
    attributes.set(produto, "alergenos", ["glúten", "cardamomo"], source="recipe")

    assert attributes.get(produto, "alergenos") == ["glúten", "cardamomo"]
    d.refresh_from_db()
    assert "cardamomo" in d.option_values(), "a ficha tinha de ter ampliado o vocabulário"


@pytest.mark.django_db
def test_digitado_a_mao_continua_recusado():
    """Ali o erro provável é de digitação, não um alérgeno novo do mundo."""
    from shopman.offerman.models import Product

    from shopman.shop.services import attributes
    from shopman.shop.services.attributes import AttributeError_

    produto = Product.objects.create(sku="TESTE-RECUSA", name="Teste")
    with pytest.raises(AttributeError_):
        attributes.set(produto, "alergenos", ["glútem"], source="manual")
