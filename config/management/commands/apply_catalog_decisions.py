"""Aplica o que o dono decidiu sobre o catálogo: quem sai e quem se despublica.

Usage::

    python manage.py apply_catalog_decisions            # ensaio: executa e desfaz
    python manage.py apply_catalog_decisions --apply    # grava

A coluna `Situação` da planilha de curadoria é a decisão, e ele a revisou duas
vezes; o que ele decide depois entra nas mesmas listas, com a data. Este comando
a executa — não a discute.

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

#: Sai do catálogo. Coluna `Situação = excluir` da planilha de curadoria (2ª
#: revisão do dono em 22–23/09/2026), e o que ele decidiu depois, com a data.
DELETE: tuple[tuple[str, str], ...] = (
    ("COAD", "era ideia, não virou produto"),
    ("CE", "era ideia, não virou produto"),
    ("PU", "era ideia, não virou produto"),
    ("TJ", "era ideia, não virou produto"),
    ("PG", "era ideia, não virou produto"),
    ("TABUA", "era ideia, não virou produto"),
    ("COMBO-PETIT-DEJ", "era ideia, não virou produto"),
    ("GL", "placeholder de sabor indefinido; no lugar nascem os dois minis reais"),
    # Placeholders da despensa do Cardápio 2027 (decisão do dono, 24/09/2026).
    # O que os substitui nasce pelo `apply_grocery_catalog`.
    ("MT", "placeholder; no lugar entra o trio Maille (Dijon, com Mel e, com GTIN, à l'Ancienne)"),
    ("QP", "placeholder; no lugar entram os cremes Pomerode e o Queijo Vale do Testo"),
    ("CX", "placeholder; a casa não vende cornichons"),
    ("BK", "placeholder; o frio real da mercearia é o Presunto Cru"),
    ("GR", "placeholder; a casa não revende café"),
    ("LN", "placeholder; no lugar entram as quatro caixas presente"),
    ("THL", "placeholder; os chás Kãnfa em lata e pouch são o chá para levar"),
    ("CV", "Cream Soda do dia: era só uma ideia (dono, 24/09/2026)"),
)

#: Sai da loja, o cadastro fica. Coluna `Situação = despublicar`.
UNPUBLISH: tuple[tuple[str, str], ...] = (
    ("MIB", "fica para a encomenda do restaurante; o lugar dela no cardápio é a baguetinha de ciabatta"),
    ("MA", "sai da loja, o produto fica cadastrado"),
    ("PORQ", "sai da loja, o produto fica cadastrado"),
    ("MELICE", "sai da loja, o produto fica cadastrado"),
    # 24/09: vendeu 34 em 12 meses, contra 1.367 da de bacon. Fica cadastrada.
    ("FOC", "Focaccia Cebola Roxa quase não sai; o produto fica cadastrado"),
    ("FOCP", "a mini da Cebola Roxa acompanha a irmã: 16 vendas em 12 meses"),
)


class Command(BaseCommand):
    help = "Aplica as decisões do dono sobre o catálogo: exclui e despublica."

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

        targets = {p.sku: p for p in Product.objects.filter(
            sku__in=[s for s, _r in DELETE] + [s for s, _r in UNPUBLISH]
        )}

        # Peça de bundle vivo não se apaga por comando: o bundle ficaria oco.
        locked = {
            c.component.sku: c.parent.sku
            for c in ProductComponent.objects.filter(
                component__sku__in=[s for s, _r in DELETE]
            ).select_related("component", "parent")
        }
        if locked:
            for component, bundle in sorted(locked.items()):
                self.stderr.write(self.style.ERROR(
                    f"⛔ {component} é peça do bundle {bundle}. Apagá-lo deixaria o bundle sem "
                    "conteúdo — decida o bundle primeiro."
                ))
            raise CommandError("Nada foi gravado.")

        deleted: list[tuple[str, str, int, int]] = []
        unpublished: list[tuple[str, str]] = []
        missing: list[str] = []

        with transaction.atomic():
            for sku, _reason in UNPUBLISH:
                product = targets.get(sku)
                if product is None:
                    missing.append(sku)
                    continue
                if not product.is_published:
                    continue
                product.is_published = False
                product.save(update_fields=["is_published"])
                unpublished.append((sku, product.name))

            for sku, reason in DELETE:
                product = targets.get(sku)
                if product is None:
                    missing.append(sku)
                    continue
                # O de-para sobrevive ao produto, com a FK vazia: é assim que o
                # B.I. continua lendo a venda antiga pelo nome da origem.
                detached_aliases = ProductAlias.objects.filter(product=product).update(product=None)
                removed_bindings = self._remove_bindings(product)
                # A lápide nasce ANTES do delete: o vínculo com a coleção é
                # CASCADE, e depois dele a prateleira de origem não existe mais
                # em lugar nenhum (ver `shop.services.retired_urls`).
                collection_refs = list(
                    product.collection_items.order_by("-is_primary", "pk")
                    .values_list("collection__ref", flat=True)
                )
                record_retired(sku=sku, collection_refs=collection_refs, note=reason)
                name = product.name
                product.delete()
                deleted.append((sku, name, detached_aliases, removed_bindings))

            if not apply:
                transaction.set_rollback(True)

        verb = "Feito" if apply else "Faria"
        if deleted:
            out.write(self.style.SUCCESS(f"\n{verb}: {len(deleted)} produto(s) apagado(s)."))
            for sku, name, detached_aliases, removed_bindings in deleted:
                extra = []
                if detached_aliases:
                    extra.append(f"{detached_aliases} de-para(s) ficaram sem produto (a série segue pelo nome)")
                if removed_bindings:
                    extra.append(f"{removed_bindings} vínculo(s) de canal desfeito(s)")
                out.write(f"  {sku:18s} {name[:34]:34s} {'· ' + ', '.join(extra) if extra else ''}")
        if unpublished:
            out.write(self.style.SUCCESS(f"\n{verb}: {len(unpublished)} despublicado(s)."))
            for sku, name in unpublished:
                out.write(f"  {sku:18s} {name[:34]}")
        if not deleted and not unpublished:
            out.write(self.style.SUCCESS("\nNada a fazer: as decisões já estão aplicadas."))

        if missing:
            out.write(f"\n{len(missing)} já não estão no catálogo: {', '.join(sorted(set(missing)))}")

        out.write(self.style.WARNING(
            "\n⚠️  Produto apagado não tem destino de redirect: a URL dele é 410, não 301, "
            "e a lápide com as coleções de origem foi gravada junto do delete."
        ))
        if not apply:
            out.write(self.style.WARNING("\n(ensaio: executado e desfeito, nada gravado. Para gravar: --apply)"))

    def _remove_bindings(self, product) -> int:
        """O vínculo com cardápio de canal externo some com o produto."""
        from shopman.shop.models import CatalogBinding

        removed, _ = CatalogBinding.objects.filter(product=product).delete()
        return removed
