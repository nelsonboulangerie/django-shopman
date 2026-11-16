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
onde o texto vai: um provedor aparece quando uma rota que leva mensagem de cliente
resolve para uma conexão dele, liberada para isso. Conexão liberada cujo provedor não
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


def _setting_is_set(expression: str) -> bool:
    """Resolve `SENTRY_DSN`, `SHOPMAN_IFOOD[merchant_id]` e `DOORMAN[A][B]`."""
    name, _, resto = expression.partition("[")
    value = getattr(settings, name.strip(), None)
    for chave in (parte.strip() for parte in resto.split("]") if parte.strip()):
        if not isinstance(value, dict):
            return False
        value = value.get(chave.lstrip("["))
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
    QUAL rota aponta para a conexão (ver `_AGENT_PURPOSE`).
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

#: O laço do agente (`concierge/agent.py`) é o único propósito que manda mais que a
#: mensagem: o nome vai no contexto do sistema (`concierge/prompt.py`) e o endereço de
#: entrega volta nas ferramentas do pedido (`concierge/tools.py`). Enquanto ele existir
#: (o WP-08 do CONCIERGE-PLANO-DE-ACAO o apaga), quem recebe esta rota recebe a frase
#: larga, a mesma que a Anthropic tinha desde 12/11/2026.
_AGENT_PURPOSE = "concierge"

_AGENT_ROLE = "responde quando você conversa com o atendimento automático no WhatsApp"
_AGENT_SHARES = (
    "o que você escreve na conversa, o seu nome e, quando o pedido é para "
    "entregar, o endereço da entrega"
)

#: Triagem, leitura de intenções, pré-rótulo e o Jev. ⚠️ A frase é verdade quando o
#: texto sai redigido (`redact_observation_text`), que é o WP-03 do plano para a
#: leitura de intenções. Mudou o redator? Releia esta frase.
_READING_ROLE = "lê a sua mensagem no WhatsApp para o atendimento automático entender o que você pediu"
_READING_SHARES = (
    "a sua mensagem, depois que a loja tira dela documento, telefone, e-mail, "
    "endereço, número de cartão e detalhe de saúde"
)


def _customer_text_purposes() -> tuple[str, ...]:
    """Os propósitos cujo pedido leva mensagem de cliente.

    Os de `ai.CUSTOMER_TEXT_PURPOSES` e o do Jev (`decision`), que leva mensagem de
    cliente quando a conexão dele está liberada para isso (`ai.jev_endpoint`).
    """
    from shopman.shop import ai

    return tuple(sorted(set(ai.CUSTOMER_TEXT_PURPOSES) | {"decision"}))


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

    Para cada propósito que leva mensagem de cliente, pergunta à porta (`ai.resolve`)
    para onde o texto iria, e conta a conexão só se ela está liberada para isso. Não há
    sinal paralelo: se a porta não manda, a página não declara; se manda, declara.
    """
    from shopman.shop import ai
    from shopman.shop.models import AIConnection

    #: chave do operador → (nome, propósitos, sinais)
    found: dict[str, tuple[str, set[str], list[str]]] = {}
    for purpose in _customer_text_purposes():
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
        agent = _AGENT_PURPOSE in purposes
        processors.append(
            Processor(
                key=key,
                name=name,
                role=_AGENT_ROLE if agent else _READING_ROLE,
                shares=_AGENT_SHARES if agent else _READING_SHARES,
                wired_by=tuple(signals),
            )
        )
    return tuple(processors)
