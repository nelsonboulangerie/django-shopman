"""Aplica Marca e GTIN do Catálogo (``Product.metadata['social']``) num banco que já roda.

Usage::

    python manage.py apply_product_brands            # só mostra o que mudaria
    python manage.py apply_product_brands --apply    # grava
    python manage.py apply_product_brands --sku CT   # um SKU só

**Por que existe.** O feed do Google/Meta e a página de produto declaram a
marca e o GTIN que o Catálogo do Gestor guarda em ``metadata['social']`` (PRs
#957/#955). No alpha nenhum produto tinha marca, e o Search Console acusava
"Nenhum identificador global fornecido" nos 48 itens do feed.

**A regra (decisão do dono, 22/09/2026).** Produto que a casa faz ou monta aqui
(pão, doce, salgado, prato, bebida preparada no balcão) leva a marca da casa,
lida de ``Shop.brand_name``. Revenda leva a marca do fabricante e, quando
conferido, o GTIN do código de barras. Revenda **nunca** leva a marca da loja,
e o que ninguém confirmou fica fora da tabela: marca e GTIN vazios são "não
informado", não um palpite.

Toca ``metadata['social']['brand']``, ``metadata['social']['gtin']`` e a marca
``metadata['purchase']['resale']``, que declara "a casa compra este produto
pronto" — é o que o Compras oferece na entrada de mercadoria. Não
sobrescreve valor já preenchido com outra coisa (curadoria feita no Gestor
vence): a divergência sai no relatório e o SKU fica como está. Sem ``--apply``
não grava nada.

O ``seed`` chama :func:`apply_brands` logo depois de semear o catálogo, para que
um banco novo nasça igual ao que este comando deixa num banco vivo.
"""

from __future__ import annotations

from dataclasses import replace

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from shopman.offerman import get_social_attributes
from shopman.offerman.contrib.social.schema import set_social_attributes
from shopman.offerman.models import Product

# Feito ou montado aqui. Conferido contra o catálogo vivo do alpha em
# 22/09/2026. Os chás do bule são preparados aqui com blend Kãnfa: a bebida
# servida é da casa, como o espresso não leva a marca do torrador. Ficam fora
# porque a casa ainda não faz: Cream Soda (CV), Bacon (BK) e Mostarda (MT).
HOUSE_SKUS: frozenset[str] = frozenset({
    # Pães, viennoiserie, doces e salgados de forno
    "COE", "PORQ", "URS", "BAT", "BGL", "ITA", "BRBB", "BRBB2", "BRCH", "BGG", "BGGP",
    "TRADI", "BICH", "BRNT", "FOB", "CPBG", "CPG", "CPR", "CHLH", "CI", "CRP", "CN", "CO",
    "COC", "CRPQ", "CPX", "CRO", "DELI", "FORMA", "FENDU", "FFGO", "FOA", "FOC", "HOD", "JO",
    "KUBB", "KUP", "MA", "BRBBP", "MDLN", "MELON", "FFGOP", "MIB", "FOBP", "FOAP", "FOCP",
    "HODP", "PCHOC", "TRABB", "HOL", "HOL4", "PIT", "PIT4", "BRRSN", "TABAT",
    # Pratos montados aqui
    "CQCOM", "CQMA", "CQMO", "JB", "MELSA", "PERDU", "QJQT",
    # Bebidas preparadas no balcão
    "SFTCH", "CAFL", "CHOQ", "CTFV", "FRAP", "CHHIB", "CAPMO", "MOCHA", "CAP", "VIEN",
    "SPMC", "SDLA", "SP", "CHBLU", "CHCAM", "CHROU", "CHSOP",
    # Despensa feita na casa (dono, 22/09)
    "RTAT", "TPND",
})

# Revenda: marca do fabricante; GTIN só quando o código foi conferido (dígito
# verificador GS1 fecha e o produto do SKU é um só). Fonte: API do Yooga, a
# PlanilhaProdutos2024 do dono e as NF-e de compra.
#
# ⚠️ A Kãnfa declara "SEM GTIN" no campo próprio da NF-e e põe o código de
# barras no CÓDIGO DO PRODUTO — só o Aconchego Pouch veio no campo certo. Os
# códigos abaixo são EAN-13 com dígito verificador válido e prefixo de empresa
# 7898708, o mesmo do item que ela declarou: é o código da embalagem, lido do
# lugar errado da nota. Quem não tem código aqui é porque o fabricante manda
# código interno (Aconchego Lata) ou lixo de cadastro (Chalosofia vem como
# "CFOP5102"), ou porque o item não apareceu em nenhuma nota lida.
RESALE: dict[str, dict[str, str]] = {
    "QUEIJO-CAMEMBERT-ILEDEFRANCE-125": {"brand": "Ile de France", "gtin": "3161712996108"},  # Camembert 125g
    "AGUA-MINERAL-PRATA-310": {"brand": "Prata"},  # com e sem gás no mesmo SKU: dois GTINs
    # GTIN do pedido de venda 7970 da Kãnfa (My Chai, 30/06/2026), dígito
    # verificador GS1 conferido. Aconchego e Chalosofia vieram com código
    # interno do fabricante, que não é GTIN. As latas de Mama e Namastê são
    # "Lata 70g" na nota, e o nome do catálogo dizia 60g: o dono confirmou os
    # 70g em 22/09, então o identificador vale — o nome da peça é corrigido na
    # curadoria do catálogo, e o SKU segue o mesmo (SKU é endereço, não
    # descrição: trocá-lo quebraria o histórico de venda).
    "CHA-ACONCHEGO-KANFA-L50": {"brand": "Kãnfa"},
    "CHA-ACONCHEGO-KANFA-P50": {"brand": "Kãnfa", "gtin": "7898708850316"},
    "CHA-INTIMIDADE-KANFA-L50": {"brand": "Kãnfa", "gtin": "7898708850347"},
    "CHA-INTIMIDADE-KANFA-P50": {"brand": "Kãnfa", "gtin": "7898708850354"},
    "CHA-INTUICAO-KANFA-L70": {"brand": "Kãnfa", "gtin": "7898708850408"},
    "CHA-INTUICAO-KANFA-P50": {"brand": "Kãnfa", "gtin": "7898708850385"},
    "CHA-MAMA-KANFA-L70": {"brand": "Kãnfa", "gtin": "7898708850705"},
    "CHA-MAMA-KANFA-P50": {"brand": "Kãnfa", "gtin": "7898708850682"},
    "CHA-NAMASTE-KANFA-L70": {"brand": "Kãnfa", "gtin": "7898708850668"},
    "CHA-NAMASTE-KANFA-P50": {"brand": "Kãnfa", "gtin": "7898708850644"},
    "CHA-CHALOSOFIA-KANFA-P50": {"brand": "Kãnfa"},
    "CHA-VITAL-KANFA-P50": {"brand": "Kãnfa"},
}


