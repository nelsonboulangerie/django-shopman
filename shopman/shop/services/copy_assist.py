"""A IA que escreve para a loja — um transporte, uma voz.

Este módulo tem duas responsabilidades e nenhuma terceira: falar com o provedor, e
carregar a **voz da marca** em toda chamada.

## Por que service e não adapter

O plano da fase pedia `adapters/copy_assist.py`. Adapter existe para **2+ implementações
reais** ([ADR-001](../../../docs/decisions/adr-001-protocol-adapter.md)), nunca "para o
futuro" — e há um provedor só. Criar registry aqui repetiria exatamente a dívida que a F5
desfez ao matar `adapters/promotion.py`, que tinha uma impl e existia para contornar uma
fronteira. Se um segundo provedor real aparecer, a troca é mecânica; até lá, é um service.

## Por que a voz mora no banco

A voz era um literal em `backstage/services/catalog.py` — invisível para quem opera, não
editável, e **inexistente do lado da campanha**. Resultado: o catálogo falava de um jeito e
o anúncio de outro, na mesma padaria. Agora `Shop.brand_voice` é o dono único da pergunta
"como esta loja fala?", e quem escreve consome ([[feedback_one_question_one_owner]]).

O fallback é a voz padrão do sistema, não silêncio: uma loja recém-criada sem voz
configurada precisa de sugestão em português decente, não de texto sem tom.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: Voz padrão de quando a loja não configurou a sua. Não é a voz da Nelson — é o piso
#: razoável: idioma, pessoa, e o que nunca fazer. O que é da marca vive em
#: `Shop.brand_voice`, editável.
DEFAULT_VOICE = (
    "Você escreve para uma padaria artesanal brasileira. Escreva em português do Brasil, "
    'na primeira pessoa do plural ("nós", "conosco"), nunca "a gente". Tom acolhedor e '
    "concreto, sem superlativo vazio, sem emoji e sem travessão (—). Responda APENAS com "
    "o texto pedido, sem aspas, sem rótulo e sem comentário."
)


class CopyAssistNotConfigured(Exception):
    """Sem credencial neste ambiente. É configuração, não falha."""


class CopyAssistError(Exception):
    """O provedor não respondeu, ou respondeu vazio."""


def is_configured(purpose: str = "copy") -> bool:
    """Há conexão de IA para pedir sugestão neste propósito?

    A tela pergunta isto ANTES de oferecer o botão: oferecer e falhar depois ensina o
    gestor a não confiar no recurso.
    """
    from shopman.shop import ai

    return ai.is_configured(purpose)


def brand_voice() -> str:
    """A voz da loja, com a voz padrão como piso.

    Degrada para o padrão em vez de explodir: sem `Shop` (bootstrap, teste) ainda dá para
    escrever — só não dá para escrever com a voz da casa.
    """
    try:
        from shopman.shop.models import Shop

        voice = (Shop.load().brand_voice or "").strip()
    except Exception:
        logger.debug("copy_assist.brand_voice degraded; using default", exc_info=True)
        return DEFAULT_VOICE
    return voice or DEFAULT_VOICE


def suggest(
    prompt: str,
    *,
    max_tokens: int = 400,
    voice: str = "",
    timeout: float | None = None,
    purpose: str = "copy",
) -> str:
    """Uma sugestão de texto. Devolve o texto limpo, ou levanta.

    ``voice`` vazio busca a voz da loja — o caminho normal. Passar voz explícita existe
    para quem já a resolveu e não quer uma segunda consulta ao banco.
    """
    import anthropic

    from shopman.shop import ai

    try:
        client, model = ai.anthropic_client(purpose, timeout=timeout)
    except ai.AINotConfigured as exc:
        raise CopyAssistNotConfigured(f"Assist de IA não configurado: {exc}.") from exc
    try:
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=voice or brand_voice(),
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as exc:
        # Provider messages may echo request fragments or identifiers.  The caller gets
        # a stable, useful failure while the exception class remains server-side only.
        logger.warning("copy_assist.provider_failed exception_class=%s", type(exc).__name__)
        raise CopyAssistError("O assistente não respondeu. Tente novamente mais tarde.") from exc

    # Resposta cortada no teto não é resposta: é meia frase, ou meio JSON, que
    # quem chamou vai ler como se fosse inteira. Os modelos atuais raciocinam
    # antes de escrever e esse raciocínio sai do MESMO ``max_tokens`` — o teto
    # precisa ser folgado, e estourá-lo precisa gritar com o motivo certo.
    if getattr(message, "stop_reason", "") == "max_tokens":
        raise CopyAssistError(f"O assistente parou no limite de {max_tokens} tokens: resposta cortada.")
    text = "\n".join(block.text for block in message.content if getattr(block, "type", "") == "text").strip()
    if not text:
        raise CopyAssistError("O assistente devolveu uma sugestão vazia.")
    return text
