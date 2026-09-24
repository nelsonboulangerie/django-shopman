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

#: (código externo, SKU do produto de destino, o que a linha de 19/08 dizia).
#: Autorizado pelo dono em 22/09/2026 ("faz"), depois de ver o ensaio do rename.
#:
#: ⚠️ O destino é escrito, não deduzido do próprio código. Quando estes pares
#: nasceram, o produto tinha o mesmo código do Yooga — e deduzir bastava. O
#: rename de 23/09 trocou os códigos, e o comando passou a avisar "não existe
#: produto CHEGO_L50" toda vez que rodava, sobre linhas que já estavam certas.
#: Comando que grita quando não há nada errado ensina a ignorar o grito.
REAPONTAR: tuple[tuple[str, str, str], ...] = (
    ("CHEGO_L50", "CHA-ACONCHEGO-KANFA-L50", "chás Kãnfa lata/pouch = Chá da Casa (lata)"),
    ("CHEGO_P50", "CHA-ACONCHEGO-KANFA-P50", "chás Kãnfa lata/pouch = Chá da Casa (lata)"),
    ("INTIMI_L50", "CHA-INTIMIDADE-KANFA-L50", "chás Kãnfa lata/pouch = Chá da Casa (lata)"),
    ("INTIMI_P50", "CHA-INTIMIDADE-KANFA-P50", "chás Kãnfa lata/pouch = Chá da Casa (lata)"),
    ("INTU_L70", "CHA-INTUICAO-KANFA-L70", "chás Kãnfa lata/pouch = Chá da Casa (lata)"),
    ("INTU_P50", "CHA-INTUICAO-KANFA-P50", "chás Kãnfa lata/pouch = Chá da Casa (lata)"),
    ("MAMA_L60", "CHA-MAMA-KANFA-L70", "chás Kãnfa lata/pouch = Chá da Casa (lata)"),
    ("MAMA_P50", "CHA-MAMA-KANFA-P50", "chás Kãnfa lata/pouch = Chá da Casa (lata)"),
    ("NAMAS_L60", "CHA-NAMASTE-KANFA-L70", "chás Kãnfa lata/pouch = Chá da Casa (lata)"),
    ("NAMAS_P50", "CHA-NAMASTE-KANFA-P50", "chás Kãnfa lata/pouch = Chá da Casa (lata)"),
    ("SOFIA_P50", "CHA-CHALOSOFIA-KANFA-P50", "chás Kãnfa lata/pouch = Chá da Casa (lata)"),
    ("VITAL_P50", "CHA-VITAL-KANFA-P50", "chás Kãnfa lata/pouch = Chá da Casa (lata)"),
    ("BBB", "BRBB", "a unidade estava creditada ao pacote de 2"),
    ("PHO", "HOL", "a unidade estava creditada ao pacote de 4"),
    ("CHAI_A", "SFTCH", "estava como produto de outra época, sem produto nenhum"),
)

#: Segunda leva (23/09/2026), conferida linha a linha por ele: as "METADE DO
#: PREÇO" do Yooga, que a curadoria de 19/08 pendurou no produto errado porque
#: naquele dia o catálogo ainda não tinha o irmão separado. Aqui o destino NÃO é
#: o produto de mesmo código — é o pai da variante, que o nome da linha nomeia.
REAPONTAR_PARA: tuple[tuple[str, str, str], ...] = (
    ("MBBB", "BRBB", "a unidade estava creditada ao pacote de 2 (BRBB2)"),
    ("MPHO", "HOL", "a unidade estava creditada ao pacote de 4 (HOL4)"),
    ("MJO", "JO", "estava creditada ao Coelhinho; é a metade do Caranguejo"),
    ("MANU", "URS", "estava creditada ao Coelhinho; é a metade do Ursinho"),
    ("MANP", "PORQ", "estava creditada ao Coelhinho; é a metade do Porquinho"),
    ("MCGR", "CPR", "estava creditada ao Campagne oval; é a metade do Redondo"),
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

        # (código externo, sku do produto de destino, nota)
        alvos: list[tuple[str, str, str]] = list(REAPONTAR) + list(REAPONTAR_PARA)
        codigos = [sku for sku, _destino, _nota in alvos]
        produtos = dict(
            Product.objects.filter(
                sku__in={d for _s, d, _n in alvos}
            ).values_list("sku", "id")
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
            for sku, destino_sku, nota_de_origem in alvos:
                alias = aliases.get(sku)
                if alias is None:
                    parados.append(f"{sku}: não há de-para '{FONTE}:{sku}' — nada a reapontar.")
                    continue
                destino = produtos.get(destino_sku)
                if destino is None:
                    parados.append(
                        f"{sku}: não existe produto '{destino_sku}' no catálogo para apontar."
                    )
                    continue
                antes = alias.product.sku if alias.product_id else "—"
                if alias.product_id == destino:
                    continue  # já está certo
                alias.product_id = destino
                alias.status = AliasStatus.CONFIRMED
                alias.note = (
                    f"reapontado para {destino_sku} (o dono conferiu). "
                    f"Antes: {antes} — {nota_de_origem}"
                )[:200]
                alias.save(update_fields=["product", "status", "note"])
                trocas.append((sku, antes, destino_sku, vendas.get(sku, 0)))
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
