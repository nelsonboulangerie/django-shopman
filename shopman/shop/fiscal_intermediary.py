"""Venda por intermediador: o que é dinheiro da casa, e quem intermediou.

Uma venda por plataforma de terceiro tem **dois donos de dinheiro dentro do
mesmo total**. O ``orderAmount`` do iFood é, pela composição oficial deles,
``subTotal + deliveryFee + additionalFees − benefits``, e a própria plataforma
diz das ``additionalFees`` que "todas representam receita do iFood e não devem
ser adicionadas à nota fiscal". A nota da casa declara a venda da casa — quem
emite é o estabelecimento, o intermediador só intermedeia.

Além do valor, a nota precisa **dizer que houve intermediação**: o Ajuste
SINIEF 22/20 (CONFAZ, efeitos desde abr/2021) pede o ``indIntermed`` e o grupo
``infIntermed`` (CNPJ do intermediador + identificador do cadastro da loja na
plataforma).

**Este módulo é sobre INTERMEDIADOR, não sobre iFood.** O conceito é da nota e
vale para qualquer marketplace; por isso a camada fiscal não ganha nenhum
``if channel == "ifood"``. O que é por plataforma é só a *leitura* do
detalhamento financeiro, porque cada uma entrega o dela com um nome próprio —
e hoje existe uma só, lida aqui pelo nome dela, sem registry plugável para um
segundo consumidor que não existe.

Quem é intermediador não é palpite do código: é a configuração
``settings.SHOPMAN_FISCAL_INTERMEDIARIES`` (canal → CNPJ/identificador), porque
o CNPJ do intermediador é dado do deployment, não do pedido.

**Duas omissões, um único modo de falhar.** Uma venda intermediada pode chegar
aqui faltando duas coisas diferentes, e as duas são graves do mesmo jeito:

- falta a **configuração** do grupo (CNPJ/identificador) → a nota sai fora do
  Ajuste SINIEF 22/20; grita por :func:`missing_configuration`;
- falta o **detalhamento financeiro** que sustenta a base → a nota sai pelo
  total cheio, com a receita da plataforma dentro; grita por
  :func:`unreadable_breakdown`;
- falta saber **quem patrocinou o cupom** → o valor cai no lado errado da base
  (desconto da loja × repasse da plataforma); grita por
  :func:`unattributable_benefits`.

Nenhuma das três pode sair calada, e é fácil que as últimas saiam: elas se
disfarça de "não há o que corrigir". A ausência de registry (correta: não se
cria backend plugável sem dois consumidores reais) não pode virar silêncio no
dia em que um segundo marketplace for declarado — ver
:data:`READABLE_BREAKDOWN_CHANNELS`, que é esse seam, nomeado.
"""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

#: Os canais cujo detalhamento financeiro este módulo sabe LER.
#:
#: ⚠️ **Este é o seam por onde um segundo marketplace entra.** O conceito de
#: intermediador é genérico, mas a *leitura* do detalhamento não pode ser: cada
#: plataforma entrega o dela com um nome próprio. Não há registry plugável
#: porque não há segundo consumidor real — a casa não cria backend plugável
#: para o futuro.
#:
#: O que a ausência de registry **não** pode virar é silêncio. Um canal
#: declarado como intermediado que não esteja aqui é justamente o caso grave:
#: a base da nota não seria corrigida, e a receita da plataforma entraria no
#: documento — o defeito que este módulo existe para consertar, de volta
#: inteiro, para o canal novo. Por isso ele **grita**, em
#: :func:`unreadable_breakdown`.
READABLE_BREAKDOWN_CHANNELS = frozenset({"ifood"})

#: Onde o iFood guarda o detalhamento, dentro de ``Order.data``.
IFOOD_DATA_KEY = "ifood"