def desired_identity(house_brand: str) -> dict[str, dict[str, str]]:
    """SKU → campos de ``metadata['social']`` que este comando garante."""
    table = {sku: {"brand": house_brand} for sku in HOUSE_SKUS}
    table.update({sku: dict(fields) for sku, fields in RESALE.items()})
    return table


def _house_brand() -> str:
    from shopman.shop.models import Shop

    shop = Shop.objects.only("brand_name", "name").first()
    brand = (shop.brand_name or shop.name).strip() if shop else ""
    if not brand:
        raise CommandError("A loja não tem marca (Shop.brand_name): nada para declarar nos produtos da casa.")
    return brand


def _mark_resale(product) -> bool:
    """Declara ``metadata['purchase']['resale']``. Devolve True se mudou.

    Sem esta marca o Compras não deixa a linha da nota apontar para o produto:
    o perfil fiscal ``resale`` fala de substituição tributária, não de "comprado
    pronto", e a falta de ficha só diz que ninguém cadastrou a ficha.
    """
    metadata = dict(product.metadata) if isinstance(product.metadata, dict) else {}
    purchase = dict(metadata.get("purchase") or {})
    if purchase.get("resale") is True:
        return False
    purchase["resale"] = True
    metadata["purchase"] = purchase
    product.metadata = metadata
    return True


def apply_brands(*, apply: bool, only_sku: str | None = None) -> dict[str, list]:
    """Calcula (e, com ``apply``, grava) marca/GTIN. Devolve o relatório.

    Chaves: ``changes`` [(sku, [linhas])], ``conflicts`` [(sku, campo, atual,
    desejado)], ``missing`` [sku], ``invalid`` [(sku, erros)].
    """
    table = desired_identity(_house_brand())
    if only_sku:
        if only_sku not in table:
            raise CommandError(f"SKU {only_sku} não está na tabela deste comando.")
        table = {only_sku: table[only_sku]}

    products = {p.sku: p for p in Product.objects.filter(sku__in=table)}
    report: dict[str, list] = {
        "changes": [],
        "conflicts": [],
        "missing": sorted(set(table) - set(products)),
        "invalid": [],
    }

    with transaction.atomic():
        for sku in sorted(products):
            product = products[sku]
            current = get_social_attributes(product)
            wanted = table[sku]
            updates: dict[str, str] = {}
            lines: list[str] = []
            for field, value in wanted.items():
                have = getattr(current, field)
                if have == value:
                    continue
                if have:
                    report["conflicts"].append((sku, field, have, value))
                    continue
                updates[field] = value
                lines.append(f"{field}: → {value}")
            marked = sku in RESALE and _mark_resale(product)
            if marked:
                lines.append("compra: mercadoria de revenda")
            if not updates and not marked:
                continue
            new_attrs = replace(current, **updates) if updates else current
            errors = new_attrs.errors()
            if errors:
                report["invalid"].append((sku, errors))
                continue
            report["changes"].append((sku, lines))
            if apply:
                if updates:
                    product.metadata = set_social_attributes(product.metadata, new_attrs)
                product.save(update_fields=["metadata", "updated_at"])
    return report


class Command(BaseCommand):
    help = "Aplica a marca da casa nos produtos feitos aqui e a do fabricante na revenda."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Grava. Sem esta flag só mostra.")
        parser.add_argument("--sku", type=str, default=None, help="Um SKU só.")

    def handle(self, *args, apply: bool = False, sku: str | None = None, **options):
        report = apply_brands(apply=apply, only_sku=sku)

        for product_sku, lines in report["changes"]:
            self.stdout.write(f"  {product_sku:16} {'; '.join(lines)}")
        for product_sku, field, have, want in report["conflicts"]:
            self.stdout.write(self.style.WARNING(
                f"  {product_sku:16} {field} já é {have!r} (a tabela diz {want!r}) — mantido"
            ))
        for product_sku, errors in report["invalid"]:
            self.stdout.write(self.style.ERROR(f"  {product_sku:16} recusado: {' '.join(errors)}"))
        if report["missing"]:
            self.stdout.write(self.style.WARNING(
                f"  {len(report['missing'])} SKU(s) fora do catálogo deste banco: {', '.join(report['missing'])}"
            ))

        verb = "gravados" if apply else "mudariam (rode com --apply para gravar)"
        self.stdout.write(self.style.SUCCESS(
            f"{len(report['changes'])} produto(s) {verb}; "
            f"{len(report['conflicts'])} divergência(s) mantida(s); {len(report['invalid'])} recusado(s)."
        ))
