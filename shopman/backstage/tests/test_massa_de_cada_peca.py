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
"""

from __future__ import annotations

import pytest
from django.core.management import call_command
from shopman.craftsman.models import Recipe

pytestmark = pytest.mark.django_db

#: SKU do produto → massa que a ficha dele tem de consumir.
MASSA_DA_PECA = {
    "PR": "MASSA-BRIOCHE",
    "BEP": "MASSA-CIABATTA",
    "BAP": "MASSA-CIABATTA",
    # Os três bichinhos são de BUTTER, não de brioche — e esta linha é a
    # cicatriz de eu ter usado o Ursinho como "âncora do que já estava certo"
    # sem perguntar. O dono corrigiu na mesma hora: "Ursinho, porquinho,
    # coelhinho? A massa é butter".
    "ANC": "MASSA-BUTTER",
    "ANU": "MASSA-BUTTER",
    "ANP": "MASSA-BUTTER",
    # Âncoras do que já estava certo: o croissant é de croissant, a ciabatta
    # de ciabatta.
    "CT": "MASSA-CROISSANT",
    "CI": "MASSA-CIABATTA",
}


def test_a_massa_de_cada_peca_e_a_que_o_dono_confirmou(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "Seed-Massas-2026!")
    call_command("seed", verbosity=0)

    divergencias = []
    for sku, massa in sorted(MASSA_DA_PECA.items()):
        recipe = Recipe.objects.filter(output_sku=sku, is_active=True).first()
        if recipe is None:
            divergencias.append(f"{sku}: sem ficha ativa")
            continue
        massas = [item.input_sku for item in recipe.items.all() if item.input_sku.startswith("MASSA-")]
        if massas != [massa]:
            divergencias.append(f"{sku}: ficha usa {massas or 'nenhuma massa'}, deveria usar [{massa}]")

    assert not divergencias, "Ficha com massa errada:\n  " + "\n  ".join(divergencias)
