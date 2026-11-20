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
    rows = tuple(
        OperatorAlertProjection(
            pk=alert.pk,
            rev=alert.rev,
            type=alert.type,
            type_label=alert.get_type_display(),
            severity=alert.severity,
            severity_label=alert.get_severity_display(),
            audience=alert.audience,
            message=readable_message(alert.message),
            order_ref=alert.order_ref,
            created_at_display=format_local(alert.created_at, "%d/%m às {clock}"),
            respond_by_iso=_deadline_iso(alert),
            deadline_kind=deadline_kind(alert),
            origin_label=_spec_value(alert, "origin"),
            origin_icon=_spec_value(alert, "origin_icon"),
            subject=verify_subjects.get(alert.pk) or _spec_value(alert, "subject") or alert.get_type_display(),
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
    # Gestor: produto que sumiu do cardápio por coleção desativada.
    "catalog_hidden_by_inactive_collection": ("orders", "/catalog", "Abrir o Catálogo"),
    # Compras: a NF-e que diverge do cadastro fiscal.
    "purchase_invoice_fiscal_divergence": ("purchase", "/", "Abrir o Compras"),
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


#: A Concierge sem modelo (``concierge_no_model``): a tela do Admin que resolve cada causa,
#: com o rótulo do botão (dono, 20/11/2026: o aviso leva até lá, não ensina o caminho).
_AI_CONNECTIONS = ("/admin/shop/aiconnection/", "Abrir conexões de IA")
_NO_MODEL_HOMES = {
    "brake": ("/admin/shop/shop/", "Abrir freio de IA"),
    "ambiguous": ("/admin/shop/shop/", "Abrir rotas de IA"),
}
_NO_MODEL_CAUSE = re.compile(r"Dedupe: concierge:no_model:(\w+)")


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


def _home_for(alert, *, target_date: str) -> tuple[str, str, str] | None:
    """(app, caminho com o filtro do registro, rótulo) de onde o aviso se resolve."""
    if alert.type == "concierge_no_model":
        found = _NO_MODEL_CAUSE.search(alert.message or "")
        path, label = _NO_MODEL_HOMES.get(found.group(1) if found else "", _AI_CONNECTIONS)
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
    rows = (
        ("answer_concierge_verification", "Responder ao cliente", 1, "answer", "ConciergeVerificationAnswerRequest"),
        ("take_over_conversation", "Assumir a conversa", 2, "take-over", ""),
    )
    return [
        ProductionActionProjection(
            ref=f"{kind}:{alert.pk}",
            kind=kind,
            label=label,
            priority=priority,
            enabled=True,
            reason="",
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


def _open_context_action(alert, *, label: str, href: str) -> ProductionActionProjection:
    return ProductionActionProjection(
        ref=f"open-context:{alert.pk}",
        kind="open_alert_context",
        label=label,
        priority=10,
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