#: O valor de ``deliveredBy`` — vocabulário **do iFood** — que responde "sim" à
#: pergunta genérica *o transporte foi da casa?*.
#:
#: A regra fiscal é sobre quem prestou o transporte: entrega da **loja** ⇒ a
#: taxa é receita da loja e consta na nota; entrega da **plataforma** ⇒ não
#: consta, porque nem o serviço nem o dinheiro são da casa. Hoje, na Nelson,
#: todo pedido do iFood é entregue pelo iFood — mas a regra é lida do campo, e
#: não cravada, justamente para que o dia em que a entrega própria for ligada a
#: nota saia certa em vez de errada em silêncio.
#:
#: O nome privado é deliberado: a pergunta da casa é :func:`house_delivered`;
#: esta constante é só a palavra com que UMA plataforma a responde. Um segundo
#: marketplace responderá com outra palavra, e ela entra junto com o leitor do
#: detalhamento dele.
_IFOOD_DELIVERED_BY_HOUSE = "MERCHANT"

#: Quem pagou o cupom — vocabulário **do iFood**, tabela "Sponsorship" da página
#: de Detalhes de pedido do portal do desenvolvedor.
#:
#: A tabela deles não é decoração: ela diz, para cada patrocinador, como o valor
#: deve ser TRATADO, e só um dos quatro é desconto.
#:
#: - ``MERCHANT`` — "trate o valor do cupom como **desconto**": o subsídio é da
#:   loja, o dinheiro não entra, e a base da nota cai.
#: - ``IFOOD`` / ``EXTERNAL`` / ``CHAIN`` — "trate o valor do cupom como
#:   **pagamento**": a plataforma (ou o parceiro, ou a rede) repassa aquele
#:   valor à loja. A loja recebe cheio, e a base da nota **compõe** com ele.
#:
#: Um cupom só pode ter mais de um patrocinador (``sponsorshipValues`` é lista),
#: e aí a divisão é por parcela, não pelo cupom inteiro.
_IFOOD_SPONSOR_HOUSE = "MERCHANT"
_IFOOD_SPONSORS = frozenset({"IFOOD", "MERCHANT", "EXTERNAL", "CHAIN"})

#: Sobre o QUE o cupom incidiu — tabela "Targets" da mesma página.
#:
#: Importa porque desconto de frete e desconto de mercadoria não caem no mesmo
#: lugar da nota: quando o transporte não foi da casa, o frete nem está na base,
#: e abater dele um cupom seria tirar duas vezes.
_IFOOD_TARGETS_GOODS = frozenset({"CART", "ITEM", "PROGRESSIVE_DISCOUNT_ITEM"})
_IFOOD_TARGET_FREIGHT = "DELIVERY_FEE"


def _configured(channel_ref: str) -> dict:
    mapping = dict(getattr(settings, "SHOPMAN_FISCAL_INTERMEDIARIES", {}) or {})
    entry = mapping.get(str(channel_ref or ""))
    return dict(entry) if isinstance(entry, dict) else {}


def _digits(value: object) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _store_profile_name() -> str:
    """O nome da loja, para o ``idCadIntTran`` quando o deployment não o fixou.

    A Nota Técnica 2020.006 define o campo YB03 como "nome do usuário ou
    identificação do perfil do vendedor no site do intermediador", String de 2 a
    60 caracteres, **e a SEFAZ não valida o conteúdo**. Ou seja: o campo é uma
    etiqueta de quem é a loja lá dentro, não uma chave que alguém confere.

    Daí a escolha: o **nome fantasia da loja** (``Shop.name``), que é o mesmo
    nome com que ela aparece no iFood. Não é chute nem valor de teste cravado no
    código — é o nome que o deployment já configurou para tudo mais, e cada
    deployment tem o seu. A env var ``FISCAL_INTERMEDIARY_IFOOD_ID_CAD`` continua
    vencendo, para a loja cujo perfil na plataforma tenha outro nome.

    ⚠️ O que este atalho NÃO faz é deixar o campo vazio por omissão. Enquanto o
    identificador faltava, o grupo inteiro do intermediador não saía e a nota
    ficava fora do Ajuste SINIEF 22/20 — em silêncio, se ninguém lesse o alerta.
    """
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
    except Exception:
        logger.warning("fiscal_intermediary: nome da loja indisponível para o idCadIntTran", exc_info=True)
        return ""
    return str(getattr(shop, "name", "") or "").strip()


