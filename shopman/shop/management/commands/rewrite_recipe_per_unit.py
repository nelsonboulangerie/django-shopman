"""Reexpressa a ficha de produto por unidade num banco que já roda.

Uso::

    python manage.py rewrite_recipe_per_unit
    python manage.py rewrite_recipe_per_unit --apply
    python manage.py rewrite_recipe_per_unit baguete batard --apply

**Por que este comando existe.** A ficha da baguete dizia "7 kg de Massa
Tradição rendem 25 un". O 25 não é propriedade da baguete: é quanto se decidiu
fazer naquele dia. A ficha de produto passa a dizer o que entra em UMA peça —
``batch_size = 1``, ``MASSA-TRADICAO 0,280 kg`` (WP-FICHA-DE-PRODUTO-E-PROMESSA
§A). O ``seed`` já nasce assim; este comando é o mesmo gesto num banco povoado,
onde ``Recipe.batch_size`` e as quantidades já estão gravados.

**É reexpressão, não mudança.** O consumo é sempre ``quantidade planejada ÷
batch_size × quantidade do item``, e dividir os dois lados pelo mesmo número não
mexe na razão: 40 baguetes consomem 11,2 kg de massa antes e depois. Nenhum
movimento de estoque nasce daqui, nenhum custo muda, nenhuma nutrição
recalculada dá outro número.

A régua é **o que a ficha rende**, declarado (catálogo ou ``meta["output_unit"]``,
nunca deduzido): rende unidade, é produto e vira por unidade; rende massa, é
fórmula e não se toca. Fórmula por unidade não faz sentido — 1 kg de Massa
Tradição não é "uma" de nada.

O que ele **não** toca, de propósito
------------------------------------

* **fornada concluída ou cancelada**. História não se reescreve: o consumo dela
  já virou movimento no ledger, e o padeiro leu no dia o que leu;
* **fornada aberta**, porque ela já está protegida: o
  ``WorkOrder.meta["_recipe_snapshot"]`` congela ``batch_size`` **e** os itens
  JUNTOS no planejamento, e os três consumidores (o ``finish``, a pesagem e a
  checagem de insumo) leem os dois do mesmo snapshot. A razão congelada já é
  coerente, então reexpressá-la não mudaria conta nenhuma — e mexer ali seria
  reescrever o que o padeiro está com a etiqueta na mão lendo agora.

  A exceção é o snapshot **quebrado pela metade**: com itens congelados e sem
  ``batch_size``, a pesagem cai no rendimento VIVO (é o defeito que a
  ``_work_order_recipe`` documenta), e aí a reexpressão cortaria os pesos. Esse
  o comando conserta pela preservação: grava no snapshot o ``batch_size`` que a
  ficha tem AGORA, que é exatamente o que aquela fornada já estava lendo.

* **o livro de receitas** (``RecipeEntry``/``RecipeVersion``). Versão publicada é
  história por contrato (a ``origin`` é imutável). O comando **relata** as entries
  cuja versão atual ainda fala o rendimento antigo: republicar uma delas
  reescreveria a ficha de volta para o rendimento de lote, e quem executa precisa
  saber disso antes de acontecer.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from shopman.utils import units

#: Casas decimais de ``Recipe.batch_size`` e ``RecipeItem.quantity``.
_QUANT_EXP = Decimal("0.001")

_UM = Decimal("1")

#: Status de fornada que ainda vai consumir insumo. As demais são história.
_FORNADAS_ABERTAS = ("planned", "started")


class Command(BaseCommand):
    help = "Reexpressa por unidade as fichas de produto que rendem unidade."

    def add_arguments(self, parser):
        parser.add_argument(
            "refs", nargs="*",
            help="Refs das fichas (ex.: baguete batard). Sem nenhuma, varre todas.",
        )
        parser.add_argument(
            "--apply", action="store_true",
            help="Executa. Sem esta flag o comando só relata o que faria.",
        )

    def handle(self, *args, **options):
        Recipe = apps.get_model("craftsman", "Recipe")
        aplicar = options["apply"]

        fichas = Recipe.objects.all().order_by("ref")
        if options["refs"]:
            fichas = fichas.filter(ref__in=options["refs"])
            faltando = set(options["refs"]) - set(fichas.values_list("ref", flat=True))
            if faltando:
                raise CommandError(f"Ficha não encontrada: {', '.join(sorted(faltando))}.")

        self.stdout.write(self.style.MIGRATE_HEADING("\nFicha de produto por unidade\n"))

        recusas: list[str] = []
        reexpressas = 0
        rendem_massa = 0
        ja_por_unidade = 0
        sem_unidade: list[str] = []

        with transaction.atomic():
            for ficha in fichas:
                dimensao = units.dimension(ficha._declared_output_unit())
                if not dimensao:
                    # Unidade da saída não declarada: a régua não existe, e
                    # deduzir seria adivinhar (ADR-024 §R4). Sai relatada.
                    sem_unidade.append(ficha.ref)
                    continue
                if dimensao != units.COUNT:
                    rendem_massa += 1
                    continue
                if ficha.batch_size == _UM:
                    ja_por_unidade += 1
                    continue

                linhas, problemas = self._reexpressar(ficha)
                for linha in linhas:
                    self.stdout.write(linha)
                recusas.extend(problemas)
                if not problemas:
                    reexpressas += 1

            if recusas:
                transaction.set_rollback(True)
                for problema in recusas:
                    self.stdout.write(self.style.ERROR(f"  ⛔ {problema}"))
                raise CommandError(
                    "Nada foi gravado: alguma ficha não sobrevive à reexpressão. "
                    "Acerte as quantidades acima e rode de novo."
                )

            self.stdout.write("")
            self.stdout.write(
                f"  {reexpressas} ficha(s) reexpressa(s); {ja_por_unidade} já por unidade; "
                f"{rendem_massa} rendem massa e ficaram como estão."
            )
            if sem_unidade:
                self.stdout.write(self.style.WARNING(
                    f"  ⚠️  {len(sem_unidade)} ficha(s) sem unidade de saída declarada, fora da "
                    f"varredura (declare no catálogo ou em meta[\"output_unit\"]): "
                    f"{', '.join(sem_unidade)}"
                ))
            for linha in self._relatar_livro_de_receitas():
                self.stdout.write(linha)

            if not aplicar:
                transaction.set_rollback(True)
                self.stdout.write(
                    self.style.WARNING("\n  ⚠️  Ensaio — nada foi gravado. Repita com --apply.\n")
                )
                return

        self.stdout.write(self.style.SUCCESS("\n  ✅ Reexpressão gravada.\n"))

    # ────────────────────────────────────────────────────────────────────
    # Uma ficha
    # ────────────────────────────────────────────────────────────────────
    def _reexpressar(self, ficha) -> tuple[list[str], list[str]]:
        """Divide rendimento e itens pelo rendimento antigo. Devolve (relato, recusas)."""
        rendimento = Decimal(str(ficha.batch_size))
        relato = [self.style.MIGRATE_LABEL(f"\n{ficha.ref} — {ficha.name}")]
        relato.append(f"  rendimento: {_numero(rendimento)} → 1")

        itens = list(ficha.items.all().order_by("sort_order"))
        recusas: list[str] = []
        novos: list[tuple[object, Decimal]] = []
        for item in itens:
            exata = Decimal(str(item.quantity)) / rendimento
            nova = exata.quantize(_QUANT_EXP, rounding=ROUND_HALF_UP)
            if nova <= 0:
                recusas.append(
                    f"{ficha.ref}: {item.input_sku} sai de {_numero(item.quantity)} {item.unit} "
                    f"por lote para {_numero(exata)} por unidade, que arredonda a zero em três "
                    "casas. Uma linha da ficha não pode virar nada: declare o insumo em grama, "
                    "ou revise o rendimento antes de reexpressar."
                )
                continue
            desvio = abs(exata - nova)
            marca = f"   (arredondado, desvio de {_numero(desvio)} {item.unit} por unidade)" if desvio else ""
            relato.append(
                f"    {item.input_sku}: {_numero(item.quantity)} → {_numero(nova)} {item.unit}{marca}"
            )
            novos.append((item, nova))

        if recusas:
            return relato, recusas

        relato.extend(self._congelar_fornadas_abertas(ficha, rendimento))
        relato.extend(self._contar_fornadas_fechadas(ficha))

        for item, nova in novos:
            item.quantity = nova
            item.save(update_fields=["quantity"])
        ficha.batch_size = _UM
        ficha.save(update_fields=["batch_size", "updated_at"])
        return relato, []

    def _congelar_fornadas_abertas(self, ficha, rendimento: Decimal) -> list[str]:
        """Fornada aberta não muda; só a de snapshot pela metade é preservada.

        O snapshot congela rendimento e itens juntos, então a fornada aberta já
        lê uma razão coerente e a reexpressão passa por ela sem tocar em nada.
        O caso que precisa de gesto é o snapshot com itens e SEM ``batch_size``:
        esse cai no rendimento vivo, e a reexpressão cortaria os pesos da
        pesagem. Grava-se nele o rendimento que a ficha tem agora — é o número
        que aquela fornada já estava usando, escrito onde ela vai continuar
        lendo.
        """
        WorkOrder = apps.get_model("craftsman", "WorkOrder")
        abertas = list(
            WorkOrder.objects.filter(recipe=ficha, status__in=_FORNADAS_ABERTAS)
        )
        if not abertas:
            return []

        remendadas = []
        for fornada in abertas:
            meta = fornada.meta if isinstance(fornada.meta, dict) else {}
            snapshot = meta.get("_recipe_snapshot")
            if not isinstance(snapshot, dict) or not snapshot.get("items"):
                # Sem snapshot a fornada lê a ficha VIVA inteira (rendimento e
                # itens), então a razão dela acompanha a reexpressão sozinha.
                continue
            if snapshot.get("batch_size"):
                continue
            snapshot["batch_size"] = str(rendimento)
            fornada.meta = {**meta, "_recipe_snapshot": snapshot}
            fornada.save(update_fields=["meta", "updated_at"])
            remendadas.append(fornada.ref)

        linhas = [
            f"    {len(abertas)} fornada(s) aberta(s): a razão delas já está congelada no "
            "snapshot; nenhuma foi reescrita."
        ]
        if remendadas:
            linhas.append(
                f"    {len(remendadas)} delas tinham snapshot sem rendimento e receberam o de "
                f"agora ({_numero(rendimento)}), para a pesagem não mudar: {', '.join(remendadas)}"
            )
        return linhas

    def _contar_fornadas_fechadas(self, ficha) -> list[str]:
        WorkOrder = apps.get_model("craftsman", "WorkOrder")
        fechadas = WorkOrder.objects.filter(recipe=ficha).exclude(status__in=_FORNADAS_ABERTAS).count()
        if not fechadas:
            return []
        return [f"    {fechadas} fornada(s) concluída(s) ou cancelada(s): história, intocadas."]

    # ────────────────────────────────────────────────────────────────────
    # O livro de receitas
    # ────────────────────────────────────────────────────────────────────
    def _relatar_livro_de_receitas(self) -> list[str]:
        """Relata a entry cuja versão atual ainda fala o rendimento de lote.

        Publicar uma versão escreve ``Recipe.batch_size = version.yield_quantity``:
        uma versão publicada com o rendimento antigo desfaria esta reexpressão no
        dia em que alguém apertar "Publicar". Não se reescreve versão publicada
        (a ``origin`` é imutável por contrato), então o que resta é dizer o nome
        de cada uma.
        """
        try:
            RecipeEntry = apps.get_model("craftsman", "RecipeEntry")
        except LookupError:
            return []

        pendentes = []
        entries = (
            RecipeEntry.objects.exclude(current_version=None)
            .select_related("current_version")
            .order_by("ref")
        )
        for entry in entries:
            versao = entry.current_version
            if units.dimension(versao.yield_unit) != units.COUNT:
                continue
            if Decimal(str(versao.yield_quantity)) == _UM:
                continue
            pendentes.append(f"{entry.ref}@{versao.number} (rende {_numero(versao.yield_quantity)})")

        if not pendentes:
            return []
        return [
            "",
            self.style.WARNING(
                f"  ⚠️  {len(pendentes)} versão(ões) do livro de receitas ainda falam o rendimento "
                "de lote. Publicar qualquer uma reescreve a ficha de volta:"
            ),
            *[f"      {linha}" for linha in pendentes],
            "      Versão publicada é história e não se reescreve: crie uma versão nova por "
            "unidade, ou refaça o bootstrap da entry.",
        ]


def _numero(valor) -> str:
    """Decimal sem zeros à direita, na vírgula da casa."""
    texto = format(Decimal(str(valor)).normalize(), "f")
    return texto.replace(".", ",")
