"""Instala só o dado de referência que as leituras novas do B.I. precisam.

O `seed` completo popula um ambiente vazio, e faz isso muito bem — mas rodá-lo
num ambiente que já tem operação de verdade injeta venda de demonstração
(pedidos, sessões, pagamentos, fechamentos, 5.748 pedidos de volume) junto com o
que se queria instalar. A leitura do B.I. passaria a somar operação real com
operação inventada, que é exatamente o defeito que a guarda do histórico
sintético existe para evitar — só que do lado nativo.

Este comando faz o recorte: **cinco tabelas de referência, zero movimento.**

- papéis de consumo (o vocabulário: consome aqui · leva · híbrido)
- etiquetas por SKU (a curadoria do cardápio, `reviewed=True`)
- lugares do salão (o denominador da ociosidade)
- de-paras de categoria e de forma de pagamento do histórico (os vocabulários
  do B.I., confirmados — mapeamento é dado, não código)

Nenhuma delas é fato operacional: são cadastro. Reinstalar não reescreve
passado, não cria venda e não apaga nada — tudo é `update_or_create`, então
rodar duas vezes é igual a rodar uma.

⚠️ **O que ele NÃO faz:** a taxonomia de coleções (extinguir "Balcão", renomear
"Despensa" para "Mercearia", criar "Combos") mora dentro do `_seed_catalog`, que
é grande demais para recortar aqui. O B.I. não depende dela — a etiqueta é
chaveada por SKU, não por coleção —, então ela pode esperar um reseed completo
ou ser feita no Admin.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Instala papéis de consumo, etiquetas por SKU, lugares do salão e os de-paras "
        "de categoria/forma de pagamento (sem tocar em operação)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Mostra o que existe hoje e o que seria instalado, sem gravar.",
        )

    def handle(self, *args, **options):
        from shopman.backstage.models import (
            CategoryAlias,
            ConsumptionRole,
            PaymentMethodAlias,
            ProductConsumptionTag,
            SeatingSpot,
        )

        from .seed import Command as Seed

        models = (ConsumptionRole, ProductConsumptionTag, SeatingSpot, CategoryAlias, PaymentMethodAlias)
        before = self._counts(*models)

        if options["dry_run"]:
            self.stdout.write("Hoje no banco:")
            self._report(before)
            self.stdout.write(
                "\n(--dry-run: nada gravado. Sem o --dry-run, o comando instala o "
                "vocabulário, a curadoria do cardápio, os lugares do salão e os de-paras.)"
            )
            return

        # A fonte é o próprio seed: uma curadoria, um lugar. Duplicar a lista
        # aqui garantiria que as duas divergissem no primeiro produto novo.
        seed = Seed()
        seed.stdout = self.stdout
        seed.style = self.style
        seed._seed_consumption_roles()
        seed._seed_consumption_tags()
        seed._seed_seating()
        seed._seed_bi_aliases()

        after = self._counts(*models)
        self.stdout.write(self.style.SUCCESS("\nInstalado:"))
        self._report(after, before)
        self.stdout.write(
            "\nNenhum pedido, sessão, pagamento ou movimento de estoque foi tocado."
        )
        pending = ProductConsumptionTag.objects.filter(reviewed=False).count()
        if pending:
            self.stdout.write(self.style.WARNING(
                f"⚠️ {pending} etiqueta(s) seguem como proposta não revisada — "
                "confira em Admin → Como vendemos → Etiquetas de consumo."
            ))

    def _counts(self, role_model, tag_model, spot_model, category_model, payment_model) -> dict:
        return {
            "papéis de consumo": role_model.objects.count(),
            "etiquetas por SKU": tag_model.objects.count(),
            "lugares do salão": spot_model.objects.count(),
            "lugares na capacidade oficial": spot_model.objects.filter(
                counts_in_capacity=True
            ).count(),
            "de-paras de categoria": category_model.objects.count(),
            "de-paras de forma de pagamento": payment_model.objects.count(),
        }

    def _report(self, counts: dict, before: dict | None = None) -> None:
        for label, value in counts.items():
            delta = ""
            if before is not None:
                diff = value - before[label]
                delta = f"  (+{diff})" if diff else "  (sem mudança)"
            self.stdout.write(f"  {label:<32} {value:>4}{delta}")
