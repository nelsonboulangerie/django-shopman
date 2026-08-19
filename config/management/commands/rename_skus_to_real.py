"""Troca os SKUs inventados pelo seed pelos códigos que a casa usa (SKU-REAL-PLAN F3).

Os identificadores do cardápio 2027 (`CROISSANT`, `ESPRESSO`, `PAIN-CHOCOLAT`)
nasceram de geração automática. Os códigos da casa são os do Yooga — `CT`, `SS`,
`PC` —, usados por dois anos em 353 mil linhas de venda. O mapa foi conferido
produto a produto pelo dono em 18/08 (ver `docs/plans/sku-real-mapa.csv`).

**Por que um comando e não uma migração de dados:** o rename atravessa 17
campos em 9 apps, e o `RefBulk.cascade_rename` já faz isso — com transação,
`select_for_update` e auditoria no `Ref`. Migração de dados duplicaria a
travessia e ficaria desatualizada no dia em que um campo novo de SKU nascesse.
O `test_sku_cascade_coverage` é que garante a cobertura.

Idempotente: rodar de novo não faz nada. Seguro de rodar em ambiente com
operação — é troca de identificador, não de dado de venda.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

# (sku do seed, código real do Yooga). Conferido pelo dono, 18/08.
RENAMES = (
    ("BAGUETE", "BF"),                    # Baguete Francesa
    ("BAGUETE-GERGELIM", "BE"),           # Baguete Gergelim
    ("CAMPAGNE", "CGO"),                  # Pain de Campagne Oval
    ("CAMPAGNE-PASSAS", "CPX"),           # Campagne Passas e Castanhas
    ("CAPPUCCINO", "PS"),                 # Cappuccino
    ("CIABATTA", "CI"),                   # Ciabatta
    ("CORNET", "CO"),                     # Cornet
    ("CROISSANT", "CT"),                  # Croissant Tradicional
    ("CROQUE-COMPLET", "CCOM"),           # Croque Completo
    ("CROQUE-MADAME", "CMA"),             # Croque Madame
    ("CROQUE-MONSIEUR", "CMO"),           # Croque Monsieur
    ("ESPRESSO", "SS"),                   # Espresso
    ("FENDU", "FE"),                      # Fendu
    ("FRAPPE", "FP"),                     # Frappé Chocolate
    ("JAMBON-BEURRE", "JB"),              # Jambon Beurre
    ("KURO-PAN", "KP"),                   # Kuro Pan
    ("MADELEINE", "MD"),                  # Madeleine
    ("MELON-PAN", "ME"),                  # Melon
    ("MINI-BAGUETE", "MIB"),              # Mini Baguete Francesa
    ("MOCHACCINO", "MC"),                 # Mocaccino — NÃO o MH, que é Mocha
    ("PAIN-CHOCOLAT", "PC"),              # Pain Au Chocolat
    ("PAIN-PERDU", "PPU"),                # Pain Perdu
    ("PAO-HAMBURGER", "PH"),              # o Yooga chama de "Hambúrguer Artesanal 100g"
    ("QUEIJO-QUENTE", "QQ"),              # Queijo Quente
    ("TABATIERE", "TB"),                  # Tabatière
)

# ⚠️ Retidos de propósito: o código casa, mas a UNIDADE mudou. `PHO` era "Pão
# para Hot Dog — unidade" a R$ 6; no cardápio 2027 é pacote de 4 a R$ 28. `BBB`
# era unidade a R$ 8; hoje é pacote de 2 a R$ 16. Herdar o código faria o B.I.
# comparar 6.360 vendas de UNIDADE com vendas de PACOTE — erro de 4×. A decisão
# pendente é dar código próprio ao pacote (`PHO4`, `BBB2`).
RETIDOS = {
    "PAO-HOTDOG": ("PHO", "era unidade (R$ 6), hoje é pacote de 4 (R$ 28)"),
    "BRIOCHE-BURGER": ("BBB", "era unidade (R$ 8), hoje é pacote de 2 (R$ 16)"),
}


class Command(BaseCommand):
    help = "Troca os SKUs inventados do catálogo pelos códigos reais do Yooga."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Executa e desfaz, mostrando o que aconteceria.",
        )
        parser.add_argument(
            "--only",
            help="Roda um SKU só, pelo nome atual (ex.: --only CROISSANT). Para conferir entre um e outro.",
        )

    def handle(self, *args, **options):
        from shopman.offerman.models import Product
        from shopman.refs.bulk import RefBulk

        dry_run = options["dry_run"]
        alvo = (options["only"] or "").strip().upper()
        pares = [p for p in RENAMES if not alvo or p[0] == alvo]
        if alvo and not pares:
            retido = RETIDOS.get(alvo)
            if retido:
                self.stderr.write(self.style.ERROR(
                    f"'{alvo}' está retido: {retido[1]}. "
                    "Decida o código do pacote antes (ver SKU-REAL-PLAN §F1)."
                ))
            else:
                self.stderr.write(self.style.ERROR(f"'{alvo}' não está no mapa."))
            return

        feitos: list[tuple[str, str, int]] = []
        pulados: list[str] = []
        avisos: list[str] = []

        with transaction.atomic():
            for antigo, real in pares:
                tem_antigo = Product.objects.filter(sku=antigo).exists()
                tem_real = Product.objects.filter(sku=real).exists()

                if tem_antigo and tem_real:
                    # Não escolho por você: renomear aqui violaria o unique e,
                    # pior, fundiria dois produtos que alguém criou separados.
                    avisos.append(
                        f"{antigo} e {real} existem os dois — não mexi. Decida qual fica."
                    )
                    continue
                if not tem_antigo:
                    pulados.append(f"{antigo} → {real}")
                    continue

                linhas = RefBulk.cascade_rename("SKU", antigo, real, actor="rename_skus_to_real")
                feitos.append((antigo, real, linhas))

            if dry_run:
                # Executa e desfaz, em vez de simular: só assim o relatório
                # reflete o que a execução faria de verdade.
                transaction.set_rollback(True)

        self._report(feitos, pulados, avisos, alvo=alvo, dry_run=dry_run)

    def _report(self, feitos, pulados, avisos, *, alvo, dry_run):
        verbo = "Faria" if dry_run else "Feito"
        if feitos:
            total = sum(linhas for _a, _r, linhas in feitos)
            self.stdout.write(self.style.SUCCESS(
                f"\n{verbo}: {len(feitos)} SKU(s), {total} linha(s) atualizadas."
            ))
            for antigo, real, linhas in feitos:
                self.stdout.write(f"  {antigo:<20} → {real:<6} {linhas:>5} linha(s)")
        else:
            self.stdout.write(self.style.SUCCESS("\nNada a renomear."))

        if pulados:
            self.stdout.write(f"\n{len(pulados)} já renomeado(s) ou ausente(s) do catálogo:")
            for item in pulados[:10]:
                self.stdout.write(f"  {item}")
            if len(pulados) > 10:
                self.stdout.write(f"  … e mais {len(pulados) - 10}")

        for aviso in avisos:
            self.stdout.write(self.style.WARNING(f"⚠️  {aviso}"))

        if not alvo and RETIDOS:
            self.stdout.write(self.style.WARNING(
                f"\n⚠️  {len(RETIDOS)} retido(s) — o código casa, mas a unidade mudou:"
            ))
            for antigo, (real, motivo) in RETIDOS.items():
                self.stdout.write(f"  {antigo:<20} → {real:<6} {motivo}")
            self.stdout.write(
                "  Herdar o código faria o B.I. comparar unidade com pacote. "
                "Ver SKU-REAL-PLAN §F1."
            )

        if dry_run:
            self.stdout.write("\n(--dry-run: executado e desfeito, nada gravado)")
