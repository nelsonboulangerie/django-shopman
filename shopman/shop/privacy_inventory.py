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
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings


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
    #: Formato: `"setting:NOME"` ou `"setting:NOME[chave][subchave]"`.
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
        shares="o valor e o identificador da cobrança — nada que diga quem você é",
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
        wired_by=("setting:SHOPMAN_NOTIFICATION_ADAPTERS[whatsapp]",),
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
            "o que a nota exige quando você pede CPF nela: nome, CPF, e — na entrega — "
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
        key="sentry",
        name="Sentry",
        role="recebe o relatório quando uma tela dá erro, para a loja consertar",
        shares=(
            "a falha e a tela em que ela aconteceu. Endereço, telefone e e-mail são "
            "removidos antes de sair"
        ),
        wired_by=("setting:SENTRY_DSN",),
    ),
    Processor(
        key="anthropic",
        name="Anthropic",
        role="responde quando você conversa com o atendimento automático no WhatsApp",
        shares="o que você escreve na conversa e o seu primeiro nome",
        wired_by=("setting:SHOPMAN_CONCIERGE[enabled]",),
    ),
)

#: Adapters que falam com a internet e NÃO recebem dado de cliente. Cada linha é uma
#: isenção declarada: se um deles passar a mandar dado do titular, a linha vira mentira
#: e alguém tem de mexer aqui de propósito.
ADAPTERS_SEM_DADO_DE_CLIENTE: dict[str, str] = {
    "catalog_projection_ifood": "publica o CARDÁPIO no iFood; nenhum dado de cliente",
    "catalog_projection_meta": "publica o CARDÁPIO na Meta; nenhum dado de cliente",
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
_NAO_SAI_DA_CASA = ("console", "locmem", "dummy", "mock", "filebased")


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
    catálogo e falso na vida dele. Quem decide é a configuração que roteia o tráfego.
    """
    return tuple(processor for processor in PROCESSORS if _wired(processor))
