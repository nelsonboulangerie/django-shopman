"""Inventário de privacidade — quem recebe dado do cliente, declarado ao lado da PROVA.

## Por que este arquivo existe

A política de privacidade dizia, com estas palavras: *"Hoje são estes, e é a lista
inteira"*. Em 23/09/2026 a varredura achou **cinco operadores fora da lista**, um deles
recebendo o IP do titular em HTTP puro. Nenhum deles entrou por má-fé: entraram por
commits legítimos, meses depois de o texto ter sido escrito, e ninguém tinha como saber
que aquele parágrafo dependia deles.

Esse é o ponto. **Texto que COPIA a verdade envelhece em silêncio; texto que EXIBE a
verdade não tem como.** Aqui a lista deixa de ser prosa numa página e passa a ser dado
derivado do mesmo lugar que decide o tráfego de verdade — os registries de adapter em
`config/settings.py`. Ligar um adapter novo muda a página no mesmo commit.

## O que este arquivo NÃO consegue garantir sozinho

Ele cobre o terceiro que recebe dado **pelo servidor**. Não alcança o que o NAVEGADOR
do cliente busca direto (fonte, mapa, script) — isso é do lado da superfície, e tem
trava irmã em `surfaces/storefront-nuxt/tests/privacyInventory.test.ts`.

A trava deste lado vive em `shopman/shop/tests/test_privacy_inventory.py`, e a regra é:
**todo adapter que fala com a internet precisa estar reivindicado por um operador
declarado aqui, ou constar da isenção com motivo escrito.** Adapter novo reprova até
alguém declarar o que ele manda para fora — que é exatamente a conversa que não
aconteceu nas cinco vezes em que a lista defasou.

## A IA não mora em `settings`: mora nas conexões

Quem recebe a mensagem do cliente para um modelo ler não é decidido por adapter nem por
setting, e sim pelas `AIConnection` do banco e pelas rotas de `Shop.ai_routes` (a porta
`shopman/shop/ai.py`). Ler um sinal de `settings` aqui seria copiar a verdade de novo:
em 16/11/2026 o dono trocou a Anthropic pelo Jev (TypeSafe) com a DeepSeek (D-040), e a
página continuaria dizendo "Anthropic", porque o sinal dela era a chave liga-desliga da
Concierge. Por isso o operador de IA sai de `ai.resolve`, a mesma função que decide para
onde o texto vai: um provedor aparece quando um caminho que leva mensagem de cliente
roda neste deployment e a rota dele resolve para uma conexão do provedor, liberada para
isso. A frase de cada um diz o que AQUELE caminho manda (`AI_USES`), medido no código
que monta o pedido. Conexão liberada cujo provedor não
tem operador declarado em `AI_PROCESSORS` é defeito (`undeclared_ai_connections`), e a
página a mostra mesmo assim, pelo nome que a casa deu a ela: omitir é a mentira que
este arquivo existe para impedir.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlparse

from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Processor:
    """Um terceiro que recebe dado do cliente.

    `role` e `shares` são o texto que o CLIENTE lê. Ficam aqui, e não na página, porque
    quem sabe o que sai é quem escreveu a integração — e porque assim a frase e a prova
    envelhecem juntas ou não envelhecem.
    """

    key: str
    name: str
    #: O que ele faz, em uma frase que a pessoa entende sem saber o que é um adapter.
    role: str
    #: Que dado do cliente sai daqui para lá. Específico: "telefone", não "dados".
    shares: str
    #: Os sinais na configuração que provam que ele está LIGADO neste deployment.
    #: Formato: `"setting:NOME"` ou `"setting:NOME[chave][subchave]"`. Os operadores de
    #: IA nascem de `active_ai_processors` com `"ai:<propósito>:<conexão>"`, a rota que
    #: os ligou.
    wired_by: tuple[str, ...]
    #: Os adapters de `shopman/shop/adapters/` que falam com ele. É por aqui que a
    #: trava sabe que um módulo novo já tem dono declarado.
    adapters: tuple[str, ...] = ()


#: O catálogo declarado. Ordem: pagamento, mensagem, fiscal, endereço, entrega, canal,
#: infraestrutura — que é mais ou menos a ordem em que o cliente encontra cada um.
PROCESSORS: tuple[Processor, ...] = (
    Processor(
        key="efi",
        name="Efí",
        role="recebe o pagamento por Pix",
        shares="o valor e o identificador da cobrança (nada que diga quem você é)",
        wired_by=("setting:SHOPMAN_PAYMENT_ADAPTERS[pix]",),
        adapters=("payment_efi",),
    ),
    Processor(
        key="stripe",
        name="Stripe",
        role="recebe o pagamento por cartão",
        shares=(
            "o valor. O número do cartão você digita na tela da própria Stripe: "
            "ele não passa pela loja"
        ),
        wired_by=("setting:SHOPMAN_PAYMENT_ADAPTERS[card]",),
        adapters=("payment_stripe",),
    ),
    Processor(
        key="manychat",
        name="ManyChat",
        role="entrega as mensagens no WhatsApp",
        shares=(
            "o seu telefone e o contexto do pedido, que ficam guardados na sua ficha "
            "de contato lá dentro"
        ),
        # O login pelo WhatsApp também passa pelo ManyChat (o Flow chama o webhook de
        # entrada), com ou sem notificação ligada: sem este sinal, um deployment que
        # oferece "Entre pelo WhatsApp" omitia a Meta/ManyChat da lista (beta 05/11, LOJA-08).
        wired_by=(
            "setting:SHOPMAN_NOTIFICATION_ADAPTERS[whatsapp]",
            "setting:MANYCHAT_WEBHOOK_SECRET",
        ),
        adapters=("notification_manychat", "notification_whatsapp", "otp_manychat", "marketing_delivery_whatsapp"),
    ),
    Processor(
        key="comtele",
        name="Comtele",
        role="entrega o código de acesso por SMS",
        shares="o seu telefone e o código",
        wired_by=("setting:DOORMAN[DELIVERY_SENDERS][sms]",),
        adapters=("otp_sms_comtele", "otp_sms_twilio", "notification_sms"),
    ),
    Processor(
        key="email",
        name="o serviço de e-mail da loja",
        role="entrega e-mail de confirmação, segunda via e código de acesso",
        shares="o seu e-mail e o conteúdo da mensagem",
        wired_by=("setting:MAILERS[default][BACKEND]",),
        adapters=("notification_email",),
    ),
    Processor(
        key="focusnfe",
        name="Focus NFe",
        role="transmite a nota fiscal para a Secretaria da Fazenda",
        shares=(
            "o que a nota exige quando você pede CPF nela: nome, CPF e, na entrega, "
            "endereço, telefone e e-mail"
        ),
        wired_by=("setting:SHOPMAN_FISCAL_ADAPTER",),
        adapters=("fiscal_focusnfe",),
    ),
    Processor(
        key="google_maps",
        name="Google Maps",
        role="completa e localiza o endereço de entrega",
        shares="o endereço que você digita",
        wired_by=("setting:GOOGLE_MAPS_API_KEY",),
    ),
    Processor(
        key="courier_machine",
        name="a empresa de entrega",
        role="leva o pedido até você quando a entrega é terceirizada",
        shares="o seu nome, o seu telefone e o endereço da entrega",
        wired_by=("setting:SHOPMAN_COURIER_ADAPTER",),
        adapters=("courier_machine", "courier_mock"),
    ),
    Processor(
        key="ifood",
        name="iFood",
        role="é por onde o pedido chega, quando você pede por lá",
        shares=(
            "nada da loja para o iFood: são os seus dados do iFood que chegam aqui, "
            "e o que vale lá é a política deles"
        ),
        wired_by=("setting:SHOPMAN_IFOOD[merchant_id]", "setting:SHOPMAN_IFOOD[client_id]"),
    ),
    Processor(
        key="digitalocean",
        name="DigitalOcean",
        role="hospeda o sistema e o banco de dados da loja, em servidores nos Estados Unidos",
        shares=(
            "tudo o que a loja guarda sobre você, porque é lá que ela guarda. Os dados "
            "viajam e ficam gravados cifrados"
        ),
        # Hospedagem não tem adapter: é o chão. O sinal é o ambiente declarado no spec de
        # deploy (`.do/*.yaml`); na máquina de quem desenvolve ele vale `development`, e
        # nada sai de casa. O país da frase está amarrado à `region` dos specs por
        # `test_hospedagem_declara_o_pais_dos_specs_de_deploy`.
        wired_by=("setting:SHOPMAN_ENVIRONMENT",),
    ),
    Processor(
        key="sentry",
        name="Sentry",
        role="recebe o relatório quando uma tela dá erro, para a loja consertar",
        shares=(
            "a falha e a tela em que ela aconteceu. Endereço, telefone e e-mail são "
            "removidos antes de sair"
        ),
        wired_by=("setting:SENTRY_DSN",),
    ),
)

#: Adapters que falam com a internet e NÃO recebem dado de cliente. Cada linha é uma
#: isenção declarada: se um deles passar a mandar dado do titular, a linha vira mentira
#: e alguém tem de mexer aqui de propósito.
ADAPTERS_SEM_DADO_DE_CLIENTE: dict[str, str] = {
    "catalog_projection_ifood": "publica o CARDÁPIO no iFood; nenhum dado de cliente",
    "catalog_projection_meta": "publica o CARDÁPIO na Meta; nenhum dado de cliente",
    "catalog_projection_google": "publica o CARDÁPIO no Google; nenhum dado de cliente",
    "marketing_delivery_meta": "publica anúncio PÚBLICO; não recebe destinatário",
    "marketing_delivery_facebook": "publica anúncio PÚBLICO; não recebe destinatário",
    "marketing_delivery_instagram": "publica anúncio PÚBLICO; não recebe destinatário",
    "marketing_delivery_tiktok": "publica anúncio PÚBLICO; não recebe destinatário",
    "marketing_delivery_google": "publica anúncio PÚBLICO; não recebe destinatário",
    # O mock cita URL de exemplo no código e nunca chama ninguém; `courier_mock` idem,
    # mas ele já é reivindicado pelo operador de entrega, para o dia em que a casa
    # trocar o adapter sem lembrar da política.
    "payment_mock": "simulador local; a URL no arquivo é exemplo, não destino",
}


#: Valores que existem mas não falam com a internet. Um deployment com o backend de
#: console não manda e-mail para lugar nenhum, e declarar um operador ali seria mentira
#: na direção contrária — assustar o cliente com terceiro que não recebe nada.
_NAO_SAI_DA_CASA = ("console", "locmem", "dummy", "mock", "filebased", "development")


def _setting_value(expression: str):
    """O valor de `SENTRY_DSN`, `SHOPMAN_IFOOD[merchant_id]` ou `DOORMAN[A][B]` (None se falta)."""
    name, _, resto = expression.partition("[")
    value = getattr(settings, name.strip(), None)
    for chave in (parte.strip() for parte in resto.split("]") if parte.strip()):
        if not isinstance(value, dict):
            return None
        value = value.get(chave.lstrip("["))
    return value


def _setting_is_set(expression: str) -> bool:
    """Resolve `SENTRY_DSN`, `SHOPMAN_IFOOD[merchant_id]` e `DOORMAN[A][B]`."""
    value = _setting_value(expression)
    if isinstance(value, str):
        alvo = value.lower()
        if any(marca in alvo for marca in _NAO_SAI_DA_CASA):
            return False
    return bool(value)


def _wired(processor: Processor) -> bool:
    for signal in processor.wired_by:
        kind, _, target = signal.partition(":")
        if kind == "setting" and _setting_is_set(target):
            return True
    return False


def active_processors() -> tuple[Processor, ...]:
    """Os operadores que ESTE deployment de fato usa.

    A loja não deve declarar ao cliente um terceiro que ela não usa: seria verdadeiro no
    catálogo e falso na vida dele. Quem decide é a configuração que roteia o tráfego: as
    settings para os adapters, as conexões e rotas de IA para os provedores de modelo.
    """
    return tuple(processor for processor in PROCESSORS if _wired(processor)) + active_ai_processors()


# ── IA: o operador sai das conexões e das rotas ──────────────────────────────


@dataclass(frozen=True)
class AIProcessor:
    """Um provedor de IA que pode receber a mensagem do cliente.

    Não tem `wired_by` nem `shares` fixos, como o `Processor`: quem o liga é uma
    `AIConnection` (reconhecida pelo endereço dela), e o que sai para ele depende de
    QUAIS rotas apontam para a conexão (`AI_USES`).
    """

    key: str
    #: O nome que o cliente lê: a empresa, não o produto.
    name: str
    #: Domínios do provedor. `api.deepseek.com/anthropic` é DeepSeek mesmo falando o
    #: formato Anthropic: quem recebe o texto é o dono do endereço, não o do formato.
    hosts: tuple[str, ...]


#: Os provedores declarados. Conexão liberada para mensagem de cliente com endereço fora
#: destes domínios reprova em `undeclared_ai_connections`.
AI_PROCESSORS: tuple[AIProcessor, ...] = (
    AIProcessor(key="anthropic", name="Anthropic", hosts=("anthropic.com",)),
    AIProcessor(key="deepseek", name="DeepSeek", hosts=("deepseek.com",)),
    # O Jev é o modelo de decisão da TypeSafe (`AIProtocol.JEV`).
    AIProcessor(key="typesafe", name="TypeSafe", hosts=("typesafe.ai",)),
)

#: O endereço que a porta usa quando a conexão deixa o campo vazio. O do Jev vem de
#: `ai.JEV_DEFAULT_URL`; o do formato Anthropic é o padrão do SDK.
_ANTHROPIC_DEFAULT_URL = "https://api.anthropic.com"


@dataclass(frozen=True)
class AIUse:
    """Um propósito que leva mensagem de cliente, e o que ele de fato manda.

    A frase é MEDIDA no código que monta o pedido, não desejada: cada uso cita onde o
    pedido é montado, e `shopman/shop/tests/test_privacy_inventory_ai.py` monta o pedido
    de verdade e confere a frase. Mudou o que sai (o WP-03 vai redigir a leitura)? A
    trava reprova até alguém mudar a frase junto.

    A ordem da frase é decisão do dono (16/11/2026: "o cliente precisa se sentir seguro
    ao ler; o que é verdade não pode estar mal dito"): primeiro o limite ("só ..."),
    logo depois o que NÃO vai, e por último o que vai a mais em certos casos.
    """

    purpose: str
    #: Completa "ajuda o atendimento automático do WhatsApp a ...".
    helps_to: str
    #: O que sai, item por item, completando "Recebe ...". Item que começa com "quando"
    #: é condicional e vai para o fim da lista; item repetido entre usos sai uma vez.
    sends: tuple[str, ...]
    #: O pedido não leva nada do cadastro (nome, telefone, endereço): só o texto. É o
    #: que permite dizer "só" e "os dados do seu cadastro não vão".
    keeps_profile: bool
    #: O texto sai depois de `redact_observation_text`. Quando um provedor recebe um uso
    #: redigido e um cru, vale o cru: a frase não promete o que um caminho não cumpre.
    redacts: bool
    #: O que vai a mais só em certos casos, como frase inteira, no fim.
    also: str = ""


#: Ordem: do que menos sai para o que mais sai.
AI_USES: tuple[AIUse, ...] = (
    # `triage.jev_scores` (e a sombra, `intent_pilot.shadow_triage`): só o texto,
    # depois de `redact_observation_text`.
    AIUse(
        purpose="decision",
        helps_to="entender o assunto da sua mensagem",
        sends=("o texto da sua mensagem",),
        keeps_profile=True,
        redacts=True,
    ),
    # `intent_pilot` (pré-rótulo do gabarito): mensagens já recebidas, pelo
    # `MessageIntentSample.redacted_text`.
    AIUse(
        purpose="labeling",
        helps_to="conferir, com mensagens que a loja já recebeu, se ele entende direito",
        sends=("o texto da sua mensagem",),
        keeps_profile=True,
        redacts=True,
    ),
    # `intents.build_request`: a fala do turno e `TurnMemory.prompt_lines` (o pedido em
    # aberto: número, retirada ou entrega, dia e situação). Só quando o porteiro hesita.
    AIUse(
        purpose="intents",
        helps_to="separar o que você pede do que você pergunta",
        sends=("o texto da sua mensagem como você escreveu",),
        keeps_profile=True,
        redacts=False,
        also="Se você tem pedido em aberto, vão também o número, o dia e a situação dele",
    ),
    # `triage.build_prompt`: a fala do turno e as falas anteriores de `context_for`
    # (até seis, do cliente e da loja).
    AIUse(
        purpose="triage",
        helps_to="ver se a sua mensagem precisa de alguém da equipe",
        sends=(
            "o texto da sua mensagem como você escreveu",
            "as seis mensagens anteriores da conversa (suas e da loja)",
        ),
        keeps_profile=True,
        redacts=False,
    ),
    # O laço antigo (`agent.run_agent`): `history_for` (até 40 mensagens), o nome, a
    # sacola e o último pedido em `prompt.dynamic_block`, e o endereço de entrega nas
    # ferramentas (`tools.py`), que também tocam o cadastro: daqui não se promete que
    # nada dele fica. O WP-08 do CONCIERGE-PLANO-DE-ACAO o apaga.
    AIUse(
        purpose="concierge",
        helps_to="escrever a resposta",
        sends=(
            "as últimas mensagens da conversa",
            "o seu nome",
            "o que está na sacola",
            "o número do seu último pedido",
            "quando o pedido é para entregar, o endereço da entrega",
        ),
        keeps_profile=False,
        redacts=False,
    ),
)

#: Logo depois do "só": nenhum pedido com `keeps_profile` leva o cadastro.
_PROFILE_STAYS = "Os dados do seu cadastro (nome, telefone e endereço) não vão"

#: O que `redact_observation_text` troca por aviso, dito pelo que o cliente escreveria.
_REDACTION = (
    "Documento, e-mail, telefone, endereço, pagamento, alergia ou doença que você "
    "escrever também não vão: a loja troca cada um por um aviso antes de enviar"
)

_ROLE_PREFIX = "ajuda o atendimento automático do WhatsApp a "


def _customer_text_purposes() -> tuple[str, ...]:
    """Os propósitos cujo pedido leva mensagem de cliente.

    Os de `ai.CUSTOMER_TEXT_PURPOSES` e o do Jev (`decision`), que leva mensagem de
    cliente quando a conexão dele está liberada para isso (`ai.jev_endpoint`).
    Propósito de texto de cliente sem `AIUse` reprova no teste: a página não teria frase.
    """
    from shopman.shop import ai

    return tuple(sorted(set(ai.CUSTOMER_TEXT_PURPOSES) | {"decision"}))


def _concierge_setting(key: str):
    return _setting_value(f"SHOPMAN_CONCIERGE[{key}]")


def _intents_mode() -> str:
    """O mesmo que `concierge.intents.mode`: vazio é `cohort`, desconhecido desliga."""
    mode = str(_concierge_setting("intents_plural") or "cohort").strip().casefold()
    return mode if mode in {"off", "cohort", "subjects", "all"} else "off"


def _concierge_answers() -> bool:
    """O mesmo que `concierge.service.disabled_reason`, menos a conexão (a rota já conta)."""
    mode = str(_concierge_setting("operation_mode") or "assist").strip().casefold()
    return mode == "assist" and bool(_concierge_setting("enabled"))


def _purpose_sends(purpose: str) -> bool:
    """A rota existe; o propósito chega a mandar alguma coisa neste deployment?

    A leitura, a triagem e o laço antigo só rodam quando a Concierge atende, cada um com
    a sua chave (as mesmas que o turno lê em `concierge/service.py`, `intents.py` e
    `triage.py`). O Jev e o pré-rótulo rodam também fora do atendimento (a sombra e o
    piloto): a rota basta.
    """
    if purpose in {"decision", "labeling"}:
        return True
    if not _concierge_answers():
        return False
    if purpose == "intents":
        return _intents_mode() != "off"
    if purpose == "concierge":
        # Em `subjects`, quem está na coorte e fora da lista segue no laço antigo.
        return _intents_mode() in {"off", "subjects"}
    if purpose == "triage":
        classifier = str(_concierge_setting("triage_classifier") or "anthropic").strip().casefold()
        return bool(_concierge_setting("triage_with_model")) and classifier != "jev"
    return False


def _join(parts: list[str], glue: str = "") -> str:
    if len(parts) == 1:
        return parts[0]
    # "e, quando o pedido é para entregar, ...": a oração condicional pede a vírgula.
    last = f"e, {parts[-1]}" if parts[-1].startswith("quando") else f"e {glue}{parts[-1]}"
    return f"{f', {glue}'.join(parts[:-1])} {last}"


def ai_role_and_shares(purposes) -> tuple[str, str]:
    """O papel e o "Recebe ..." de um provedor que recebe estes propósitos.

    A página escreve "Recebe {shares}." e põe o ponto final.
    """
    uses = [use for use in AI_USES if use.purpose in set(purposes)]
    role = _ROLE_PREFIX + _join([use.helps_to for use in uses], glue="a ")
    redacted = all(use.redacts for use in uses)
    # O cru vale: quem recebe um caminho cru não ganha a promessa do redigido.
    sources = uses if redacted else [use for use in uses if not use.redacts]
    keeps_profile = all(use.keeps_profile for use in uses)
    items: list[str] = []
    for use in sources:
        items.extend(item for item in use.sends if item not in items)
    items.sort(key=lambda item: item.startswith("quando"))
    sentences = [("só " if keeps_profile else "") + _join(items)]
    if keeps_profile:
        sentences.append(_PROFILE_STAYS)
    if redacted:
        sentences.append(_REDACTION)
    for use in sources:
        if use.also and use.also not in sentences:
            sentences.append(use.also)
    return role, ". ".join(sentences)


def _host_of(protocol: str, base_url: str) -> str:
    from shopman.shop import ai
    from shopman.shop.models import AIProtocol

    url = (base_url or "").strip()
    if not url:
        url = ai.JEV_DEFAULT_URL if protocol == AIProtocol.JEV else _ANTHROPIC_DEFAULT_URL
    return (urlparse(url).hostname or "").lower()


def _declared_for(host: str) -> AIProcessor | None:
    for processor in AI_PROCESSORS:
        if any(host == domain or host.endswith(f".{domain}") for domain in processor.hosts):
            return processor
    return None


def undeclared_ai_connections() -> tuple[str, ...]:
    """Conexões ativas liberadas para mensagem de cliente sem operador declarado.

    Vazio é o único estado aceitável. Cada item diz o nome da conexão, a referência e
    o endereço, que é o que alguém precisa para declarar o provedor em `AI_PROCESSORS`
    (ou desmarcar "pode receber mensagem de cliente").
    """
    from shopman.shop.models import AIConnection

    connections = AIConnection.objects.filter(is_active=True, customer_text_approved=True).order_by("ref")
    return tuple(
        f"{connection.name} (referência {connection.ref}, endereço {_host_of(connection.protocol, connection.base_url)})"
        for connection in connections
        if _declared_for(_host_of(connection.protocol, connection.base_url)) is None
    )


def active_ai_processors() -> tuple[Processor, ...]:
    """Os provedores de IA que recebem mensagem de cliente NESTE deployment.

    Para cada propósito que leva mensagem de cliente e chega a rodar aqui
    (`_purpose_sends`), pergunta à porta (`ai.resolve`) para onde o texto iria, e conta
    a conexão só se ela está liberada para isso. Não há sinal paralelo: se a porta não
    manda, a página não declara; se manda, declara o que sai por aquele caminho.
    """
    from shopman.shop import ai
    from shopman.shop.models import AIConnection

    #: chave do operador → (nome, propósitos, sinais)
    found: dict[str, tuple[str, set[str], list[str]]] = {}
    for purpose in _customer_text_purposes():
        if not _purpose_sends(purpose):
            continue
        try:
            resolved = ai.resolve(purpose)
        except ai.AINotConfigured:
            continue
        if not resolved.customer_text_approved:
            continue
        declared = _declared_for(_host_of(resolved.protocol, resolved.base_url))
        if declared is not None:
            key, name = declared.key, declared.name
        else:
            # Falha gritando, nunca por omissão: a conexão aparece pelo nome que a casa
            # deu a ela, e o log acusa o operador que falta declarar.
            connection = AIConnection.objects.filter(ref=resolved.ref).first()
            key = f"ai-connection:{resolved.ref}"
            name = connection.name if connection else resolved.ref
            logger.error(
                "privacy_inventory: a conexão de IA %r recebe mensagem de cliente (rota %r) "
                "e o provedor dela não está em AI_PROCESSORS",
                resolved.ref,
                purpose,
            )
        _name, purposes, signals = found.setdefault(key, (name, set(), []))
        purposes.add(purpose)
        signals.append(f"ai:{purpose}:{resolved.ref}")

    order = {processor.key: index for index, processor in enumerate(AI_PROCESSORS)}
    processors = []
    for key in sorted(found, key=lambda chave: (order.get(chave, len(order)), chave)):
        name, purposes, signals = found[key]
        role, shares = ai_role_and_shares(purposes)
        processors.append(Processor(key=key, name=name, role=role, shares=shares, wired_by=tuple(signals)))
    return tuple(processors)
