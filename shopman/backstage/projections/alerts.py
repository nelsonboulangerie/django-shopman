"""Typed operator-alert projections shared by Django and the operator UI."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote, urlencode

from shopman.utils.formatting import format_local

from shopman.backstage.alert_specs import deadline_for, deadline_kind, spec_for
from shopman.backstage.projections.production import (
    ProductionActionConfirmationProjection,
    ProductionActionIdempotencyProjection,
    ProductionActionProjection,
)


@dataclass(frozen=True)
class OperatorAlertCountsProjection:
    active: int
    critical: int


@dataclass(frozen=True)
class OperatorAlertProjection:
    pk: int
    rev: int
    type: str
    type_label: str
    severity: Literal["warning", "error", "critical"]
    severity_label: str
    audience: str
    message: str
    order_ref: str
    created_at_display: str
    actions: tuple[ProductionActionProjection, ...]
    #: Prazo em que a causa decide sozinha (ISO). Com prazo e sem Visto, a
    #: superfície interrompe a tela; vazio para aviso sem prazo.
    respond_by_iso: str = ""
    #: ``external`` (o iFood decide no fim: vencido, sai) ou ``house`` (régua da
    #: casa: vencido, fica e diz há quanto passou). Vazio sem prazo.
    deadline_kind: str = ""
    #: De onde vem e do que se trata, para ler num relance (``alert_specs``).
    origin_label: str = ""
    origin_icon: str = ""
    subject: str = ""
    #: Também no topo da tela, e não só no sino (``AlertSpec.on_screen``).
    on_screen: bool = False
    #: O combinado do pedido do aviso, na frase do cartão (``order_queue._schedule``):
    #: o "Aceitar" do sino aceita uma encomenda, e quem toca precisa ler para quando.
    #: Só no Gestor; vazio sem pedido ou sem combinado.
    order_schedule_label: str = ""
    order_schedule_state: str = ""


@dataclass(frozen=True)
class OperatorAlertsProjection:
    alerts: tuple[OperatorAlertProjection, ...]
    counts: OperatorAlertCountsProjection
    generated_at: str = ""
    source_revision: str = ""
    fresh_until: str = ""
    contract_version: int = 1


#: O marcador técnico de dedupe que ``create_operator_alert`` pendura no fim da
#: mensagem quando a chave não aparece no texto. Ele continua no banco (o
#: dedupe e ``fiscal.emit_failed_alert_open`` procuram por ele), mas não é
#: frase para o operador.
# Sem ``\s*`` em sequência com ``\n``: os quantificadores sobrepostos davam
# custo polinomial. O espaço antes da linha em branco sai no ``strip()``.
_DEDUPE_SUFFIX = re.compile(r"\n[ \t\r]*\nDedupe: [^\n]*(?:\n\s*)?$")


def readable_message(message: str) -> str:
    """A mensagem como o operador lê: sem o marcador técnico de dedupe."""
    return _DEDUPE_SUFFIX.sub("", str(message or "")).strip()


def _deadline_iso(alert) -> str:
    deadline = deadline_for(alert)
    return deadline.isoformat() if deadline else ""


def _spec_value(alert, field: str) -> str:
    spec = spec_for(alert.type)
    return getattr(spec, field) if spec else ""


def build_operator_alerts_projection(*, alerts, counts, surface: str = "", user=None) -> OperatorAlertsProjection:
    alert_rows = tuple(alerts)
    acceptable = _acceptable_orders(alert_rows, surface=surface, user=user)
    schedules = _order_schedules(alert_rows, surface=surface)
    production_refs = {alert.order_ref for alert in alert_rows if alert.order_ref and alert.audience == "production"}
    target_dates: dict[str, str] = {}
    if production_refs:
        from shopman.craftsman.models import WorkOrder

        target_dates = {
            ref: target_date.isoformat()
            for ref, target_date in WorkOrder.objects.filter(
                ref__in=production_refs,
            ).values_list("ref", "target_date")
            if target_date is not None
        }
    # O cartão do "vou verificar" diz no título quem espera ("Ana espera a resposta da
    # equipe"), pelo nome da conversa dele; os outros tipos ficam com o assunto da spec.
    from shopman.shop.concierge_verification import ALERT_TYPE as VERIFY_TYPE
    from shopman.shop.concierge_verification import card_subjects

    verify_subjects = card_subjects(alert.pk for alert in alert_rows if alert.type == VERIFY_TYPE)
    handoff = handoff_cards([alert.pk for alert in alert_rows if alert.type == HANDOFF_TYPE])
    # O dia fraco por papel (dono, 21/11/2026): quem tem o panorama (lê o B.I. ou
    # audita o caixa) lê a proporção do esperado; o Gerente e o Caixa, a frase sem
    # número que o alerta grava.
    revenue_share: dict[int, str] = {}
    if user is not None and any(alert.type == "bi_below_baseline" for alert in alert_rows):
        from shopman.backstage.bi.alerts import revenue_share_messages
        from shopman.backstage.permissions import can_audit_cash, can_view_bi

        if can_view_bi(user) or can_audit_cash(user):
            revenue_share = revenue_share_messages(
                alert.pk for alert in alert_rows if alert.type == "bi_below_baseline"
            )
    rows = tuple(
        OperatorAlertProjection(
            pk=alert.pk,
            rev=alert.rev,
            type=alert.type,
            type_label=alert.get_type_display(),
            severity=alert.severity,
            severity_label=alert.get_severity_display(),
            audience=alert.audience,
            message=_with_ago(readable_message(revenue_share.get(alert.pk) or alert.message), handoff.get(alert.pk)),
            order_ref=alert.order_ref,
            created_at_display=format_local(alert.created_at, "%d/%m às {clock}"),
            respond_by_iso=_deadline_iso(alert),
            deadline_kind=deadline_kind(alert),
            origin_label=_spec_value(alert, "origin"),
            origin_icon=_spec_value(alert, "origin_icon"),
            subject=(
                verify_subjects.get(alert.pk)
                or (handoff.get(alert.pk) or {}).get("subject")
                or _spec_value(alert, "subject")
                or alert.get_type_display()
            ),
            on_screen=bool(_spec_value(alert, "on_screen")),
            order_schedule_label=schedules.get(alert.order_ref, ("", ""))[0],
            order_schedule_state=schedules.get(alert.order_ref, ("", ""))[1],
            actions=_alert_actions(
                alert,
                target_date=target_dates.get(alert.order_ref, ""),
                surface=surface,
                acceptable=alert.order_ref in acceptable,
            ),
        )
        for alert in alert_rows
    )
    return OperatorAlertsProjection(
        alerts=rows,
        counts=OperatorAlertCountsProjection(
            active=counts.active,
            critical=counts.critical,
        ),
    )


#: Onde cada aviso se resolve: o app (id de ``surfaces/registry.json``), o caminho
#: dentro dele e o rótulo do botão, que diz aonde leva (dono, 09/10/2026: "aviso que
#: descreve algo a fazer leva a quem pode fazê-lo"). O registro vai no filtro: o lote
#: (``?q=<lote>&date=``) na Produção, o pedido (``/<ref>``) no Gestor.
#:
#: Quem NÃO está aqui não tem tela de operador onde se resolve, e o motivo é um destes:
#: avisos de sistema (TI, pelo e-mail crítico e pelo Admin: ``SYSTEM_TYPES``), ajustes de
#: cadastro que só existem no Admin (horário da loja, parâmetro de lei, certificado,
#: cupom, exclusão de conta, de-para e importação do B.I.), e o que se resolve fora do
#: sistema (exclusão manual no ManyChat, conversa da "outra mesa" do WhatsApp).
_ALERT_HOMES: dict[str, tuple[str, str, str]] = {
    # Produção: o lote, filtrado, na tela do gesto.
    "production_late": ("production", "/", "Abrir o lote"),
    "production_low_yield": ("production", "/quality", "Revisar a qualidade do lote"),
    "production_stock_short": ("production", "/close", "Fechar o lote"),
    "production_stock_shortfall": ("production", "/plan", "Conferir o lote no plano"),
    "production_forgotten": ("production", "/plan", "Abrir o lote no plano"),
    "production_unfinished": ("production", "/close", "Fechar o lote"),
    "production_batch_traceability": ("production", "/close", "Fechar o lote de novo"),
    "production_quality_communication": ("production", "/quality", "Revisar a qualidade do lote"),
    "production_quality_hold_risk": ("production", "/quality", "Revisar a qualidade do lote"),
    "stock_discrepancy": ("production", "/plan", "Abrir o plano"),
    "stock_low": ("production", "/plan", "Abrir o plano"),
    # Gestor: o card filtrado no quadro, quando o gesto mora no card.
    "order_production_quality_risk": ("orders", "/", "Abrir o pedido no painel"),
    "danfe_print_failed": ("orders", "/", "Imprimir a DANFE no card"),
    "dispatch_unchecked_volumes": ("orders", "/", "Abrir o pedido no painel"),
    # Gestor: a loja no iFood (o interruptor do canal mora na Fila).
    "ifood_store_closed_while_open": ("orders", "/", "Conferir o iFood na Fila"),
    "ifood_store_open_while_closed": ("orders", "/", "Conferir o iFood na Fila"),
    "ifood_store_sync_failed": ("orders", "/", "Conferir o iFood na Fila"),
    # O módulo de loja ainda não liberado: pausa e horário só pelo Portal.
    "ifood_store_module_pending": ("external", "https://portal.ifood.com.br/", "Abrir o Portal"),
    # Gestor: produto que sumiu do cardápio por coleção desativada.
    "catalog_hidden_by_inactive_collection": ("orders", "/catalog", "Abrir o Catálogo"),
    # Compras: a NF-e que diverge do cadastro fiscal.
    "purchase_invoice_fiscal_divergence": ("purchase", "/", "Abrir o Compras"),
    # Compras: o insumo sem custo que deixou a fornada sem custo (#2360).
    "production_cost_gap": ("purchase", "/", "Abrir o Compras"),
    # PDV: a gaveta e o caixa.
    "pos_drawer_sensor_blind": ("pos", "/", "Abrir o PDV"),
    "pos_drawer_left_open": ("pos", "/", "Abrir o PDV"),
    "cash_change_requested": ("pos", "/", "Abrir o PDV"),
    "card_machine_refund_due": ("pos", "/session", "Registrar o estorno no PDV"),
    "cash_shift_open_at_closing": ("pos", "/session", "Fechar o caixa"),
    "cash_sale_after_shift_close": ("pos", "/session/report", "Conferir o relatório do caixa"),
    # B.I.: o número que passou da régua.
    "cash_out_of_tolerance": ("bi", "/cash", "Ver o caixa no B.I."),
    "bi_cash_variance": ("bi", "/cash", "Ver o caixa no B.I."),
    "bi_below_baseline": ("bi", "/sales", "Ver as vendas no B.I."),
    # Marketing: a fila de decisões é onde o disparo se resolve.
    "marketing_outbox_stuck": ("marketing", "/", "Abrir a fila de decisões"),
    "marketing_partial_without_action": ("marketing", "/", "Abrir a fila de decisões"),
    "marketing_consent_violation": ("marketing", "/", "Abrir a fila de decisões"),
    "marketing_duplicate_confirmed": ("marketing", "/history", "Abrir o histórico"),
    "marketing_reconciliation_mismatch": ("marketing", "/history", "Abrir o histórico"),
    "marketing_unknown_stale": ("marketing", "/history", "Abrir o histórico"),
    "marketing_readiness_stale": ("marketing", "/platforms", "Conferir as plataformas"),
}


def alert_home(alert_type: str) -> tuple[str, str, str] | None:
    """Onde o tipo se resolve (app, caminho, rótulo), sem o filtro do registro."""

    return _ALERT_HOMES.get(alert_type)

#: O id do app no registro de URLs das superfícies (o Gestor é ``gestor`` ali).
_SURFACE_URL_KEYS = {"orders": "gestor"}

#: Onde, dentro do pedido, mora o gesto do aviso (âncora do detalhe).
_ORDER_DETAIL_ANCHORS = {
    "ifood_negotiation_open": "ifood-negotiations",
    "ifood_accept_not_delivered": "ifood-accept",
    "customer_contact_requested": "customer-contact",
}

#: O rótulo do botão quando o aviso leva ao pedido: diz aonde leva, não "resolver".
_ORDER_LABELS = {
    "ifood_negotiation_open": "Responder",
    "card_authorization_expiring": "Aceitar ou recusar",
    "ifood_accept_not_delivered": "Abrir e tentar de novo",
    "customer_contact_requested": "Falar com o cliente",
}


def _catalog_product_href(alert) -> str:
    """GTIN recusado: o produto aberto no Catálogo do Gestor, na aba do GTIN."""
    from shopman.shop.services.fiscal import GTIN_REJECTED_ALERT_TYPE, gtin_rejected_alert_sku

    if alert.type != GTIN_REJECTED_ALERT_TYPE:
        return ""
    sku = gtin_rejected_alert_sku(alert.message)
    return f"/catalog?{urlencode({'sku': sku, 'tab': 'social'})}" if sku else ""


def _ifood_binding_href(alert) -> str:
    """Item do iFood sem produto da casa: a revisão de vínculos, filtrada pelo item.

    É lá que cada item do iFood se liga a um produto (``channel_health``: "Revisar
    vínculos"). O filtro é o NOME do item, que é o que a revisão mostra; sem o
    item no pedido, o código que veio.
    """
    from shopman.orderman.models import Order, OrderItem

    from shopman.shop.services.ifood_ingest import IFOOD_CHANNEL_REF
    from shopman.shop.services.stock import UNKNOWN_SKU_ALERT_TYPE, unknown_sku_alert_sku

    if alert.type != UNKNOWN_SKU_ALERT_TYPE or not alert.order_ref:
        return ""
    row = Order.objects.filter(ref=alert.order_ref).values_list("pk", "channel_ref").first()
    if row is None or row[1] != IFOOD_CHANNEL_REF:
        return ""
    sku = unknown_sku_alert_sku(alert.message)
    name = OrderItem.objects.filter(order_id=row[0], sku=sku).values_list("name", flat=True).first() if sku else None
    needle = str(name or sku or "").strip()
    path = f"/channels/{quote(IFOOD_CHANNEL_REF, safe='')}/catalog"
    return f"{path}?{urlencode({'q': needle})}" if needle else path


#: A Concierge sem modelo (``concierge_no_model``): o rótulo do botão de cada causa (dono,
#: 20/11/2026: o aviso leva até a tela que resolve, não ensina o caminho). O freio e as
#: rotas moram em Configuração, Integrações, seção "Inteligência artificial".
_NO_MODEL_LABELS = {"brake": "Abrir freio de IA", "ambiguous": "Abrir rotas de IA"}
_NO_MODEL_CAUSE = re.compile(r"Dedupe: concierge:no_model:(\w+)")


def _no_model_home(cause: str) -> tuple[str, str]:
    """(caminho no Admin, rótulo) da causa, pelo ``reverse`` do Admin (nunca por string)."""
    from django.urls import reverse

    if cause in _NO_MODEL_LABELS:
        from shopman.shop.models import Shop

        shop = Shop.load()
        path = (
            reverse("admin:shop_shopintegrations_change", args=[shop.pk])
            if shop is not None else reverse("admin:shop_shopintegrations_changelist")
        )
        return path, _NO_MODEL_LABELS[cause]
    return reverse("admin:shop_aiconnection_changelist"), "Abrir conexões de IA"


def _admin_link(path: str) -> str:
    """O endereço absoluto de ``path`` no Admin, que mora noutro host que os apps.

    Sem ``SHOPMAN_ADMIN_HOST``, cai no host da API do operador, onde /admin/ também
    responde; em DEBUG sem nenhum dos dois, no Django de desenvolvimento.
    """
    from django.conf import settings

    host = str(getattr(settings, "SHOPMAN_ADMIN_HOST", "") or "").strip() or str(
        getattr(settings, "SHOPMAN_OPERATOR_API_HOST", "") or ""
    ).strip()
    if host:
        return f"https://{host}{path}"
    return f"http://127.0.0.1:8000{path}" if settings.DEBUG else ""


def _faq_drafts_home() -> tuple[str, str]:
    """O rascunho, quando é um só; a lista dos rascunhos vindos de conversa, quando são vários."""
    from django.urls import reverse

    from shopman.shop.services.faq_drafts import waiting

    drafts = waiting()
    if len(drafts) == 1:
        return reverse("admin:shop_faqentry_change", args=[drafts[0].pk]), "Revisar no Admin"
    query = urlencode({"is_published__exact": "0", "origem": "concierge"})
    return f"{reverse('admin:shop_faqentry_changelist')}?{query}", "Revisar no Admin"


#: Os cartões da Concierge que se resolvem na conversa: o botão abre a conversa no Admin.
_CONVERSATION_CARDS = frozenset({
    "concierge_handoff", "concierge_other_desk", "concierge_unavailable", "concierge_handoff_sync",
    "concierge_output_blocked", "concierge_output_pending", "concierge_empty_output",
    "concierge_identity_conflict",
})


def _conversation_home(alert) -> tuple[str, str] | None:
    """(caminho no Admin, rótulo) da conversa dona do cartão (``Conversation.flags["alerts"]``)."""
    from django.urls import reverse

    from shopman.shop.models import Conversation

    owner = (
        Conversation.objects.filter(**{f"flags__alerts__{alert.type}": alert.pk}).values_list("pk", flat=True).first()
    )
    if owner is None:
        return None
    return reverse("admin:shop_conversation_change", args=[owner]), "Abrir conversa"


HANDOFF_TYPE = "concierge_handoff"

#: O título do handoff pelo motivo, como no "vou verificar": quem e o quê, num relance
#: (coordenação, 20/11/2026). A chave é a intenção da triagem, ou o ``escalated_by``.
_HANDOFF_TITLES = {
    "human": "{name} pediu para falar com alguém da equipe",
    "complaint": "{name} fez uma reclamação",
    "allergy": "{name} perguntou sobre alergia",
    "special_order": "{name} quer uma encomenda especial",
    "cancel_order": "{name} quer cancelar um pedido",
    "order": "{name} quer fazer um pedido",
    "order_not_closed": "{name} quer fazer um pedido",
    "no_useful_answer": "{name} não recebeu resposta da Concierge",
}
_HANDOFF_TITLE_DEFAULT = "{name} precisa da equipe"


def handoff_cards(alert_pks) -> dict[int, dict]:
    """Título e "há quanto tempo" de cada cartão de handoff, pela conversa dona dele.

    "Ana pediu para falar com alguém da equipe"; e, se foi o prazo do "vou verificar",
    "Ana espera a resposta da equipe desde 14h22". O tempo é o da última mensagem dela.
    """
    from shopman.utils.formatting import format_clock

    from shopman.shop.concierge_verification import card_subject
    from shopman.shop.models import Conversation

    pks = [int(pk) for pk in alert_pks]
    if not pks:
        return {}
    conversations = Conversation.objects.filter(**{f"flags__alerts__{HANDOFF_TYPE}__in": pks})
    out: dict[int, dict] = {}
    for conversation in conversations:
        flags = conversation.flags or {}
        pk = int((flags.get("alerts") or {}).get(HANDOFF_TYPE) or 0)
        name = (conversation.customer_name or "").strip().split(" ")[0] or "Cliente"
        triage = flags.get("triage") or {}
        if triage.get("escalated_by") == "verification_timeout":
            subject = card_subject(name)
            opened = _parse_iso((flags.get("verification") or {}).get("opened_at"))
            if opened is not None:
                subject = f"{subject} desde {format_clock(opened)}"
        else:
            key = triage.get("escalated_by") if triage.get("escalated_by") in _HANDOFF_TITLES else triage.get("intent")
            subject = _HANDOFF_TITLES.get(key or "", _HANDOFF_TITLE_DEFAULT).format(name=name)
        out[pk] = {"subject": subject, "since": conversation.last_inbound_at}
    return out


def _parse_iso(value):
    from datetime import datetime

    try:
        return datetime.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def _with_ago(message: str, card: dict | None) -> str:
    """A fala do cliente e há quanto tempo ela escreveu ("há 3 min")."""
    since = (card or {}).get("since")
    if since is None:
        return message
    from django.utils import timezone

    minutes = max(0, int((timezone.now() - since).total_seconds() // 60))
    # Espaço que não quebra: "há 3 min" fica inteiro na linha (a 375 px virava "há 3 / min").
    ago = "agora há pouco" if minutes < 1 else f"há {minutes} min" if minutes < 60 else f"há {minutes // 60} h"
    ago = ago.replace(" ", "\u00a0")
    first, _, rest = message.partition("\n")
    line = f"{first} ·\u00a0{ago}" if first else f"Escreveu {ago}"
    return f"{line}\n{rest}" if rest else line


#: O cartão cuja resposta é no Live Chat do ManyChat: a equipe assumiu a conversa.
_LIVE_CHAT_CARDS = frozenset({HANDOFF_TYPE})
_LIVE_CHAT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
LIVE_CHAT_LABEL = "Responder no Live Chat"


def live_chat_href(alert) -> str:
    """A conversa do cliente na Caixa de Entrada do ManyChat, ou ``""``.

    ``https://app.manychat.com/<conta>/chat/<subscriber_id>``: a conta é a página do
    ManyChat da loja (``Shop.integrations["manychat"]["live_chat_account"]``, no Admin em
    Integrações; ADR-042, nunca por env) e o ``subscriber_id`` é o ``subject`` do vínculo
    ManyChat da conversa. Sem um dos dois, ou com valor fora do formato, nada: o aviso
    fica com "Abrir conversa" e nunca leva a um link quebrado.
    """
    if alert.type not in _LIVE_CHAT_CARDS:
        return ""
    from shopman.shop.models import Conversation

    owner = (
        Conversation.objects.filter(**{f"flags__alerts__{alert.type}": alert.pk}).values_list("pk", flat=True).first()
    )
    return _conversation_live_chat_href(owner)


def live_chat_account() -> str:
    """A conta do ManyChat da loja para o Live Chat (Admin, Integrações), ou ``""``."""
    from shopman.shop.models import Shop

    shop = Shop.load()
    account = str((((getattr(shop, "integrations", None) or {}).get("manychat") or {}).get("live_chat_account")) or "").strip()
    return account if _LIVE_CHAT_ID.match(account) else ""


def verification_live_chat_href(alert) -> str:
    """A conversa do "vou verificar" (cartão ``concierge_verify``) no Live Chat, ou ``""``."""
    from shopman.shop.models import Conversation

    owner = (
        Conversation.objects.filter(flags__verification__alert_pk=alert.pk).order_by("-pk").values_list("pk", flat=True).first()
    )
    return _conversation_live_chat_href(owner)


def _conversation_live_chat_href(owner) -> str:
    from shopman.shop.models import ConversationBinding

    account = live_chat_account()
    if not account or owner is None:
        return ""
    subject = (
        ConversationBinding.objects.filter(conversation_id=owner, provider="manychat")
        .order_by("-last_inbound_at", "-pk")
        .values_list("subject", flat=True)
        .first()
    )
    subject = str(subject or "").strip()
    if not _LIVE_CHAT_ID.match(subject):
        return ""
    return f"https://app.manychat.com/{account}/chat/{subject}"


def _home_for(alert, *, target_date: str) -> tuple[str, str, str] | None:
    """(app, caminho com o filtro do registro, rótulo) de onde o aviso se resolve."""
    if alert.type == "faq_drafts_waiting":
        return ("admin", *_faq_drafts_home())


    if alert.type in _CONVERSATION_CARDS:
        found = _conversation_home(alert)
        return ("admin", *found) if found else None
    if alert.type == "concierge_no_model":
        found = _NO_MODEL_CAUSE.search(alert.message or "")
        path, label = _no_model_home(found.group(1) if found else "")
        return ("admin", path, label)
    catalog_href = _catalog_product_href(alert)
    if catalog_href:
        return ("orders", catalog_href, "Conferir o GTIN no Catálogo")
    binding_href = _ifood_binding_href(alert)
    if binding_href:
        return ("orders", binding_href, "Revisar vínculos do iFood")
    home = _ALERT_HOMES.get(alert.type)
    if home is not None:
        surface, path, label = home
        params = {}
        if alert.order_ref and path in {"/", "/plan", "/close", "/quality"}:
            params["q"] = alert.order_ref
        if target_date and surface == "production":
            params["date"] = target_date
        return (surface, f"{path}?{urlencode(params)}" if params else path, label)
    if alert.order_ref:
        # Todo aviso preso a um pedido leva ao pedido: é lá que estão o contato do
        # cliente, a nota, a corrida, o pagamento e o cancelamento.
        path = f"/{quote(alert.order_ref, safe='')}"
        anchor = _ORDER_DETAIL_ANCHORS.get(alert.type)
        if anchor:
            path = f"{path}#{anchor}"
        return ("orders", path, _ORDER_LABELS.get(alert.type, "Abrir o pedido"))
    return None


def alert_context_href(alert, *, surface: str, target_date: str = "") -> tuple[str, str]:
    """(href, rótulo) do botão do aviso, visto do app ``surface``.

    No mesmo app, o caminho relativo; noutro, o endereço absoluto do app que resolve
    (``hub.surface_link``). Sem URL configurada para o outro app, nada: um caminho
    relativo levaria a uma tela que não existe no app de onde foi tocado.
    ``surface`` vazio é o leitor sem app (Admin, testes de contrato): caminho relativo.
    """
    home = _home_for(alert, target_date=target_date)
    if home is None:
        return ("", "")
    home_surface, path, label = home
    if home_surface == "external":
        # Fora da casa (o Portal do Parceiro do iFood): o endereço é o próprio.
        return (path, label)
    if home_surface == "admin":
        href = _admin_link(path)
        return (href, label) if href else ("", "")
    if not surface or surface == home_surface:
        return (path, label)
    from shopman.backstage.projections.hub import surface_link

    href = surface_link(_SURFACE_URL_KEYS.get(home_surface, home_surface), path)
    return (href, label) if href else ("", "")


#: O aviso cujo gesto direto é aceitar o pedido (P2-19 do mapa de cenários): o pedido
#: parado sem aceite traz o "Aceitar" pronto, sem precisar abrir o pedido antes.
_ACCEPT_ALERT_TYPES = frozenset({"stale_new_order"})


def _acceptable_orders(alert_rows, *, surface: str, user) -> frozenset[str]:
    """Os pedidos destes avisos que ESTA pessoa pode aceitar agora, no Gestor.

    Só no Gestor (``surface == "orders"``): é o app que sabe executar o aceite. E só
    quando a régua canônica do quadro (``operator_orders.operational_actions``)
    oferece o "Aceitar" habilitado; pedido que já andou, pagamento que ainda trava o
    aceite ou pessoa sem ``shop.manage_orders`` ficam com "Abrir o pedido". A rota
    do aceite revalida tudo sob trava: oferecer não é autorizar.
    """
    if surface != "orders" or user is None:
        return frozenset()
    refs = {alert.order_ref for alert in alert_rows if alert.type in _ACCEPT_ALERT_TYPES and alert.order_ref}
    if not refs:
        return frozenset()
    from shopman.orderman.models import Order

    from shopman.shop.services import operator_orders

    acceptable = set()
    for order in Order.objects.filter(ref__in=refs, status=Order.Status.NEW):
        confirm = next(
            (action for action in operator_orders.operational_actions(order, user=user) if action.ref == "confirm"),
            None,
        )
        if confirm is not None and confirm.enabled:
            acceptable.add(order.ref)
    return frozenset(acceptable)


def _order_schedules(alert_rows, *, surface: str) -> dict[str, tuple[str, str]]:
    """O combinado de cada pedido destes avisos, pela régua do cartão do Gestor.

    Só no Gestor, que mostra o "Aceitar" ao lado. Pedido sem combinado (ou já
    cumprido) não entra: o aviso não tem o que dizer sobre ele.
    """
    if surface != "orders":
        return {}
    refs = {alert.order_ref for alert in alert_rows if alert.order_ref}
    if not refs:
        return {}
    from shopman.orderman.models import Order

    from shopman.backstage.projections.order_queue import _schedule

    out = {}
    for order in Order.objects.filter(ref__in=refs):
        label, state = _schedule(order)
        if state:
            out[order.ref] = (label, state)
    return out


def _accept_order_action(alert) -> ProductionActionProjection:
    """O "Aceitar" do aviso: o mesmo aceite do quadro, na rota do pedido.

    A tela relê o pedido e manda a intenção canônica dele (``base_revision``,
    ``expected_actor_id``), como o botão do cartão. O aviso fecha sozinho quando o
    pedido sai de "novo" (``handlers/alert_resolution``).
    """
    ref = alert.order_ref
    return ProductionActionProjection(
        ref=f"confirm-order:{alert.pk}",
        kind="confirm_order",
        label="Aceitar",
        priority=5,
        enabled=True,
        reason="",
        method="POST",
        href=f"/api/v1/backstage/orders/{quote(ref, safe='')}/confirm/",
        payload_schema="",
        expected_rev=None,
        idempotency=ProductionActionIdempotencyProjection(
            required=True,
            key_scope=f"orders.confirm:{ref}",
        ),
        confirmation=ProductionActionConfirmationProjection(
            required=False,
            reason_required=False,
            title="",
            confirm_label="Aceitar",
        ),
        approval_requirement=None,
        source_alert_ref=str(alert.pk),
        source_alert_effect="resolves",
        proof="",
    )


def _concierge_verification_actions(alert) -> list[ProductionActionProjection]:
    """O "vou verificar" da Concierge (WP-05): responder ao cliente, ou assumir a conversa.

    A resposta vai no corpo (``{"text": ...}``) e sai ao cliente pela Concierge; o
    cartão fecha sozinho quando ela sai ou quando alguém assume.
    """
    base = f"/api/v1/backstage/alerts/{alert.pk}/concierge-verification"
    live_chat = verification_live_chat_href(alert)
    rows = (
        ("answer_concierge_verification", "Responder ao cliente", 1, "answer", "ConciergeVerificationAnswerRequest"),
        ("take_over_conversation", TAKE_OVER_LIVE_CHAT_LABEL if live_chat else TAKE_OVER_LABEL, 2, "take-over", ""),
    )
    return [*_verification_gestures(alert, base, rows), _live_chat_link(alert, live_chat)]


#: "Assumir" tira a Concierge da conversa (WP-05). O botão diz para onde leva, e a linha
#: sob ele diz o que acontece (dono, 21/11/2026; rótulo longo estourava o cartão a 375 px).
TAKE_OVER_LIVE_CHAT_LABEL = "Assumir no Live Chat"
TAKE_OVER_LABEL = "Assumir a conversa"
TAKE_OVER_CONSEQUENCE = "Ao assumir, a Concierge para de responder nesta conversa."
LIVE_CHAT_MISSING = "Assumir não abre a conversa do ManyChat: falta a conta do Live Chat no Admin."
LIVE_CHAT_CONFIGURE_LABEL = "Configurar o Live Chat"


def _live_chat_link(alert, live_chat: str) -> ProductionActionProjection:
    """O Live Chat que o "Assumir" abre no mesmo gesto; sem a conta, o caminho para configurar.

    Tipo próprio (``open_live_chat`` / ``configure_live_chat``): a caixa de Avisos não o
    mostra como botão solto, quem o usa é o gesto de assumir do cartão.
    """
    from django.urls import reverse

    from shopman.shop.models import Shop

    if live_chat:
        kind, label, href, reason = "open_live_chat", LIVE_CHAT_LABEL, live_chat, ""
    else:
        shop = Shop.load()
        path = (
            reverse("admin:shop_shopintegrations_change", args=[shop.pk])
            if shop is not None else reverse("admin:shop_shopintegrations_changelist")
        )
        kind, label, href, reason = "configure_live_chat", LIVE_CHAT_CONFIGURE_LABEL, _admin_link(path), LIVE_CHAT_MISSING
    return ProductionActionProjection(
        ref=f"{kind}:{alert.pk}",
        kind=kind,
        label=label,
        priority=3,
        enabled=True,
        reason=reason,
        method="GET",
        href=href,
        payload_schema="",
        expected_rev=None,
        idempotency=ProductionActionIdempotencyProjection(required=False, key_scope=""),
        confirmation=ProductionActionConfirmationProjection(
            required=False, reason_required=False, title="", confirm_label=label,
        ),
        approval_requirement=None,
        source_alert_ref=str(alert.pk),
        source_alert_effect="",
        proof="",
    )


def _verification_gestures(alert, base: str, rows) -> list[ProductionActionProjection]:
    return [
        ProductionActionProjection(
            ref=f"{kind}:{alert.pk}",
            kind=kind,
            label=label,
            priority=priority,
            enabled=True,
            reason=TAKE_OVER_CONSEQUENCE if kind == "take_over_conversation" else "",
            method="POST",
            href=f"{base}/{path}/",
            payload_schema=schema,
            expected_rev=None,
            idempotency=ProductionActionIdempotencyProjection(required=False, key_scope=""),
            confirmation=ProductionActionConfirmationProjection(
                required=False,
                reason_required=False,
                title="",
                confirm_label=label,
            ),
            approval_requirement=None,
            source_alert_ref=str(alert.pk),
            source_alert_effect="resolves",
            proof="",
        )
        for kind, label, priority, path, schema in rows
    ]


def _alert_actions(
    alert, *, target_date: str = "", surface: str = "", acceptable: bool = False
) -> tuple[ProductionActionProjection, ...]:
    actions = []
    if acceptable:
        actions.append(_accept_order_action(alert))
    if alert.type == "concierge_verify":
        actions.extend(_concierge_verification_actions(alert))
    if alert.type == "concierge_handoff" and alert.resolved_at is None:
        actions.append(_give_back_action(alert))
    live_chat = live_chat_href(alert)
    if live_chat:
        # A resposta é no Live Chat (o principal); a conversa no Admin fica como segunda saída.
        actions.append(_open_context_action(alert, label=LIVE_CHAT_LABEL, href=live_chat, ref="live-chat", priority=9))
    href, label = alert_context_href(alert, surface=surface, target_date=target_date)
    if href:
        actions.append(_open_context_action(alert, label=label, href=href))
    if not alert.acknowledged:
        actions.append(
            ProductionActionProjection(
                ref=f"acknowledge:{alert.pk}",
                kind="acknowledge_alert",
                label="Visto",
                priority=20,
                enabled=True,
                reason="",
                method="POST",
                href=f"/api/v1/backstage/alerts/{alert.pk}/ack/",
                payload_schema="AlertAckMutationRequest",
                expected_rev=alert.rev,
                idempotency=ProductionActionIdempotencyProjection(
                    required=True,
                    key_scope=f"backstage.alert-ack:{alert.pk}",
                ),
                confirmation=ProductionActionConfirmationProjection(
                    required=False,
                    reason_required=False,
                    title="",
                    confirm_label="Confirmar",
                ),
                approval_requirement=None,
                source_alert_ref=str(alert.pk),
                source_alert_effect="acknowledges",
                proof="",
            )
        )
    return tuple(actions)


#: O gesto do cartão do handoff (#3578): a conversa parada com a equipe volta à Concierge ali mesmo.
GIVE_BACK_LABEL = "Devolver à Concierge"


def _give_back_action(alert) -> ProductionActionProjection:
    return ProductionActionProjection(
        ref=f"give-back:{alert.pk}",
        kind="give_back_to_concierge",
        label=GIVE_BACK_LABEL,
        priority=5,
        enabled=True,
        reason="",
        method="POST",
        href=f"/api/v1/backstage/alerts/{alert.pk}/concierge-handoff/give-back/",
        payload_schema="",
        expected_rev=alert.rev,
        idempotency=ProductionActionIdempotencyProjection(
            required=False,
            key_scope="",
        ),
        confirmation=ProductionActionConfirmationProjection(
            required=False,
            reason_required=False,
            title="",
            confirm_label="Devolver",
        ),
        approval_requirement=None,
        source_alert_ref=str(alert.pk),
        source_alert_effect="resolves",
        proof="",
    )


def _open_context_action(
    alert, *, label: str, href: str, ref: str = "open-context", priority: int = 10
) -> ProductionActionProjection:
    return ProductionActionProjection(
        ref=f"{ref}:{alert.pk}",
        kind="open_alert_context",
        label=label,
        priority=priority,
        enabled=True,
        reason="",
        method="GET",
        href=href,
        payload_schema="",
        expected_rev=None,
        idempotency=ProductionActionIdempotencyProjection(
            required=False,
            key_scope="",
        ),
        confirmation=ProductionActionConfirmationProjection(
            required=False,
            reason_required=False,
            title="",
            confirm_label="Abrir",
        ),
        approval_requirement=None,
        source_alert_ref=str(alert.pk),
        source_alert_effect="keeps_open",
        proof="",
    )
