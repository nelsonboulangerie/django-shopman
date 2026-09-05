"""Aplica peso, medida e rendimento do catálogo num banco que já roda.

Usage::

    python manage.py apply_product_measurements            # só mostra o que mudaria
    python manage.py apply_product_measurements --apply    # grava
    python manage.py apply_product_measurements --sku CGO  # um SKU só

**Por que este comando existe.** O `seed` é bootstrap, não ferramenta de
correção: além do catálogo ele reescreve estoque, clientes, configuração e
receitas, e no perfil `demo` inventa milhares de pedidos. Num banco que já roda
isso é destrutivo, então corrigir um peso pelo `seed` não é opção — e sem opção
nenhuma a correção fica no repositório sem nunca chegar na tela de quem compra.

Este comando toca **três campos** e nada mais:

- ``Product.unit_weight_g``
- ``Product.metadata["approx_dimensions"]``
- o atributo ``porcoes`` do registro (era ``Product.metadata["serves"]``)

Preço, nome, descrição, estoque, pedido e configuração ficam intocados. Sem
``--apply`` ele não grava nada: imprime a tabela do que mudaria e sai.

Depois de gravar, acerta o rótulo dos SKUs alcançados, porque a porção da
nutrição é rotulada pelo ``unit_weight_g``: mudar o peso sem acertar o rótulo o
deixa descrevendo a peça antiga.

- Rótulo derivado da ficha → remontado por ``fill_nutrition_from_recipe``.
- Rótulo **manual** (``auto_filled=False``) → nada o recalcula, então aqui só o
  contador ``servings_per_container`` é reacertado pelo peso novo. Os valores
  por porção são medidos e continuam valendo: 100 g de campagne têm as mesmas
  calorias num pão de 300 g ou de 500 g.

⚠️ A tabela abaixo é uma CÓPIA do que o `seed` declara, e cópia diverge. O que
segura as duas juntas é
``shopman/backstage/tests/test_apply_product_measurements_matches_seed.py``:
ele roda o seed do zero e falha se qualquer valor daqui discordar do catálogo
semeado. Mexeu num, mexa no outro — o teste avisa.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from shopman.offerman.models import Product

from shopman.shop.services import attributes
from shopman.shop.services.nutrition_from_recipe import fill_nutrition_from_recipe

# Medidas conferidas com o dono em 21/08/2026 e corrigidas no PR #280: a ficha
# passou a falar em massa CRUA e o catálogo em peça ASSADA, com ~12% de perda no
# forno entre as duas. Em 26/08 o dono pesou a massa crua peça a peça
# (PESO_MASSA_CRUA_G no seed) e seis valores assados foram recalibrados a
# partir dela — estimativas de ~12%, a conferir na balança com a peça pronta.
MEASUREMENTS: dict[str, dict[str, object]] = {
    "CGO": {
        "unit_weight_g": 300,
        "serves": "2 a 3 pessoas",
        "approx_dimensions": "aprox. 15 cm de diâmetro x 10 cm de altura",
    },
    "CPX": {"unit_weight_g": 500, "approx_dimensions": "aprox. 15 x 15 x 10 cm"},
    "CGR": {"unit_weight_g": 300},
    "CF": {"unit_weight_g": 265},
    "CI": {"unit_weight_g": 180},
    "CT": {"unit_weight_g": 70},
    "KP": {"unit_weight_g": 250},
    "MD": {"unit_weight_g": 25},
    "BH": {"unit_weight_g": 90},
    "CN": {"unit_weight_g": 72},
    "FOA": {"unit_weight_g": 370},
    "CBT": {"unit_weight_g": 600},
    "FOC": {"unit_weight_g": 475},
}

# `approx_dimensions` segue chave solta do metadata (é do catálogo);
# `serves` virou o atributo `porcoes` do registro do tenant.
_METADATA_FIELDS = ("approx_dimensions",)
_ATTRIBUTE_FIELDS = {"serves": "porcoes"}


def _corrigir_porcoes_do_rotulo_manual(product) -> bool:
    """Reacerta ``servings_per_container`` num rótulo escrito à mão.

    Rótulo manual (``auto_filled=False``) não é recalculado por nada, então
    mudar o peso da peça o deixa descrevendo a peça antiga: o campagne caiu para
    300 g e seguia anunciando 5 porções de 100 g, ou seja meio quilo de pão.

    Só o CONTADOR muda. Os valores por porção são medidos e continuam válidos —
    100 g de campagne têm as mesmas calorias num pão de 300 g ou de 500 g.
    """
    facts = product.nutrition_facts
    if not isinstance(facts, dict) or facts.get("auto_filled") is not False:
        return False

    porcao = facts.get("serving_size_g") or 0
    peso = product.unit_weight_g or 0
    if not porcao or not peso:
        return False

    correto = max(1, round(peso / porcao))
    if facts.get("servings_per_container") == correto:
        return False

    product.nutrition_facts = {**facts, "servings_per_container": correto}
    product.save(update_fields=["nutrition_facts"])
    return True


class Command(BaseCommand):
    help = "Aplica peso, medida e rendimento nos produtos, sem tocar em preço ou estoque."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Grava. Sem esta flag o comando só mostra o que mudaria.",
        )
        parser.add_argument("--sku", type=str, default=None, help="Um SKU só.")

    def handle(self, *args, apply: bool = False, sku: str | None = None, **options):
        alvo = {sku: MEASUREMENTS[sku]} if sku and sku in MEASUREMENTS else MEASUREMENTS
        if sku and sku not in MEASUREMENTS:
            self.stdout.write(self.style.ERROR(f"SKU {sku} não está na tabela deste comando."))
            return

        produtos = {p.sku: p for p in Product.objects.filter(sku__in=alvo)}
        ausentes = sorted(set(alvo) - set(produtos))
        mudancas: list[tuple[Product, list[str]]] = []

        for product_sku, desejado in sorted(alvo.items()):
            product = produtos.get(product_sku)
            if product is None:
                continue
            metadata = dict(product.metadata) if isinstance(product.metadata, dict) else {}
            linhas: list[str] = []

            peso = desejado.get("unit_weight_g")
            if peso is not None and product.unit_weight_g != peso:
                linhas.append(f"peso {product.unit_weight_g} → {peso} g")

            for campo in _METADATA_FIELDS:
                novo = desejado.get(campo)
                if novo is not None and metadata.get(campo) != novo:
                    linhas.append(f"{campo} {metadata.get(campo)!r} → {novo!r}")

            if linhas:
                mudancas.append((product, linhas))

        if ausentes:
            self.stdout.write(self.style.WARNING(
                f"  {len(ausentes)} SKU(s) fora do catálogo deste banco: {', '.join(ausentes)}"
            ))

        if not mudancas:
            self.stdout.write(self.style.SUCCESS("Nada a fazer: o catálogo já bate com a tabela."))
            return

        for product, linhas in mudancas:
            self.stdout.write(f"  {product.sku:6} {product.name[:28]:30} {' · '.join(linhas)}")

        if not apply:
            self.stdout.write(self.style.WARNING(
                f"\n{len(mudancas)} produto(s) mudariam. Nada foi gravado — repita com --apply."
            ))
            return

        rotulos = 0
        for product, _linhas in mudancas:
            desejado = alvo[product.sku]
            campos = []

            peso = desejado.get("unit_weight_g")
            if peso is not None and product.unit_weight_g != peso:
                product.unit_weight_g = peso
                campos.append("unit_weight_g")

            metadata = dict(product.metadata) if isinstance(product.metadata, dict) else {}
            for campo in _METADATA_FIELDS:
                novo = desejado.get(campo)
                if novo is not None and metadata.get(campo) != novo:
                    metadata[campo] = novo
                    if "metadata" not in campos:
                        campos.append("metadata")
            if "metadata" in campos:
                product.metadata = metadata

            for campo, ref in _ATTRIBUTE_FIELDS.items():
                novo = desejado.get(campo)
                if novo is None or attributes.get(product, ref) == novo:
                    continue
                attributes.set(product, ref, novo, source="manual", save=False)
                if "metadata" not in campos:
                    campos.append("metadata")

            product.save(update_fields=campos)

            # A porção do rótulo é rotulada pelo peso: sem remontar, ela passa a
            # descrever uma peça que não existe mais.
            if fill_nutrition_from_recipe(product):
                rotulos += 1
            elif _corrigir_porcoes_do_rotulo_manual(product):
                rotulos += 1

        self.stdout.write(self.style.SUCCESS(
            f"\n{len(mudancas)} produto(s) atualizados, {rotulos} rótulo(s) remontados."
        ))
