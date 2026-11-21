"""De que MASSA cada peça é feita — conferido com o dono, e travado aqui.

A ficha não é rótulo: é o que a produção consome e o que o custo calcula. Uma
massa errada na ficha é um erro silencioso — o pão sai igual na vitrine e a
conta sai errada no fim do mês.

Três estavam erradas no seed, e as três vieram de inferência de agente, não de
quem faz o pão (dono, 22/09):

- **Pain aux Raisins** era croissant; é BRIOCHE. *"nosso pain au raisin é de
  brioche, sim. folhado foi confusão de agente de IA"*.
- **Baguete Gergelim Pequena** e **Baguete Lanche** eram tradição; são
  CIABATTA. A massa da ciabatta dá casca mais fina, e é por isso que a
  baguetinha sem gergelim vai no Jambon-Beurre.
- **Coelhinho, Ursinho e Porquinho** eram brioche; são BUTTER.

⚠️ Este teste roda o seed inteiro de propósito. Ler a tabela do seed em vez do
banco semeado provaria que a tabela concorda consigo mesma.

⚠️ A chave é o **ref da ficha**, não o SKU do produto. A primeira versão deste
teste era indexada por SKU e ficou vermelha na CI algumas horas depois: o
WP de rename passou no `main` e ANC/ANU/ANP/BAP/BEP/CT viraram COE/URS/PORQ/
BGL/BGGP/CRO. O SKU é nome comercial e está em obra; o ref da ficha é a
identidade dela e não mudou. O que este teste afirma — de que massa cada peça
é — não deve cair porque o código do produto foi trocado.
"""

from __future__ import annotations

import pytest
from django.core.management import call_command
from shopman.craftsman.models import Recipe

pytestmark = pytest.mark.django_db

#: ref da ficha → massa que ela tem de consumir.
MASSA_DA_PECA = {
    "pain-aux-raisins": "MASSA-BRIOCHE",
    "baguete-gergelim-pequena": "MASSA-CIABATTA",
    "baguete-lanche": "MASSA-CIABATTA",
    # Os três bichinhos são de BUTTER, não de brioche — e esta linha é a
    # cicatriz de eu ter usado o Ursinho como "âncora do que já estava certo"
    # sem perguntar. O dono corrigiu na mesma hora: "Ursinho, porquinho,
    # coelhinho? A massa é butter".
    "coelhinho": "MASSA-BUTTER",
    "ursinho": "MASSA-BUTTER",
    "porquinho": "MASSA-BUTTER",
    # Os três pãezinhos de tradição da aba TRAD da RECEITAS 2.4 (#2925). O Pão
    # de Hambúrguer é tradição pela resposta 4 do dono (02/10), não butter.
    "fendu": "MASSA-TRADICAO",
    "tabatiere": "MASSA-TRADICAO",
    "pao-hamburguer": "MASSA-TRADICAO",
    # Os outros itens da casa que ganharam ficha pela palavra do dono (21/11,
    # #2925). O melonpan leva duas massas (butter e a da cobertura) e é
    # conferido à parte, abaixo.
    "baguete-gergelim": "MASSA-CIABATTA",
    "campagne-passas-castanhas": "MASSA-CAMPAGNE",
    "brioche-burger-bun": "MASSA-BRIOCHE",
    "pao-hot-dog": "MASSA-BUTTER",
    "cornet": "MASSA-BUTTER",
    # Âncoras do que já estava certo: o croissant é de croissant, a ciabatta
    # de ciabatta.
    "croissant": "MASSA-CROISSANT",
    "ciabatta": "MASSA-CIABATTA",
}


def test_a_massa_de_cada_peca_e_a_que_o_dono_confirmou(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "Seed-Massas-2026!")
    call_command("seed", verbosity=0)

    divergencias = []
    for ref, massa in sorted(MASSA_DA_PECA.items()):
        recipe = Recipe.objects.filter(ref=ref, is_active=True).first()
        if recipe is None:
            divergencias.append(f"{ref}: sem ficha ativa")
            continue
        massas = [item.input_sku for item in recipe.items.all() if item.input_sku.startswith("MASSA-")]
        if massas != [massa]:
            divergencias.append(
                f"{ref} ({recipe.output_sku}): ficha usa {massas or 'nenhuma massa'}, "
                f"deveria usar [{massa}]"
            )

    assert not divergencias, "Ficha com massa errada:\n  " + "\n  ".join(divergencias)

    melonpan = Recipe.objects.get(ref="melonpan", is_active=True)
    assert sorted(i.input_sku for i in melonpan.items.all()) == ["MASSA-BUTTER", "MASSA-COBERTURA-MELONPAN"]
    # O recheio do cornet é UM dos dois cremes: o de chocolate é o alternativo.
    cornet = {i.input_sku: i.is_optional for i in Recipe.objects.get(ref="cornet").items.all()}
    assert cornet == {"MASSA-BUTTER": False, "CREME-BAUNILHA": False, "CREME-CHOCOLATE": True}

    # Feitos aqui em lote: numa data ainda sem lote planejado, a encomenda deles
    # vira pedido à Produção, e não "Sem saldo" (#2925, regra do WP-E3).
    from shopman.offerman.models import Product

    from shopman.shop.adapters.production import get_batch_produced_skus, get_made_to_order_skus

    em_lote = {"FENDU", "TABAT", "TRABB", "BGG", "CPX", "BRBB", "HOL", "CO", "MELON"}
    assert get_batch_produced_skus(sorted(em_lote)) == em_lote
    # O Melon Iced Sando é montado na hora, como o Jambon-Beurre.
    assert get_made_to_order_skus(["MELSA", "JB"]) == {"MELSA", "JB"}
    # A Mini Baguete saiu de venda; a Baguete Lanche, de 170 g, toma o lugar dela.
    assert Product.objects.get(sku="MIB").is_sellable is False
    bgl = Recipe.objects.get(ref="baguete-lanche").items.get(input_sku="MASSA-CIABATTA")
    assert bgl.quantity == 170

    # O que o dono mandou conferir aparece NA LINHA da ficha, não só no código.
    notas = {
        (i.recipe.ref, i.input_sku)
        for i in Recipe.objects.get(ref="baguete-gergelim").items.all()
        if "a conferir" in (i.meta or {}).get("note", "")
    }
    assert notas == {("baguete-gergelim", "GERGELIM")}