def _id_cad_int_tran(entry: dict) -> str:
    """O identificador da loja na plataforma: o configurado, ou o nome da loja."""
    configured = str(entry.get("id_cad_int_tran") or "").strip()
    return (configured or _store_profile_name())[:60]


def is_intermediated(order) -> bool:
    """Esta venda veio por plataforma de terceiro?

    A pergunta é do canal, não do conteúdo do pedido: quem declara que um canal
    é marketplace é o deployment.
    """
    return bool(_configured(getattr(order, "channel_ref", "")))


def intermediary_for(order) -> dict | None:
    """Grupo do intermediador desta venda, ou ``None``.

    ``None`` cobre dois casos diferentes de propósito, e ambos significam "não
    mande o grupo": a casa vendeu direto (canal não intermediado), ou o canal é
    intermediado e **falta configuração** para preencher o grupo.

    Os dois campos são obrigatórios juntos — a Focus NF-e documenta
    ``cnpj_intermediario`` e ``id_intermediario`` como obrigatórios quando
    ``indicador_intermediario = 1``. Meio grupo não é meio-certo: é nota
    recusada. Quando ainda assim faltar (loja sem nome configurado, banco
    indisponível), o grupo não sai — e a ausência **grita**, em
    :func:`missing_configuration`, em vez de virar uma nota silenciosamente fora
    do Ajuste SINIEF 22/20.

    O identificador da loja na plataforma vem de :func:`_id_cad_int_tran`: a env
    var quando o deployment a fixou, o nome fantasia da loja quando não.
    """
    entry = _configured(getattr(order, "channel_ref", ""))
    if not entry:
        return None
    cnpj = _digits(entry.get("cnpj"))
    id_cad = _id_cad_int_tran(entry)
    if len(cnpj) != 14 or len(id_cad) < 2:
        return None
    return {"cnpj": cnpj, "id_cad_int_tran": id_cad}


def missing_configuration(order) -> str:
    """Por que o grupo do intermediador não pode ser montado nesta venda.

    ``""`` quando não há nada faltando (inclusive quando a venda não é
    intermediada). Texto para humano quando falta — é o que o alerta do
    operador mostra.
    """
    entry = _configured(getattr(order, "channel_ref", ""))
    if not entry:
        return ""
    missing = []
    if len(_digits(entry.get("cnpj"))) != 14:
        missing.append("CNPJ do intermediador (14 dígitos)")
    if len(_id_cad_int_tran(entry)) < 2:
        missing.append(
            "identificador do cadastro da loja na plataforma (idCadIntTran, 2 a 60 caracteres): "
            "a loja está sem nome fantasia e FISCAL_INTERMEDIARY_IFOOD_ID_CAD está vazia"
        )
    return ", ".join(missing)


def house_delivered(order) -> bool:
    """O transporte desta venda foi da CASA, e não da plataforma?

    Numa **venda direta** é sempre da casa: não há plataforma para entregar, e
    o entregador é da padaria ou contratado por ela. Numa venda **intermediada**
    a resposta vem do campo — a pergunta é genérica, a palavra que a responde é
    de cada plataforma.

    Quem pergunta isto são dois: a base da nota (frete da casa entra, frete da
    plataforma não) e o grupo do transportador (a padaria só se declara
    transportadora do que ela transportou).
    """
    if not is_intermediated(order):
        return True
    data = (order.data or {}).get(IFOOD_DATA_KEY) or {}
    return str(data.get("delivered_by") or "").strip().upper() == _IFOOD_DELIVERED_BY_HOUSE


