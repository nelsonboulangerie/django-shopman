"""O rótulo manual precisa descrever a peça que está na prateleira.

Um rótulo com ``auto_filled=False`` é escrito à mão e nada o recalcula: mudar o
peso do produto não o alcança. Então ``servings_per_container`` — quantas porções
o rótulo diz que a embalagem traz — pode ficar descrevendo a peça antiga sem que
nenhum erro apareça, e a tela do cliente segue anunciando um produto que não
existe.

Foi o que aconteceu, por duas causas diferentes:

- **peso mudou, rótulo não** — o campagne caiu de 500 g para 300 g no PR #280 e
  o rótulo seguiu dizendo 5 porções de 100 g;
- **chave errada** — o pacote de pães gravava ``servings`` em vez de
  ``servings_per_container``. Ninguém lê ``servings``, então o pacote de 4 pães
  para hot dog herdava "1 porção de 80 g" da unidade e declarava conter um pão.

⚠️ **A regra é arredondamento, não tolerância.** ``servings_per_container`` é uma
CONTAGEM inteira: a baguete de gergelim tem 260 g e a porção é 100 g, então são
2,6 porções e o rótulo declara 3. Isso está certo. Medir isso como "3 × 100 g =
300 g, 15% acima dos 260 g" é aplicar uma régua que não existe — foi o erro da
primeira versão deste teste, e ele acusou cinco produtos saudáveis. O certo é
``servings_per_container == round(peso / porção)``, que é exatamente a conta que
o ``apply_product_measurements`` usa para corrigir.
"""

from __future__ import annotations

import pytest
from django.core.management import call_command
from shopman.offerman.models import Product

pytestmark = pytest.mark.django_db


def _porcoes_certas(peso: int, porcao: int) -> int:
    """A mesma conta do comando. Empate em .5 segue o ``round`` do Python."""
    return max(1, round(peso / porcao))


def test_rotulo_manual_declara_as_porcoes_da_peca(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "Rotulos-2026-Nelson!")
    call_command("seed", verbosity=0)

    erradas: list[str] = []
    conferidos = 0

    for product in Product.objects.exclude(nutrition_facts={}).order_by("sku"):
        facts = product.nutrition_facts or {}
        if facts.get("auto_filled") is not False:
            continue  # derivado da ficha; a nutrição já cuida da coerência
        peso = product.unit_weight_g or 0
        porcao = facts.get("serving_size_g") or 0
        if not peso or not porcao:
            continue

        conferidos += 1
        certo = _porcoes_certas(peso, porcao)
        declarado = facts.get("servings_per_container")
        if declarado != certo:
            erradas.append(
                f"{product.sku} {product.name}: peça {peso} g ÷ porção {porcao} g "
                f"= {peso / porcao:.2f} → {certo}, mas o rótulo declara {declarado}"
            )

    assert conferidos > 20, "a varredura não encontrou rótulos manuais — o filtro quebrou?"
    assert not erradas, (
        "Rótulo manual declarando um número de porções que não é o da peça:\n  "
        + "\n  ".join(erradas)
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
