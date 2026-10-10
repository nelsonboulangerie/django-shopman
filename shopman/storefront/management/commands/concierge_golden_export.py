"""Exporta mensagens reais de clientes como casos do conjunto de avaliação.

Fatia 1 do estudo ``docs/plans/CONCIERGE-ARQUITETURA-ALVO.md`` (seção 6.3). Cada
mensagem de entrada com texto vira um caso em JSON Lines: o texto REDIGIDO
(``redact_observation_text``: documento, telefone, e-mail, endereço, link,
número longo, dado financeiro e de saúde), até 2 falas anteriores da mesma
conversa (também redigidas), o que a casa mediu na hora (sombra do Jev, latência
da resposta do alpha e ferramentas chamadas) e um rótulo PROPOSTO pela regra
local, marcado ``reviewed: false``.

O arquivo é rascunho para conferência humana, não o conjunto pronto: a redação
automática não reconhece nome próprio solto ("Obrigado Wagner"), e o rótulo da
regra é justamente o que está sendo medido. O conjunto conferido mora em
``shopman/storefront/concierge/golden_set.json`` e é medido por
``concierge_reply_eval``.

Lê o banco configurado e não grava nada. Para ler o alpha: conexão DIRETA (porta
25060, banco ``shopman``), nunca o pool (25061), e com
``PGOPTIONS='-c default_transaction_read_only=on'`` (CLAUDE.md da raiz).
"""

from __future__ import annotations

import json
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

CONTEXT_WINDOW = timedelta(hours=12)


class Command(BaseCommand):
    help = "Exporta mensagens de entrada redigidas como casos do conjunto de avaliação (JSON Lines). Não grava nada."

    def add_arguments(self, parser):
        parser.add_argument("--output", required=True, help="Arquivo JSON Lines de saída.")
        parser.add_argument("--days", type=int, default=0, help="Só entradas dos últimos N dias (0 = todas).")
        parser.add_argument("--limit", type=int, default=1000, help="Máximo de casos (default 1000).")

    def handle(self, *args, **options):
        from shopman.shop.models import ConversationMessage

        inbound = ConversationMessage.objects.filter(kind=ConversationMessage.Kind.INBOUND).order_by("id")
        if options["days"]:
            inbound = inbound.filter(created_at__gte=timezone.now() - timedelta(days=options["days"]))
        written = 0
        with open(options["output"], "w", encoding="utf-8") as handle:
            for message in inbound[: options["limit"]]:
                case = build_case(message)
                if case is None:
                    continue
                handle.write(json.dumps(case, ensure_ascii=False) + "\n")
                written += 1
        self.stdout.write(
            f"{written} caso(s) em {options['output']}. Rascunho: confira nome próprio e rótulo antes de "
            "levar ao golden_set.json."
        )


def _redacted(text: str) -> str:
    from shopman.storefront.concierge.observation_privacy import redact_observation_text

    return redact_observation_text(text or "").text


def build_case(message) -> dict | None:
    """O caso de uma mensagem de entrada, ou ``None`` se não há nada a avaliar."""
    from shopman.shop.models import ConversationMessage
    from shopman.storefront.concierge import triage

    envelope = message.envelope or {}
    message_type = str(envelope.get("message_type") or "text")
    text = _redacted(message.text)
    if not text and message_type == "text":
        return None
    previous_rows = list(
        ConversationMessage.objects.filter(
            conversation_id=message.conversation_id,
            kind__in=[ConversationMessage.Kind.INBOUND, ConversationMessage.Kind.REPLY],
            id__lt=message.pk,
            created_at__gte=message.created_at - CONTEXT_WINDOW,
        )
        .exclude(text="")
        .order_by("-id")
        .values_list("kind", "text")[:2]
    )
    who = {ConversationMessage.Kind.INBOUND: "Cliente", ConversationMessage.Kind.REPLY: "Casa"}
    previous = [{"who": who[kind], "text": _redacted(line)[:300]} for kind, line in reversed(previous_rows)]

    intent, source = triage.classify_rules(message.text or "")
    shadow = envelope.get("triage_shadow") or {}
    return {
        "ref": f"msg-{message.pk}",
        "text": text,
        "message_type": message_type,
        "previous": previous,
        "expected": {
            "layer": "",
            "intent": intent if source == "rules" else "",
            "destination": triage.ROUTES[intent][0] if source == "rules" else "",
            "reviewed": False,
        },
        "alpha": {
            "at": message.created_at.date().isoformat(),
            "rules": intent,
            "rules_source": source,
            "jev": shadow.get("jev", ""),
            "jev_latency_ms": shadow.get("latency_ms"),
            **_reply_measure(message),
        },
    }


def _reply_measure(message) -> dict:
    """Quanto a resposta automática do alpha levou e quantas ferramentas chamou, se houve."""
    from shopman.shop.models import ConversationMessage

    rows = ConversationMessage.objects.filter(conversation_id=message.conversation_id, id__gt=message.pk).order_by("id")
    tools = 0
    for row in rows.values("kind", "created_at")[:40]:
        if row["kind"] == ConversationMessage.Kind.INBOUND:
            return {}
        if row["kind"] == ConversationMessage.Kind.TOOL_CALL:
            tools += 1
        if row["kind"] == ConversationMessage.Kind.REPLY:
            elapsed = (row["created_at"] - message.created_at).total_seconds() * 1000
            return {"reply_ms": round(elapsed), "tool_calls": tools}
    return {}