def _house_share_of(benefit: dict) -> tuple[int, str]:
    """Quanto DESTE cupom saiu do bolso da loja, e por que não deu para saber.

    O segundo item é ``""`` quando deu. Quando não deu, a parcela devolvida é
    **zero** — de propósito: não saber quem pagou o cupom não pode virar um
    desconto na nota, porque desconto que não houve é subdeclaração. O erro
    para o lado de declarar a mais, e grita.
    """
    value_q = benefit.get("value_q")
    if not isinstance(value_q, int) or value_q < 0:
        return 0, "cupom sem valor legível"
    shares = benefit.get("sponsorships")
    if not isinstance(shares, list) or not shares:
        return 0, "cupom sem patrocinador declarado"
    house_q = 0
    declared_q = 0
    for share in shares:
        if not isinstance(share, dict):
            return 0, "patrocínio ilegível"
        amount = share.get("value_q")
        if not isinstance(amount, int) or amount < 0:
            return 0, "patrocínio sem valor legível"
        sponsor = str(share.get("sponsor") or "").strip().upper()
        if sponsor not in _IFOOD_SPONSORS:
            return 0, f"patrocinador desconhecido ({sponsor or 'vazio'})"
        declared_q += amount
        if sponsor == _IFOOD_SPONSOR_HOUSE:
            house_q += amount
    if declared_q != value_q:
        return 0, "a soma dos patrocínios não fecha com o valor do cupom"
    return house_q, ""


def house_discounts(order) -> dict:
    """O que os cupons DESTA venda tiraram do bolso da loja, por onde incidiram.

    ``{"goods_q", "freight_q", "unreadable"}``. Só o cupom patrocinado pela
    **loja** entra: ele é desconto e derruba a base. O cupom patrocinado pelo
    iFood, por parceiro externo ou pela rede é **repasse** — a loja recebe
    cheio, e a plataforma manda o dinheiro na conciliação —, então ele compõe a
    base em vez de reduzi-la. Quem diz isso não é interpretação nossa: é a
    tabela "Sponsorship" do portal do iFood, que para cada patrocinador prescreve
    "trate como desconto" ou "trate como pagamento".

    ``unreadable`` é o motivo de a atribuição não ter fechado, ``""`` quando
    fechou. Não é informação de log: é o gatilho do grito, porque cupom não
    atribuído é a diferença entre a nota certa e uma nota que declara a menos.
    """
    facts = (order.data or {}).get(IFOOD_DATA_KEY) or {}
    benefits = facts.get("benefits")
    declared_q = max(0, int(((facts.get("totals") or {}).get("benefits_q")) or 0))

    if not isinstance(benefits, list) or not benefits:
        if declared_q:
            return {"goods_q": 0, "freight_q": 0, "unreadable": (
                f"o pedido tem R$ {declared_q / 100:.2f} de cupom no total, e nenhum "
                "detalhamento de patrocínio para dizer se saiu do bolso da loja (desconto) "
                "ou se é repasse da plataforma (pagamento)"
            )}
        return {"goods_q": 0, "freight_q": 0, "unreadable": ""}

    goods_q = freight_q = 0
    listed_q = 0
    reasons: list[str] = []
    for benefit in benefits:
        if not isinstance(benefit, dict):
            reasons.append("cupom ilegível")
            continue
        value_q = benefit.get("value_q")
        listed_q += value_q if isinstance(value_q, int) and value_q > 0 else 0
        target = str(benefit.get("target") or "").strip().upper()
        share_q, reason = _house_share_of(benefit)
        if reason:
            reasons.append(reason)
            continue
        if not share_q:
            continue
        if target == _IFOOD_TARGET_FREIGHT:
            freight_q += share_q
        elif target in _IFOOD_TARGETS_GOODS:
            goods_q += share_q
        else:
            # Alvo desconhecido: não dá para saber se o cupom bateu na
            # mercadoria ou no frete, e os dois caem em lugares diferentes da
            # nota. Não abate, e grita.
            reasons.append(f"alvo de cupom desconhecido ({target or 'vazio'})")

    if declared_q and listed_q != declared_q:
        reasons.append(
            f"a soma dos cupons detalhados (R$ {listed_q / 100:.2f}) não fecha com o "
            f"cupom do total do pedido (R$ {declared_q / 100:.2f})"
        )
    return {"goods_q": goods_q, "freight_q": freight_q, "unreadable": "; ".join(reasons)}


