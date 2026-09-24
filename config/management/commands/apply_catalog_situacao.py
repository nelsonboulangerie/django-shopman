"""Aplica a SITUAÇÃO que o dono decidiu na planilha: quem sai e quem se despublica.

Usage::

    python manage.py apply_catalog_situacao            # ensaio: executa e desfaz
    python manage.py apply_catalog_situacao --apply    # grava

A coluna `Situação` da planilha de curadoria é a decisão, e ele a revisou duas
vezes. Este comando a executa — não a discute.

**Excluir apaga o produto.** Despublicar tira da loja e deixa o cadastro.

**O que o apagar precisa desatar antes**, e por quê:

- ``backstage.ProductAlias.product`` é ``PROTECT``, de propósito: apagar um
  produto com de-para confirmado apagaria a tradução de anos de histórico em
  silêncio. A regra do próprio model é a saída — *"produto extinto fica com FK
  vazia; o alias segue existindo, e a leitura usa o nome da origem"*. O comando
  esvazia a FK e **mantém** o alias.
- ``shop.CatalogBinding.product`` também é ``PROTECT`` (o vínculo com o
  cardápio de um canal externo). Some junto com o produto: sem produto não há o
  que vincular.
- ``ProductComponent.component`` é ``PROTECT``: um bundle aponta para as peças.
  Se o produto que sai é peça de um bundle vivo, o comando **recusa** — apagar
  ali deixaria o bundle sem conteúdo, e isso é decisão de catálogo.
- Coleção e listagem são ``CASCADE``: o vínculo some com o produto, como deve.

O que **não** se desata, porque é história: `OrderItem.sku` e
`HistoricalSaleItem.sku` guardam o código como texto. O pedido antigo continua
dizendo o que vendeu.

⚠️ **A URL vira 410, não 301.** Produto apagado não tem para onde redirecionar:
o comando grava a lápide (`shop.services.retired_urls.record`) no mesmo
``atomic()`` e antes do delete, com as coleções de onde ele saiu, e a loja
responde "saiu do cardápio" em vez de 404 mudo. `sku_history.retired_skus()`
os deixa de fora do mapa de redirect de propósito.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

#: Sai do catálogo. Coluna `Situação = excluir`, planilha de curadoria,
#: 2ª revisão do dono em 22–23/09/2026.
EXCLUIR: tuple[tuple[str, str], ...] = (
    ("COAD", "era ideia, não virou produto"),
    ("CE", "era ideia, não virou produto"),
    ("PU", "era ideia, não virou produto"),
    ("TJ", "era ideia, não virou produto"),
    ("PG", "era ideia, não virou produto"),
    ("TABUA", "era ideia, não virou produto"),
    ("COMBO-PETIT-DEJ", "era ideia, não virou produto"),
    ("GL", "placeholder de sabor indefinido; no lugar nascem os dois minis reais"),
)

#: Sai da loja, o cadastro fica. Coluna `Situação = despublicar`.
DESPUBLICAR: tuple[tuple[str, str], ...] = (
    ("MIB", "fica para a encomenda do restaurante; o lugar dela no cardápio é a baguetinha de ciabatta"),
    ("MA", "sai da loja, o produto fica cadastrado"),
    ("PORQ", "sai da loja, o produto fica cadastrado"),
    ("MELICE", "sai da loja, o produto fica cadastrado"),
)


class Command(BaseCommand):
    help = "Aplica a situação decidida na planilha: exclui e despublica."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Grava. Sem isto o comando executa e desfaz, e só mostra o relatório.",
        )

    def handle(self, *args, **options):
        from shopman.offerman.models import Product, ProductComponent

        from shopman.backstage.models import ProductAlias
        from shopman.shop.services.retired_urls import record as record_retired

        apply = options["apply"]
        out = self.stdout

        alvos = {p.sku: p for p in Product.objects.filter(
            sku__in=[s for s, _m in EXCLUIR] + [s for s, _m in DESPUBLICAR]
        )}

        # Peça de bundle vivo não se apaga por comando: o bundle ficaria oco.
        presos = {
            c.component.sku: c.parent.sku
            for c in ProductComponent.objects.filter(
                component__sku__in=[s for s, _m in EXCLUIR]
            ).select_related("component", "parent")
        }
        if presos:
            for peca, bundle in sorted(presos.items()):
                self.stderr.write(self.style.ERROR(
                    f"⛔ {peca} é peça do bundle {bundle}. Apagá-lo deixaria o bundle sem "
                    "conteúdo — decida o bundle primeiro."
                ))
            raise CommandError("Nada foi gravado.")

        apagados: list[tuple[str, str, int, int]] = []
        despublicados: list[tuple[str, str]] = []
        ausentes: list[str] = []

        with transaction.atomic():
            for sku, _motivo in DESPUBLICAR:
                produto = alvos.get(sku)
                if produto is None:
                    ausentes.append(sku)
                    continue
                if not produto.is_published:
                    continue
                produto.is_published = False
                produto.save(update_fields=["is_published"])
                despublicados.append((sku, produto.name))

            for sku, motivo in EXCLUIR:
                produto = alvos.get(sku)
                if produto is None:
                    ausentes.append(sku)
                    continue
                # O de-para sobrevive ao produto, com a FK vazia: é assim que o
                # B.I. continua lendo a venda antiga pelo nome da origem.
                soltos = ProductAlias.objects.filter(product=produto).update(product=None)
                vinculos = self._soltar_bindings(produto)
                # A lápide nasce ANTES do delete: o vínculo com a coleção é
                # CASCADE, e depois dele a prateleira de origem não existe mais
                # em lugar nenhum (ver `shop.services.retired_urls`).
                prateleiras = list(
                    produto.collection_items.order_by("-is_primary", "pk")
                    .values_list("collection__ref", flat=True)
                )
                record_retired(sku=sku, collection_refs=prateleiras, note=motivo)
                nome = produto.name
                produto.delete()
                apagados.append((sku, nome, soltos, vinculos))

            if not apply:
                transaction.set_rollback(True)

        verbo = "Feito" if apply else "Faria"
        if apagados:
            out.write(self.style.SUCCESS(f"\n{verbo}: {len(apagados)} produto(s) apagado(s)."))
            for sku, nome, soltos, vinculos in apagados:
                extra = []
                if soltos:
                    extra.append(f"{soltos} de-para(s) ficaram sem produto (a série segue pelo nome)")
                if vinculos:
                    extra.append(f"{vinculos} vínculo(s) de canal desfeito(s)")
                out.write(f"  {sku:18s} {nome[:34]:34s} {'· ' + ', '.join(extra) if extra else ''}")
        if despublicados:
            out.write(self.style.SUCCESS(f"\n{verbo}: {len(despublicados)} despublicado(s)."))
            for sku, nome in despublicados:
                out.write(f"  {sku:18s} {nome[:34]}")
        if not apagados and not despublicados:
            out.write(self.style.SUCCESS("\nNada a fazer: a situação da planilha já está aplicada."))

        if ausentes:
            out.write(f"\n{len(ausentes)} já não estão no catálogo: {', '.join(sorted(set(ausentes)))}")

        out.write(self.style.WARNING(
            "\n⚠️  Produto apagado não tem destino de redirect: a URL dele é 410, não 301, "
            "e a lápide com as coleções de origem foi gravada junto do delete."
        ))
        if not apply:
            out.write(self.style.WARNING("\n(ensaio: executado e desfeito, nada gravado. Para gravar: --apply)"))

    def _soltar_bindings(self, produto) -> int:
        """O vínculo com cardápio de canal externo some com o produto."""
        from shopman.shop.models import CatalogBinding

        apagados, _ = CatalogBinding.objects.filter(product=produto).delete()
        return apagados
