"""Propõe uma etiqueta de consumo por SKU, para o gestor REVISAR (F3).

Etiquetar produto a produto é curadoria de quem conhece o cardápio, e vai
continuar sendo — este comando não substitui isso, ele troca *decidir do zero*
por *conferir uma lista*. A diferença entre 59 formulários em branco e 59 sim/não
é a diferença entre a curadoria acontecer e não acontecer.

⚠️ **Proposta não é curadoria, e o código não deixa as duas se confundirem.**
Toda linha nasce com ``reviewed=False``. O nome do produto engana — foi
exatamente assim que o "Hambúrguer 100g" quase virou lanche quando é o pão — e
número calculado sobre palpite não pode aparecer como se fosse conferido.

Duas fontes, nesta ordem: a **coleção do catálogo** (produto que a casa vende
hoje) e a **categoria do histórico** (produto que só existe nos dois anos do
Yooga). O que nenhuma das duas alcança sai listado, para alguém decidir — nunca
chutado.

⚠️ **A etiqueta diz a VOCAÇÃO do produto, não um fato sobre a venda** (nomeado
pelo dono, 17/08). Croissant tem vocação ambígua; o croissant daquela venda pode
ter sido comido ali ou levado, e ninguém sabe. Por isso ela mora do lado
analítico e não no catálogo, e por isso toda leitura derivada dela sai rotulada
como inferida.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

# A tabela mora no service, junto da regra que a usa — uma pergunta, um dono.
from shopman.backstage.services.consumption import category_readings

# Coleção do catálogo → leitura. Visível de propósito: é uma regra de negócio,
# não um detalhe, e quem discordar tem de conseguir apontar a linha.
COLLECTION_READING: dict[str, str] = {
    "bebidas-quentes": "anchor",
    "bebidas-geladas": "anchor",
    "torneira": "anchor",
    # Correção do dono (17/08): "Salgados" na Nelson é prato quente servido no
    # prato — Croque Monsieur, Croque Madame, Queijo-Quente, Jambon-Beurre,
    # Pain Grillé, Tábua de Iguarias. Quem pede um croque sentou. A proposta
    # anterior os lia como "acompanha", o que esvaziaria o salão nos almoços.
    "salgados": "anchor",
    "rusticos": "takeaway",
    "mercearia": "takeaway",
    "finos": "hybrid",
    "doces": "hybrid",
}

# Palavra na categoria do histórico → leitura. Só entra quando o SKU não está
# em nenhuma coleção viva: o catálogo de hoje manda mais que o rótulo de ontem.
# "Combos" fica de fora de propósito: um bundle não tem vocação própria — ele
# herda a dos componentes, e propor uma leitura para ele a partir da coleção
# seria inventar. Fica para a curadoria, que é onde ele já está.
UNMAPPED_COLLECTIONS = ("combos",)


class Command(BaseCommand):
    help = "Propõe etiquetas de consumo por SKU a partir do catálogo e do histórico (revisar no Admin)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Mostra o que seria proposto, sem gravar nada.",
        )
        parser.add_argument(
            "--include-historical", action="store_true",
            help="Propõe também para SKUs que só existem no histórico externo.",
        )

    def handle(self, *args, **options):
        from shopman.offerman.models import CollectionItem, Product

        from shopman.backstage.models import ConsumptionRole, ProductConsumptionTag

        dry_run = options["dry_run"]
        # Papel por leitura; para bebida do histórico, o papel que DECLARA o
        # tipo de bebida (bebida-preparada/bebida-pronta) vence o genérico —
        # é ele que faz o strike rate enxergar a linha.
        active = list(ConsumptionRole.objects.filter(is_active=True).order_by("-ordering"))
        roles = {role.reading: role for role in active}
        beverage_roles = {(role.reading, role.beverage): role for role in active if role.beverage}
        missing = {reading for reading in set(COLLECTION_READING.values()) if reading not in roles}
        if missing:
            self.stderr.write(self.style.ERROR(
                f"Faltam papéis ativos para as leituras {sorted(missing)}. "
                "Rode o seed ou cadastre-os no Admin antes."
            ))
            return

        already = set(ProductConsumptionTag.objects.values_list("sku", flat=True))

        # SKU → leitura, pela coleção. Um produto em duas coleções mapeadas com
        # leituras diferentes não é proposto: é ambíguo, e ambíguo é do gestor.
        by_sku: dict[str, set[str]] = {}
        rows = CollectionItem.objects.select_related("collection", "product").values_list(
            "product__sku", "collection__ref"
        )
        for sku, collection_ref in rows:
            reading = COLLECTION_READING.get(collection_ref)
            if sku and reading:
                by_sku.setdefault(sku, set()).add(reading)

        proposals: list[tuple[str, str, str, str]] = []
        conflicted: list[str] = []
        for sku, readings in sorted(by_sku.items()):
            if sku in already:
                continue
            if len(readings) > 1:
                conflicted.append(sku)
                continue
            proposals.append((sku, next(iter(readings)), "coleção do catálogo", ""))

        proposed_skus = {sku for sku, *_rest in proposals}
        uncovered = sorted(
            sku for sku in Product.objects.values_list("sku", flat=True)
            if sku and sku not in already and sku not in proposed_skus and sku not in conflicted
        )

        historical_uncovered: list[str] = []
        if options["include_historical"]:
            proposals_h, historical_uncovered = self._historical(already, proposed_skus, conflicted)
            proposals.extend(proposals_h)

        for sku, reading, source, beverage in proposals:
            if dry_run:
                continue
            ProductConsumptionTag.objects.update_or_create(
                sku=sku,
                defaults={
                    "role": beverage_roles.get((reading, beverage)) or roles[reading],
                    "note": f"proposto pela {source} — revisar",
                    "reviewed": False,
                },
            )

        self._report(proposals, conflicted, uncovered, historical_uncovered, dry_run=dry_run)

    def _historical(self, already, proposed_skus, conflicted):
        from shopman.backstage.models import HistoricalSaleItem
        from shopman.backstage.services.consumption import CATEGORY_BEVERAGE

        proposals: list[tuple[str, str, str, str]] = []
        uncovered: set[str] = set()
        seen: dict[str, str] = {}
        # ⚠️ `.order_by()` limpando o ordering do Meta é OBRIGATÓRIO antes do
        # `.distinct()`: o Django acrescenta as colunas do ORDER BY ao SELECT, e
        # com `ordering = ["sale", "seq"]` o DISTINCT passava a ser sobre
        # (sku, categoria, venda, linha) — ou seja, não deduplicava nada. O
        # comando varria 380 mil linhas para achar ~150 pares, e a lista de
        # não-cobertos repetia o mesmo SKU centenas de vezes.
        rows = (
            HistoricalSaleItem.objects.exclude(sku="")
            .order_by()
            .values_list("sku", "category")
            .distinct()
        )
        by_category = category_readings()
        for sku, category in rows:
            if sku in already or sku in proposed_skus or sku in conflicted or sku in seen:
                continue
            lowered = (category or "").lower()
            for needle, reading in by_category:
                if needle in lowered:
                    seen[sku] = reading
                    beverage = next(
                        (kind for word, kind in CATEGORY_BEVERAGE if word in lowered), ""
                    )
                    proposals.append((sku, reading, "categoria do histórico", beverage))
                    break
            else:
                uncovered.add(sku)
        return proposals, sorted(uncovered)

    def _report(self, proposals, conflicted, uncovered, historical_uncovered, *, dry_run):
        from shopman.backstage.models import Reading

        labels = dict(Reading.choices)
        verb = "Proporia" if dry_run else "Propostas"
        by_reading: dict[str, int] = {}
        for _sku, reading, *_rest in proposals:
            by_reading[reading] = by_reading.get(reading, 0) + 1

        self.stdout.write(self.style.SUCCESS(f"\n{verb} {len(proposals)} etiquetas:"))
        for reading, count in sorted(by_reading.items(), key=lambda item: -item[1]):
            self.stdout.write(f"  {labels.get(reading, reading):<16} {count:>4}")

        if conflicted:
            self.stdout.write(self.style.WARNING(
                f"\n{len(conflicted)} em coleções que discordam — decisão sua:"
            ))
            for sku in conflicted:
                self.stdout.write(f"  {sku}")

        for title, skus in (
            ("sem coleção mapeada (inclui 'Combos' — bundle herda a vocação dos componentes)", uncovered),
            ("só no histórico, sem categoria reconhecida", historical_uncovered),
        ):
            if skus:
                self.stdout.write(self.style.WARNING(f"\n{len(skus)} {title}:"))
                for sku in skus[:40]:
                    self.stdout.write(f"  {sku}")
                if len(skus) > 40:
                    self.stdout.write(f"  … e mais {len(skus) - 40}")

        if dry_run:
            self.stdout.write("\n(--dry-run: nada gravado)")
            return
        self.stdout.write(self.style.WARNING(
            "\n⚠️ Tudo entrou como PROPOSTA, não como curadoria. Revise em "
            "Admin → Como vendemos → Etiquetas de consumo, filtrando por "
            "'revisada = não'. O nome engana: 'Hambúrguer 100g' é o pão."
        ))