def unattributable_benefits(order) -> str:
    """Por que o cupom desta venda intermediada não pôde ser atribuído. GRITA.

    Terceira irmã de :func:`missing_configuration` e
    :func:`unreadable_breakdown`, e existe pelo mesmo motivo que elas: a
    omissão que sai calada é a cara. Cupom sem patrocinador conhecido é tratado
    como repasse (não abate a base), o que declara **a mais** — seguro para o
    fisco, errado para a loja, e invisível se ninguém falar.
    """
    if not is_intermediated(order):
        return ""
    if str(getattr(order, "channel_ref", "") or "") not in READABLE_BREAKDOWN_CHANNELS:
        # Canal sem leitor já grita inteiro em unreadable_breakdown().
        return ""
    return house_discounts(order)["unreadable"]


def unreadable_breakdown(order) -> str:
    """Por que a base desta venda intermediada NÃO pôde ser corrigida. GRITA.

    ``""`` quando não há nada a dizer — e são dois silêncios **diferentes**,
    os dois legítimos:

    - **Venda direta.** Não é intermediada; não há base a corrigir.
    - **Pedido do iFood sem o detalhamento** (simulação de dev, payload
      antigo). Este é silêncio *merecido*, não suposto: sem ``totals``, o
      ``ifood_ingest`` monta ``total_q`` a partir da soma dos itens
      (``total_q = order_amount_q or items_subtotal_q``) — ou seja, não há
      receita de plataforma dentro dele, e a base já está certa.

    O que NÃO é silêncio é o caso que a ausência de registry criaria: canal
    declarado como intermediado que este módulo **não sabe ler**. Aí a base
    ficaria sem correção com a receita da plataforma dentro dela, que é
    exatamente o defeito de origem — e ele voltaria mudo, para o canal novo.
    """
    if not is_intermediated(order):
        return ""
    channel = str(getattr(order, "channel_ref", "") or "")
    if channel in READABLE_BREAKDOWN_CHANNELS:
        return ""
    return (
        f"o canal '{channel}' está declarado como intermediado em "
        "SHOPMAN_FISCAL_INTERMEDIARIES, mas shopman.shop.fiscal_intermediary não "
        "sabe ler o detalhamento financeiro dele (hoje só o iFood tem leitor). "
        "Sem isso a base da nota não é corrigida e a receita da plataforma entra "
        "no documento"
    )


def issues_as_presential(order, *, requested_tax_id: str) -> bool:
    """Esta entrega intermediada sai como NFC-e PRESENCIAL, sem destinatário?

    Decisão do dono (24/09/2026), praxe do mercado (ERPs de restaurante fazem
    assim); a confirmação do contador fica registrada como pendência dele.

    A nota de entrega a domicílio (``indPres=4``) exige destinatário
    identificado (E01-20 → 787) e endereço (E05-20 → 788), as duas vivas. O
    transportador NÃO é mais exigido: a X03-20 (rejeição 786) foi desabilitada
    pela NT 2023.004, seção 2.3.2, em produção desde 01/07/2024 — o que não
    muda esta decisão, porque quem a sustenta são o destinatário e o endereço.
    O marketplace só repassa o documento quando o cliente pede
    a nota — o caso comum é chegar sem CPF, e o cliente já foi embora com o
    pedido fechado no app de outro. Nesse caso a venda é declarada como
    **presencial** (``indPres=1``), consumidor não identificado, sem endereço,
    sem frete e sem transportador. A taxa de entrega que foi da casa não some
    da nota: vira **outras despesas** (``vOutro``), para o total bater com o que
    o cliente pagou à casa.

    **Só vale para canal intermediado.** Nos canais próprios (loja, PDV,
    WhatsApp) o dono decidiu o contrário: o CPF é exigido na ENTRADA do pedido
    de entrega, e entrega sem ele continua recusada e gritando. Com documento,
    a venda intermediada segue a nota de entrega completa.

    ``requested_tax_id`` é o documento PEDIDO para esta nota (``fiscal.tax_id``),
    nunca o do cadastro. Documento informado e inválido **não** entra aqui: é
    pedido de nota com dado errado, e a recusa ruidosa do adapter continua
    sendo a resposta certa.
    """
    if not is_intermediated(order):
        return False
    if (order.data or {}).get("fulfillment_type") != "delivery":
        return False
    return not _digits(requested_tax_id)


