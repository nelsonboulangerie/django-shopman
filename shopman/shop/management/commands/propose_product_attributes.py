"""Propõe natureza, sabor e temperatura por SKU, a partir das coleções.

Os três atributos nascem vazios, e preencher 200 produtos à mão é a diferença
entre a coisa acontecer e não acontecer. A coleção já é a taxonomia da casa: se
o produto mora em "Bebidas quentes", sua natureza é bebida e sua temperatura é
quente, e nenhum humano precisa digitar isso.

⚠️ **Proposta não é curadoria.** Tudo o que este comando escreve sai com
``source="derived"`` e ``reviewed=False``, e o gestor revisa no painel do
produto. Valor que já foi escrito por gente (``source="manual"``) **nunca** é
sobrescrito — rodar de novo é seguro.

A coleção PRIMÁRIA manda. Um croissant recheado é Folhados e também é Doces; a
primeira aparição é onde ele mora (regra do dono, 02/09) e é dela que a proposta
sai — senão a ordem alfabética decidiria o sabor do cardápio.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

# Coleção → (natureza, sabor, temperatura). Visível de propósito: é regra de
# negócio, e quem discordar tem de conseguir apontar a linha.
#
# ``None`` significa "a coleção não responde essa pergunta" — e aí o atributo
# fica em branco, esperando gente. É diferente de propor "neutro": ausência de
# dado é ausência de dado.
COLLECTION_ATTRIBUTES: dict[str, dict[str, str | None]] = {
    "bebidas-quentes": {"natureza": "bebida", "sabor": None, "temperatura": "quente"},
    "bebidas-geladas": {"natureza": "bebida", "sabor": None, "temperatura": "gelado"},
    # Pão é comida de sabor neutro: a baguete não é doce nem salgada, é a base
    # sobre a qual as duas acontecem. É o que faz "pão pede café" e "pão pede
    # manteiga" valerem sem que o motor precise de exceção.
    "rusticos": {"natureza": "comida", "sabor": "neutro", "temperatura": "ambiente"},
    "macios": {"natureza": "comida", "sabor": "neutro", "temperatura": "ambiente"},
    # A massa laminada manda na coleção, mas não no sabor: há folhado doce e
    # folhado salgado na mesma prateleira. Sabor fica para a curadoria.
    "folhados": {"natureza": "comida", "sabor": None, "temperatura": "ambiente"},
    # "Salgados" na Nelson é prato quente servido no prato — croque, queijo
    # quente, pain grillé (correção do dono, 17/08).
    "salgados": {"natureza": "comida", "sabor": "salgado", "temperatura": "quente"},
    "doces": {"natureza": "comida", "sabor": "doce", "temperatura": "ambiente"},
    # Mercearia é a coleção que a coleção não resolve: manteiga e geleia se
    # comem COM o pão (acompanhamento), café em grão e chá em lata saem pela
    # porta (outro). As palavras-chave desempatam — ver ACCOMPANIMENT_KEYWORDS.
    "mercearia": {"natureza": None, "sabor": None, "temperatura": "ambiente"},
    # Combo não tem natureza própria: herda a dos componentes. Propor uma seria
    # inventar. Fica para a curadoria, que é onde ele já está.
    "combos": {"natureza": None, "sabor": None, "temperatura": None},
}

# Palavra-chave que faz um item de mercearia ser algo que se come COM o pão.
ACCOMPANIMENT_KEYWORDS = frozenset({
    "geleia", "mostarda", "tapenade", "pate", "queijo", "picles", "bacon", "manteiga",
})

DERIVED_REFS = ("natureza", "sabor", "temperatura")


class Command(BaseCommand):
    help = "Propõe natureza, sabor e temperatura a partir das coleções (revisar no Admin)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Mostra o que faria, sem gravar.",
        )
        parser.add_argument(
            "--overwrite-derived", action="store_true",
            help=(
                "Reescreve propostas anteriores (source=derived). O que o gestor "
                "escreveu à mão continua intocado, sempre."
            ),
        )

    def handle(self, *args, **options):
        from shopman.offerman.models import Product

        from shopman.shop.services import attributes

        dry_run = options["dry_run"]
        overwrite = options["overwrite_derived"]

        missing = [ref for ref in DERIVED_REFS if attributes.definition(ref) is None]
        if missing:
            self.stderr.write(
                self.style.ERROR(
                    f"Atributos ausentes ou inativos no registro: {', '.join(missing)}. "
                    "Rode as migrações do shop antes."
                )
            )
            return

        products = (
            Product.objects.filter(is_published=True, is_sellable=True)
            .prefetch_related("collection_items__collection", "keywords")
            .order_by("sku")
        )

        written = 0
        kept = 0
        unresolved: list[str] = []

        for product in products:
            proposal = self._propose(product)
            if not proposal:
                unresolved.append(product.sku)
                continue

            dirty = False
            for ref, value in proposal.items():
                current = attributes.get(product, ref)
                if current is not None:
                    is_derived = attributes.source(product, ref) == "derived"
                    if not (is_derived and overwrite):
                        kept += 1
                        continue
                    if current == value:
                        kept += 1
                        continue
                attributes.set(
                    product, ref, value,
                    source="derived", reviewed=False, save=False,
                )
                dirty = True
                written += 1

            if dirty and not dry_run:
                product.save(update_fields=["metadata"])

        for sku in unresolved:
            self.stdout.write(f"  sem coleção que responda: {sku}")

        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}{written} valor(es) propostos, {kept} preservado(s), "
            f"{len(unresolved)} produto(s) sem proposta."
        ))
        if written and not dry_run:
            self.stdout.write(
                "Revise em Admin → Atributos de produto; tudo saiu como proposta."
            )

    def _propose(self, product) -> dict[str, str]:
        """Os atributos que a coleção primária de ``product`` sabe responder."""
        primary = next(
            (item.collection for item in product.collection_items.all() if item.is_primary),
            None,
        )
        if primary is None:
            return {}

        mapping = COLLECTION_ATTRIBUTES.get(primary.ref)
        if mapping is None:
            return {}

        proposal = {ref: value for ref, value in mapping.items() if value is not None}

        if primary.ref == "mercearia":
            keywords = {k.lower() for k in product.keywords.names()}
            proposal["natureza"] = (
                "acompanhamento" if keywords & ACCOMPANIMENT_KEYWORDS else "outro"
            )

        return proposal
