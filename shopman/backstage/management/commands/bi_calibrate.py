"""As contagens que congelam o F3 com número em vez de opinião (F2).

Roda onde o histórico do Yooga está carregado — hoje, só o staging. Imprime e
não grava nada: é medição, não migração.

Duas perguntas, independentes:

1. **Que formas de pagamento o sistema antigo escrevia?** Dimensiona o
   vocabulário de normalização e, principalmente, mostra o que ele NÃO reconhece
   — que hoje aparece na tela com o texto original em vez de sumir num balde.
2. **Quanto o retrato do modo de consumo muda conforme a leitura da classe
   ambígua?** São duas leituras plausíveis do mesmo dado (§3.1.2 do
   BI-QUESTION-CATALOG), e a diferença entre elas é uma medida, não um debate.

⚠️ A pergunta 2 **depende das etiquetas existirem**. Sem elas tudo sai "sem
etiqueta" e não há o que comparar — por isso a ordem é curadoria, depois
variantes, depois congelar.

As variantes não reimplementam a regra: elas **remapeiam a leitura** de cada SKU
e chamam a mesma função. Regra alternativa seria uma segunda verdade a manter.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from django.core.management.base import BaseCommand

# Chave de variante é CÓDIGO, e código é em inglês. O `ref` do papel que vai no
# `--role` é DADO — e dado de catálogo nesta casa é pt-BR (`bebidas-quentes`,
# `falta-de-energia`), então `acompanha` está certo onde está.
VARIANTS: dict[str, str] = {
    "base": "como etiquetado",
    "ambiguous-as-takeaway": 'classe "híbrido" lida como "leva" (a proposta do booleano)',
}


class Command(BaseCommand):
    help = "Mede formas de pagamento e variantes do modo de consumo sobre o histórico (F2)."

    def add_arguments(self, parser):
        parser.add_argument("--from", dest="date_from", help="AAAA-MM-DD (padrão: tudo)")
        parser.add_argument("--to", dest="date_to", help="AAAA-MM-DD (padrão: tudo)")
        parser.add_argument(
            "--role", action="append", default=[], metavar="REF=LEITURA",
            help=(
                "Variante extra: relê um papel com outra leitura. "
                "Ex.: --role acompanha=takeaway. O REF é o do papel cadastrado; "
                "a LEITURA é anchor, takeaway ou hybrid."
            ),
        )

    def handle(self, *args, **options):
        window = self._window(options)
        self._payments(window)
        self._consumption(window, options["role"])

    def _window(self, options):
        parsed = []
        for key in ("date_from", "date_to"):
            raw = options.get(key)
            parsed.append(date.fromisoformat(raw) if raw else None)
        return tuple(parsed)

    # ── 1. Formas de pagamento ──────────────────────────────────────────────

    def _payments(self, window):
        from shopman.backstage.models import HistoricalSale
        from shopman.backstage.projections.bi_payments import (
            UNKNOWN_PREFIX,
            normalize_historical_payment,
        )

        sales = HistoricalSale.objects.all()
        date_from, date_to = window
        if date_from:
            sales = sales.filter(occurred_at__date__gte=date_from)
        if date_to:
            sales = sales.filter(occurred_at__date__lte=date_to)

        counts: dict[str, int] = defaultdict(int)
        amounts: dict[str, int] = defaultdict(int)
        raw_examples: dict[str, str] = {}
        total = 0
        for raw, total_q in sales.values_list("payment", "total_q"):
            key, label = normalize_historical_payment(raw)
            counts[key] += 1
            amounts[key] += total_q or 0
            raw_examples.setdefault(key, label)
            total += 1

        self.stdout.write(self.style.SUCCESS(
            f"\n═══ 1. Formas de pagamento no histórico ({total:,} vendas) ═══".replace(",", ".")
        ))
        if not total:
            self.stdout.write(self.style.WARNING(
                "  Nenhuma venda histórica carregada. Rode `ingest_yooga` ou use o staging."
            ))
            return

        known = [k for k in counts if not k.startswith(UNKNOWN_PREFIX)]
        unknown = [k for k in counts if k.startswith(UNKNOWN_PREFIX)]
        for key in sorted(known, key=lambda k: -counts[k]):
            self._line(raw_examples[key], counts[key], total, amounts[key])

        if unknown:
            self.stdout.write(self.style.WARNING(
                f"\n  ⚠️ {len(unknown)} forma(s) que o vocabulário NÃO reconhece. "
                "Aparecem na tela com o texto original — nunca somem num balde. "
                "Se alguma pesar, vale acrescentá-la ao vocabulário para somar com o nativo:"
            ))
            for key in sorted(unknown, key=lambda k: -counts[k]):
                self._line(raw_examples[key], counts[key], total, amounts[key])

    def _line(self, label: str, count: int, total: int, amount_q: int) -> None:
        share = count * 100 / total if total else 0
        self.stdout.write(
            f"  {label[:34]:<34} {count:>7} {share:>5.1f}%   R$ {amount_q / 100:>12,.2f}"
        )

    # ── 2. Variantes do modo de consumo ─────────────────────────────────────

    def _consumption(self, window, role_overrides):
        from shopman.backstage.models import HistoricalSale, HistoricalSaleItem
        from shopman.backstage.services.consumption import (
            HYBRID,
            MODE_LABELS,
            TAKEAWAY_ITEM,
            UNCLASSIFIED,
            sku_readings,
        )

        base = sku_readings()
        self.stdout.write(self.style.SUCCESS("\n═══ 2. Retrato do modo de consumo ═══"))
        if not base:
            self.stdout.write(self.style.WARNING(
                "  Nenhum SKU etiquetado — sem etiqueta, toda venda sai 'sem etiqueta' e não\n"
                "  há o que comparar. Rode `propose_consumption_tags`, revise no Admin, e volte."
            ))
            return

        sales = HistoricalSale.objects.all()
        date_from, date_to = window
        if date_from:
            sales = sales.filter(occurred_at__date__gte=date_from)
        if date_to:
            sales = sales.filter(occurred_at__date__lte=date_to)
        delivery = dict(sales.values_list("id", "is_delivery"))
        if not delivery:
            self.stdout.write(self.style.WARNING("  Nenhuma venda histórica carregada."))
            return

        lines: dict[int, list] = defaultdict(list)
        for sale_id, sku, qty in HistoricalSaleItem.objects.filter(
            sale_id__in=delivery
        ).values_list("sale_id", "sku", "qty"):
            lines[sale_id].append((sku, qty))

        variants = {
            "base": base,
            "ambiguous-as-takeaway": {
                sku: (TAKEAWAY_ITEM if reading == HYBRID else reading)
                for sku, reading in base.items()
            },
        }
        titles = dict(VARIANTS)
        for override in role_overrides:
            ref, _, reading = override.partition("=")
            variants[override] = self._override(base, ref, reading)
            titles[override] = f"papel '{ref}' lido como '{reading}'"

        results = {
            name: self._portrait(lines, delivery, readings)
            for name, readings in variants.items()
        }

        names = list(results)
        header = "  " + f"{'':<20}" + "".join(f"{name:>22}" for name in names)
        self.stdout.write(header)
        for mode in (*[m for m in MODE_LABELS if m != UNCLASSIFIED], UNCLASSIFIED):
            row = f"  {MODE_LABELS[mode]:<20}"
            for name in names:
                portrait = results[name]
                count = portrait.get(mode, 0)
                share = count * 100 / max(1, sum(portrait.values()))
                row += f"{count:>13,} {share:>6.1f}%".replace(",", ".")
            self.stdout.write(row)

        for name in names:
            self.stdout.write(f"\n  {name}: {titles.get(name, name)}")

        covered = 100 - (
            results["base"].get(UNCLASSIFIED, 0) * 100 / max(1, sum(results["base"].values()))
        )
        self.stdout.write(self.style.WARNING(
            f"\n  Cobertura das etiquetas: {covered:.1f}% das vendas têm ao menos um SKU\n"
            "  etiquetado. O resto sai declarado como 'sem etiqueta', nunca como 'levou'."
        ))

    def _override(self, base: dict, role_ref: str, reading: str) -> dict:
        from shopman.backstage.models import ProductConsumptionTag

        affected = set(
            ProductConsumptionTag.objects.filter(role__ref=role_ref).values_list("sku", flat=True)
        )
        return {
            sku: (reading if sku in affected else current)
            for sku, current in base.items()
        }

    def _portrait(self, lines, delivery, readings) -> dict[str, int]:
        from shopman.backstage.services.consumption import classify_basket

        portrait: dict[str, int] = defaultdict(int)
        for sale_id, is_delivery in delivery.items():
            mode = classify_basket(
                lines.get(sale_id, []), readings, is_delivery=is_delivery
            )
            portrait[mode] += 1
        return portrait
