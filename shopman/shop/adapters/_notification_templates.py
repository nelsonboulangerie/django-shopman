"""Templates de notificação editáveis no Admin — compartilhados entre canais.

O lojista edita ``NotificationTemplate`` no Admin; TODOS os canais (WhatsApp/
ManyChat, SMS, e-mail) leem o mesmo template. Placeholder ausente vai literal
(``{chave}``) em vez de quebrar o envio — melhor mensagem imperfeita que
cliente sem aviso.

⚠️ E é exatamente por isso que as chaves AUXILIARES (``customer_name_greeting``,
``tracking_suffix``, ``reorder_suffix``) moram aqui, em ``derive_context``, e não
dentro de um canal. Elas eram derivadas só no adapter do ManyChat; SMS e e-mail
liam o MESMO template do Admin e mandavam ``{customer_name_greeting}`` cru para o
cliente. A política de não quebrar o envio transforma chave faltante em texto
visível, então derivação que vale em metade das saídas não é derivação: é um
defeito com data marcada. Chave nova de conveniência entra AQUI.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class SafeFormatMap(dict):
    """format_map que preserva ``{chave}`` desconhecida em vez de levantar KeyError."""

    def __missing__(self, key):  # pragma: no cover - trivial
        return "{" + key + "}"


def db_template(event: str) -> tuple[str | None, str | None]:
    """Retorna ``(subject, body)`` do NotificationTemplate ativo, ou ``(None, None)``."""
    try:
        from shopman.shop.models import NotificationTemplate

        obj = NotificationTemplate.objects.filter(event=event, is_active=True).first()
        if obj:
            return (obj.subject or None, obj.body or None)
    except Exception:
        logger.debug("notification_templates: lookup failed for event=%s", event, exc_info=True)
    return (None, None)


def render_template(tpl: str, context: dict) -> str:
    """Renderiza um template com SafeFormatMap, degradando ao template cru.

    ``str.format_map`` levanta ValueError/IndexError em chave malformada
    (chave solta, ``{0}`` posicional, spec inválido) — e SafeFormatMap só
    resgata chave AUSENTE. Um typo do lojista num assunto/corpo do Admin não
    pode suprimir a mensagem inteira; melhor o template cru que silêncio.
    """
    try:
        return tpl.format_map(SafeFormatMap(context or {}))
    except Exception:
        logger.debug("notification_templates: template render failed, using raw", exc_info=True)
        return tpl


def derive_context(context: dict | None) -> dict:
    """As chaves auxiliares que TODO canal recebe, derivadas do contexto bruto.

    Ponto único: SMS, e-mail e WhatsApp/ManyChat leem o mesmo texto (do Admin ou do
    fallback do canal), então quem produz as chaves desse texto tem de ser um só.
    São chaves auto-suprimíveis de propósito — o sufixo some limpo quando o dado não
    existe, em vez de deixar rótulo solto ("Acompanhe: ") na tela do cliente.

    Idempotente: chamar duas vezes dá o mesmo resultado.
    """
    ctx = dict(context or {})

    name = str(ctx.get("customer_name") or "").strip()
    ctx["customer_name_greeting"] = f", {name}" if name else ""

    tracking_url = str(ctx.get("tracking_url") or "").strip()
    ctx["tracking_suffix"] = f"\nAcompanhe: {tracking_url}" if tracking_url else ""

    reorder_url = str(ctx.get("reorder_url") or "").strip()
    ctx["reorder_suffix"] = f"\nPeca de novo: {reorder_url}" if reorder_url else ""

    total_q = ctx.get("total_q")
    if total_q and not ctx.get("total"):
        ctx["total"] = f"R$ {total_q / 100:,.2f}"

    # Sufixos que `services/notification._build_context` preenche no fluxo de pedido;
    # o default vazio cobre a chamada DIRETA ao adapter (produção, compras, campanha),
    # que não passa por lá e deixaria o rótulo cru na mensagem.
    ctx.setdefault("courier_tracking_suffix", "")
    ctx.setdefault("pix_suffix", "")
    reason = ctx.get("reason")
    ctx.setdefault("reason_note", f"\n\nMotivo: {reason}" if reason else "")

    return ctx


def render_message(event: str, context: dict, fallback_templates: dict[str, str]) -> str:
    """Corpo da mensagem: Admin (DB) → fallback hardcoded do canal → genérico."""
    ctx = derive_context(context)
    _, body = db_template(event)
    if body:
        return render_template(body, ctx)

    tpl = fallback_templates.get(event)
    if tpl:
        return render_template(tpl, ctx)

    order_ref = ctx.get("order_ref", "")
    return f"Notificação: {event} — Pedido {order_ref}" if order_ref else f"Notificação: {event}"
