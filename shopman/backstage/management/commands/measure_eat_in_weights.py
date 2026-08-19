"""Mede, no histórico, para onde cada SKU ambíguo inclina — e grava o peso.

O dono (19/08/2026): *"Faz esse ajuste diretamente nos dados. Faça uma média:
para onde este SKU inclina? Pronto."* Este comando é essa média, com um dono
e reproduzível: para cada SKU de papel **híbrido**, mede-se em que % das
vendas de balcão dele havia bebida na cesta, e compara-se com a média da casa.
O peso é o **quanto o SKU puxa gente para sentar ALÉM da média**:

    peso = (P(bebida | SKU) − P(bebida)) / (1 − P(bebida))

SKU na média da casa não inclina (fica no piso, 5 — como "leva"); SKU muito
acima (croissant de presunto e queijo: 59% contra 36%) inclina forte. Por que
não usar a co-ocorrência crua (41% do croissant → peso 41)? Porque ela conta o
café duas vezes: a cesta com café já é "sentou" pela âncora; o peso só decide
a cesta SEM bebida — e nessa, pela regra do dono ("doce sozinho sem bebida é
pra levar"), a chance de alguém sentado é pequena. A co-ocorrência crua daria
60% de pedidos com alguém sentado; a lift dá ~40%, o retrato do estudo do
dono (~38% local). É uma dica de co-ocorrência, não uma medição de quem sentou
(essa vem da comanda, passo 2) — mas é o dado falando em vez do 50 neutro.

Só os híbridos: "consome aqui"/bebidas (95) e "leva" (5) são curadoria firme
e ficam como estão. SKU sem venda de balcão suficiente (< ``--min-sales``)
mantém o peso do papel, declarado.

O catálogo usa os códigos da casa, então cada SKU se mede no próprio
histórico. A única herança que sobra é a do meio-preço: `MCT` é o croissant a
metade do preço e não tem base própria, então herda do `CT`. Quem não tem
histórico (geleia mini, tapenade) fica no peso do papel.

Imprime sempre; grava só com ``--apply``. A nota da etiqueta registra de onde o
peso veio e com que base, para ninguém confundir medida com palpite.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from shopman.backstage.services.consumption import HYBRID, beverage_rate, sku_signal

FLOOR, CEILING = 5, 95


class Command(BaseCommand):
    help = "Mede no histórico para onde cada SKU híbrido inclina e (com --apply) grava o peso."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Grava os pesos medidos.")
        parser.add_argument(
            "--min-sales", type=int, default=30,
            help="Vendas de balcão mínimas para o sinal valer (padrão: 30).",
        )

    def handle(self, *args, **options):
        from shopman.backstage.models import ProductConsumptionTag

        apply = options["apply"]
        min_sales = options["min_sales"]
        tags = list(
            ProductConsumptionTag.objects.filter(
                role__reading=HYBRID, role__is_active=True
            ).select_related("role").order_by("sku")
        )
        if not tags:
            self.stdout.write(self.style.WARNING("Nenhum SKU híbrido etiquetado."))
            return

        base = beverage_rate()  # % das vendas de balcão com bebida — a média da casa
        self.stdout.write(f"\nMédia da casa: {base}% das vendas de balcão têm bebida.")

        measured: dict[str, tuple[int, int]] = {}  # sku → (peso, vendas)
        lifts: dict[str, int] = {}  # sku → % com bebida (para imprimir)
        skipped: list[tuple[str, int]] = []
        for tag in tags:
            signal = sku_signal(tag.sku)
            if signal is None or signal.sales < min_sales:
                skipped.append((tag.sku, signal.sales if signal else 0))
                continue
            measured[tag.sku] = (_lift(signal.with_beverage_pct, base), signal.sales)
            lifts[tag.sku] = signal.with_beverage_pct

        inherited: dict[str, tuple[int, str]] = {}  # sku → (peso, gêmeos usados)
        for tag in tags:
            if tag.sku in measured:
                continue
            # Convenção do Yooga: "M" + SKU é a variante (metade do preço) do
            # mesmo produto — sem base própria, herda do pai.
            #
            # Havia aqui um mapa `TWINS` de SKU do cardápio 2027 para o gêmeo no
            # Yooga (CROISSANT → CT). Ele existia porque os dois lados usavam
            # códigos diferentes para o mesmo pão; desde que o catálogo passou a
            # usar os códigos da casa, os dois lados são o MESMO SKU e cada um
            # se mede sozinho. O mapa virou entrada inalcançável e saiu.
            candidates = (
                [tag.sku[1:]]
                if tag.sku.startswith("M") and tag.sku[1:] in measured
                else []
            )
            twins = [t for t in candidates if t in measured]
            if not twins:
                continue
            weight = round(sum(measured[t][0] for t in twins) / len(twins))
            inherited[tag.sku] = (_clamp(weight), "+".join(twins))
        skipped = [(sku, n) for sku, n in skipped if sku not in inherited]

        self.stdout.write(self.style.SUCCESS(
            f"\n═══ Peso de consumo local pelo histórico ({len(tags)} SKUs híbridos) ═══"
        ))
        self.stdout.write(f"  {'SKU':<34} {'peso':>5}  base")
        for sku, (weight, sales) in sorted(measured.items(), key=lambda kv: -kv[1][1]):
            sales_text = f"{sales:,}".replace(",", ".")
            self.stdout.write(
                f"  {sku:<34} {weight:>4}%  {sales_text} vendas · {lifts[sku]}% com bebida "
                f"(média {base}%)"
            )
        for sku, (weight, twins) in sorted(inherited.items()):
            self.stdout.write(f"  {sku:<34} {weight:>4}%  herdado do gêmeo {twins}")
        if skipped:
            self.stdout.write(self.style.WARNING(
                f"\n  {len(skipped)} sem base suficiente (< {min_sales} vendas de balcão) — "
                "ficam no peso do papel:"
            ))
            for sku, sales in skipped:
                self.stdout.write(f"  {sku:<34} {sales:>5} vendas")

        if not apply:
            self.stdout.write("\n(sem --apply: nada gravado)")
            return

        changed = 0
        for sku, (weight, sales) in measured.items():
            changed += ProductConsumptionTag.objects.filter(sku=sku).update(
                eat_in_weight=weight,
                note=(
                    f"peso pelo histórico: {lifts[sku]}% de {sales} vendas com bebida "
                    f"(média {base}%) → {weight}%"
                ),
            )
        for sku, (weight, twins) in inherited.items():
            changed += ProductConsumptionTag.objects.filter(sku=sku).update(
                eat_in_weight=weight,
                note=f"peso herdado do gêmeo {twins} no histórico: {weight}%",
            )
        self.stdout.write(self.style.SUCCESS(f"\n✓ {changed} peso(s) gravado(s)."))


def _lift(with_beverage_pct: int, base_pct: int) -> int:
    """Quanto o SKU puxa para sentar além da média da casa, em 0–100.

    Na média ou abaixo → piso (não inclina). 100% com bebida → teto.
    """
    if base_pct >= 100:
        return FLOOR
    lift = (with_beverage_pct - base_pct) * 100 / (100 - base_pct)
    return _clamp(round(lift))


def _clamp(value: int) -> int:
    return max(FLOOR, min(CEILING, int(value)))
