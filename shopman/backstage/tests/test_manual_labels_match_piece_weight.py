"""O rótulo manual precisa descrever a peça que está na prateleira.

Um rótulo com ``auto_filled=False`` é escrito à mão e nada o recalcula: mudar o
peso do produto não o alcança. Então ``serving_size_g × servings_per_container``
— o que o rótulo diz que a embalagem contém — pode se afastar do
``unit_weight_g`` sem que ninguém veja, e a tela do cliente segue anunciando uma
peça que não existe.

Foi o que aconteceu duas vezes, e por causas diferentes:

- **peso mudou, rótulo não** — o campagne caiu de 500 g para 300 g no PR #280 e
  o rótulo seguiu dizendo 5 porções de 100 g;
- **chave errada** — o pacote de pães gravava ``servings`` em vez de
  ``servings_per_container``. Ninguém lê ``servings``, então o pacote de 4 pães
  para hot dog herdava "1 porção de 80 g" da unidade e declarava conter um pão.

Este teste é a rede. Tolera 10% (rótulo é aproximação declarada), e carrega uma
lista curta de pendências conhecidas — que são defeito, não exceção.
"""

from __future__ import annotations

import pytest
from django.core.management import call_command
from shopman.offerman.models import Product

pytestmark = pytest.mark.django_db

TOLERANCIA = 0.10

# ⚠️ Defeitos ANTERIORES a esta rede, que precisam do número da casa para
# fechar: em cada um, ou o peso da peça está errado ou a porção do rótulo está.
# Só o dono sabe qual. Cada linha aqui é uma tarefa, não uma licença — e nada
# novo pode entrar sem que alguém explique por quê.
PENDENTES = {
    "BE": "Baguete Gergelim: peça 260 g, rótulo 3 x 100 g",
    "CO": "Cornet: peça 120 g, rótulo 1 x 100 g",
    "MIB": "Mini Baguete: peça 120 g, rótulo 1 x 100 g",
    "DL": "Deli Milho & Bacon: peça 250 g, rótulo 1 x 180 g",
    "HO": "Hot Dog Vienna: peça 250 g, rótulo 1 x 180 g",
}


def test_rotulo_manual_descreve_a_peca(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "Rotulos-2026-Nelson!")
    call_command("seed", verbosity=0)

    divergencias: dict[str, str] = {}
    conferidos = 0

    for product in Product.objects.exclude(nutrition_facts={}).order_by("sku"):
        facts = product.nutrition_facts or {}
        if facts.get("auto_filled") is not False:
            continue  # derivado da ficha; a nutrição já cuida da coerência
        peso = product.unit_weight_g or 0
        porcao = facts.get("serving_size_g") or 0
        porcoes = facts.get("servings_per_container") or 0
        if not peso or not porcao:
            continue

        conferidos += 1
        declarado = porcao * porcoes
        if abs(declarado - peso) / peso > TOLERANCIA:
            divergencias[product.sku] = (
                f"{product.name}: peça {peso} g, rótulo {porcoes} x {porcao} g = {declarado} g"
            )

    assert conferidos > 20, "a varredura não encontrou rótulos manuais — o filtro quebrou?"

    novas = {sku: msg for sku, msg in divergencias.items() if sku not in PENDENTES}
    assert not novas, (
        "Rótulo manual descrevendo uma peça que não existe:\n  "
        + "\n  ".join(f"{sku} — {msg}" for sku, msg in sorted(novas.items()))
    )

    resolvidas = sorted(set(PENDENTES) - set(divergencias))
    assert not resolvidas, (
        "Estas pendências foram resolvidas — apague-as de PENDENTES para a rede "
        f"voltar a guardá-las: {', '.join(resolvidas)}"
    )


def test_o_pacote_declara_as_porcoes_do_pacote(monkeypatch):
    """O pacote de 4 pães declarava conter um pão — chave errada, sem erro nenhum."""
    monkeypatch.setenv("ADMIN_PASSWORD", "Rotulos-2026-Nelson!")
    call_command("seed", verbosity=0)

    for pack_sku, base_sku, quantidade in (("PHO4", "PHO", 4), ("BBB2", "BBB", 2)):
        pack = Product.objects.get(sku=pack_sku)
        base = Product.objects.get(sku=base_sku)

        assert pack.nutrition_facts["servings_per_container"] == quantidade, pack_sku
        assert "servings" not in pack.nutrition_facts, (
            f"{pack_sku} gravou a chave `servings`, que o PDP não lê"
        )
        # A porção segue sendo a da unidade: o pacote muda quantas traz, não o tamanho.
        assert pack.nutrition_facts["serving_size_g"] == base.nutrition_facts["serving_size_g"]
        assert pack.unit_weight_g == (base.unit_weight_g or 0) * quantidade
