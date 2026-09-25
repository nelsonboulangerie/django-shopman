"""Leva para onde se vende o saldo de revenda que ficou guardado fora da venda.

Usage::

    python manage.py relocate_resale_stock            # ensaio: mostra e não grava
    python manage.py relocate_resale_stock --apply    # transfere

Até a régua de recebimento por papel (``shop/services/receiving_position.py``),
o Compras recebia tudo na posição padrão (``massa``, WIP da Produção) e o seed
guardava o saldo de abertura da revenda no ``deposito`` — as duas fora da
venda. A geleia existia no estoque e não aparecia na loja nem no PDV.

Para cada SKU de **revenda** (à venda e não produzido aqui), o saldo PRESENTE
(sem data-alvo) que está numa posição que não vende é transferido para a
posição de recebimento da revenda (``Move.kind=TRANSFER``: o estoque total não
muda, só o lugar). Estoque planejado (com data-alvo) não é mexido.

Idempotente: rodar de novo não acha mais nada fora do lugar.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


def misplaced_resale_stock():
    """``[(quant, destino)]`` — saldo presente de revenda fora de posição que vende."""
    from shopman.buyman.models import Material
    from shopman.offerman.models import Product
    from shopman.stockman import Quant

    from shopman.shop.services.receiving_position import RESALE, position_for_role
    from shopman.shop.services.sku_records import sku_roles_map

    destination = position_for_role(RESALE)
    if destination is None or not destination.is_saleable:
        raise CommandError("Nenhuma posição que vende foi encontrada para receber a revenda.")
    skus = set(Material.objects.values_list("sku", flat=True)) & set(
        Product.objects.filter(is_sellable=True).values_list("sku", flat=True)
    )
    roles = sku_roles_map(skus)
    resale = [sku for sku, role in roles.items() if role.sellable and not role.produced]
    quants = (
        Quant.objects.filter(sku__in=resale, target_date__isnull=True, position__is_saleable=False)
        .select_related("position")
        .order_by("sku", "pk")
    )
    # Só o que está livre: saldo reservado (hold) fica onde a reserva o prendeu.
    return [(quant, destination) for quant in quants if quant.available > 0]


class Command(BaseCommand):
    help = "Transfere para a posição que vende o saldo de revenda guardado fora da venda."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Transfere. Sem isto, só mostra.")

    def handle(self, *args, apply: bool = False, **options):
        from shopman.stockman.services.movements import StockMovements

        moves = misplaced_resale_stock()
        total = Decimal("0")
        with transaction.atomic():
            for quant, destination in moves:
                qty = quant.available
                total += qty
                self.stdout.write(
                    f"  {quant.sku:40s} {qty:>10} de {quant.position.ref} → {destination.ref}"
                    + (f" (lote {quant.batch})" if quant.batch else "")
                )
                if apply:
                    StockMovements.transfer(
                        quantity=qty,
                        sku=quant.sku,
                        from_position=quant.position,
                        to_position=destination,
                        batch=quant.batch,
                        reason="Revenda vai para onde se vende (recebimento por papel)",
                    )
        verb = "transferidos" if apply else "seriam transferidos (rode com --apply)"
        self.stdout.write(self.style.SUCCESS(f"{len(moves)} saldo(s) de revenda {verb}; {total} unidade(s)."))
