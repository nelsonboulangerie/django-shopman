"""A casa afirma o que a FÓRMULA prova, e nunca o que o ambiente não garante.

⚠️ Este arquivo já esteve errado, e o erro custou informação verdadeira no ar.
Em 06/09 ele guardava "a casa não afirma ausência" como regra única, tratando
`sem glúten` e `sem lactose` como a mesma coisa. **Não são**, e a distinção é o
que estes testes existem para fixar:

- **composição** — a ficha responde, e a casa pode afirmar. Uma baguete de
  farinha, água, sal e levain não contém lactose; dizer isso é verdade, é útil
  ao cliente, e a RDC 135/2017 dá o limiar objetivo (< 100 mg/100 g).
- **contaminação cruzada** — a ficha NÃO responde. `sem glúten` numa padaria sem
  linha segregada é afirmação sobre o ambiente, e é a única da família em que um
  celíaco pode se machucar.

O que a casa faz no lugar: declara o oposto em voz alta, e em primeiro lugar —
*"todos os nossos produtos contêm ou podem conter glúten"*.

E não há conflito entre `sem lactose` e o aviso de traços de leite: intolerância
à lactose é DOSE-dependente e traço não a alcança; alergia à proteína do leite é
outra coisa, e dela cuida o aviso. Separar as duas é prática da indústria.

Os números que vêm da lei moram em `shop/legal_parameters.py`, com data de
conferência e catraca — legislação muda, e parâmetro que ninguém revisita faz o
sistema ensinar o gestor a errar.
"""

from __future__ import annotations

import pytest

from shopman.shop.attribute_defaults import ALERGENOS_CANONICOS, DIETA_CANONICA


def test_sem_gluten_nunca_entra_no_vocabulario():
    """A única que a casa não pode honrar — e a única em que alguém se machuca."""
    assert "sem glúten" not in DIETA_CANONICA, (
        "A Nelson não tem linha segregada e não pretende ter. 'sem glúten' seria "
        "afirmação sobre o AMBIENTE, não sobre a fórmula."
    )


def test_o_que_a_ficha_prova_a_casa_afirma():
    """`sem lactose` e `vegetariano` são fato de composição, e voltaram."""
    for permitida in ("100% vegetal", "vegetariano", "sem lactose"):
        assert permitida in DIETA_CANONICA


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


def test_a_derivacao_afirma_lactose_e_nunca_gluten():
    """A baguete: farinha, água, sal e levain. Contém glúten, não contém lactose."""
    from shopman.craftsman.dietary import DIET_VEGAN, IngredientDietary

    from shopman.shop.services.dietary_from_recipe import _derive_dietary_info

    baguete = [IngredientDietary(diet=DIET_VEGAN, allergens=["glúten"])]
    info = _derive_dietary_info(baguete, ["glúten"])

    assert "sem lactose" in info, "a fórmula prova a ausência de leite; a casa afirma"
    assert "100% vegetal" in info
    assert "sem glúten" not in info, "esta a casa NUNCA afirma — não há segregação"


def test_com_leite_na_ficha_nao_ha_afirmacao_de_lactose():
    from shopman.craftsman.dietary import DIET_VEGETARIAN, IngredientDietary

    from shopman.shop.services.dietary_from_recipe import _derive_dietary_info

    brioche = [IngredientDietary(diet=DIET_VEGETARIAN, allergens=["glúten", "leite"])]
    info = _derive_dietary_info(brioche, ["glúten", "leite"])

    assert "sem lactose" not in info
    assert "vegetariano" in info, "sem abate, e é o único termo que sabe dizer isso"


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
