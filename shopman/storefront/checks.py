"""System checks da loja: o que o Concierge precisa para responder.

O ``check_whatsapp_flow_coverage`` (``shop/checks.py``) olha só campanhas de
Marketing, e o ``manychat_flows --check`` só templates de notificação. Nenhum
dos dois dizia se o Concierge, uma vez ligado, consegue atender. Este check diz.

Regras:

- **Desligado, silêncio.** Com ``SHOPMAN_CONCIERGE_ENABLED`` falso não há o que
  conferir: o deploy de hoje (Concierge em ``observe`` e desligado) passa limpo.
- **Ligado, só avisos (Warning), nunca Error.** Tudo o que falta aqui já falha
  FECHADO em runtime (``service.disabled_reason``, ``IngressRejected`` 503 sem
  chave, envio recusado sem janela). Um ``Error`` derrubaria o ``check --deploy``
  do release e o sistema inteiro ficaria sem deploy por uma faixa que já não
  responde, a lição do SHOPMAN_W020 (16/09).

IDs:

  SHOPMAN_W022  Concierge ligado que não vai responder (modo, contrato, chave da
                Anthropic, conexão ativa ou lista de assinantes)
  SHOPMAN_W023  Concierge ligado que responde, mas sem uma peça do ManyChat
                (token da API, chave do ingresso, campo de atendimento humano,
                fuso da janela de 24 horas)

O que nenhum check enxerga: se o flow do ManyChat chama o endpoint do Concierge
em TODA mensagem. A API do ManyChat não expõe o conteúdo do flow; isso continua
sendo o ensaio manual do checklist (``docs/plans/WHATSAPP-CONCIERGE-PLAN.md``).
"""

from __future__ import annotations

from django.conf import settings
from django.core.checks import Warning, register

MANYCHAT_PROVIDER = "manychat"


def concierge_findings(config: dict | None = None) -> list[tuple[str, str, str]]:
    """(id, mensagem, dica) de cada peça que falta. Vazio quando desligado ou pronto."""
    from shopman.storefront.concierge.transport import configured_connections

    config = config if config is not None else (getattr(settings, "SHOPMAN_CONCIERGE", {}) or {})
    if not config.get("enabled"):
        return []

    findings: list[tuple[str, str, str]] = []
    mode = str(config.get("operation_mode") or "assist").strip().casefold()
    if mode == "observe":
        findings.append((
            "SHOPMAN_W022",
            "SHOPMAN_CONCIERGE_ENABLED está ligado, mas CONCIERGE_OPERATION_MODE=observe: "
            "o Concierge só observa e não responde ninguém.",
            "Para responder, troque CONCIERGE_OPERATION_MODE para assist (passo 1 da "
            "sequência de ligar, no WHATSAPP-CONCIERGE-PLAN). A observação passiva para.",
        ))
    elif mode != "assist":
        findings.append((
            "SHOPMAN_W022",
            f"CONCIERGE_OPERATION_MODE={mode!r} não é observe nem assist: o Concierge não responde.",
            "Use assist para responder ou observe para só observar.",
        ))
    if config.get("contract_version") != 3:
        findings.append((
            "SHOPMAN_W022",
            "CONCIERGE_CONTRACT_VERSION não é 3: o Concierge não responde.",
            "Defina CONCIERGE_CONTRACT_VERSION=3.",
        ))
    if not (getattr(settings, "AI_ASSIST_API_KEY", "") or "").strip():
        findings.append((
            "SHOPMAN_W022",
            "Concierge ligado sem AI_ASSIST_API_KEY: o webhook responde disabled (ai_key_missing).",
            "Configure AI_ASSIST_API_KEY (segredo) no app.",
        ))

    connections = configured_connections(config)
    if not connections:
        findings.append((
            "SHOPMAN_W022",
            "Concierge ligado sem nenhuma conexão ativa: nenhuma mensagem chega a ele.",
            "Ligue a conexão do ManyChat (CONCIERGE_MANYCHAT_WHATSAPP_ACTIVE=true) com conta e chave.",
        ))
    for connection in connections:
        options = connection.options or {}
        allowed = [str(value).strip() for value in options.get("allowed_subjects") or () if str(value).strip()]
        if not allowed:
            findings.append((
                "SHOPMAN_W022",
                f"Conexão {connection.key}: lista de assinantes vazia, ninguém é atendido (not_allowed).",
                "Preencha CONCIERGE_ALLOWED_SUBSCRIBERS com a coorte do ensaio.",
            ))
        authentication = options.get("authentication") or {}
        keys = [key for key in (authentication.get("keys") or ()) if str(key or "").strip()]
        if not keys:
            findings.append((
                "SHOPMAN_W023",
                f"Conexão {connection.key}: sem chave de ingresso, o webhook recusa tudo (503).",
                "Configure CONCIERGE_API_KEY (segredo) e o mesmo valor no External Request do ManyChat.",
            ))
        if connection.provider != MANYCHAT_PROVIDER:
            continue
        if not (getattr(settings, "MANYCHAT_API_TOKEN", "") or "").strip():
            findings.append((
                "SHOPMAN_W023",
                f"Conexão {connection.key}: sem MANYCHAT_API_TOKEN, a resposta e a marca de "
                "atendimento humano não saem.",
                "Configure MANYCHAT_API_TOKEN (segredo).",
            ))
        if not str(options.get("handoff_field") or "").strip():
            findings.append((
                "SHOPMAN_W023",
                f"Conexão {connection.key}: sem campo de atendimento humano, a triagem não "
                "consegue calar o bot no ManyChat.",
                "Defina CONCIERGE_HANDOFF_FIELD (concierge_handoff) e crie o campo no ManyChat.",
            ))
        window = options.get("response_window") or {}
        if not str(window.get("timezone") or "").strip():
            findings.append((
                "SHOPMAN_W023",
                f"Conexão {connection.key}: sem fuso da janela de 24 horas, nenhuma resposta "
                "é autorizada a sair.",
                "Defina CONCIERGE_WHATSAPP_INTERACTION_TIMEZONE (ex.: America/Sao_Paulo).",
            ))
    return findings


@register(deploy=True)
def check_concierge_readiness(app_configs, **kwargs):
    return [Warning(message, hint=hint, id=check_id) for check_id, message, hint in concierge_findings()]
