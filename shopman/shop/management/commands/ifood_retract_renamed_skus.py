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


def _mapa_de_renames() -> dict[str, str]:
    """Todo par (código que foi nosso → código que ele virou), das duas levas.

    Lia só o `rename_skus_to_real` (os inventados do seed → os do Yooga). O
    `apply_product_skus` é a leva seguinte (os do Yooga → os curados) e deixa o
    MESMO tipo de órfão: o uuid do item sai do nosso SKU, então trocar o SKU
    cria item novo e deixa o antigo vendável no cardápio deles. Ler um mapa só
    não dava erro nenhum — deixava item órfão no cardápio de outra casa, que é o
    pior formato possível para uma falha.
    """
    from config.management.commands.apply_product_skus import RENAMES as CURADOS
    from config.management.commands.rename_skus_to_real import RENAMES as REAIS

    return dict(tuple(REAIS) + tuple(CURADOS))


def _orfaos_no_ifood(vivos: set[str]) -> list[str]:
    """Códigos que já foram nossos, hoje não são, e levam a produto que existe.

    As duas levas **se encadeiam**: `BAGUETE` virou `BF`, que virou `TRADI`.
    Quem olhasse só o par cru não acharia `BAGUETE`, porque `BF` já não está no
    catálogo — e o item mais antigo ficaria no cardápio deles para sempre.

    E elas chegam a **voltar**: `FENDU` virou `FE` em agosto, e a curadoria de
    setembro devolve `FE` a `FENDU`. Resolver a cadeia no papel daria um ciclo,
    e qualquer desempate seria chute — o que decide é o catálogo: a caminhada
    para quando chega num código que EXISTE hoje. Assim `FE` sai (virou órfão) e
    `FENDU` fica (é o produto vivo), sem ninguém escolher nada.
    """
    destino = _mapa_de_renames()
    orfaos: list[str] = []
    for antigo in destino:
        if antigo in vivos:
            continue  # ainda é o produto vivo: não há órfão nenhum
        atual, visitados = destino[antigo], {antigo}
        while atual not in vivos and atual in destino and atual not in visitados:
            visitados.add(atual)
            atual = destino[atual]
        if atual in vivos:
            orfaos.append(antigo)
    return sorted(orfaos)


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

        vivos = set(Product.objects.values_list("sku", flat=True))
        destino = _mapa_de_renames()

        ainda_vivos = sorted(sku for sku in destino if sku in vivos)
        if ainda_vivos:
            raise CommandError(
                f"{len(ainda_vivos)} SKU(s) antigos ainda existem no catálogo: "
                f"{', '.join(ainda_vivos[:6])}"
                f"{'…' if len(ainda_vivos) > 6 else ''}. "
                "Rode o rename primeiro (`rename_skus_to_real` ou "
                "`apply_product_skus --apply`) — retirá-los agora tiraria do ar "
                "produto que está vendendo."
            )

        orfaos = _orfaos_no_ifood(vivos)
        if not orfaos:
            self.stdout.write(self.style.SUCCESS("Nada a retirar."))
            return

        if options["dry_run"]:
            self.stdout.write(
                f"Retiraria {len(orfaos)} item(ns) do iFood (o uuid de cada um sai "
                "do SKU antigo):"
            )
            for antigo in orfaos:
                self.stdout.write(f"  {antigo:<20} (o produto hoje é outro código)")
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
