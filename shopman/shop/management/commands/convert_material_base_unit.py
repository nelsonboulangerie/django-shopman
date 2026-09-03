"""Troca a unidade-base de um insumo num banco que já roda, convertendo tudo junto.

Uso::

    python manage.py convert_material_base_unit LEITE AZEITE --to kg
    python manage.py convert_material_base_unit LEITE AZEITE --to kg --apply

**Por que este comando existe.** A ADR-024 (R1) diz que a unidade-base de um
insumo é a do momento da verdade: se a casa pesa, ``kg``. Descobrir tarde que um
insumo nasceu no eixo errado é normal, e a correção não pode ser "editar o
``Material.unit`` no Admin": o número do saldo, do movimento, da reserva, da
ficha e do custo continuariam valendo o que valiam na unidade antiga, e o
sistema inteiro passaria a ler litro como se fosse quilo. Trocar a base é uma
conversão de **todo o rastro daquele insumo**, na mesma transação, ou não é nada.

O ``seed`` não serve para isso: ele é bootstrap e reescreve estoque, pedidos e
configuração — num banco vivo isso é destrutivo. Este comando é o recorte
oposto, o mesmo do ``apply_product_measurements`` e do ``merge_suppliers``: toca
o rastro de um insumo e nada mais.

**Por que ele mora no ``shop``.** Ele orquestra quatro pacotes que não se
importam entre si (``buyman``, ``stockman``, ``craftsman`` e o que a varredura
alcançar), e é genérico: não conhece SKU nenhum da Nelson e não tem tabela de
densidade embutida — lê tudo do cadastro. Comando de dado do deployment (o
``seed``, o ``refresh_seed_dates``, o ``rename_skus_to_real``) mora em
``config/management/commands/``; orquestração cross-pacote mora aqui, ao lado do
``merge_suppliers``, que tem exatamente a mesma natureza.

O fator
-------

Da unidade atual para a alvo, e só existem três casos:

- **mesma dimensão** (kg↔g, l↔ml): é física, sai de :mod:`shopman.utils.units`.
  Não tem autor, não vira linha de tabela, não pede cadastro;
- **volume ↔ massa** (o caso real, ``l`` → ``kg``): pela ``density_g_per_ml``
  declarada em ``Material.metadata``. É a ponte aproximada da ADR-024, e é por
  isso que ela deixa um ``MaterialConversion`` da unidade antiga para trás;
- **contagem ↔ qualquer coisa**: não existe caminho, e o comando recusa. Não há
  ponte definicional entre "6 ovos" e "300 g" — essa ponte é declarada por
  insumo, e trocar a base por cima dela seria inventar o fator.

Sem densidade declarada o comando **recusa nomeando o que cadastrar** (R4): o
dado que falta grita no gesto, não vira default silencioso três telas adiante.
De propósito **não existe** ``--density`` na linha de comando: o fator tem de
estar no cadastro, com autor, senão a próxima nota fiscal não tem de onde ler.

O que ele converte
------------------

Multiplicam pelo fator (a mesma quantidade física, dita na unidade nova):

- ``stockman.Move.delta`` — o ledger, primeiro;
- ``stockman.Quant._quantity`` — recalculado a partir do ledger já convertido
  (ver :meth:`_converter_saldos`);
- ``stockman.Hold.quantity`` — reserva é saldo comprometido;
- ``stockman.StockAlert.min_quantity`` e
  ``buyman.Material.metadata["purchase"]["min_stock"]`` — os dois limiares são
  política dita em quantidade ("avise abaixo de 20 L", "peça abaixo de 20 L").
  Não convertê-los mudaria a política do dono em silêncio, que é exatamente o
  oposto do que a R3 quer;
- ``craftsman.RecipeItem.quantity`` **e** ``.unit``, porque ``RecipeItem.clean``
  exige a unidade do cadastro: ficha não convertida deixa de validar;
- ``craftsman.WorkOrder.meta["_recipe_snapshot"]`` e
  ``craftsman.WorkOrderItem`` das fornadas **abertas** (``planned``/``started``);
- ``buyman.MaterialConversion.to_base_factor``, que diz quanto uma embalagem
  vale **na base** — mudou a base, mudou o fator.

Divide pelo fator:

- ``buyman.SupplierMaterialCost.cost_q`` **quando a compra é na própria base**
  (``conversion`` vazio). Aí o centavo é por unidade-base: se 1 L custava
  R$ 5,00 e 1 L vale 1,03 kg, o quilo custa 5,00 ÷ 1,03. Quando a linha aponta
  para uma conversão, o ``cost_q`` é o preço de UMA embalagem (o número da nota)
  e não muda — quem muda é o fator daquela conversão, já convertido acima.

O que ele **não** reescreve, de propósito:

- **fornada concluída ou cancelada**. História não se reescreve: ela contou no
  que contava, e o consumo dela já virou movimento no ledger (que foi
  convertido). Mexer no snapshot de uma WO fechada mudaria o que o padeiro leu
  no dia.

Fecha criando o ``MaterialConversion`` da unidade **antiga** quando a troca
atravessou dimensão ("litro" = 1,03 kg, ``approximate``), para a próxima nota em
litro não travar (R4) — e varrendo o banco atrás de qualquer outro modelo que
guarde quantidade daquele SKU, para **relatar** o que não tocou. Relatar de
menos convertido é melhor do que converter escondido.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import models, transaction
from shopman.utils import units

#: Casas decimais dos campos de quantidade tocados (``DecimalField(decimal_places=3)``).
_QUANT_EXP = Decimal("0.001")

#: Casas decimais de ``MaterialConversion.to_base_factor``.
_FACTOR_EXP = Decimal("0.000001")

#: Modelos que guardam quantidade por SKU e que este comando **não** converte,
#: com o campo de ref para poder CONTAR as linhas afetadas. É o "relate o que
#: não tocou" da ADR-024 aplicado a este gesto: número convertido escondido é
#: pior do que número não convertido anunciado.
#: Formato: (app_label, modelo, campo de ref, campo de quantidade, filtro extra,
#: motivo). O filtro extra recorta o que ficou de fora do que já foi convertido.
_NAO_CONVERTIDOS: tuple[tuple[str, str, str, str, dict, str], ...] = (
    (
        "craftsman", "WorkOrderItem", "item_ref", "quantity",
        {"work_order__status__in": ["finished", "void"]},
        "de fornada já concluída ou cancelada — história não se reescreve",
    ),
    (
        "offerman", "Product", "sku", "unit", {},
        "existe um PRODUTO com este mesmo SKU, e é a unidade DELE que a ficha "
        "técnica confere (ComposedCatalogBackend dá precedência ao produto). "
        "Acerte a colisão de namespace antes de publicar ficha",
    ),
)

#: Guardas de quantidade que moram em JSONField e que este comando não varre
#: linha a linha — ou porque são história por contrato, ou porque o schema é
#: livre demais para uma busca automática não errar. Ficam anunciados sempre,
#: sem contagem, para quem executa saber onde olhar.
#: Formato: (onde, motivo).
_A_CONFERIR_A_MAO: tuple[tuple[str, str], ...] = (
    (
        'stockman.Move.metadata["purchase_base_qty"] / ["converted_via"]',
        "é a PROVA de como a nota foi convertida no dia do recebimento. O delta "
        "do movimento foi reexpresso; esta prova continua contando o gesto "
        "original, e reescrevê-la apagaria o que de fato foi digitado",
    ),
    (
        "craftsman.RecipeVersion.formula / .origin",
        "versão publicada da ficha é história do livro de receitas (a origin é "
        "imutável por contrato). A ficha VIVA foi convertida; republique a "
        "versão se quiser a nova base no livro",
    ),
    (
        "backstage.DayClosing.data",
        "snapshot de fechamento é auditoria do dia — o número tem de continuar "
        "batendo com o que foi assinado",
    ),
    (
        "shop.RuleConfig.params",
        "schema livre por regra: se alguma regra ativa guarda quantidade deste "
        "insumo, só revisão humana enxerga",
    ),
)


class Command(BaseCommand):
    help = "Troca a unidade-base de um insumo e converte todo o rastro dele."

    def add_arguments(self, parser):
        parser.add_argument("skus", nargs="+", help="SKUs dos insumos (ex.: LEITE AZEITE)")
        parser.add_argument(
            "--to", dest="alvo", required=True,
            help="Unidade-base alvo (ex.: kg).",
        )
        parser.add_argument(
            "--apply", action="store_true",
            help="Executa. Sem esta flag o comando só relata o que faria.",
        )

    def handle(self, *args, **options):
        alvo = units.normalize(options["alvo"])
        aplicar = options["apply"]
        Material = apps.get_model("buyman", "Material")

        if alvo not in set(Material.Unit.values):
            validas = ", ".join(Material.Unit.values)
            raise CommandError(
                f"Unidade alvo desconhecida: '{options['alvo']}'. Válidas: {validas}."
            )

        self.stdout.write(self.style.MIGRATE_HEADING(f"\nUnidade-base alvo: {alvo}\n"))

        with transaction.atomic():
            for sku in options["skus"]:
                for linha in self._converter_insumo(sku, alvo):
                    self.stdout.write(linha)
            if not aplicar:
                transaction.set_rollback(True)
                self.stdout.write(
                    self.style.WARNING(
                        "\n  ⚠️  Ensaio — nada foi gravado. Repita com --apply.\n"
                    )
                )
                return
        self.stdout.write(self.style.SUCCESS("\n  ✅ Conversão gravada.\n"))

    # ────────────────────────────────────────────────────────────────────
    # Um insumo
    # ────────────────────────────────────────────────────────────────────
    def _converter_insumo(self, sku: str, alvo: str) -> list[str]:
        Material = apps.get_model("buyman", "Material")
        material = Material.objects.filter(sku=sku).first()
        if material is None:
            raise CommandError(f"Insumo não encontrado: {sku}")

        atual = units.normalize(material.unit)
        cabecalho = self.style.MIGRATE_LABEL(f"\n{material.sku} — {material.name}")

        if atual == alvo:
            return [cabecalho, f"  já está em '{alvo}'. Nada a fazer."]

        fator, aproximada, origem_do_fator = self._fator(material, atual, alvo)

        linhas = [
            cabecalho,
            f"  unidade: {atual} → {alvo}   ·   fator {fator} ({origem_do_fator})",
        ]
        linhas += self._converter_movimentos_e_saldos(sku, fator, atual, alvo)
        linhas += self._converter_reservas(sku, fator)
        linhas += self._converter_alertas(sku, fator)
        linhas += self._converter_fichas(material, sku, alvo)
        linhas += self._converter_fornadas_abertas(material, sku, alvo)
        linhas += self._converter_conversoes(material, fator)
        linhas += self._converter_custos(material, fator, atual, alvo)
        linhas += self._converter_minimo_de_compra(material, fator)

        material.unit = alvo
        material.save(update_fields=["unit", "metadata", "updated_at"])
        linhas.append(f"  Material.unit gravado como '{alvo}'")

        linhas += self._declarar_unidade_antiga(material, atual, fator, aproximada)
        linhas += self._varrer_o_resto(sku)
        return linhas

    # ────────────────────────────────────────────────────────────────────
    # O fator
    # ────────────────────────────────────────────────────────────────────
    def _fator(self, material, atual: str, alvo: str) -> tuple[Decimal, bool, str]:
        """Quanto vale UMA unidade atual na unidade alvo, e se atravessou dimensão.

        Devolve ``(fator, aproximada, explicação)``. Recusa, com o nome do que
        cadastrar, em vez de adivinhar (ADR-024, R4).
        """
        dim_atual = units.dimension(atual)
        dim_alvo = units.dimension(alvo)
        if not dim_atual:
            raise CommandError(
                f"{material.sku}: a unidade atual '{material.unit}' não está na "
                f"tabela de física. Conhecidas: {', '.join(units.known_units())}."
            )

        if dim_atual == dim_alvo:
            return units.convert(1, atual, alvo), False, "física, mesma dimensão"

        if units.COUNT in (dim_atual, dim_alvo):
            raise CommandError(
                f"{material.sku}: não existe caminho entre '{atual}' e '{alvo}' — "
                "contagem não vira peso nem volume por conversão de base. A ponte "
                "entre os dois é uma MaterialConversion declarada no insumo, e ela "
                "não substitui a unidade-base."
            )

        densidade = self._densidade(material)
        # Volume → massa: 1 unidade atual em ml, × densidade (g/ml) = gramas,
        # e a física leva grama até a unidade alvo. Massa → volume é o inverso,
        # pelo mesmo número declarado.
        if dim_atual == units.VOLUME:
            gramas = units.convert(1, atual, "ml") * densidade
            fator = units.convert(gramas, "g", alvo)
        else:
            mililitros = units.convert(1, atual, "g") / densidade
            fator = units.convert(mililitros, "ml", alvo)
        explicacao = f"densidade {densidade} g/ml declarada no cadastro, aproximada"
        return fator, True, explicacao

    def _densidade(self, material) -> Decimal:
        bruto = (material.metadata or {}).get("density_g_per_ml")
        try:
            densidade = Decimal(str(bruto))
        except (ArithmeticError, TypeError, ValueError):
            densidade = None
        if densidade is None or densidade <= 0:
            raise CommandError(
                f"{material.sku}: a troca atravessa volume e massa, e o insumo não "
                "tem densidade declarada. Cadastre "
                f"Material.metadata[\"density_g_per_ml\"] em '{material.sku}' "
                "(gramas por mililitro, ex.: 1.03 para leite) e rode de novo. "
                "O comando não adivinha densidade: o fator tem de ter autor."
            )
        return densidade

    # ────────────────────────────────────────────────────────────────────
    # Stockman
    # ────────────────────────────────────────────────────────────────────
    def _converter_movimentos_e_saldos(
        self, sku: str, fator: Decimal, atual: str, alvo: str
    ) -> list[str]:
        """Converte o ledger e reconstrói o cache de saldo a partir dele.

        O ``Move`` é imutável por desenho: a manager recusa ``update()``,
        ``save()`` com pk e ``delete()``. A recusa existe para impedir que
        alguém **corrija estoque** por trás do ledger — e não é isso que
        acontece aqui: nenhum fato novo é registrado, o mesmo fato passa a ser
        dito em outra unidade. Estornar e relançar seria pior: inventaria dois
        eventos econômicos que nunca aconteceram. Por isso a escrita passa por
        uma ``QuerySet`` crua, que não carrega a guarda da manager — é a única
        forma de reexprimir o ledger sem mentir sobre o que houve.

        Depois disso, o ``Quant._quantity`` (que é cache de Σ(moves.delta)) é
        **relido do ledger já convertido** — a mesma conta do
        ``Quant.recalculate``, feita aqui em vez de chamá-lo porque ele registra
        ``quant.quantity_mismatch`` em nível ERROR, e o que houve não foi
        divergência: foi esta conversão. Log que grita o nome errado ensina o
        operador a ignorar o log.

        Quant cujo cache **já** divergia do ledger antes da conversão não é
        relido: isso "consertaria" por tabela uma divergência de outra origem,
        escondendo-a. Esse é escalado proporcionalmente, mantendo a divergência
        do tamanho que tinha, e sai anunciado no relatório.
        """
        Quant = apps.get_model("stockman", "Quant")
        Move = apps.get_model("stockman", "Move")

        quants = list(Quant.objects.filter(sku=sku))
        if not quants:
            return ["  saldos e movimentos: nenhuma linha"]

        ids = [q.pk for q in quants]
        somas = self._somas_por_saldo(Move, ids)
        total_antes = sum((q.quantity for q in quants), Decimal("0"))

        movimentos = self._escalar_em_lote(
            self._crua(Move), {"quant_id__in": ids}, "delta", fator
        )

        depois_do_ledger = self._somas_por_saldo(Move, ids)
        recalculados = escalados = 0
        for quant in quants:
            if somas.get(quant.pk, Decimal("0")) == quant.quantity:
                quant._quantity = depois_do_ledger.get(quant.pk, Decimal("0"))
                recalculados += 1
            else:
                quant._quantity = _escala(quant.quantity, fator, _QUANT_EXP)
                escalados += 1
            quant.save(update_fields=["_quantity", "updated_at"])

        total_depois = sum(
            Quant.objects.filter(sku=sku).values_list("_quantity", flat=True),
            Decimal("0"),
        )
        linhas = [
            f"  movimentos (Move):        {movimentos} linha(s) reexpressas",
            f"  saldos (Quant):           {len(quants)} linha(s)   "
            f"{total_antes} {atual} → {total_depois} {alvo}",
        ]
        if escalados:
            linhas.append(
                f"    ⚠️  {escalados} saldo(s) já divergiam do ledger antes desta "
                "conversão e foram escalados proporcionalmente, mantendo a "
                "divergência. Rode 'recompute_quant_quantities' para auditá-los."
            )
        else:
            linhas.append(f"    {recalculados} saldo(s) recalculados a partir do ledger")
        return linhas

    def _converter_reservas(self, sku: str, fator: Decimal) -> list[str]:
        Hold = apps.get_model("stockman", "Hold")
        tocadas = self._escalar_em_lote(Hold.objects.all(), {"sku": sku}, "quantity", fator)
        return [f"  reservas (Hold):          {tocadas} linha(s)"]

    def _converter_alertas(self, sku: str, fator: Decimal) -> list[str]:
        """O limiar de mínimo é política dita em quantidade, e a política não muda.

        "Avise quando o leite cair abaixo de 20 L" continua sendo a mesma frase
        depois da troca — mas só se o número virar 20,6 kg. Deixá-lo em 20
        mudaria a decisão do dono em 3% sem ninguém pedir.
        """
        StockAlert = apps.get_model("stockman", "StockAlert")
        tocados = self._escalar_em_lote(
            StockAlert.objects.all(), {"sku": sku}, "min_quantity", fator
        )
        return [f"  alertas de mínimo:        {tocados} linha(s)"]

    # ────────────────────────────────────────────────────────────────────
    # Craftsman
    # ────────────────────────────────────────────────────────────────────
    def _converter_fichas(self, material, sku: str, alvo: str) -> list[str]:
        """Converte quantidade **e** unidade de cada linha de ficha técnica.

        Cada linha é convertida a partir da unidade **dela**, não da base antiga
        do insumo: ``RecipeItem.clean`` obriga as duas a coincidirem, mas uma
        linha que tenha escapado disso no passado seria corrompida por um fator
        que não é o dela.
        """
        from shopman.craftsman.models.recipe import normalize_recipe_item_unit

        RecipeItem = apps.get_model("craftsman", "RecipeItem")
        grafia_alvo = normalize_recipe_item_unit(alvo)
        tocadas = divergentes = 0
        for item in RecipeItem.objects.filter(input_sku=sku):
            de = units.normalize(item.unit)
            if de != units.normalize(material.unit):
                divergentes += 1
            fator_do_item, _aprox, _ = self._fator(material, de, alvo)
            item.quantity = _escala(item.quantity, fator_do_item, _QUANT_EXP)
            item.unit = grafia_alvo
            item.save(update_fields=["quantity", "unit"])
            tocadas += 1

        linhas = [f"  fichas técnicas:          {tocadas} linha(s), unidade agora '{grafia_alvo}'"]
        if divergentes:
            linhas.append(
                f"    ⚠️  {divergentes} linha(s) estavam numa unidade diferente da "
                "base do insumo e foram convertidas a partir da unidade delas."
            )
        return linhas

    def _converter_fornadas_abertas(self, material, sku: str, alvo: str) -> list[str]:
        """Reescreve o BOM congelado e os itens das fornadas ainda abertas.

        Fornada concluída ou cancelada não é tocada: o snapshot é o que o
        padeiro leu no dia, e o consumo dela já virou movimento no ledger — que
        foi convertido. Reescrever os dois seria contar a mesma correção duas
        vezes, e a segunda por cima da história.
        """
        from shopman.craftsman.models.recipe import normalize_recipe_item_unit

        WorkOrder = apps.get_model("craftsman", "WorkOrder")
        WorkOrderItem = apps.get_model("craftsman", "WorkOrderItem")
        grafia_alvo = normalize_recipe_item_unit(alvo)
        abertas = [WorkOrder.Status.PLANNED, WorkOrder.Status.STARTED]

        fornadas = itens_do_snapshot = 0
        for wo in WorkOrder.objects.filter(status__in=abertas):
            snapshot = (wo.meta or {}).get("_recipe_snapshot") or {}
            linhas_do_bom = snapshot.get("items") or []
            mudou = False
            for linha in linhas_do_bom:
                if linha.get("input_sku") != sku:
                    continue
                de = units.normalize(linha.get("unit"))
                fator_da_linha, _aprox, _ = self._fator(material, de, alvo)
                linha["quantity"] = str(
                    _escala(Decimal(str(linha.get("quantity", "0"))), fator_da_linha, _QUANT_EXP)
                )
                linha["unit"] = grafia_alvo
                mudou = True
                itens_do_snapshot += 1
            if mudou:
                wo.save(update_fields=["meta", "updated_at"])
                fornadas += 1

        tocados = 0
        for item in WorkOrderItem.objects.filter(item_ref=sku, work_order__status__in=abertas):
            de = units.normalize(item.unit) or units.normalize(material.unit)
            fator_do_item, _aprox, _ = self._fator(material, de, alvo)
            item.quantity = _escala(item.quantity, fator_do_item, _QUANT_EXP)
            item.unit = grafia_alvo
            item.save(update_fields=["quantity", "unit"])
            tocados += 1

        return [
            f"  fornadas abertas:         {fornadas} fornada(s), "
            f"{itens_do_snapshot} linha(s) de BOM congelado",
            f"  itens de fornada aberta:  {tocados} linha(s)",
        ]

    # ────────────────────────────────────────────────────────────────────
    # Buyman
    # ────────────────────────────────────────────────────────────────────
    def _converter_conversoes(self, material, fator: Decimal) -> list[str]:
        """O fator de cada embalagem diz quanto ela vale NA BASE — a base mudou.

        "Galão = 5" com base litro vira "Galão = 5,15" com base quilo: é a mesma
        embalagem, dita na unidade nova.
        """
        Conversion = apps.get_model("buyman", "MaterialConversion")
        tocadas = 0
        for conversao in Conversion.objects.filter(material=material):
            conversao.to_base_factor = _escala(
                Decimal(conversao.to_base_factor), fator, _FACTOR_EXP
            )
            conversao.save(update_fields=["to_base_factor", "updated_at"])
            tocadas += 1
        return [f"  conversões existentes:    {tocadas} reescalada(s)"]

    def _converter_custos(
        self, material, fator: Decimal, atual: str, alvo: str
    ) -> list[str]:
        """Divide o custo só quando ele é por unidade-base.

        ``cost_q`` é o preço de UMA unidade de compra. Sem ``conversion``, a
        unidade de compra **é** a base: o número tem de ser redividido, porque
        um quilo de leite custa menos do que um litro. Com ``conversion``, o
        ``cost_q`` é o preço da embalagem (o número impresso na nota), que não
        mudou — quem mudou foi o fator daquela conversão.
        """
        from shopman.utils.monetary import format_money

        Cost = apps.get_model("buyman", "SupplierMaterialCost")
        linhas: list[str] = []
        redivididos = intocados = 0
        for custo in Cost.objects.filter(material=material).select_related("supplier"):
            if custo.conversion_id:
                intocados += 1
                continue
            antes = custo.cost_q
            depois = int(
                (Decimal(antes) / fator).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )
            if depois < 1:
                # ``CheckConstraint(cost_q > 0)``: preço que arredonda para zero
                # não tem valor válido a gravar. Fica em 1 centavo e sai
                # anunciado, porque custo mudo é pior do que custo grosseiro.
                linhas.append(
                    f"    ⚠️  custo de {custo.supplier.ref} arredondaria para zero "
                    f"({format_money(antes)}/{atual} ÷ {fator}); gravado como "
                    "1 centavo. Recadastre o preço na unidade de compra real."
                )
                depois = 1
            custo.cost_q = depois
            custo.save(update_fields=["cost_q", "updated_at"])
            redivididos += 1
            linhas.append(
                f"    {custo.supplier.ref}: {format_money(antes)}/{atual} → "
                f"{format_money(depois)}/{alvo}"
            )

        cabecalho = (
            f"  custos por fornecedor:    {redivididos} redividido(s), "
            f"{intocados} intocado(s) (preço de embalagem, o fator é que mudou)"
        )
        return [cabecalho, *linhas]

    def _converter_minimo_de_compra(self, material, fator: Decimal) -> list[str]:
        """O mínimo declarado no app Compras é quantidade na base, e é política.

        Vive em ``Material.metadata["purchase"]["min_stock"]`` como texto (é onde
        ``set_min_stock`` grava e onde a projeção do Compras procura). Deixá-lo
        em "20" depois da troca faria o operador pedir leite 3% cedo demais para
        sempre, sem nunca saber por quê. O objeto sai daqui alterado em memória
        e é gravado junto com a unidade nova, na mesma escrita.
        """
        metadata = dict(material.metadata or {})
        compras = dict(metadata.get("purchase") or {})
        chave = "min_stock" if "min_stock" in compras else "minStock"
        bruto = compras.get(chave)
        if bruto in (None, ""):
            return ["  mínimo do Compras:        não declarado"]
        try:
            antes = Decimal(str(bruto))
        except (ArithmeticError, TypeError, ValueError):
            return [
                f"    ⚠️  mínimo do Compras ilegível ({bruto!r}) — não convertido. "
                "Redeclare-o na tela de Compras."
            ]
        depois = _escala(antes, fator, _QUANT_EXP)
        compras[chave] = str(depois)
        metadata["purchase"] = compras
        material.metadata = metadata
        return [f"  mínimo do Compras:        {antes} → {depois}"]

    def _declarar_unidade_antiga(
        self, material, atual: str, fator: Decimal, aproximada: bool
    ) -> list[str]:
        """Deixa a unidade antiga cadastrada como conversão, para a nota seguinte.

        Só quando a troca atravessou dimensão. kg↔g é física: declarar isso numa
        tabela editável seria abrir a porta para alguém salvar "1 kg = 900 g" e o
        sistema obedecer calado — a ADR-024 proíbe, e por isso não criamos linha.
        """
        if not aproximada:
            return [
                "  conversão da unidade antiga: não criada — "
                f"'{atual}' é a mesma dimensão da base nova, e física não vira tabela."
            ]

        Material = apps.get_model("buyman", "Material")
        Conversion = apps.get_model("buyman", "MaterialConversion")
        rotulo = str(Material.Unit(atual).label)
        conversao, criada = Conversion.objects.update_or_create(
            material=material,
            supplier=None,
            label=rotulo,
            defaults={
                "to_base_factor": _escala(Decimal(1), fator, _FACTOR_EXP),
                "kind": Conversion.Kind.APPROXIMATE,
                "is_active": True,
            },
        )
        verbo = "criada" if criada else "atualizada"
        return [
            f"  conversão '{rotulo}' {verbo}: 1 {atual} = "
            f"{conversao.to_base_factor} {material.unit} (aproximada)"
        ]

    # ────────────────────────────────────────────────────────────────────
    # Varredura
    # ────────────────────────────────────────────────────────────────────
    def _varrer_o_resto(self, sku: str) -> list[str]:
        """Conta o que guarda quantidade deste SKU e ficou de fora, e diz por quê."""
        linhas: list[str] = []
        for app_label, nome, campo_ref, campo_qtd, extra, motivo in _NAO_CONVERTIDOS:
            try:
                modelo = apps.get_model(app_label, nome)
            except LookupError:
                continue
            achados = modelo.objects.filter(**{campo_ref: sku}, **extra).count()
            if achados:
                linhas.append(
                    f"    {app_label}.{nome}.{campo_qtd}: {achados} linha(s) "
                    f"NÃO convertidas — {motivo}"
                )
        for onde, motivo in _A_CONFERIR_A_MAO:
            linhas.append(f"    {onde}: NÃO convertido — {motivo}")
        return ["  não convertido (confira à mão):", *linhas]

    # ────────────────────────────────────────────────────────────────────
    # Utilidades
    # ────────────────────────────────────────────────────────────────────
    def _somas_por_saldo(self, Move, ids: list[int]) -> dict[int, Decimal]:
        """Σ(moves.delta) por saldo.

        ``.order_by()`` limpo de propósito: o ``Meta.ordering`` do Move entraria
        no GROUP BY e a soma sairia por movimento em vez de por saldo.
        """
        return {
            linha["quant_id"]: linha["total"]
            for linha in (
                self._crua(Move)
                .filter(quant_id__in=ids)
                .values("quant_id")
                .annotate(total=models.Sum("delta"))
                .order_by()
            )
        }

    @staticmethod
    def _crua(modelo) -> models.QuerySet:
        """QuerySet sem a manager do modelo — usada só onde a guarda é do ledger."""
        return models.QuerySet(model=modelo)

    @staticmethod
    def _escalar_em_lote(queryset, filtro: dict, campo: str, fator: Decimal) -> int:
        """Multiplica ``campo`` pelo fator, em ``Decimal``, agrupando valores iguais.

        A conta é feita em Python de propósito: deixá-la no banco entregaria a
        precisão ao dialeto (o SQLite faz aritmética decimal em ponto flutuante),
        e quantidade de insumo não é lugar para 0,0000001 aparecer.
        """
        alvo = queryset.filter(**filtro)
        por_valor: dict[Decimal, list[int]] = defaultdict(list)
        for pk, valor in alvo.values_list("pk", campo):
            por_valor[Decimal(valor)].append(pk)

        tocadas = 0
        for antigo, pks in por_valor.items():
            novo = _escala(antigo, fator, _QUANT_EXP)
            tocadas += len(pks)
            if novo != antigo:
                queryset.filter(pk__in=pks).update(**{campo: novo})
        return tocadas


def _escala(valor: Decimal, fator: Decimal, casas: Decimal) -> Decimal:
    """Multiplica em ``Decimal`` e arredonda só na ponta, na casa do campo."""
    return (Decimal(valor) * fator).quantize(casas, rounding=ROUND_HALF_UP)
