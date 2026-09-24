"""Aplica a curadoria da LISTA DE INSUMOS (WP-INSUMOS-DA-VIDA-REAL) num banco que já roda.

Usage::

    python manage.py apply_material_skus                    # ensaio: executa e desfaz
    python manage.py apply_material_skus --apply            # grava
    python manage.py apply_material_skus --sku MANTEIGA-FR  # um só, pelo SKU de hoje

**Por que existe.** Os 57 insumos do alpha nasceram do seed para a ficha técnica
fechar. São plausíveis, mas alguns têm nome que só quem cadastrou decifra
(``MANTEIGA-FR``), outros estão fora da família onde se procura (``CENTEIO`` é
farinha), um é órfão (``AGUA``, nenhuma ficha) e uma ficha aponta para o vazio
(o Vinagrete à Francesa usa ``MT``, que é o SKU de um **produto**). É o mesmo
trabalho que o catálogo de produtos recebeu em 22–23/09, do outro lado da
cozinha — e por isso o molde é o mesmo do ``apply_product_skus``.

**O que este comando faz**, e nada além:

1. **renomeia** insumo, arrastando a ficha técnica e o ledger pelo cascade;
2. **apaga** o insumo órfão que o dono mandou apagar, com o que ele leva junto
   dito no relatório ANTES de qualquer gravação;
3. **cria** o insumo que falta;
4. **reaponta** a linha de ficha que hoje cita um SKU de produto.

**O que ele NÃO faz, de propósito.** Não mexe em unidade-base, em custo de
fornecedor, em conversão de compra nem em GTIN — essas são
``WP-INSUMOS-SEM-FRICCAO`` e ``WP-ENRIQUECIMENTO-INSUMOS-GTIN``, e as duas
assumem que a lista está certa. Não inventa marca: campo que ninguém confirmou
fica vazio e vira pergunta na planilha.

**O trabalho pesado não é nosso.** ``RefBulk.cascade_rename`` já atravessa os
campos de SKU registrados, com transação e ``select_for_update``, e o
``test_sku_cascade_coverage`` é quem garante que nenhum campo novo nasça órfão.
Aqui mora a tabela, o ensaio e as recusas.

**O ensaio prova cinco coisas antes de qualquer gravação:**

1. **Colisão no namespace compartilhado.** ``Product.sku`` e ``Material.sku``
   dividem um endereço só (``shop/services/sku_namespace.py``), e a colisão é
   recusada em ``pre_save`` nos dois modelos. Alvo que já é produto recusa aqui,
   antes de o ``pre_save`` estourar no meio da travessia.
2. **Campo de SKU único onde os DOIS valores já existem no banco.** A varredura
   é mais larga que a do ``apply_product_skus``: além de ``unique=True``, ela
   olha ``unique_together`` e ``UniqueConstraint``, porque o
   ``unique_quant_coordinate`` do Stockman é ``NULLS NOT DISTINCT`` — dois
   insumos no mesmo depósito com ``target_date`` nulo colidem de verdade. Foi
   isso que travou o ``AGUA-FILTRADA → AGUA`` enquanto ele existiu.
3. **O que a exclusão leva junto** — quant, saldo e movimento, contados e ditos.
4. **Quantas linhas de ficha cada par arrasta**, medidas executando e desfazendo.
5. **As tabelas de código que citam o SKU literal.** O ``seed.py`` é a fonte da
   lista: renomear só no banco é meia correção, porque o próximo ``seed``
   recria o nome antigo. O comando conta as ocorrências; quem as troca é o
   commit, e o relatório cobra.

Idempotente: rodar de novo não faz nada, porque o insumo já renomeado não acha
mais o SKU antigo.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

#: (SKU de hoje, SKU curado). Planilha "Catálogo Nelson — consolidado", aba
#: ``Insumos``. A terceira coluna diz **de quem é a decisão**: o que veio dele
#: em 22/09/2026 e o que é proposta da curadoria esperando a palavra dele. A
#: distinção não é decorativa — ela é o que o relatório mostra antes do
#: ``--apply``, e é por ela que ele decide de uma vez só.
#:
#: A convenção que a aba fecha: **família na frente, sem abreviação**. Quem
#: procura digita a família (``FARINHA``, ``CHOCOLATE``, ``FERMENTO``) e quer as
#: irmãs juntas; abreviação como ``-FR`` ou ``-DESID`` só o autor do cadastro
#: decifra.
RENOMEACOES: tuple[tuple[str, str, str], ...] = (
    # ── 1ª rodada (22/09) ─────────────────────────────────────────────────
    # "a tônica de INSUMO é a Antarctica; a Wewi é revenda e vive no catálogo".
    # Com o fabricante no nome, as duas deixam de se confundir.
    ("TONICA", "TONICA-ANTARCTICA", "dele"),
    # ⚠️ `AGUA-FILTRADA → AGUA` esteve aqui e SAIU: ele voltou atrás em 23/09
    # ("Agua pode ser AGUA-FILTRADA mesmo ok"). Com a linha saiu a única colisão
    # de coordenada de quant que este comando conhecia, e por isso o órfão
    # `AGUA` deixou de ter pressa para sumir.
    #
    # ── 2ª rodada (23–24/09) ──────────────────────────────────────────────
    # Ele reescreveu a aba `Insumos` inteira e depois respondeu 20 perguntas
    # pelo celular. O par vai do SKU que está no ALPHA direto ao curado: o
    # banco nunca viu os intermediários da 1ª rodada, que só existiram no seed.
    ("ACUCAR", "ACUCAR-CRISTAL", "dele"),          # o refinado virou linha própria
    ("ALECRIM", "ALECRIM-FRESCO", "dele"),
    ("AZEITE", "AZEITE-EXTRAVIRGEM", "dele"),
    ("AZEITONA", "AZEITONA-AZAPA", "dele"),
    ("BAUNILHA", "BAUNILHA-EXTRATO-NATURAL", "dele"),   # é extrato, não fava
    ("CANELA", "CANELA-PO", "dele"),                     # o pau virou linha própria
    ("CHOCOLATE-70", "CHOCOLATE-GOTAS-MEIOAMARGO", "dele"),
    ("BATON-CHOCOLATE", "CHOCOLATE-BATON-MEIOAMARGO", "dele"),
    # ⚠️ AO LEITE: o rótulo de quem usa esta ficha passa a declarar LEITE, que o
    # meio amargo não declarava. Ele confirmou em 24/09, ciente disso.
    ("GOTAS-CHOCOLATE", "CHOCOLATE-GOTAS-AOLEITE", "dele"),
    ("CREME-DE-LEITE", "NATA-FRESCA", "dele"),
    ("CENTEIO", "FARINHA-CENTEIO-INTEGRAL-ORGANICA", "dele"),
    ("FARINHA-INT", "FARINHA-INTEGRAL-ORGANICA", "dele"),
    ("FARINHA-T45", "FARINHA-BAGATELLE-T45", "dele"),
    # ⚠️ As duas de baixo TROCAM o nome "T55" entre si, e ele confirmou que é de
    # propósito: a que está em 6 fichas é a Anaconda Premium (nacional, tipo
    # T45) e a de 4 é a Novara T55. Quem ler só o nome se perde — quem lê o SKU,
    # não. Não há colisão: os dois alvos são códigos novos.
    ("FARINHA-T55", "FARINHA-ANACONDA-PREMIUM", "dele"),
    ("FARINHA-T65", "FARINHA-NOVARA-T55", "dele"),
    ("FERMENTO-BIO", "FERMENTO-BIOLOGICO-FRESCO", "dele"),
    ("FERMENTO-NAT", "LEVAIN-LIQUIDO", "dele"),
    ("LEITE", "LEITE-INTEGRAL-A", "dele"),               # tipo A, confirmado
    ("LIMAO", "LIMAO-SICILIANO", "dele"),                # o tahiti virou linha própria
    ("MACA", "MACA-FUJI", "dele"),
    ("MALTE", "MALTE-EXTRATO", "dele"),
    ("MANTEIGA-FR", "MANTEIGA-PRESIDENT-SEM-SAL", "dele"),
    ("MILHO-VERDE", "MILHO-VERDE-CONSERVA", "dele"),
    ("QUEIJO-GRUYERE", "QUEIJO-GOUDA", "dele"),          # a ficha real confirma
    ("SAL", "SAL-REFINADO", "dele"),                     # refinado nas 13 fichas
    ("SALSINHA-DESID", "SALSINHA-DESIDRATADA", "dele"),
    ("TOMILHO", "TOMILHO-FRESCO", "dele"),
    # ⚠️ O CAFÉ não está aqui, e não é esquecimento: `CAFE-GRAO` não vira um
    # insumo, vira DOIS. Rename não divide insumo — ver `DIVISOES`.
)

#: Insumo genérico que escondia mais de um, e por isso não cabe em ``RENOMEACOES``.
#:
#: ``CAFE-GRAO`` é o caso que abriu o WP inteiro, quando ele disse que os insumos
#: eram genéricos. Ele era pior do que parecia: não faltava só a torra, faltava
#: **um café inteiro**. São dois blends, de dois fornecedores — e um deles vem
#: direto do produtor, sem distribuidor.
#:
#: A travessia é rename + criação + reapontamento das fichas que mudam de lado:
#: quem fica com o SKU herdado leva o ledger e o histórico junto, e é por isso
#: que o Chocomelo (6 fichas) herda e o Orfeu (1) nasce.
DIVISOES: tuple[dict, ...] = (
    {
        "de": "CAFE-GRAO",
        "herda": "CAFE-TAMURA-CHOCOMELO",
        "nasce": {
            "sku": "CAFE-ORFEU-CLASSICO",
            "name": "Café Orfeu Clássico em grão",
            "unit": "kg",
            "shelf_life_days": 90,
        },
        "fichas_que_mudam": ("espresso",),
        "curadoria": (
            "dele, 24/09/2026: «Café São 2! Tamura chocomelo e Orfeu Clássico» e «Orfeu para "
            "espresso, Tamura para os demais». O Orfeu vem DIRETO da Orfeu Cafés Especiais; o "
            "Chocomelo, da Tamura (é o PRD00015 da nota que o sistema já leu). "
            "⚠️ «Chocomelo» é palavra dele: o sistema guarda o código do fornecedor, a embalagem "
            "e a chave de acesso da NF-e, mas NÃO o nome do produto — a grafia não dá para "
            "conferir por aqui, e a próxima leitura de nota confirma"
        ),
    },
)

#: Insumo que sai do cadastro, com quem decidiu e por quê. Excluir insumo é
#: destrutivo e por isso a lista é curta e nominal: nada entra aqui por regra
#: ("órfão sai"), só por decisão escrita.
EXCLUSOES: dict[str, str] = {
    "AGUA": (
        "dele, 22/09/2026: «água mineral é só revenda, não insumo». O registro é órfão — "
        "nenhuma ficha o usa, e o saldo de 5 l é do seed, não de contagem"
    ),
}

#: Insumo que passa a existir. ``unit`` é a unidade-base — aquela em que o livro
#: conta o insumo no momento da verdade (ADR-024 §Regra 1) — e **não** a
#: embalagem de compra, que é outro eixo (``MaterialConversion``). O balde de
#: 1 kg está no NOME porque é como o padeiro o reconhece na prateleira; quem
#: ensina o sistema a converter a nota é o ``WP-INSUMOS-SEM-FRICCAO``.
CRIACOES: tuple[dict, ...] = (
    {
        "sku": "MOSTARDA-DIJON",
        "name": "Mostarda Dijon Beaufor (balde 1 kg)",
        "unit": "kg",
        "shelf_life_days": None,
        "curadoria": (
            "dele, 22/09/2026: «a mostarda de INSUMO é Beaufor, Dijon, balde de 1 kg, "
            "food service — melhor preço que a Maille de prateleira»"
        ),
    },
)

#: Linha de ficha que aponta para o SKU errado: ``(ref da ficha, SKU de hoje,
#: SKU certo)``.
#:
#: ⚠️ **Isto não é rename, e a diferença importa.** ``MT`` é o SKU do produto
#: *Mostarda da Casa*, que segue no catálogo; um ``cascade_rename("SKU", "MT",
#: …)`` levaria o produto junto. O que está errado é o endereço que a ficha
#: cita, e é só ele que se troca — uma linha, não um namespace.
REAPONTAMENTOS: tuple[tuple[str, str, str], ...] = (
    (
        "vinagrete-frances",
        "MT",
        "MOSTARDA-DIJON",
    ),
)

#: Fica de fora com o motivo escrito, para que a ausência seja decisão e não
#: esquecimento.
FORA_DA_TABELA: dict[str, str] = {
    # A aba propõe BAUNILHA-EXT-NAT, e esse nome DECLARA um fato: que a casa usa
    # extrato. O cadastro de hoje diz "fava/pasta", que é outra coisa, e ninguém
    # confirmou qual das duas entra. Renomear aqui gravaria no SKU uma resposta
    # que não existe — e o insumo não está em ficha nenhuma, então não há pressa.
    "BAUNILHA-EXTRATO-NATURAL": (
        "o nome proposto (BAUNILHA-EXT-NAT) declara que é EXTRATO, e o cadastro diz "
        "«fava/pasta». Qual das duas a casa usa é pergunta dele, na planilha"
    ),
    # Sem ficha que o use. O SKU está certo; o que falta decidir é se ele fica
    # (falta a ficha) ou sai (saiu de uso) — e isso não se deduz do banco.
    "QUEIJO-COLONIAL": (
        "nenhuma ficha o usa, e o SKU não tem defeito. Ou falta a ficha, ou o insumo "
        "saiu de uso: pergunta dele, na planilha"
    ),
}

#: Arquivos que guardam SKU de insumo como literal. O comando os LÊ para contar,
#: nunca escreve.
#:
#: ⚠️ O ``seed.py`` não é "mais um lugar que cita": ele é a **fonte da lista**.
#: O alpha ainda vai ser resemeado, e o seed que não conhecer o nome novo
#: ressuscita o antigo. Por isso o relatório cobra a contagem em vez de
#: informá-la.
TABELAS_DE_CODIGO: tuple[str, ...] = (
    "config/management/commands/seed.py",
    "shopman/backstage/tests/test_purchase_costs_batch.py",
    "shopman/backstage/tests/test_seed_liquid_base_unit.py",
    "packages/craftsman/shopman/craftsman/tests/test_recipe_book.py",
    "packages/craftsman/shopman/craftsman/tests/test_percentages.py",
    "surfaces/purchase-nuxt/tests/purchase.test.ts",
)


def _colisoes_por_campo_unico(antigo: str, novo: str) -> list[str]:
    """Campos de SKU onde os DOIS valores já existem — e o cascade estouraria.

    O ``cascade_rename`` faz um ``update()`` cru por campo registrado. Onde o
    campo participa de uma restrição de unicidade e as duas linhas existem, o
    banco recusa **no meio da travessia**, com metade do rename aplicado dentro
    da transação.

    A varredura olha as três formas em que a unicidade aparece — ``unique=True``,
    ``unique_together`` e ``UniqueConstraint`` — porque a que morde neste WP é a
    terceira: ``unique_quant_coordinate`` é ``(sku, position, target_date,
    batch)`` com ``NULLS NOT DISTINCT``, e os dois quants de água moram no mesmo
    depósito com ``target_date`` nulo.
    """
    from django.apps import apps
    from shopman.refs.registry import _ref_source_registry

    achados: list[str] = []
    for label, campo in sorted(_ref_source_registry.get_sources_for_type("SKU")):
        app_label, model_name = label.split(".", 1)
        try:
            Model = apps.get_model(app_label, model_name)
        except LookupError:
            continue

        grupos: list[tuple[str, ...]] = []
        if Model._meta.get_field(campo).unique:
            grupos.append((campo,))
        grupos.extend(t for t in Model._meta.unique_together if campo in t)
        grupos.extend(
            tuple(c.fields)
            for c in Model._meta.constraints
            if getattr(c, "fields", None) and campo in c.fields
        )
        if not grupos:
            continue

        for grupo in grupos:
            outros = [f for f in grupo if f != campo]
            velhas = Model.objects.filter(**{campo: antigo})
            if not velhas.exists():
                continue
            for velha in velhas.values(*outros) if outros else [{}]:
                if Model.objects.filter(**{campo: novo}, **velha).exists():
                    coord = ", ".join(f"{k}={v!r}" for k, v in velha.items()) or "linha inteira"
                    achados.append(f"{label}.{campo} ({'+'.join(grupo)}; {coord})")
    return achados


class Command(BaseCommand):
    help = "Aplica a curadoria da lista de insumos: renomeia, apaga o órfão, cria o que falta."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Grava. Sem isto o comando executa e desfaz, e só mostra o relatório.",
        )
        parser.add_argument(
            "--sku",
            help="Roda um insumo só, pelo SKU de HOJE (ex.: --sku MANTEIGA-FR).",
        )

    def handle(self, *args, **options):
        from shopman.buyman.models import Material

        apply = options["apply"]
        alvo = (options["sku"] or "").strip()

        pares = [p for p in RENOMEACOES if not alvo or p[0] == alvo]
        exclusoes = {k: v for k, v in EXCLUSOES.items() if not alvo or k == alvo}
        criacoes = [c for c in CRIACOES if not alvo or c["sku"] == alvo]
        reapontamentos = [r for r in REAPONTAMENTOS if not alvo or r[1] == alvo]
        divisoes = [d for d in DIVISOES if not alvo or d["de"] == alvo]

        if alvo and not (pares or exclusoes or criacoes or reapontamentos or divisoes):
            motivo = FORA_DA_TABELA.get(alvo)
            raise CommandError(
                f"'{alvo}' está fora da tabela: {motivo}." if motivo
                else f"'{alvo}' não está na curadoria de insumos."
            )

        insumos = set(Material.objects.values_list("sku", flat=True))

        # Lido ANTES da travessia: depois dela o órfão já teria saído, e o
        # relatório não teria como dizer o que ele levava junto.
        carga_da_exclusao = {sku: self._carga(sku) for sku in exclusoes}

        # Duas ordens de problema, e elas não se resolvem igual. **Recusa** diz
        # que a TABELA está errada — dois insumos querendo o mesmo endereço, alvo
        # que já é produto — e aí nada pode ser gravado até alguém corrigi-la.
        # **Impedimento** diz que o MUNDO trava uma linha: o ledger não deixa o
        # órfão sair. Só aquela frente para; o resto segue.
        recusas = self._recusar(pares, criacoes, reapontamentos, divisoes, insumos)
        if recusas:
            self._escrever_recusas(recusas)
            raise CommandError(
                "Nada foi gravado. Recusa fechada: colisão de SKU não se resolve por escolha "
                "do comando — quem decide qual linha fica é quem cura a lista."
            )
        impedidos = self._impedimentos(pares, exclusoes, insumos, carga_da_exclusao)

        divididos: list[dict] = []
        apagados: list[tuple[str, dict]] = []
        criados: list[str] = []
        feitos: list[tuple[str, str, str, int]] = []
        reapontados: list[tuple[str, str, str]] = []
        pulados: list[tuple[str, str]] = []

        with transaction.atomic():
            # A exclusão vem primeiro: enquanto houve um rename mirando o SKU
            # de um insumo a apagar, essa ordem era a diferença entre caber e
            # estourar a constraint no meio da travessia.
            for sku in exclusoes:
                if sku in insumos and sku not in impedidos:
                    self._apagar(sku)
                    apagados.append((sku, carga_da_exclusao[sku]))

            for criacao in criacoes:
                if criacao["sku"] not in insumos:
                    Material.objects.create(
                        sku=criacao["sku"],
                        name=criacao["name"],
                        unit=criacao["unit"],
                        shelf_life_days=criacao["shelf_life_days"],
                        metadata={"curadoria": criacao["curadoria"]},
                    )
                    criados.append(criacao["sku"])

            for divisao in divisoes:
                if divisao["de"] in insumos:
                    divididos.append(self._dividir(divisao))

            for antigo, novo, quem in pares:
                if antigo in impedidos:
                    continue
                if antigo not in insumos:
                    pulados.append((antigo, novo))
                    continue
                linhas = self._renomear(antigo, novo)
                feitos.append((antigo, novo, quem, linhas))

            for ficha, antigo, novo in reapontamentos:
                if self._reapontar(ficha, antigo, novo):
                    reapontados.append((ficha, antigo, novo))

            if not apply:
                # Executa e desfaz, em vez de simular: só assim o número de
                # linhas do relatório é o que a gravação faria de verdade.
                transaction.set_rollback(True)

        self._relatorio(
            feitos, apagados, criados, reapontados, pulados, impedidos, divididos,
            pares=pares, apply=apply, alvo=alvo,
        )
        if alvo and alvo in impedidos:
            raise CommandError(impedidos[alvo])

    # ---------------------------------------------------------------- recusas

    def _recusar(self, pares, criacoes, reapontamentos, divisoes, insumos) -> list[str]:
        """O que diz que a TABELA está errada. Lista inteira, não a primeira."""
        from shopman.craftsman.models import Recipe, RecipeItem
        from shopman.offerman.models import Product

        recusas: list[str] = []
        produtos = set(Product.objects.values_list("sku", flat=True))

        vistos: dict[str, str] = {}
        for antigo, novo, _quem in RENOMEACOES:
            if novo in vistos:
                recusas.append(
                    f"{antigo} e {vistos[novo]} querem os dois o SKU {novo}. "
                    "Dois insumos não dividem endereço."
                )
            vistos[novo] = antigo

        for antigo, novo, _quem in pares:
            if antigo not in insumos:
                continue  # já renomeado ou ausente: o relatório conta como pulado
            if novo in produtos:
                recusas.append(
                    f"{antigo} → {novo}: o SKU {novo} já é produto vendável do catálogo. "
                    "Insumo e produto dividem um namespace só — o ledger indexa por SKU, "
                    "e vender a garrafa consumiria a água da massa no mesmo quant "
                    "(ver shopman/shop/services/sku_namespace.py)."
                )
            if novo in insumos and novo not in EXCLUSOES:
                recusas.append(
                    f"{antigo} → {novo}: o SKU {novo} já é de outro insumo, e ele não está "
                    "na lista de exclusões. Decida qual fica antes de renomear."
                )

        for criacao in criacoes:
            sku = criacao["sku"]
            if sku in produtos:
                recusas.append(
                    f"criar {sku}: o SKU já é produto vendável do catálogo. "
                    "Insumo e produto dividem um namespace só."
                )
            if sku in insumos:
                recusas.append(
                    f"criar {sku}: já existe um insumo com esse SKU. "
                    "Criar de novo apagaria a curadoria dele."
                )

        for divisao in divisoes:
            if divisao["de"] not in insumos:
                continue
            for sku in (divisao["herda"], divisao["nasce"]["sku"]):
                if sku in produtos:
                    recusas.append(
                        f"dividir {divisao['de']}: o SKU {sku} já é produto vendável do catálogo."
                    )
                if sku in insumos:
                    recusas.append(
                        f"dividir {divisao['de']}: o SKU {sku} já é de outro insumo. Uma divisão "
                        "cria endereços novos — se um deles já existe, a curadoria mudou e a "
                        "tabela envelheceu."
                    )
            for ficha in divisao["fichas_que_mudam"]:
                if not Recipe.objects.filter(ref=ficha).exists():
                    recusas.append(
                        f"dividir {divisao['de']}: a ficha '{ficha}' não existe, e é ela que "
                        "distingue os dois. Sem ela a divisão não tem como saber o que vai "
                        "para onde."
                    )

        for ficha, antigo, novo in reapontamentos:
            receita = Recipe.objects.filter(ref=ficha).first()
            if receita is None:
                continue  # ficha ausente: o relatório conta como pulado
            if RecipeItem.objects.filter(recipe=receita, input_sku=novo).exists():
                recusas.append(
                    f"ficha {ficha}: já existe uma linha com {novo}, e (ficha, insumo) é "
                    f"único. Fundir a de {antigo} com ela somaria quantidade — quem decide "
                    "quanto entra é quem cura a ficha, não este comando."
                )

        return recusas

    # ----------------------------------------------------------- impedimentos

    def _impedimentos(self, pares, exclusoes, insumos, carga) -> dict[str, str]:
        """Frentes que param sozinhas porque o MUNDO as trava, não a tabela.

        Só uma coisa trava aqui, e ela foi descoberta no ensaio contra a cópia
        do alpha: **o ledger do Stockman é imutável por construção**. ``Move``
        recusa ``delete()`` e ``update()`` no próprio queryset, e ``Move.quant``
        é ``PROTECT``. Logo o quant de um insumo que já teve qualquer movimento
        — nem que seja o saldo de abertura do seed — **não sai do banco**.

        É o que segura o órfão ``AGUA``: o saldo de 5 l dele é do seed, mas o
        movimento que o registrou é ledger, e ledger não se apaga.

        Enquanto existiu um rename mirando esse SKU, o impedimento era duplo —
        ``unique_quant_coordinate`` é ``(sku, position, target_date, batch)``
        com ``NULLS NOT DISTINCT``, e os dois quants de água moravam no mesmo
        depósito com ``target_date`` nulo, então o ``update`` do cascade
        estouraria a constraint no meio da travessia. Esse rename saiu em 23/09,
        e a varredura continua aqui porque o próximo par pode repeti-lo.

        A cura nunca é forçar a trava. Para o órfão sair de verdade, o caminho é
        o ``seed --flush``, que reconstrói o cadastro sem ele — e reseed pede a
        palavra do dono.
        """
        impedidos: dict[str, str] = {}

        for sku in exclusoes:
            if sku not in insumos:
                continue
            if carga[sku]["fichas"]:
                impedidos[sku] = (
                    f"apagar {sku}: {carga[sku]['fichas']} linha(s) de ficha ainda o usam. "
                    "Apagar deixaria a ficha apontando para o vazio — o mesmo defeito que "
                    "este comando conserta no `MT`."
                )
            elif carga[sku]["movimentos"]:
                impedidos[sku] = (
                    f"apagar {sku}: o ledger guarda {carga[sku]['movimentos']} movimento(s) "
                    f"({'; '.join(carga[sku]['historia'])}), e o Move é imutável por "
                    "construção — recusa delete() e update(), e a FK para o quant é PROTECT. "
                    "O cadastro não sai enquanto o saldo tiver história.\n"
                    "    Cure pelo seed: a lista mora no `seed.py`, e um `seed --flush` "
                    "reconstrói o cadastro sem o órfão. Reseed do alpha pede a palavra dele."
                )

        for antigo, novo, _quem in pares:
            if antigo not in insumos:
                continue
            if novo in exclusoes and novo in impedidos:
                impedidos[antigo] = (
                    f"{antigo} → {novo}: o SKU {novo} só fica livre quando o insumo homônimo "
                    "sair, e ele está preso pela linha acima. As duas curam juntas, pelo seed."
                )
                continue
            colisoes = _colisoes_por_campo_unico(antigo, novo)
            if colisoes and novo not in exclusoes:
                impedidos[antigo] = (
                    f"{antigo} → {novo}: os dois SKUs já existem em {'; '.join(colisoes)}, "
                    "que tem restrição de unicidade. O update do cascade estouraria a "
                    "constraint no meio da travessia."
                )

        return impedidos

    def _escrever_recusas(self, recusas: list[str]) -> None:
        self.stderr.write(self.style.ERROR(f"\n{len(recusas)} recusa(s):"))
        for r in recusas:
            self.stderr.write(self.style.ERROR(f"  ⛔ {r}"))

    # --------------------------------------------------------------- travessia

    def _carga(self, sku: str) -> dict:
        """O que a exclusão de um insumo leva junto — contado, não suposto.

        O ledger do Stockman indexa por SKU em coluna de texto, sem FK para o
        ``Material``: apagar o insumo NÃO apaga o quant, e o saldo ficaria de pé
        sem dono. Por isso a exclusão apaga os dois, e por isso o relatório diz
        o número antes.
        """
        from shopman.craftsman.models import RecipeItem
        from shopman.stockman.models import Move, Quant

        quants = Quant.objects.filter(sku=sku)
        movimentos = Move.objects.filter(quant__sku=sku)
        return {
            "fichas": RecipeItem.objects.filter(input_sku=sku).count(),
            "quants": quants.count(),
            "saldo": sum((q.quantity for q in quants), start=0),
            "movimentos": movimentos.count(),
            "historia": [
                f"{m.kind} {m.delta:+} em {m.timestamp:%d/%m/%Y} — «{m.reason}»"
                for m in movimentos[:4]
            ],
        }

    def _apagar(self, sku: str) -> None:
        from shopman.buyman.models import Material
        from shopman.stockman.models import Quant

        # O quant sai junto porque é o saldo DESTE insumo e não tem FK que o
        # leve: apagar só o Material deixaria o saldo de pé sem dono.
        #
        # Só chega aqui insumo cujo quant NÃO tem movimento — `_impedimentos` já
        # parou o resto. O ledger é imutável por construção (Move recusa
        # delete/update, e a FK é PROTECT), e essa trava não se contorna: ela é a
        # razão de o estoque poder ser auditado.
        Quant.objects.filter(sku=sku).delete()
        Material.objects.filter(sku=sku).delete()

    def _dividir(self, divisao: dict) -> dict:
        """Um insumo genérico vira dois, sem que o ledger perca o fio.

        Quem HERDA o SKU antigo leva junto o saldo, os movimentos e as fichas —
        é um rename comum. Quem NASCE começa do zero, e só as fichas nomeadas
        mudam de lado. A escolha de quem herda não é estética: herda quem está
        na maioria das fichas, porque é o caminho com menos linha a reapontar e
        menos chance de o histórico se descolar do insumo errado.
        """
        from shopman.buyman.models import Material

        nasce = divisao["nasce"]
        Material.objects.create(
            sku=nasce["sku"],
            name=nasce["name"],
            unit=nasce["unit"],
            shelf_life_days=nasce["shelf_life_days"],
            metadata={"curadoria": divisao["curadoria"]},
        )
        linhas = self._renomear(divisao["de"], divisao["herda"])
        mudadas = [
            ficha for ficha in divisao["fichas_que_mudam"]
            if self._reapontar(ficha, divisao["herda"], nasce["sku"])
        ]
        return {
            "de": divisao["de"], "herda": divisao["herda"], "nasce": nasce["sku"],
            "linhas": linhas, "fichas": mudadas, "curadoria": divisao["curadoria"],
        }

    def _renomear(self, antigo: str, novo: str) -> int:
        from shopman.refs.bulk import RefBulk

        return RefBulk.cascade_rename("SKU", antigo, novo, actor="apply_material_skus")

    def _reapontar(self, ficha: str, antigo: str, novo: str) -> bool:
        from shopman.craftsman.models import Recipe, RecipeItem

        receita = Recipe.objects.filter(ref=ficha).first()
        if receita is None:
            return False
        return bool(
            RecipeItem.objects.filter(recipe=receita, input_sku=antigo).update(input_sku=novo)
        )

    # ------------------------------------------------------------- relatório

    def _relatorio(
        self, feitos, apagados, criados, reapontados, pulados, impedidos, divididos,
        *, pares, apply, alvo,
    ):
        verbo = "Feito" if apply else "Faria"
        out = self.stdout

        out.write(self.style.SUCCESS(f"\n1) Renomeações — {verbo.lower()}:"))
        if feitos:
            total = sum(n for *_x, n in feitos)
            for antigo, novo, quem, linhas in feitos:
                marca = "✅ dele" if quem == "dele" else "⏳ proposta"
                out.write(f"  {antigo:<16} → {novo:<22} {linhas:>5} linha(s)   {marca}")
            out.write(f"  {len(feitos)} insumo(s), {total} linha(s) atualizadas.")
            esperando = [f"{a} → {n}" for a, n, q, _l in feitos if q == "proposta"]
            if esperando:
                out.write(self.style.WARNING(
                    f"\n  ⏳ {len(esperando)} destas são PROPOSTA da curadoria, não decisão dele.\n"
                    "  A convenção que elas fecham — família na frente, sem abreviação — está na "
                    "aba `Insumos` da planilha, numa coluna que ele sobrescreve."
                ))
        else:
            out.write("  nada a renomear: a lista já está nos SKUs curados.")

        if impedidos:
            out.write(self.style.WARNING(
                f"\n  ⛔ {len(impedidos)} frente(s) NÃO aplicada(s) — o mundo as trava, "
                "não a tabela:"
            ))
            for chave in sorted(impedidos):
                out.write(self.style.WARNING(f"    {impedidos[chave]}"))

        out.write("\n2) Exclusão do órfão:")
        if apagados:
            for sku, carga in apagados:
                out.write(
                    f"  {sku}: {carga['quants']} quant(s), saldo {carga['saldo']}, "
                    f"{carga['movimentos']} movimento(s), {carga['fichas']} linha(s) de ficha."
                )
                out.write(f"    {EXCLUSOES[sku]}")
            out.write(
                "  ⚠️ O quant sai junto porque o ledger indexa por SKU em texto, sem FK: "
                "apagar só o insumo deixaria o saldo de pé sem dono.\n"
                "  Os movimentos caem por cascade do quant. Por isso a lista de exclusões "
                "é nominal e curta — insumo com história de compra não entra nela."
            )
        elif any(sku in impedidos for sku in EXCLUSOES):
            out.write("  nenhuma: a exclusão está impedida — ver a lista acima.")
        elif EXCLUSOES and not alvo:
            out.write("  nada a apagar: o órfão já saiu.")
        else:
            out.write("  nenhuma exclusão neste escopo.")

        out.write("\n2b) Insumo genérico que virou DOIS:")
        if divididos:
            for d in divididos:
                out.write(
                    f"  {d['de']} → {d['herda']} (herda saldo, ledger e fichas, "
                    f"{d['linhas']} linha(s))"
                )
                out.write(f"     + {d['nasce']} nasce, e leva a(s) ficha(s): {', '.join(d['fichas'])}")
                out.write(f"     {d['curadoria']}")
        else:
            out.write("  nenhuma divisão neste escopo.")

        out.write("\n3) Insumo que passa a existir:")
        if criados:
            for sku in criados:
                criacao = next(c for c in CRIACOES if c["sku"] == sku)
                out.write(f"  {sku:<16} {criacao['name']}  ({criacao['unit']})")
                out.write(f"    {criacao['curadoria']}")
        else:
            out.write("  nada a criar.")

        out.write("\n4) Ficha que apontava para o vazio:")
        if reapontados:
            for ficha, antigo, novo in reapontados:
                out.write(f"  {ficha}: {antigo} → {novo}")
            out.write(
                "  ⚠️ Isto NÃO é rename: `MT` é o SKU do produto Mostarda da Casa, que segue "
                "no catálogo. O que muda é o endereço que a ficha cita — uma linha, não um "
                "namespace. Um cascade levaria o produto junto."
            )
        else:
            out.write("  nenhuma linha a reapontar.")

        self._secao_namespace()
        self._secao_codigo([a for a, _n, _q, _l in feitos] or [a for a, _n, _q in pares])

        if pulados:
            out.write(f"\n{len(pulados)} par(es) sem insumo no cadastro (já renomeado ou ausente):")
            for antigo, novo in pulados:
                out.write(f"  {antigo} → {novo}")

        if not alvo and FORA_DA_TABELA:
            out.write(f"\n{len(FORA_DA_TABELA)} insumo(s) fora da tabela, com motivo:")
            for sku, motivo in sorted(FORA_DA_TABELA.items()):
                out.write(f"  {sku:<18} {motivo}")

        if not apply:
            out.write(self.style.WARNING(
                "\n(ensaio: executado e desfeito, nada gravado. Para gravar: --apply)"
            ))
        else:
            out.write(self.style.WARNING(
                "\nDepois deste comando: o `seed.py` precisa dos nomes novos no mesmo commit.\n"
                "Ele é a fonte da lista, e o próximo reseed ressuscita o nome antigo sem avisar."
            ))

    def _secao_namespace(self) -> None:
        from shopman.shop.services.sku_namespace import find_sku_collisions

        colisoes = find_sku_collisions()
        self.stdout.write("\n5) Namespace compartilhado com o produto vendável:")
        if colisoes:
            self.stdout.write(self.style.ERROR(f"  {len(colisoes)} colisão(ões): {', '.join(colisoes)}"))
        else:
            self.stdout.write("  zero colisão.")

    def _secao_codigo(self, antigos: list[str]) -> None:
        from django.conf import settings

        raiz = Path(settings.BASE_DIR)
        alvo = sorted(set(antigos), key=len, reverse=True)
        if not alvo:
            return
        padrao = re.compile(r'["\'](' + "|".join(re.escape(s) for s in alvo) + r')["\']')

        self.stdout.write("\n6) Código que cita o SKU antigo (NÃO reescrito aqui):")
        total = 0
        for rel in TABELAS_DE_CODIGO:
            caminho = raiz / rel
            if not caminho.is_file():
                self.stdout.write(f"  {rel}: arquivo não encontrado")
                continue
            n = len(padrao.findall(caminho.read_text(errors="ignore")))
            total += n
            self.stdout.write(f"  {n:>5} ocorrência(s)  {rel}")
        if total:
            self.stdout.write(self.style.WARNING(
                f"  ⚠️ {total} ocorrência(s) ainda no código. O `seed.py` é a FONTE da lista: "
                "renomear só no banco é meia correção,\n"
                "  porque o próximo reseed do alpha recria o nome antigo — e ninguém recebe erro."
            ))
        else:
            self.stdout.write("  nenhuma: o código já fala os nomes novos.")
