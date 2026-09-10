"""Recalcula a tabela de afinidade a partir das cestas do último ano.

Roda no ``maintenance_worker``, nunca dentro de um request: um ano de cestas é
trabalho de minutos, e a sugestão no carrinho tem que sair em milissegundos.

⚠️ **O comando controla a própria cadência.** O worker roda o ciclo a cada 5
minutos e não tem noção de "uma vez por noite" — quem sabe quanto custa este
cálculo é ele mesmo, não o worker. Por isso ele se recusa a recalcular enquanto
a tabela for mais nova que ``--min-interval-hours``, e o ``computed_at`` que já
existe é o relógio: nenhuma bookkeeping nova.

## As três decisões que este cálculo carrega

**Ano inteiro, com peso decrescente** (resposta do dono, 04/09). A cesta de
ontem ensina mais do que a de janeiro, mas a de janeiro ainda ensina — a casa
tem sazonalidade e um recorte curto a perderia. O peso cai por meia-vida: aos
``--half-life-days`` uma cesta vale metade.

**Lift, não contagem.** Contagem crua elege a água, que aparece com tudo porque
aparece com tudo. O lift pergunta se o par acontece mais do que aconteceria por
acaso — ``P(a,b) / (P(a) · P(b))`` — e é isso que separa "combina com" de "vende
muito".

**Piso de suporte.** Duas cestas com o mesmo par produzem um lift enorme e sem
sentido nenhum. Abaixo de ``--min-support`` cestas, o par não vira linha: ruído
não pode virar sugestão.

Uso::

    python manage.py compute_product_affinity
    python manage.py compute_product_affinity --window-days 180 --min-support 3
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_DAYS = 365
DEFAULT_HALF_LIFE_DAYS = 120
DEFAULT_MIN_SUPPORT = 5
#: Menos que 24h de propósito: 24 exatas fariam o cálculo pular um dia sempre
#: que o ciclo atrasasse um minuto.
DEFAULT_MIN_INTERVAL_HOURS = 20

#: Cesta gigante não ensina companhia — ensina que alguém fez a compra do mês.
#: Um pedido de 40 itens gera 780 pares, todos fracos, e afogaria os pares reais.
MAX_BASKET_SIZE = 25


class Command(BaseCommand):
    help = "Recalcula shop.ProductAffinity a partir das cestas do histórico e dos pedidos."

    def add_arguments(self, parser):
        parser.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
        parser.add_argument("--half-life-days", type=int, default=DEFAULT_HALF_LIFE_DAYS)
        parser.add_argument(
            "--min-support", type=int, default=DEFAULT_MIN_SUPPORT,
            help="Mínimo de cestas em comum para o par virar linha.",
        )
        parser.add_argument(
            "--min-interval-hours", type=int, default=DEFAULT_MIN_INTERVAL_HOURS,
            help="Não recalcula se a tabela for mais nova que isto. 0 desliga.",
        )
        parser.add_argument(
            "--force", action="store_true",
            help="Recalcula mesmo com a tabela fresca.",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        from shopman.shop.adapters import baskets as basket_source
        from shopman.shop.models import ProductAffinity

        window_days = options["window_days"]
        half_life = max(1, options["half_life_days"])
        min_support = options["min_support"]
        dry_run = options["dry_run"]

        now = timezone.now()
        since = now - timedelta(days=window_days)

        min_interval = options["min_interval_hours"]
        if min_interval and not (options["force"] or dry_run):
            fresh_since = now - timedelta(hours=min_interval)
            last = (
                ProductAffinity.objects.order_by("-computed_at")
                .values_list("computed_at", flat=True)
                .first()
            )
            if last and last >= fresh_since:
                self.stdout.write(
                    f"Tabela calculada em {last:%d/%m %H:%M}, "
                    f"dentro das {min_interval}h. Nada a fazer (--force ignora)."
                )
                return

        # Peso da cesta, contagem crua do item, contagem crua do par.
        item_weight: dict[str, float] = defaultdict(float)
        pair_weight: dict[tuple[str, str], float] = defaultdict(float)
        pair_count: dict[tuple[str, str], int] = defaultdict(int)
        total_weight = 0.0
        baskets_read = 0
        baskets_skipped = 0

        for basket in basket_source.all_baskets(since=since):
            if len(basket.skus) > MAX_BASKET_SIZE:
                baskets_skipped += 1
                continue

            age_days = max(0.0, (now - basket.occurred_at).total_seconds() / 86400)
            weight = 0.5 ** (age_days / half_life)

            baskets_read += 1
            total_weight += weight

            skus = sorted(basket.skus)
            for sku in skus:
                item_weight[sku] += weight
            for i, a in enumerate(skus):
                for b in skus[i + 1:]:
                    pair_weight[(a, b)] += weight
                    pair_count[(a, b)] += 1

        if not total_weight:
            self.stdout.write(self.style.WARNING(
                "Nenhuma cesta com dois itens ou mais na janela. Tabela intocada."
            ))
            return

        rows = []
        for (a, b), count in pair_count.items():
            if count < min_support:
                continue
            # P(a,b) / (P(a)·P(b)), tudo sobre o mesmo peso total.
            p_ab = pair_weight[(a, b)] / total_weight
            p_a = item_weight[a] / total_weight
            p_b = item_weight[b] / total_weight
            if not (p_a and p_b):
                continue
            lift = p_ab / (p_a * p_b)
            score = pair_weight[(a, b)]

            # Nos dois sentidos: a leitura pergunta sempre por `sku_a`.
            for x, y in ((a, b), (b, a)):
                rows.append(ProductAffinity(
                    sku_a=x, sku_b=y,
                    together_count=count, score=score, lift=lift,
                    window_days=window_days, computed_at=now,
                ))

        if dry_run:
            self.stdout.write(
                f"[dry-run] {baskets_read} cesta(s) lidas, "
                f"{len(rows) // 2} par(es) acima do suporte de {min_support}."
            )
            self._show_top(rows)
            return

        with transaction.atomic():
            # Substituição inteira: um par que caiu abaixo do suporte tem de
            # sumir, e não sobrar como resíduo de um cálculo antigo.
            ProductAffinity.objects.all().delete()
            ProductAffinity.objects.bulk_create(rows, batch_size=1000)

        skipped_note = f", {baskets_skipped} cesta(s) grandes demais ignoradas" if baskets_skipped else ""
        self.stdout.write(self.style.SUCCESS(
            f"{len(rows) // 2} par(es) gravados a partir de {baskets_read} cesta(s) "
            f"em {window_days} dias{skipped_note}."
        ))
        logger.info(
            "compute_product_affinity: %s pares, %s cestas, janela=%sd, suporte>=%s",
            len(rows) // 2, baskets_read, window_days, min_support,
        )

    def _show_top(self, rows) -> None:
        top = sorted(rows, key=lambda r: r.lift, reverse=True)[:10]
        for row in top:
            self.stdout.write(
                f"  {row.sku_a} → {row.sku_b}: lift {row.lift:.2f} "
                f"({row.together_count} cestas)"
            )
