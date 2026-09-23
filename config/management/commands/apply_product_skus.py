"""Aplica os SKUs curados do Catálogo (WP-CATALOGO-PUBLICAVEL F1) num banco que já roda.

Usage::

    python manage.py apply_product_skus              # ensaio: executa e desfaz
    python manage.py apply_product_skus --apply      # grava
    python manage.py apply_product_skus --sku CT     # um SKU só, pelo código de hoje

**Por que existe.** Os códigos do catálogo são os que o Yooga usava, e eles não
dizem de que família o produto é: hoje ``MI`` devolve mini-baguete, mini-focaccia
e mini-folhado, e as seis baguetes moram em ``BF``/``BE``/``BEP``/``BAP``/``MIB``/
``CF``. A planilha de curadoria (revisada duas vezes pelo dono em 22/09/2026) fecha
duas convenções: **casa** = código curto com a família no começo e a variante no
fim (``TRADI``, ``CRO``, ``CROPQ``); **revenda** = ``TIPO-VARIANTE-MARCA-EMBALAGEM``
(``GELEIA-FIGO-STDALFOUR-284``), porque ali ninguém decora código de fornecedor e
embalagem diferente é GTIN diferente.

**O que este comando NÃO faz, de propósito.** Não cria produto que ainda não
existe, não apaga, não despublica e não mexe em nome, preço ou foto. Ele troca o
endereço do que já está no catálogo — nada mais. O resto da planilha é outra
fatia do WP.

**O trabalho pesado não é nosso.** ``RefBulk.cascade_rename`` já atravessa os 18
campos de SKU registrados em 9 apps, com transação e ``select_for_update``, e o
``test_sku_cascade_coverage`` é quem garante que nenhum campo novo nasça órfão.
Aqui mora a tabela, o ensaio e as recusas.

**O ensaio prova seis coisas antes de qualquer gravação** (a sexta não estava no
WP; apareceu ao medir o alpha):

1. **Série do B.I.** — ``HistoricalSaleItem`` casa por SKU externo e o
   ``ProductAlias`` é que traduz. O produto que tem venda no histórico e **não**
   tem alias com o próprio código perde a série em silêncio no rename. O comando
   cria o alias que falta; se a chave ``(fonte, sku)`` já pertence a OUTRO
   produto, recusa fechado e diz a qual.
2. **URL da PDP e ``g:id`` do feed** — os dois derivam do SKU
   (``/produto/<sku>``, ``id`` do item no Merchant Center). O relatório lista o
   antes e o depois de quem está em coleção de feed.
3. **Tabelas de código** — ``seed.py``, ``apply_product_brands.py``,
   ``sku-real-mapa.csv`` e companhia citam o código literal. O relatório conta as
   ocorrências por arquivo: elas NÃO são reescritas aqui.
4. **Fichas do Craftsman** — ``output_sku``/``input_sku`` entram no cascade; o
   relatório conta quantas linhas cada um arrasta.
5. **Colisão no namespace compartilhado** com o insumo do Buyman
   (``shop/services/sku_namespace.py``): alvo que já é produto ou insumo recusa.
6. **JSON que o cascade não alcança** — payload de evento, ``snapshot`` de
   pedido, ``content`` de anúncio. Quase tudo é história e fica como está; o que
   for estado vivo (anúncio por publicar, pedido aberto) sai nomeado no relatório.

Idempotente: rodar de novo não faz nada, porque o par já renomeado não acha mais
o código antigo no catálogo.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

#: A fonte do histórico que o ``ProductAlias`` traduz. Uma só hoje.
FONTE_HISTORICO = "yooga"

#: (código de hoje, código curado). Planilha "Catálogo Nelson — consolidado",
#: abas `Proposta SKU da casa` e `Produtos`, 2ª revisão do dono em 22/09/2026.
#: Só entra par cujo código de hoje EXISTE no catálogo: produto a criar é outra
#: fatia, e renomear o que não existe seria inventar.
RENAMES: tuple[tuple[str, str], ...] = (
    # --- casa: família no começo, variante no fim ---
    ("ANC", "COE"),          # Coelhinho de Chocolate (o código dizia Animalzinho)
    ("ANP", "PORQ"),         # Porquinho
    ("ANU", "URS"),          # Ursinho
    ("BA", "BAT"),           # Bâtard
    ("BAP", "BGL"),        # Baguete Lanche (massa tradição)
    ("BAX", "ITA"),          # Italiano Rústico
    ("BBB", "BRBB"),         # Brioche Burger Bun
    ("BBB2", "BRBB2"),       # Brioche Burger Bun (pc. 2un.)
    ("BCH", "BRCH"),         # Brioche Chocolat
    ("BE", "BGG"),           # Baguete Gergelim — irmã da BGGP, a pequena
    ("BEP", "BGGP"),         # Baguete Gergelim Pequena
    ("BF", "TRADI"),         # Baguette de Tradition
    ("BH", "BICH"),          # Bichon au Citron
    ("BN", "BRNT"),          # Brioche Nanterre
    ("CBT", "FOB"),          # Focaccia Cebola, Bacon e Tomilho
    ("CCOM", "CQCOM"),       # Croque Complet
    ("CD", "COAD"),          # Café Coado
    ("CF", "CPBG"),          # Baguette Campagne
    ("CGO", "CPG"),          # Pain de Campagne
    ("CGR", "CPR"),          # Pain de Campagne Redondo
    ("CH", "CHLH"),          # Challah
    ("CHAI_A", "SFTCH"),     # Soft Chai Cítrico
    ("CL", "CAFL"),          # Caffè Latte
    ("CM", "CRP"),         # Croissant Mini
    ("CMA", "CQMA"),         # Croque Madame
    ("CMO", "CQMO"),         # Croque Monsieur
    ("CPQ", "CRPQ"),        # Croissant Presunto e Queijo
    ("CQ", "CHOQ"),          # Chocolate Quente
    ("CT", "CRO"),           # Croissant
    ("CTV", "CTFV"),         # Chá Tônica Frutas Vermelhas
    ("DL", "DELI"),          # Deli Milho & Bacon
    ("FA", "FORMA"),         # Forma Artesanal (era Shokupan)
    ("FE", "FENDU"),         # Fendu
    ("FF", "FFGO"),          # Folhado de Frango
    ("FP", "FRAP"),          # Frappé
    ("HI", "CHHIB"),         # Chá Hibisco
    ("HO", "HOD"),           # Hot Dog Vienna
    ("KBB", "KUBB"),         # Kuro Pan Burger
    ("KP", "KUP"),           # Kuro Pan
    ("MBBBG", "BRBBP"),      # Mini Brioche Burger Bun com gergelim — irmão de BRBB/BRBB2
    ("MC", "CAPMO"),         # Mochaccino
    ("MD", "MDLN"),          # Madeleine
    ("ME", "MELON"),         # Melonpan
    ("MFF", "FFGOP"),        # Mini Folhado de Frango
    ("MH", "MOCHA"),         # Mocha
    ("MICBT", "FOBP"),       # Mini Focaccia Cebola, Bacon e Tomilho
    ("MIF", "FOAP"),         # Mini Focaccia Alecrim
    ("MIFOC", "FOCP"),       # Mini Focaccia Cebola Roxa
    ("MIHO", "HODP"),        # Mini Hot Dog Vienna
    ("MS", "MELSA"),         # Melon Iced Sando — o pão dele é o melonpan (MELON)
    ("PC", "PCHOC"),         # Pain au Chocolat
    ("PH", "TRABB"),         # Pão de Hambúrguer (massa tradição)
    ("PHO", "HOL"),         # Pão para Hot Dog
    ("PHO4", "HOL4"),       # Pão para Hot Dog (pc. 4un.)
    ("PI", "PIT"),           # Pita
    ("PI4", "PIT4"),         # Pita (pc. 4un.)
    ("PPU", "PERDU"),        # Pain Perdu
    ("PR", "BRRSN"),         # Pain aux Raisins
    ("PS", "CAP"),           # Cappuccino
    ("PT", "RTAT"),          # Patê de Ratatouille
    ("QQ", "QJQT"),          # Queijo-Quente
    ("SE", "VIEN"),          # Vienna
    ("SL", "SPMC"),          # Espresso Macchiato
    ("SO", "SDLA"),          # Soda de Laranja
    ("SS", "SP"),            # Espresso
    ("TB", "TABAT"),         # Tabatière
    ("THB", "CHBLU"),        # Chá Bleu
    ("THC", "CHCAM"),        # Chá Camille
    ("THR", "CHROU"),        # Chá Rouge
    ("THS", "CHSOP"),        # Chá Sophie
    ("TI", "TABUA"),         # Tábua de Iguarias da Casa
    ("TP", "TPND"),          # Tapenade
    # --- revenda: TIPO-VARIANTE-MARCA-EMBALAGEM ---
    ("AG", "AGUA-MINERAL-PRATA-310"),
    ("CHEGO_L50", "CHA-ACONCHEGO-KANFA-L50"),
    ("CHEGO_P50", "CHA-ACONCHEGO-KANFA-P50"),
    ("INTIMI_L50", "CHA-INTIMIDADE-KANFA-L50"),
    ("INTIMI_P50", "CHA-INTIMIDADE-KANFA-P50"),
    ("INTU_L70", "CHA-INTUICAO-KANFA-L70"),
    ("INTU_P50", "CHA-INTUICAO-KANFA-P50"),
    ("MAMA_L60", "CHA-MAMA-KANFA-L70"),      # a gramatura no código passa a ser a real
    ("MAMA_P50", "CHA-MAMA-KANFA-P50"),
    ("NAMAS_L60", "CHA-NAMASTE-KANFA-L70"),  # idem
    ("NAMAS_P50", "CHA-NAMASTE-KANFA-P50"),
    ("QC", "QUEIJO-CAMEMBERT-ILEDEFRANCE-125"),
    ("SOFIA_P50", "CHA-CHALOSOFIA-KANFA-P50"),
    ("VITAL_P50", "CHA-VITAL-KANFA-P50"),
)

#: A SEGUNDA leva da curadoria (23/09/2026), depois de ele ver os códigos na
#: tela. Um banco está em exatamente um dos dois estados — nos códigos do Yooga
#: (e aí ``RENAMES`` o leva direto ao final) ou já nos intermediários (e aí é
#: esta tabela que fecha). Por isso as duas convivem sem encadear.
#:
#: O que ele mudou, e por quê:
#:
#: - **``M`` de mini virou ``P``**: em português ``M`` se lê MÉDIO, e essa é a
#:   leitura que o operador faz de relance. O nome na tela continua "Mini
#:   Focaccia" — a letra é para digitar e ler, não para falar.
#: - **``HOBB`` não é burger bun**: o pão do cachorro-quente é comprido, um
#:   *roll*. Virou ``HOL`` (dele: "L pode ser de longo, em vez de redondo").
#:   O ``BB`` segue certo no ``BRBB`` e no ``TRABB``, que são burger buns.
#: - **``CROQ`` colidiria com os croques** (``CQMO``, ``CQMA``, ``CQCOM``) e
#:   fecharia a porta do croissant só de queijo. A família virou ``CR``:
#:   ``CRO`` · ``CRP`` · ``CRPQ`` · ``CRPQP``, com ``CRQJ`` reservado.
#: - **``TRADP`` mentia a massa**: a Baguete Lanche é ``MASSA-CIABATTA``, não
#:   tradição. Virou ``BGL``, ao lado de ``BGG`` e ``BGGP``, que são a mesma
#:   massa.
AJUSTES: tuple[tuple[str, str], ...] = (
    ("FOAM", "FOAP"),        # Mini Focaccia Alecrim
    ("FOBM", "FOBP"),        # Mini Focaccia Cebola, Bacon e Tomilho
    ("FOCM", "FOCP"),        # Mini Focaccia Cebola Roxa
    ("FFGOM", "FFGOP"),      # Mini Folhado de Frango
    ("HODM", "HODP"),        # Mini Hot Dog Vienna
    ("BRBBM", "BRBBP"),      # Mini Brioche Burger Bun com gergelim
    ("CROMI", "CRP"),        # Croissant Mini
    ("CROPQ", "CRPQ"),       # Croissant Presunto e Queijo
    ("HOBB", "HOL"),         # Pão para Hot Dog — é um roll, não um burger bun
    ("HOBB4", "HOL4"),       # Pão para Hot Dog (pc. 4un.)
    ("TRADP", "BGL"),        # Baguete Lanche — massa ciabatta, não tradição
)

#: As duas tabelas, na ordem em que se aplicam. Cada uma é validada em si: o
#: alvo repetido ENTRE elas é esperado (as duas levam ao mesmo lugar, por
#: caminhos que nunca coexistem no mesmo banco).
TABELAS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("curadoria", RENAMES),
    ("ajustes", AJUSTES),
)

#: Fica de fora com o motivo escrito, para que a ausência seja decisão e não
#: esquecimento. A planilha não tem linha para estes oito, e um deles
#: (``MT``) ainda é insumo de ficha — ver ``WP-INSUMOS-SEM-FRICCAO.md``.
FORA_DA_TABELA: dict[str, str] = {
    # Um produto não vira dois por rename: o `GL` é placeholder de sabor
    # indefinido, e no lugar dele nascem os DOIS minis reais (damasco e frutas
    # vermelhas, GTINs distintos). Renomeá-lo para um dos dois declararia um
    # sabor que ele nunca teve e esconderia o outro. Sai como exclusão, e os
    # dois entram como produto novo — outra fatia deste WP.
    "GL": (
        "o dono decidiu em 22/09 que o placeholder sai: no lugar dele nascem os DOIS "
        "minis St. Dalfour reais, damasco e frutas vermelhas. Rename não divide produto"
    ),
    "BK": "sem linha na planilha — a casa ainda não faz o bacon (ver apply_product_brands)",
    "CV": "sem linha na planilha — Cream Soda do dia, a casa ainda não faz",
    "CX": "sem linha na planilha — Cornichons, placeholder da despensa do Cardápio 2027",
    "GR": "sem linha na planilha — Café em Grão 250g, placeholder da despensa",
    "LN": "sem linha na planilha — Lata Nelson, placeholder da despensa",
    "MT": "sem linha na planilha — e o código é o da Mostarda em ficha; ver WP-INSUMOS-SEM-FRICCAO",
    "QP": "sem linha na planilha — Queijo Pomerode, placeholder da despensa",
    "THL": "sem linha na planilha — Chá da Casa (lata), placeholder da despensa",
}

#: Arquivos que guardam SKU como literal. O comando os LÊ para contar, nunca
#: escreve: trocar aqui é commit de código, não gravação de banco.
TABELAS_DE_CODIGO: tuple[str, ...] = (
    "config/management/commands/seed.py",
    "config/management/commands/apply_product_brands.py",
    "config/management/commands/rename_skus_to_real.py",
    "shopman/shop/management/commands/apply_product_measurements.py",
    "shopman/backstage/management/commands/measure_eat_in_weights.py",
    "docs/plans/sku-real-mapa.csv",
)

#: JSON que guarda SKU e que o cascade NÃO alcança, com o que a linha significa.
#: "história" = foto do que aconteceu, fica como está. "vivo" = estado que ainda
#: vai ser lido, e por isso sai nomeado no relatório.
JSON_FORA_DO_CASCADE: tuple[tuple[str, str, str], ...] = (
    ("orderman.Directive", "payload", "história"),
    ("orderman.OrderEvent", "payload", "história"),
    ("orderman.SessionEvent", "payload", "história"),
    ("orderman.Order", "snapshot", "história"),
    ("orderman.Order", "data", "vivo"),
    ("orderman.Session", "data", "vivo"),
    ("orderman.IdempotencyKey", "response_body", "história"),
    ("crafting.WorkOrderEvent", "payload", "história"),
    ("crafting.WorkOrderItem", "meta", "vivo"),
    ("backstage.KDSTicket", "items", "vivo"),
    ("stockman.Hold", "metadata", "vivo"),
    ("shop.Announcement", "content", "vivo"),
    ("customer_insights.CustomerInsight", "favorite_products", "derivado"),
    ("shop.ProductAffinity", "sku_a/sku_b", "derivado"),
)


#: Campo de SKU **único** onde os dois valores podem coexistir no banco. Aí o
#: ``update`` do cascade estoura a constraint no meio da travessia, e o que
#: fazer depende do que a linha significa — por isso a política é explícita por
#: model, e model sem política faz o comando parar. É a mesma mecânica do
#: ``rename_skus_to_real``, e pela mesma razão: prefiro recusar a inventar
#: semântica de merge para tabela que não conheço.
POLITICA_DE_COLISAO: dict[str, str] = {
    # Etiqueta de consumo é ANOTAÇÃO sobre um produto, não o produto. A do
    # código antigo e a do código novo descrevem a mesma coisa — a segunda
    # sobrou do `propose_consumption_tags --include-historical`, que etiquetou
    # também os códigos do cardápio 2027. Fundir é o certo.
    "backstage.ProductConsumptionTag": "fundir",
    # Produto é ENTIDADE: fundir apagaria um catálogo de vínculos, preços e
    # listagens. Insumo idem — e insumo com SKU de produto vendável é sintoma.
    # Os dois já são recusa dura em `_recusar`; ficam aqui para que a varredura
    # não os leia como "sem política".
    "offerman.Product": "recusar",
    "buyman.Material": "recusar",
}


def mapa_de_renames() -> dict[str, str]:
    """Todo código que já foi nosso → o código que ele virou, nas duas levas.

    Mora em ``shopman.shop.services.sku_history``, que é a porta para quem só
    quer perguntar: o cardápio do iFood, o 301 da loja, a herança de peso do
    B.I. As TABELAS ficam aqui, que é onde a curadoria as edita.
    """
    from shopman.shop.services.sku_history import rename_map

    return rename_map()


def codigo_de_hoje(sku: str, conhecidos) -> str:
    """Segue a cadeia de renames até um código que EXISTE em ``conhecidos``."""
    from shopman.shop.services.sku_history import current_sku

    return current_sku(sku, conhecidos)


def _curadoria(nota: str | None) -> str:
    """A nota do de-para, quando existe: quem decidiu e quando."""
    nota = (nota or "").strip()
    return f"A linha diz: «{nota}»." if nota else "A linha não diz quem decidiu."


class Command(BaseCommand):
    help = "Troca os códigos do catálogo pelos SKUs curados da planilha (WP-CATALOGO-PUBLICAVEL F1)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Grava. Sem isto o comando executa e desfaz, e só mostra o relatório.",
        )
        parser.add_argument(
            "--sku",
            help="Roda um par só, pelo código de HOJE (ex.: --sku CT).",
        )

    def handle(self, *args, **options):
        from shopman.offerman.models import Product

        apply = options["apply"]
        alvo = (options["sku"] or "").strip()
        todos = [par for _rotulo, tabela in TABELAS for par in tabela]
        pares = [p for p in todos if not alvo or p[0] == alvo]
        if alvo and not pares:
            motivo = FORA_DA_TABELA.get(alvo)
            raise CommandError(
                f"'{alvo}' está fora da tabela: {motivo}." if motivo
                else f"'{alvo}' não está na tabela de renomeação."
            )

        vivos = set(Product.objects.values_list("sku", flat=True))

        # Duas ordens de problema, e elas não se resolvem igual. Colisão de
        # namespace diz que a TABELA está errada, e nada pode ser gravado até
        # alguém corrigi-la. De-para vencido diz que a CURADORIA de uma linha
        # envelheceu: só aquele par para, e o resto segue.
        recusas = self._recusar(pares, vivos)
        if recusas:
            self._escrever_recusas(recusas)
            raise CommandError(
                "Nada foi gravado. Recusa fechada: colisão de SKU não se resolve por escolha "
                "do comando — quem decide qual linha fica é quem cura o catálogo."
            )
        impedidos = self._impedimentos_de_serie(pares, vivos)
        # Lido ANTES da travessia: depois dela a coleção já responde com o
        # código novo, e o relatório não teria mais como dizer o antes.
        no_feed = self._skus_em_feed()

        feitos: list[tuple[str, str, int]] = []
        pulados: list[tuple[str, str]] = []
        aliases: list[str] = []
        fusoes: list[str] = []

        with transaction.atomic():
            for antigo, novo in pares:
                if antigo in impedidos:
                    continue
                if antigo not in vivos:
                    pulados.append((antigo, novo))
                    continue
                aliases.extend(self._garantir_alias(antigo))
                fusoes.extend(self._fundir_anotacoes(antigo, novo))
                linhas = self._renomear(antigo, novo)
                feitos.append((antigo, novo, linhas))
            if not apply:
                # Executa e desfaz, em vez de simular: só assim o número de
                # linhas do relatório é o que a gravação faria de verdade.
                transaction.set_rollback(True)

        self._relatorio(
            feitos, pulados, aliases, impedidos, fusoes,
            no_feed=no_feed, pares=pares, apply=apply, alvo=alvo,
        )
        if alvo and alvo in impedidos:
            raise CommandError(impedidos[alvo])

    # ---------------------------------------------------------------- recusas

    def _recusar(self, pares, vivos) -> list[str]:
        """Tudo que impede a gravação. Lista inteira, não a primeira."""
        from shopman.buyman.models import Material


        recusas: list[str] = []
        insumos = set(Material.objects.values_list("sku", flat=True))

        for campo in self._sem_politica():
            recusas.append(
                f"{campo} é campo de SKU único e não tem política de colisão. "
                "Acrescente-a em POLITICA_DE_COLISAO antes de renomear — sem ela o "
                "cascade estoura a constraint no meio da travessia."
            )

        # Alvo repetido se cobra DENTRO de cada tabela: entre elas, o mesmo alvo
        # é o ponto de encontro de dois caminhos que nunca coexistem no mesmo
        # banco (o do Yooga e o dos códigos intermediários).
        for rotulo, tabela in TABELAS:
            vistos: dict[str, str] = {}
            for antigo, novo in tabela:
                if novo in vistos:
                    recusas.append(
                        f"em '{rotulo}': {antigo} e {vistos[novo]} querem os dois o código "
                        f"{novo}. Dois produtos não dividem endereço."
                    )
                vistos[novo] = antigo

        for antigo, novo in pares:
            if antigo not in vivos:
                continue  # já renomeado ou ausente: o relatório conta como pulado

            if novo in vivos:
                recusas.append(
                    f"{antigo} → {novo}: o código {novo} já é de outro produto do catálogo. "
                    "Decida qual fica antes de renomear."
                )
            if novo in insumos:
                recusas.append(
                    f"{antigo} → {novo}: o código {novo} já é insumo do Buyman. "
                    "Produto e insumo dividem um namespace só — o estoque indexa por SKU "
                    "(ver shopman/shop/services/sku_namespace.py)."
                )

        return recusas

    def _impedimentos_de_serie(self, pares, vivos) -> dict[str, str]:
        """Pares que param sozinhos: a série daquele código é de outro produto.

        A chave do de-para é ``(fonte, sku externo)`` e é única. Quando o código
        de hoje já está nessa chave apontando para OUTRO produto, não há alias a
        criar — e o que está lá diz que a venda histórica daquele código foi
        creditada a outro produto.

        Renomear não pioraria nada (o de-para não olha para o SKU do produto, e
        sim para o FK). O que se perde é a última chance barata de notar o
        engano: depois do rename, o laço entre "o código antigo" e "este
        produto" existe só nesta tabela. Por isso o par para aqui, sozinho, com
        a curadoria de origem citada — e os outros seguem.
        """
        from shopman.backstage.models import ProductAlias

        impedidos: dict[str, str] = {}
        linhas = ProductAlias.objects.filter(
            source=FONTE_HISTORICO, external_sku__in=[a for a, _n in pares if a in vivos]
        ).values_list("external_sku", "product_id", "product__sku", "product__name", "note")
        for antigo, pid, sku_do_dono, nome_do_dono, nota in linhas:
            if pid is None:
                impedidos[antigo] = (
                    f"{antigo}: o de-para '{FONTE_HISTORICO}:{antigo}' existe sem produto "
                    f"(marcado como extinto). {_curadoria(nota)} "
                    "Aponte-o para o produto certo, ou apague-o, antes de renomear."
                )
            elif sku_do_dono != antigo:
                impedidos[antigo] = (
                    f"{antigo}: o de-para '{FONTE_HISTORICO}:{antigo}' credita a venda histórica "
                    f"a {sku_do_dono} ({nome_do_dono}), não ao produto {antigo}. {_curadoria(nota)} "
                    "Enquanto ela valer, este produto segue sem série — e renomeá-lo apagaria "
                    "a última pista de que o código antigo era dele."
                )
        return impedidos

    def _escrever_recusas(self, recusas: list[str]) -> None:
        self.stderr.write(self.style.ERROR(f"\n{len(recusas)} recusa(s):"))
        for r in recusas:
            self.stderr.write(self.style.ERROR(f"  ⛔ {r}"))

    # ------------------------------------------------------------------ alias

    def _garantir_alias(self, antigo: str) -> list[str]:
        """O de-para que segura a série do B.I. depois que o código mudar.

        ``HistoricalSaleItem`` guarda o SKU como o Yooga o escreveu, e isso não
        se reescreve (é registro de terceiro). Quem junta os dois anos de
        histórico ao presente é o ``ProductAlias``, pelo FK: com ele, o rename
        passa despercebido pela série; sem ele, a série se descola do produto e
        ninguém recebe erro.
        """
        from shopman.offerman.models import Product

        from shopman.backstage.models import AliasStatus, HistoricalSaleItem, ProductAlias

        if not HistoricalSaleItem.objects.filter(sku=antigo).exists():
            return []
        if ProductAlias.objects.filter(source=FONTE_HISTORICO, external_sku=antigo).exists():
            return []

        produto = Product.objects.get(sku=antigo)
        nome = (
            HistoricalSaleItem.objects.filter(sku=antigo)
            .values_list("product_name", flat=True)
            .first()
            or produto.name
        )
        ProductAlias.objects.create(
            source=FONTE_HISTORICO,
            external_sku=antigo,
            external_name=nome,
            product=produto,
            status=AliasStatus.CONFIRMED,
            note=f"criado pelo rename de SKU ({antigo} → {produto.sku})",
        )
        return [f"{FONTE_HISTORICO}:{antigo} → {produto.name}"]

    # ------------------------------------------------------- campo único

    def _campos_unicos_de_sku(self):
        """(label, campo) de todo campo de SKU registrado que seja ``unique``."""
        from django.apps import apps
        from shopman.refs.registry import _ref_source_registry

        for label, campo in sorted(_ref_source_registry.get_sources_for_type("SKU")):
            app_label, model_name = label.split(".", 1)
            try:
                Model = apps.get_model(app_label, model_name)
            except LookupError:
                continue
            if Model._meta.get_field(campo).unique:
                yield label, campo, Model

    def _sem_politica(self) -> list[str]:
        return [
            f"{label}.{campo}"
            for label, campo, _Model in self._campos_unicos_de_sku()
            if label not in POLITICA_DE_COLISAO
        ]

    def _fundir_anotacoes(self, antigo: str, novo: str) -> list[str]:
        """Resolve o campo único onde os DOIS códigos já existem.

        Sem isto o ``update`` do cascade estoura a constraint no meio da
        travessia — e só aparece em banco com operação, porque teste unitário
        cria um lado de cada vez.
        """
        fusoes: list[str] = []
        for label, campo, Model in self._campos_unicos_de_sku():
            if POLITICA_DE_COLISAO.get(label) != "fundir":
                continue
            velha = Model.objects.filter(**{campo: antigo}).first()
            nova = Model.objects.filter(**{campo: novo}).first()
            if velha is None or nova is None:
                continue
            # A curada vence a proposta. No empate sobrevive a do código antigo:
            # ela descreve o produto que está sendo renomeado, e a outra sobrou
            # de um catálogo que não existe mais.
            if getattr(nova, "reviewed", False) and not getattr(velha, "reviewed", False):
                fica, sai, motivo = nova, velha, "sobreviveu a curada"
            else:
                fica, sai, motivo = velha, nova, (
                    "sobreviveu a curada" if getattr(velha, "reviewed", False)
                    else "sobreviveu a do produto renomeado"
                )
            sai.delete()
            setattr(fica, campo, antigo)  # o cascade a leva para o código novo
            fica.save(update_fields=[campo])
            fusoes.append(f"{label}: {antigo} + {novo} — {motivo}")
        return fusoes

    # --------------------------------------------------------------- travessia

    def _renomear(self, antigo: str, novo: str) -> int:
        from shopman.refs.bulk import RefBulk

        return RefBulk.cascade_rename("SKU", antigo, novo, actor="apply_product_skus")

    # ------------------------------------------------------------- relatório

    def _relatorio(
        self, feitos, pulados, aliases, impedidos, fusoes, *, no_feed, pares, apply, alvo
    ) -> None:
        verbo = "Feito" if apply else "Faria"
        out = self.stdout

        if feitos:
            total = sum(n for _a, _n, n in feitos)
            out.write(self.style.SUCCESS(
                f"\n{verbo}: {len(feitos)} código(s) trocado(s), {total} linha(s) atualizadas."
            ))
            for antigo, novo, linhas in feitos:
                out.write(f"  {antigo:<12} → {novo:<34} {linhas:>6} linha(s)")
        else:
            out.write(self.style.SUCCESS("\nNada a renomear: o catálogo já está nos códigos curados."))

        out.write("\n1) Série do B.I.")
        if aliases:
            out.write(f"  {len(aliases)} de-para {'criado' if apply else 'a criar'}:")
            for a in aliases:
                out.write(f"    {a}")
            out.write(
                "  Sem eles a venda histórica daquele código se descola do produto, "
                "e nada acusa."
            )
        elif feitos:
            out.write("  nenhum de-para a criar: quem tem série já tem o seu.")
        if impedidos:
            out.write(self.style.WARNING(
                f"\n  ⛔ {len(impedidos)} par(es) NÃO renomeado(s) — a série daquele código "
                "está creditada a outro produto:"
            ))
            for antigo in sorted(impedidos):
                out.write(self.style.WARNING(f"    {impedidos[antigo]}"))
            out.write(
                "  Isto é decisão de curadoria, não do rename: a de-para de origem valia "
                "quando o catálogo ainda não tinha o produto separado.\n"
                "  Conserto: apontar o de-para para o produto certo no Gestor "
                "(Admin → de-paras de produto), e rodar este comando de novo."
            )

        if fusoes:
            out.write(f"\n  {len(fusoes)} anotação(ões) fundida(s) no caminho:")
            for f in fusoes:
                out.write(f"    {f}")

        self._secao_vitrine(feitos, no_feed)
        self._secao_codigo([a for a, _n, _l in feitos] or [a for a, _ in pares])
        self._secao_fichas([a for a, _n, _l in feitos] or [a for a, _ in pares])
        self._secao_namespace()
        self._secao_json([a for a, _n, _l in feitos] or [a for a, _ in pares])

        if pulados:
            out.write(f"\n{len(pulados)} par(es) sem produto no catálogo (já renomeado ou ainda por criar):")
            for antigo, novo in pulados[:12]:
                out.write(f"  {antigo} → {novo}")
            if len(pulados) > 12:
                out.write(f"  … e mais {len(pulados) - 12}")

        if not alvo and FORA_DA_TABELA:
            out.write(f"\n{len(FORA_DA_TABELA)} código(s) do catálogo fora da tabela, com motivo:")
            for sku, motivo in sorted(FORA_DA_TABELA.items()):
                out.write(f"  {sku:<6} {motivo}")

        if not apply:
            out.write(self.style.WARNING(
                "\n(ensaio: executado e desfeito, nada gravado. Para gravar: --apply)"
            ))
        else:
            out.write(self.style.WARNING(
                "\nDepois deste comando, nesta ordem:\n"
                "  1. ifood_retract_renamed_skus  — o item antigo segue vendável no cardápio deles\n"
                "  2. sync_catalog_ifood --full   — publica os códigos novos\n"
                "  3. compute_product_affinity    — a afinidade guarda SKU e não entra no cascade"
            ))

    def _skus_em_feed(self) -> set[str]:
        """Os SKUs que hoje saem num feed de vitrine (Google/Meta).

        O canal de exibição SEM formato é menuboard, não feed: item de TV não
        passa por revisão de plataforma nenhuma.
        """
        from shopman.offerman.models import Collection

        from shopman.shop.models import Channel

        refs: set[str] = set()
        for channel in Channel.objects.filter(commerce_policy=Channel.CommercePolicy.DISPLAY):
            display = (channel.config or {}).get("display") or {}
            if display.get("format") or "":
                refs.update(display.get("collections") or [])
        skus: set[str] = set()
        for coll in Collection.objects.filter(ref__in=refs):
            # O feed omite item sem imagem (`image_link` é obrigatório).
            skus.update(p.sku for p in coll.product_queryset() if p.image_url)
        return skus

    def _secao_vitrine(self, feitos, no_feed: set[str]) -> None:
        """2) O que muda na URL da PDP e no id do item no feed."""
        self.stdout.write("\n2) Endereço público — /produto/<sku> e o id do item no feed:")
        if not feitos:
            self.stdout.write("  nada a mudar.")
            return
        mudam = [(a, n) for a, n, _l in feitos if a in no_feed]
        for antigo, novo in mudam:
            self.stdout.write(f"  /produto/{antigo} → /produto/{novo}   ·   g:id {antigo} → {novo}")
        self.stdout.write(
            f"  {len(mudam)} de {len(feitos)} estão em coleção de feed; os outros trocam "
            "só a URL da página de produto.\n"
            "  O Merchant Center trata id novo como item novo: o item passa por revisão "
            "outra vez, e o antigo fica órfão até o feed ser lido de novo. Antes do go-live "
            "isso é barato — depois custa reindexação e redirect."
        )

    def _secao_codigo(self, antigos: list[str]) -> None:
        """3) As tabelas de código que citam o SKU literal."""
        from django.conf import settings

        raiz = Path(settings.BASE_DIR)
        alvo = sorted(set(antigos), key=len, reverse=True)
        padrao = re.compile(r'["\',](' + "|".join(re.escape(s) for s in alvo) + r')["\',]')

        self.stdout.write("\n3) Tabelas de código que citam o código antigo (NÃO reescritas aqui):")
        achou = False
        for rel in TABELAS_DE_CODIGO:
            caminho = raiz / rel
            if not caminho.is_file():
                self.stdout.write(f"  {rel}: arquivo não encontrado")
                continue
            texto = caminho.read_text(errors="ignore")
            n = len(padrao.findall(texto))
            achou = achou or bool(n)
            self.stdout.write(f"  {n:>5} ocorrência(s)  {rel}")
        if not achou:
            self.stdout.write("  nenhuma.")
        self.stdout.write(
            "  A contagem é de literal entre aspas ou vírgulas, então inclui falso positivo "
            "de código curto. Quem cobra a travessia de verdade é a suíte."
        )

    def _secao_fichas(self, antigos: list[str]) -> None:
        """4) As fichas do Craftsman que o cascade arrasta junto."""
        from shopman.craftsman.models import Recipe, RecipeItem, WorkOrder

        self.stdout.write("\n4) Fichas do Craftsman arrastadas pelo cascade:")
        for rotulo, qs in (
            ("crafting.Recipe.output_sku", Recipe.objects.filter(output_sku__in=antigos)),
            ("crafting.RecipeItem.input_sku", RecipeItem.objects.filter(input_sku__in=antigos)),
            ("crafting.WorkOrder.output_sku", WorkOrder.objects.filter(output_sku__in=antigos)),
        ):
            self.stdout.write(f"  {qs.count():>5}  {rotulo}")

    def _secao_namespace(self) -> None:
        """5) A colisão com o insumo, medida e não suposta."""
        from shopman.shop.services.sku_namespace import find_sku_collisions

        colisoes = find_sku_collisions()
        self.stdout.write("\n5) Namespace compartilhado com o insumo do Buyman:")
        if colisoes:
            self.stdout.write(self.style.ERROR(f"  {len(colisoes)} colisão(ões): {', '.join(colisoes)}"))
        else:
            self.stdout.write("  zero colisão.")

    def _secao_json(self, antigos: list[str]) -> None:
        """6) O JSON que guarda SKU e que o cascade não alcança."""
        from django.apps import apps
        from django.db.models import Q

        self.stdout.write("\n6) JSON que cita o código antigo e o cascade NÃO alcança:")
        for label, campo, natureza in JSON_FORA_DO_CASCADE:
            if "/" in campo:
                continue  # par de colunas: não é JSON, entra pela nota abaixo
            try:
                Model = apps.get_model(label)
            except LookupError:
                continue
            filtro = Q()
            for antigo in antigos:
                filtro |= Q(**{f"{campo}__icontains": f'"{antigo}"'})
            try:
                n = Model.objects.filter(filtro).count()
            except Exception:  # noqa: BLE001 — coluna que não aceita icontains
                continue
            if n:
                marca = "  ← estado vivo" if natureza == "vivo" else ""
                self.stdout.write(f"  {n:>6}  {label}.{campo}  ({natureza}){marca}")
        self.stdout.write(
            "  História fica como está: payload de evento e snapshot são a foto do que "
            "aconteceu, e reescrevê-los seria falsificar o registro.\n"
            "  Estado vivo é que pede janela: renomeie com o balcão sem pedido aberto, "
            "e confira anúncio por publicar (o link dele carrega o código antigo).\n"
            "  shop.ProductAffinity guarda SKU em coluna própria fora do cascade: "
            "é derivada, e `compute_product_affinity` a refaz."
        )
