"""As VIAS do pedido — um registro de quem é cada papel, e o que a tela oferece.

A casa imprime vários papéis não fiscais do MESMO pedido, e eles nasceram
separados: o recibo (``receipt_escpos.sale_receipt``), a ficha do painel
(``order_ticket``) e a via do entregador (``courier_ticket``). Cada um foi
desenhado para um leitor diferente — o que é certo. O que faltava era dizer
isso em algum lugar: sem registro, a diferença entre eles só existia dentro da
cabeça de quem leu as três docstrings, e cada tela oferecia o papel de que o
programador daquela tela se lembrou.

Este módulo é esse registro. Ele responde duas perguntas, e só duas:

1. **Quem é cada via** (:data:`DOCUMENTS`) — audiência, permissão, chave do
   carimbo de reimpressão, rota que compõe os bytes, filtros a que ela está
   sujeita e em que contextos ela é oferecida.
2. **Que vias fazem sentido para ESTE pedido, NESTA tela**
   (:func:`documents_for`) — com os filtros já resolvidos e o rótulo pronto.

**Ele não compõe papel nenhum.** O leiaute tem um dono só
(:mod:`shopman.backstage.services.receipt_escpos`), e continua tendo. Este
registro é o índice, não a gráfica.

## Três vias, por AUDIÊNCIA

- **Via Cozinha** — o KDS materializado, para o posto que tem impressora e não
  tem tela.
- **Via Encomenda** — nasce no painel físico e viaja com a sacola. **Um papel
  só, com duas fases de vida**: ela fica pregada enquanto o pedido espera, e
  sai com a mercadoria quando ele parte.
- **Via Recibo** — o papel de quem pagou.

⚠️ **"Painel" e "sacola" não são vias diferentes**, e "via do entregador"
também não é uma. A via do entregador é a **Via Encomenda com o filtro de
identificação ligado** — o mesmo papel, com uma fatia a menos, porque quem o
segura mudou. Modelá-la como documento próprio era descrever o filtro como se
fosse audiência.

## Dois filtros, uma família

Os filtros são **de divulgação**: eles não mudam a que via o papel pertence,
mudam o que aquela via mostra. São ortogonais entre si e à via, têm a mesma
forma (:class:`DisclosureFilter`) e a mesma origem — **o PEDIDO**. Nenhum dos
dois é escolha de quem imprime, e essa é a regra que sustenta as duas: a rota
da via que viaja recusa um parâmetro de variante justamente porque ele seria a
porta por onde o endereço do cliente sairia num papel de parceiro de entrega.

Cada via declara a que filtros ela está **sujeita**. Ortogonal não quer dizer
que todo filtro morde toda via: o recibo é a prova do pagamento e esconder
valor ali o destrói; a via da cozinha não carrega nem contato nem dinheiro. O
que é igual é a MÁQUINA — quem pergunta, quem responde, e o fato de que quem
imprime não opina.

## Por que o registro mora no backstage

Papel é coisa de operador: as rotas que compõem bytes vivem em
``backstage/api/operations.py``, o leiaute vive em ``backstage/services``, e as
telas que oferecem o botão são as superfícies de operador. A loja não tem
impressora. Pôr o registro em ``shop/`` levaria uma decisão que só o operador
toma para a camada que as duas superfícies compartilham.

O que ficou em ``shop/`` foi o que já estava lá e é do PEDIDO, não do papel: a
derivação dos filtros (``shop.services.order_helpers``), perguntada aqui e em
mais lugar nenhum.

## O que NÃO é via

A **DANFE da NFC-e** não entra neste registro. Ela é o documento fiscal do
pedido — nasce do XML autorizado, obedece ao Manual de Especificações Técnicas
do DANFE NFC-e e não pode trazer informação que não conste da nota. As vias são
documentos OPERACIONAIS e estampam, em destaque, que não são fiscais. Um
catálogo só para os dois convidaria a próxima tela a tratá-los igual.

## Duas coisas que o papel ainda não diz

1. **O carimbo de reimpressão.** O dono decidiu que ele passa a dizer
   "REIMPRESSÃO", e não "2a VIA": "via" agora nomeia a audiência, e "segunda
   via da Via Encomenda" é ambíguo. Os quatro compositores de
   ``receipt_escpos`` ainda estampam "2a VIA", e trocar a palavra é mexer em
   documento existente — migração, não fundação.
2. **O nome no alto da via que viaja.** O papel ainda se apresenta como "Via do
   entregador — Identificada/Anônima". Reconciliar essa copy com "Via
   Encomenda" é parte de migrar o documento, não de registrá-lo.

## "Via" na tela, ``OrderDocument`` no código

Mesma separação que a casa já faz entre *comanda* (o que o operador fala) e
``POSTab`` (o nome no código): identificador em inglês, prosa e rótulo em
português. A palavra do dono para o conceito é **via**, e é ela que sai na tela.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ── As três vias, por AUDIÊNCIA ───────────────────────────────────────────
#
# A chave é a audiência, e não o leiaute, porque foi assim que o dono cortou o
# problema: cada via mostra uma fatia, conforme o contexto. Quem LÊ o papel é o
# que decide qual fatia é essa.

#: O KDS materializado em papel — o posto com impressora e sem tela.
KITCHEN = "kitchen"
#: O papel do pedido: fica no painel enquanto espera, viaja com a sacola quando
#: parte. Hoje é a filipeta (``order_ticket``) e a via do entregador
#: (``courier_ticket``) — o mesmo papel em duas fases, com um filtro de
#: diferença.
ORDER = "order"
#: O papel de quem pagou.
RECEIPT = "receipt"


# ── Os contextos: as telas que oferecem via ───────────────────────────────

#: O PDV logo depois de a venda fechar.
CONTEXT_POS_CHECKOUT = "pos_checkout"
#: As últimas vendas do balcão — a casa do papel depois que a tela da venda passou.
CONTEXT_POS_RECENT_SALES = "pos_recent_sales"
#: A tela das fichas do painel (intervalo, conferência, bobina).
CONTEXT_ORDER_PANEL = "order_panel"
#: O card do pedido no Gestor.
CONTEXT_ORDER_CARD = "order_card"
#: O gesto de despachar — a fase em que a via deixa o painel e vai com a sacola.
CONTEXT_DISPATCH = "dispatch"
#: O posto da cozinha.
CONTEXT_KITCHEN_STATION = "kitchen_station"


# ── Os filtros de divulgação ──────────────────────────────────────────────

#: Esconde nome, telefone e endereço do cliente.
FILTER_CUSTOMER_IDENTITY = "customer_identity"
#: Esconde os valores do pedido.
FILTER_VALUES = "values"


def _customer_identity_is_hidden(order) -> bool:
    """A identificação do cliente sai deste pedido, ou fica?

    Quem responde é ``order_helpers.courier_ticket_variant``, e a resposta não
    se reimplementa aqui: ela já carrega a configuração do canal (o canal
    próprio entrega com transportadora contratada pela casa, que não tem app
    nenhum e precisa do endereço no papel; o canal de marketplace não) **e o
    piso que essa configuração não fura** — quando o PEDIDO diz que quem entrega
    não é a casa, a identificação some assim mesmo, com log. Configuração é do
    operador, e operador erra; privacidade de cliente não pode custar um campo
    mal preenchido.
    """
    from shopman.shop.services.order_helpers import (
        COURIER_TICKET_ANONYMOUS,
        courier_ticket_variant,
    )

    return courier_ticket_variant(order) == COURIER_TICKET_ANONYMOUS


def _values_are_hidden(order) -> bool:
    """Os valores saem deste pedido, ou ficam?

    A marca é do CLIENTE e vem do checkout: ``Order.data["gift_hide_values"]``,
    gravada por ``storefront.intents.gift`` quando ele pede que o presente não
    mostre preço, e propagada ao pedido pela lista explícita do
    ``CommitService``. Ninguém no balcão liga ou desliga isso.

    **O piso: o que se COBRA na porta não é valor do presente, é instrução.**
    Enquanto há dinheiro a receber na entrega, o papel tem de dizer quanto
    receber e quanto de troco levar. Esconder isso não protege surpresa
    nenhuma — manda o entregador para a porta sem saber o que cobrar, e a saída
    dele é perguntar, que é exatamente o que o presente queria evitar. Então o
    filtro não se aplica, e o log diz por quê.
    """
    data = getattr(order, "data", None) or {}
    if data.get("gift_hide_values") is not True:
        return False

    payment = data.get("payment") if isinstance(data.get("payment"), dict) else {}
    if _charging_at_the_door(order, payment):
        # ⚠️ A razão ANTES do retorno, como na via do entregador: quem lê o log
        # precisa saber que o valor saiu no papel de um presente e que não foi
        # descuido de ninguém. Sem esta linha a correção iria para o lugar
        # errado — alguém mexeria no leiaute em vez de olhar a cobrança.
        logger.warning(
            "Valores VISÍVEIS no pedido %s: o cliente pediu presente sem valores "
            "(gift_hide_values), mas ainda há cobrança na entrega. Quanto cobrar e o "
            "troco saem no papel — o entregador não pode chegar à porta sem isso.",
            getattr(order, "ref", "?"),
        )
        return False
    return True


def _charging_at_the_door(order, payment: dict) -> bool:
    """Ainda há dinheiro para entrar NA PORTA deste pedido?

    Pergunta ao dono da resposta (``receipt_escpos``), que é quem os papéis com
    valor já consultam para imprimir o bloco de cobrança. Um segundo cálculo
    aqui apareceria como o entregador cobrando um valor que o papel não traz.
    """
    from shopman.backstage.services import receipt_escpos
    from shopman.shop.services import payment as payment_svc

    paid = (payment_svc.get_payment_status(order) or "") in {"captured", "paid"}
    return receipt_escpos._charging_at_the_door(order, payment, paid=paid)


@dataclass(frozen=True)
class DisclosureFilter:
    """Um filtro de divulgação: o que a via deixa de mostrar, e por decisão de quem.

    Os dois filtros têm a mesma forma de propósito. Eles não são casos
    especiais de vias diferentes — são a mesma pergunta feita ao mesmo lugar:
    **o pedido**. ``resolve`` recebe o pedido e só o pedido, e é isso que os
    mantém ortogonais à via e entre si.

    ``label`` é o que a tela diz quando o filtro está ligado, para o operador
    saber qual papel vai pegar antes do gesto.
    """

    key: str
    label: str
    #: Onde a derivação mora, para quem for mudá-la não procurar aqui.
    source: str
    resolve: Callable[[object], bool]


#: A família. Ordem = ordem em que os rótulos aparecem na tela.
FILTERS: tuple[DisclosureFilter, ...] = (
    DisclosureFilter(
        key=FILTER_CUSTOMER_IDENTITY,
        label="sem identificação do cliente",
        source="shop.services.order_helpers.courier_ticket_variant",
        resolve=_customer_identity_is_hidden,
    ),
    DisclosureFilter(
        key=FILTER_VALUES,
        label="sem valores",
        source='Order.data["gift_hide_values"]',
        resolve=_values_are_hidden,
    ),
)

#: Índice por chave.
FILTERS_BY_KEY: dict[str, DisclosureFilter] = {item.key: item for item in FILTERS}


@dataclass(frozen=True)
class OrderDocument:
    """Uma via do pedido, como ela é declarada — antes de encontrar um pedido.

    ``permission`` é o codename Django exigido para pegar este papel, e ele é
    por via de propósito: o recibo é documento do CAIXA
    (``cashman.operate_pos``), a Via Encomenda é de quem cuida da FILA
    (``shop.manage_orders``) e a Via Cozinha é do posto de preparo
    (``backstage.operate_kds``). Colapsar os três daria a quem opera o caixa o
    endereço do cliente de qualquer pedido da casa — e à cozinha, o recibo da
    venda.

    ``print_stamp_key`` é a chave em ``Order.data`` que registra a PRIMEIRA
    composição desta via. ``filtered_print_stamp_keys`` guarda a chave própria
    de uma combinação de filtros, quando ela existe.

    ⚠️ **As chaves não se unificam, e o motivo é a FASE.** A Via Encomenda é um
    papel só, mas ela é composta duas vezes na vida: uma para ficar no painel e
    outra para viajar com a sacola. "A ficha já ter ido para o painel não faz da
    primeira via do entregador uma segunda" — se as duas dividissem carimbo, a
    primeira via que sai pela porta nasceria marcada como reimpressão de um
    papel que ninguém segurou. Hoje as duas composições são dois compositores
    (``order_ticket`` e ``courier_ticket``); o dia em que forem um só, as duas
    chaves continuam sendo duas, porque a pergunta "este papel já saiu para ESTE
    destino?" continua sendo duas perguntas.

    ``route_name`` vazio significa **via sem papel ainda**. Ela consta do
    registro porque o catálogo é a decisão; o papel é a migração, que vem
    depois, uma via por vez. :func:`documents_for` não oferece via sem papel —
    botão que responde 404 é pior do que botão ausente.

    ``alternate_surface`` nomeia a superfície alternativa desta via quando a
    impressora falha. Só o recibo tem uma (``PosReceipt.vue`` +
    ``presentation/receipt.ts``), e isso é deliberado: há um recibo DESENHADO na
    tela para o diálogo do navegador imprimir, e é ele também que o cliente vê.
    As outras vias não têm gêmea em HTML porque inventar uma criaria um segundo
    leiaute com um segundo dono — o que a docstring de ``receipt_escpos``
    proíbe. Vazio aqui quer dizer "sem impressora, sem papel", e a tela precisa
    dizer isso alto em vez de cair em silêncio.
    """

    key: str
    label: str
    audience: str
    permission: str
    print_stamp_key: str
    contexts: tuple[str, ...]
    #: A que filtros esta via está sujeita. Vazio é declaração, não esquecimento.
    filters: tuple[str, ...] = ()
    #: ``{chave do filtro: chave do carimbo}`` quando a via, sob aquele filtro,
    #: sai para outro destino e por isso tem carimbo próprio.
    filtered_print_stamp_keys: dict[str, str] = field(default_factory=dict)
    route_name: str = ""
    #: ``{chave do filtro: rota}`` quando a via, sob aquele filtro, é composta
    #: por outra rota — hoje verdade, e provisório: é o que a migração junta.
    filtered_route_names: dict[str, str] = field(default_factory=dict)
    alternate_surface: str = ""

    @property
    def has_paper(self) -> bool:
        """Esta via já tem um papel que alguém consegue imprimir?"""
        return bool(self.route_name)


@dataclass(frozen=True)
class OfferedDocument:
    """Uma via JÁ resolvida contra um pedido — o que a tela recebe.

    ``applied_filters`` é o que esta via deixa de mostrar neste pedido.
    ``print_stamp_key`` e ``route_name`` já vêm resolvidos para a combinação de
    filtros: a tela não escolhe rota, ela recebe a que corresponde ao papel que
    o servidor decidiu.
    """

    key: str
    label: str
    audience: str
    permission: str
    print_stamp_key: str
    route_name: str
    applied_filters: frozenset[str]
    filter_labels: tuple[str, ...]
    alternate_surface: str

    @property
    def headline(self) -> str:
        """O rótulo pronto: a via, e o que ela deixa de mostrar."""
        if not self.filter_labels:
            return self.label
        return f"{self.label} — {', '.join(self.filter_labels)}"

    @property
    def hides_customer_identity(self) -> bool:
        return FILTER_CUSTOMER_IDENTITY in self.applied_filters

    @property
    def hides_values(self) -> bool:
        return FILTER_VALUES in self.applied_filters

    @property
    def has_alternate_surface(self) -> bool:
        return bool(self.alternate_surface)


#: O registro. Ordem = ordem de oferta na tela: de dentro da casa para fora.
DOCUMENTS: tuple[OrderDocument, ...] = (
    OrderDocument(
        key=KITCHEN,
        label="Via Cozinha",
        audience="quem prepara o pedido",
        # A cozinha tem permissão PRÓPRIA, e ela não é a do Gestor nem a do
        # caixa: o grupo "Cozinha" tem `backstage.operate_kds` e não tem as
        # outras duas. É a separação mais dura das três — o posto de preparo
        # não alcança endereço de cliente nem recibo de venda.
        permission="backstage.operate_kds",
        print_stamp_key="kitchen_ticket_printed_at",
        contexts=(CONTEXT_KITCHEN_STATION,),
        # Sujeita a filtro nenhum, e isso é declaração: o papel fica no posto,
        # e o que ele mostra do cliente (o nome pelo qual a cozinha chama o
        # pedido, a observação que muda o preparo) é o que faz o preparo
        # acontecer. Valor não entra — preço na cozinha não decide nada e
        # atravanca a leitura de longe.
        filters=(),
        # ⚠️ Sem papel ainda. O KDS existe em tela (`projections/kds.py`); o
        # posto com impressora e sem tela é o caso que ainda não foi servido.
        # A chave do carimbo já está reservada acima para a migração não ter de
        # escolher um nome sob pressão — e para ninguém escolher outro.
        route_name="",
    ),
    OrderDocument(
        key=ORDER,
        label="Via Encomenda",
        audience="o painel da casa, e depois quem leva a mercadoria",
        permission="shop.manage_orders",
        print_stamp_key="ticket_printed_at",
        contexts=(CONTEXT_ORDER_PANEL, CONTEXT_ORDER_CARD, CONTEXT_DISPATCH),
        # A única via sujeita aos dois filtros, e não por acaso: é a única que
        # sai da casa carregando tudo — contato, endereço e dinheiro.
        filters=(FILTER_CUSTOMER_IDENTITY, FILTER_VALUES),
        # Com a identificação filtrada, a via viaja na mão de um terceiro: outro
        # destino, outro carimbo. Ver a nota sobre FASE em `OrderDocument`.
        filtered_print_stamp_keys={FILTER_CUSTOMER_IDENTITY: "courier_ticket_printed_at"},
        route_name="api-backstage-order-ticket-escpos",
        filtered_route_names={
            FILTER_CUSTOMER_IDENTITY: "api-backstage-order-courier-ticket-escpos",
        },
    ),
    OrderDocument(
        key=RECEIPT,
        label="Via Recibo",
        audience="quem pagou",
        # O recibo é documento do CAIXA. É a permissão que impede que a via de
        # quem pagou seja tratada como mais um papel do pedido.
        permission="cashman.operate_pos",
        print_stamp_key="receipt_printed_at",
        contexts=(CONTEXT_POS_CHECKOUT, CONTEXT_POS_RECENT_SALES, CONTEXT_ORDER_CARD),
        # Sujeita a filtro nenhum, e também por declaração: o dado do cliente no
        # papel do próprio cliente não é divulgação, e sem os valores o recibo
        # deixa de ser recibo. Quem paga o presente é quem compra — o filtro de
        # valores protege o destinatário, que não recebe esta via.
        filters=(),
        route_name="api-backstage-pos-receipt-escpos",
        alternate_surface="pos_receipt_html",
    ),
)

#: Índice por chave, para quem já sabe qual via quer.
BY_KEY: dict[str, OrderDocument] = {document.key: document for document in DOCUMENTS}


def applied_filters(order, document: OrderDocument) -> frozenset[str]:
    """Que filtros estão ligados nesta via, neste pedido.

    **Derivado, nunca escolhido.** Quem imprime não opina: cada filtro pergunta
    ao pedido, e a via só declara se está sujeita a ele.
    """
    return frozenset(
        item.key
        for item in FILTERS
        if item.key in document.filters and item.resolve(order)
    )


def _resolve_by_filters(base: str, overrides: dict[str, str], applied: frozenset[str]) -> str:
    """A rota (ou o carimbo) que corresponde aos filtros ligados.

    Hoje há no máximo um override por via, e um ``for`` honesto é melhor do que
    uma chave composta que finge prever combinações que ainda não existem. Se um
    dia duas combinações pedirem destinos diferentes, é aqui que se decide — num
    lugar só.
    """
    for key, value in overrides.items():
        if key in applied:
            return value
    return base


def documents_for(order, *, context: str, actor) -> list[OfferedDocument]:
    """Que vias fazem sentido para ESTE pedido, NESTA tela, para ESTA pessoa.

    É o coração do que o dono pediu: o sistema oferece a impressão da via
    relevante, conforme o contexto da própria tela. Três filtros, nesta ordem, e
    cada um responde a uma pergunta diferente:

    1. **O contexto** diz com quais vias aquela tela tem o que fazer.
    2. **O papel** existe? Via registrada sem rota é decisão tomada e migração
       pendente — não se oferece botão que responde 404.
    3. **A permissão** é por via. Quem não tem a permissão daquele papel não vê
       o botão; o grupo Cozinha, por exemplo, não alcança nem a Via Encomenda
       nem a Via Recibo.

    Só então os filtros de divulgação são resolvidos, e a via sai com a rota e o
    carimbo que correspondem ao papel que o servidor decidiu.

    ``actor`` é quem está operando (a sessão É do operador — ver
    ``api/permissions.HasBackstagePermission``). Sem pessoa, nada é oferecido:
    falha fechado, porque "não sei quem é" nunca foi autorização.

    ⚠️ **Oferecer não é autorizar.** As rotas continuam conferindo a própria
    permissão; esta função decide o que a TELA mostra. Uma lista de botões não é
    controle de acesso, e no dia em que for, o primeiro caminho que esquecer de
    perguntar vira o buraco.

    ⚠️ **O filtro é do PEDIDO, não da fase.** A Via Encomenda é um papel só, e
    por isso a identificação do cliente é decidida pelo pedido, não por a via
    estar no painel ou na sacola. Num pedido cuja entrega é de terceiro, isso
    significa que a via já nasce sem o nome do cliente — inclusive enquanto está
    pregada na parede. É consequência direta de "um papel só", e é deliberada:
    o dia em que a fase voltar a mudar o conteúdo, ela volta como FASE (um
    argumento aqui), nunca como uma via a mais.
    """
    if actor is None:
        return []

    offered: list[OfferedDocument] = []
    for document in DOCUMENTS:
        if context not in document.contexts:
            continue
        if not document.has_paper:
            continue
        if not actor.has_perm(document.permission):
            continue
        applied = applied_filters(order, document)
        offered.append(
            OfferedDocument(
                key=document.key,
                label=document.label,
                audience=document.audience,
                permission=document.permission,
                print_stamp_key=_resolve_by_filters(
                    document.print_stamp_key, document.filtered_print_stamp_keys, applied
                ),
                route_name=_resolve_by_filters(
                    document.route_name, document.filtered_route_names, applied
                ),
                applied_filters=applied,
                filter_labels=tuple(
                    item.label for item in FILTERS if item.key in applied
                ),
                alternate_surface=document.alternate_surface,
            )
        )
    return offered