def seller_amounts(order) -> dict | None:
    """A base da nota desta venda intermediada: ``{"base_q", "freight_q"}``.

    ``None`` = **nada a corrigir**, e a nota segue pelo total do pedido. Os
    casos em que isso é verdade — e o caso em que parece verdade e não é —
    estão em :func:`unreadable_breakdown`, que é quem grita pelo último.
    Sozinha, esta função nunca inventa número.

    ``base_q`` é o que a nota declara: o total do pedido **menos** a receita da
    plataforma, e menos a taxa de entrega quando quem entregou foi a
    plataforma. ``freight_q`` é a taxa que sobra para a nota — zero quando não
    é da casa.

    ⚠️ ``Order.total_q`` continua sendo o total do PEDIDO (o que o cliente
    pagou ao iFood), e nada aqui o altera: B.I., fechamento e telas leem o
    total do pedido e ele não mudou de significado. O que muda é só a base
    **da nota**.
    """
    if not is_intermediated(order):
        return None
    if str(getattr(order, "channel_ref", "") or "") not in READABLE_BREAKDOWN_CHANNELS:
        # Canal intermediado sem leitor: não há o que calcular, e o silêncio
        # daqui é coberto pelo grito de unreadable_breakdown().
        return None

    totals = (((order.data or {}).get(IFOOD_DATA_KEY) or {}).get("totals") or {})
    order_amount_q = int(totals.get("order_amount_q") or 0)
    if order_amount_q <= 0:
        return None

    additional_fees_q = max(0, int(totals.get("additional_fees_q") or 0))
    delivery_fee_q = max(0, int(totals.get("delivery_fee_q") or 0))
    benefits_q = max(0, int(totals.get("benefits_q") or 0))

    # A mercadoria, ANTES de qualquer cupom. O ``orderAmount`` já vem com todos
    # os cupons descontados, e nem todos são desconto: por isso a conta parte da
    # mercadoria cheia e desconta só o que a loja bancou.
    subtotal_q = max(0, int(totals.get("subtotal_q") or 0))
    goods_q = subtotal_q or (order_amount_q - delivery_fee_q - additional_fees_q + benefits_q)

    discounts = house_discounts(order)
    freight_q = delivery_fee_q if house_delivered(order) else 0
    # O que sai da base: a receita da plataforma, sempre; a taxa de entrega
    # quando o transporte não foi da casa; e o cupom que a LOJA patrocinou.
    # O cupom patrocinado pelo iFood, por parceiro externo ou pela rede fica —
    # a plataforma repassa aquele valor e a loja recebe cheio, então ele
    # **compõe** a base em vez de reduzi-la.
    base_q = goods_q - discounts["goods_q"]
    if freight_q:
        # Cupom de frete só abate onde o frete existe. Entrega da plataforma
        # não traz o frete para a base, e abater o cupom dele tiraria duas vezes.
        base_q += freight_q - discounts["freight_q"]
    return {"base_q": base_q, "freight_q": freight_q}


__all__ = [
    "IFOOD_DATA_KEY",
    "READABLE_BREAKDOWN_CHANNELS",
    "house_delivered",
    "house_discounts",
    "intermediary_for",
    "is_intermediated",
    "issues_as_presential",
    "missing_configuration",
    "seller_amounts",
    "unattributable_benefits",
    "unreadable_breakdown",
]
