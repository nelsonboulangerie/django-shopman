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
    ("PAO-HOTDOG", "PHO4"),               # o pacote de 4; a unidade é o PHO
    ("BRIOCHE-BURGER", "BBB2"),           # o pacote de 2; a unidade é o BBB
    ("PAO-HAMBURGER", "PH"),              # o Yooga chama de "Hambúrguer Artesanal 100g"
    ("QUEIJO-QUENTE", "QQ"),              # Queijo Quente
    ("TABATIERE", "TB"),                  # Tabatière
)

# Nada retido. Os dois pacotes estiveram aqui até 19/08, porque herdar `PHO` e
# `BBB` faria o B.I. comparar venda de UNIDADE com venda de PACOTE. A medição
# fechou a questão — 99% das vendas do Yooga eram qty=1, e o preço subiu R$ 1
# por ano sem salto, até R$ 7 e R$ 8, que vezes 4 e vezes 2 dão exatamente os
# R$ 28 e R$ 16 do cardápio 2027. Eram unidades.
#
# Então o pacote não é produto: é BUNDLE sobre a unidade. `PHO` e `BBB` viram
# os produtos (a fornada produz unidade, o estoque conta unidade), e `PHO4` e
# `BBB2` são bundles que baixam 4 e 2 do estoque ao vender.
RETIDOS: dict[str, tuple[str, str]] = {}

# ⚠️ Onde o SKU é `unique`, renomear com os dois valores já no banco estoura a
# constraint no meio da travessia. Só apareceu num ensaio sobre banco semeado —
# os testes unitários passavam, porque criavam um produto de cada vez.
#
# O que fazer depende do que a linha significa, então a política é explícita por
# model. Model com SKU único e sem política aqui faz o comando parar: prefiro
# recusar a inventar semântica de merge para tabela que não conheço.
POLITICA_DE_COLISAO = {
    # Etiqueta de consumo é ANOTAÇÃO sobre um produto, não o produto. Depois do
    # rename, a etiqueta de "CROISSANT" e a de "CT" descrevem a mesma coisa — a
    # segunda nasceu do `propose_consumption_tags --include-historical`, que
    # etiquetou os códigos do Yooga. Fundir é o certo; a curada vence a proposta.
    "backstage.ProductConsumptionTag": "fundir",
    # Produto é ENTIDADE. Fundir apagaria um catálogo inteiro de vínculos,
    # preços e listagens. Se os dois existem, alguém precisa decidir.
    "offerman.Product": "recusar",
    # Insumo idem — e insumo com SKU de produto vendável é sintoma, não acidente.
    "buyman.Material": "recusar",
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
        fusoes: list[str] = []

        with transaction.atomic():
            for antigo, real in pares:
                if not Product.objects.filter(sku=antigo).exists():
                    pulados.append(f"{antigo} → {real}")
                    continue

                bloqueios, fundidos = self._resolver_colisoes(antigo, real)
                if bloqueios:
                    avisos.extend(bloqueios)
                    continue
                fusoes.extend(fundidos)

                linhas = RefBulk.cascade_rename("SKU", antigo, real, actor="rename_skus_to_real")
                feitos.append((antigo, real, linhas))

            if dry_run:
                # Executa e desfaz, em vez de simular: só assim o relatório
                # reflete o que a execução faria de verdade.
                transaction.set_rollback(True)

        self._report(feitos, pulados, avisos, fusoes, alvo=alvo, dry_run=dry_run)

    def _resolver_colisoes(self, antigo: str, real: str) -> tuple[list[str], list[str]]:
        """Trata todo campo de SKU `unique` onde os dois valores já existem.

        Devolve (bloqueios, fusões). Bloqueio impede o rename daquele par; fusão
        é o que foi resolvido e vale contar no relatório.
        """
        from django.apps import apps
        from shopman.refs.registry import _ref_source_registry

        bloqueios: list[str] = []
        fusoes: list[str] = []

        for label, field_name in sorted(_ref_source_registry.get_sources_for_type("SKU")):
            app_label, model_name = label.split(".", 1)
            try:
                Model = apps.get_model(app_label, model_name)
            except LookupError:
                continue
            if not Model._meta.get_field(field_name).unique:
                continue

            velho = Model.objects.filter(**{field_name: antigo}).first()
            novo = Model.objects.filter(**{field_name: real}).first()
            if velho is None or novo is None:
                continue

            politica = POLITICA_DE_COLISAO.get(label)
            if politica == "fundir":
                # Quem sobrevive: a curada vence a proposta. No empate (as duas
                # curadas, ou nenhuma), sobrevive a do SKU antigo — ela veio da
                # coleção do catálogo, e a outra, da categoria do histórico.
                velho_curado = getattr(velho, "reviewed", False)
                novo_curado = getattr(novo, "reviewed", False)
                if novo_curado and not velho_curado:
                    fica, sai, motivo = novo, velho, "sobreviveu a curada"
                else:
                    fica, sai, motivo = velho, novo, (
                        "sobreviveu a curada" if velho_curado else "sobreviveu a do catálogo"
                    )
                sai.delete()
                setattr(fica, field_name, antigo)  # o cascade a leva para `real`
                fica.save(update_fields=[field_name])
                fusoes.append(f"{label}: {antigo} + {real} — {motivo}")
                continue

            bloqueios.append(
                f"{antigo} e {real} existem os dois em {label} — não mexi. Decida qual fica."
                if politica == "recusar"
                else (
                    f"{label}.{field_name} é único e não tem política de colisão. "
                    f"Acrescente-a em POLITICA_DE_COLISAO antes de renomear {antigo}."
                )
            )

        return bloqueios, fusoes

    def _report(self, feitos, pulados, avisos, fusoes, *, alvo, dry_run):
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

        if fusoes:
            self.stdout.write(f"\n{len(fusoes)} anotação(ões) fundida(s):")
            for f in fusoes:
                self.stdout.write(f"  {f}")

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
