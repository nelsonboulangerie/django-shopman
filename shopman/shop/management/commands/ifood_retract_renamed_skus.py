"""Retira do iFood os itens que ficaram órfãos pelo rename de SKU (F5).

**Por que isto existe.** O id do item no iFood é derivado do NOSSO SKU:
``uuid5(merchant_id, "item:" + sku)`` (ver ``catalog_projection_ifood``). Trocar
``CROISSANT`` por ``CT`` muda o uuid — o próximo sync cria um item novo, e o
antigo **continua no cardápio deles, disponível para venda**, apontando para um
SKU que não existe mais aqui. Pedido nesse item chega e não resolve produto.

O `sync_catalog_ifood` incremental não resolve: ele reconcilia o que ESTÁ na
listagem, e o SKU antigo saiu dela. Quem sabe o nome antigo é o mapa do rename,
e é dele que este comando parte.

**A ordem importa, e o comando a protege:** rode DEPOIS do rename. Antes, o SKU
antigo ainda é o produto vivo, e retirá-lo derrubaria o cardápio. Por isso o
comando recusa retirar SKU que ainda existe no catálogo.

Depois deste, rode `sync_catalog_ifood --full` para publicar os códigos novos.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

CANAL = "ifood"


class Command(BaseCommand):
    help = "Retira do iFood os itens dos SKUs antigos, órfãos após o rename."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Mostra o que retiraria, sem chamar a API do iFood.",
        )

    def handle(self, *args, **options):
        from shopman.offerman.conf import get_projection_backend
        from shopman.offerman.models import Product

        from config.management.commands.rename_skus_to_real import RENAMES

        vivos = set(Product.objects.values_list("sku", flat=True))
        antigos = [antigo for antigo, _real in RENAMES]

        ainda_vivos = sorted(sku for sku in antigos if sku in vivos)
        if ainda_vivos:
            raise CommandError(
                f"{len(ainda_vivos)} SKU(s) antigos ainda existem no catálogo: "
                f"{', '.join(ainda_vivos[:6])}"
                f"{'…' if len(ainda_vivos) > 6 else ''}. "
                "Rode `rename_skus_to_real` primeiro — retirá-los agora tiraria "
                "do ar produto que está vendendo."
            )

        # Só faz sentido retirar o que o rename de fato trocou: se o código novo
        # não está no catálogo, o rename não rodou para aquele par.
        orfaos = [antigo for antigo, real in RENAMES if real in vivos]
        if not orfaos:
            self.stdout.write(self.style.SUCCESS("Nada a retirar."))
            return

        if options["dry_run"]:
            self.stdout.write(
                f"Retiraria {len(orfaos)} item(ns) do iFood (o uuid de cada um sai "
                "do SKU antigo):"
            )
            for antigo, real in RENAMES:
                if real in vivos:
                    self.stdout.write(f"  {antigo:<20} (hoje é {real})")
            self.stdout.write("\n(--dry-run: nada chamado na API)")
            return

        backend = get_projection_backend(CANAL)
        if backend is None:
            raise CommandError(
                "Nenhum backend de projeção configurado para 'ifood'. "
                "Sem credencial, não há o que retirar."
            )

        resultado = backend.retract(orfaos, channel=CANAL)
        if resultado.errors:
            self.stdout.write(self.style.WARNING(
                f"\n{len(resultado.errors)} erro(s):"
            ))
            for erro in resultado.errors[:20]:
                self.stdout.write(f"  {erro}")
        self.stdout.write(self.style.SUCCESS(
            f"\n{resultado.projected} de {len(orfaos)} item(ns) retirados do iFood."
        ))
        self.stdout.write(
            "Agora rode `sync_catalog_ifood --full` para publicar os códigos novos."
        )
