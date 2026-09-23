"""Devolve ao produto certo a venda histórica que o de-para credita a outro.

Usage::

    python manage.py repoint_product_aliases            # ensaio
    python manage.py repoint_product_aliases --apply    # grava

**O que aconteceu.** O B.I. junta dois anos de Yooga ao catálogo de hoje por uma
tabela de tradução (``backstage.ProductAlias``): SKU da origem → produto. Em
19/08/2026 a curadoria apontou 15 códigos para produtos que, **naquele dia**,
eram a melhor correspondência que existia:

- os 12 chás Kãnfa (lata e pouch) para ``THL`` — "Chá da Casa (lata)", porque o
  catálogo ainda não tinha os 12 separados;
- ``BBB`` e ``PHO``, que são a UNIDADE, para ``BBB2`` e ``PHO4``, que são o
  pacote — a nota da época diz "mesmo produto";
- ``CHAI_A`` para produto nenhum, como "produto de outra época".

Desde então o catálogo mudou: os 12 chás existem, e o ``rename_skus_to_real``
resolveu que o pacote é **bundle** sobre a unidade, com a unidade virando
produto próprio. A tradução ficou para trás, e o efeito é silencioso — os 15
aparecem no B.I. com venda zero, e o produto errado aparece com a venda deles.
São **10.849** linhas em ``BBB`` e **6.360** em ``PHO``.

**O que este comando faz.** Reaponta cada um desses de-paras para o produto cujo
SKU é o próprio código externo. Nada mais: não cria alias, não apaga venda, não
toca no ``HistoricalSaleItem`` (registro de terceiro). Idempotente — o de-para
que já aponta para o lugar certo não é tocado.

**Ordem.** Rode ANTES do ``apply_product_skus``: o de-para casa pelo FK, mas é
o código externo que diz qual produto é qual, e depois do rename esse laço só
existe na tabela do outro comando. O ``apply_product_skus`` recusa esses 15
pares justamente até isto ser resolvido.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

FONTE = "yooga"

#: Códigos externos cujo de-para deve apontar para o produto de MESMO SKU.
#: Autorizado pelo dono em 22/09/2026 ("faz"), depois de ver o ensaio do rename.
#: Cada um traz o que a linha de 19/08 dizia, para que a troca seja legível.
REAPONTAR: tuple[tuple[str, str], ...] = (
    ("CHEGO_L50", "chás Kãnfa lata/pouch = Chá da Casa (lata)"),
    ("CHEGO_P50", "chás Kãnfa lata/pouch = Chá da Casa (lata)"),
    ("INTIMI_L50", "chás Kãnfa lata/pouch = Chá da Casa (lata)"),
    ("INTIMI_P50", "chás Kãnfa lata/pouch = Chá da Casa (lata)"),
    ("INTU_L70", "chás Kãnfa lata/pouch = Chá da Casa (lata)"),
    ("INTU_P50", "chás Kãnfa lata/pouch = Chá da Casa (lata)"),
    ("MAMA_L60", "chás Kãnfa lata/pouch = Chá da Casa (lata)"),
    ("MAMA_P50", "chás Kãnfa lata/pouch = Chá da Casa (lata)"),
    ("NAMAS_L60", "chás Kãnfa lata/pouch = Chá da Casa (lata)"),
    ("NAMAS_P50", "chás Kãnfa lata/pouch = Chá da Casa (lata)"),
    ("SOFIA_P50", "chás Kãnfa lata/pouch = Chá da Casa (lata)"),
    ("VITAL_P50", "chás Kãnfa lata/pouch = Chá da Casa (lata)"),
    ("BBB", "a unidade estava creditada ao pacote de 2"),
    ("PHO", "a unidade estava creditada ao pacote de 4"),
    ("CHAI_A", "estava como produto de outra época, sem produto nenhum"),
)


class Command(BaseCommand):
    help = "Reaponta os de-paras do B.I. que creditam a venda histórica ao produto errado."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Grava. Sem isto o comando só mostra o que mudaria.",
        )

    def handle(self, *args, **options):
        from shopman.offerman.models import Product

        from shopman.backstage.models import AliasStatus, HistoricalSaleItem, ProductAlias

        apply = options["apply"]
        out = self.stdout

        codigos = [sku for sku, _nota in REAPONTAR]
        produtos = dict(
            Product.objects.filter(sku__in=codigos).values_list("sku", "id")
        )
        aliases = {
            a.external_sku: a
            for a in ProductAlias.objects.filter(
                source=FONTE, external_sku__in=codigos
            ).select_related("product")
        }
        vendas = dict(
            HistoricalSaleItem.objects.filter(sku__in=codigos)
            .values_list("sku")
            .annotate(n=Count("id"))
        )

        trocas: list[tuple[str, str, str, int]] = []
        parados: list[str] = []

        with transaction.atomic():
            for sku, nota_de_origem in REAPONTAR:
                alias = aliases.get(sku)
                if alias is None:
                    parados.append(f"{sku}: não há de-para '{FONTE}:{sku}' — nada a reapontar.")
                    continue
                destino = produtos.get(sku)
                if destino is None:
                    parados.append(f"{sku}: não existe produto com esse SKU no catálogo.")
                    continue
                antes = alias.product.sku if alias.product_id else "—"
                if alias.product_id == destino:
                    continue  # já está certo
                alias.product_id = destino
                alias.status = AliasStatus.CONFIRMED
                alias.note = (
                    f"reapontado em 22/09 para o próprio produto (o dono autorizou). "
                    f"Antes: {antes} — {nota_de_origem}"
                )[:200]
                alias.save(update_fields=["product", "status", "note"])
                trocas.append((sku, antes, sku, vendas.get(sku, 0)))
            if not apply:
                transaction.set_rollback(True)

        verbo = "Feito" if apply else "Faria"
        if trocas:
            total = sum(n for *_x, n in trocas)
            out.write(self.style.SUCCESS(
                f"\n{verbo}: {len(trocas)} de-para(s) reapontado(s), "
                f"{total} linha(s) de venda voltando para o produto certo."
            ))
            for sku, antes, depois, n in trocas:
                out.write(f"  {FONTE}:{sku:<12} {antes:<6} → {depois:<12} {n:>7} linha(s)")
        else:
            out.write(self.style.SUCCESS("\nNada a reapontar: todos já apontam para o produto certo."))

        for p in parados:
            out.write(self.style.WARNING(f"⚠️  {p}"))

        if not apply:
            out.write(self.style.WARNING("\n(ensaio: nada gravado. Para gravar: --apply)"))
        else:
            out.write(
                "\nAgora o `apply_product_skus` aceita esses pares. "
                "O ranking do B.I. muda na próxima leitura — não há cache a limpar."
            )
