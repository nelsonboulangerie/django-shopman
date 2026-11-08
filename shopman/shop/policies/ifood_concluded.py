"""O iFood já concluiu o pedido: recusar e cancelar morrem antes de chegar ao iFood."""

from __future__ import annotations


def concluded_refusal(order, *, verb: str = "cancelar") -> str:
    """Recusa de antemão quando o iFood já CONCLUIU o pedido (fato ``remote_concluded``).

    Depois do CON o iFood não lista mais motivos de cancelamento nem aceita o
    pedido de cancelar: tentar mesmo assim só chegava à leitura dos motivos, que
    falhava, e a tela via um 503 sem sentido (alpha, 07/11/2026, IFOOD-261107-3761).
    O fato vem gravado em ``order.data.ifood.remote_concluded`` com ``observed_at``.
    Devolve a frase para o operador, ou ``""`` quando nada impede.
    """
    if getattr(order, "channel_ref", "") != "ifood":
        return ""
    fact = ((getattr(order, "data", None) or {}).get("ifood") or {}).get("remote_concluded")
    if not fact:
        return ""
    when = ""
    observed_at = fact.get("observed_at") if isinstance(fact, dict) else None
    if observed_at:
        from datetime import datetime

        from django.utils import timezone

        try:
            moment = datetime.fromisoformat(str(observed_at))
            if timezone.is_aware(moment):
                when = f" às {timezone.localtime(moment):%H:%M}"
        except ValueError:
            when = ""
    return f"O iFood já concluiu este pedido{when}. Não dá mais para {verb}."


__all__ = ["concluded_refusal"]
