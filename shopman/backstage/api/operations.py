"""Backstage API — POS, Production, Day Closing, Orders Queue.

GET endpoints (read views):
  GET  /api/v1/backstage/pos/                 → POS terminal projection
  GET  /api/v1/backstage/production/          → Production board for today
  GET  /api/v1/backstage/production/kds/      → Production KDS (started WOs)
  GET  /api/v1/backstage/production/reports/  → Production reports (manager; ?format=csv)
  GET  /api/v1/backstage/production/management/ → Day KPIs (yield, capacity, late)
  GET  /api/v1/backstage/production/weighing/blind-map/ → Blind code ↔ prep map (manager)
  GET  /api/v1/backstage/closing/             → Day closing snapshot
  GET  /api/v1/backstage/orders/              → Operator order queue

POST endpoints (operator actions):
  POST /api/v1/backstage/orders/<ref>/advance/  → next status
  POST /api/v1/backstage/orders/<ref>/confirm/  → confirm pending order
  POST /api/v1/backstage/orders/<ref>/reject/   → reject pending order
  POST /api/v1/backstage/orders/<ref>/cancel/   → cancel order
  POST /api/v1/backstage/orders/<ref>/settle-delivery-cash/ → settle COD cash
  POST /api/v1/backstage/orders/<ref>/requeue-fiscal/ → requeue NFC-e emission
  POST /api/v1/backstage/orders/<ref>/resend-payment-link/ → resend the payment-link notice
  POST /api/v1/backstage/orders/<ref>/notes/    → save the operator's kitchen note
  POST /api/v1/backstage/production/plan/                 → plan/adjust matrix cell
  POST /api/v1/backstage/production/<wo_id>/start/        → start a planned WO
  POST /api/v1/backstage/production/<wo_id>/finish/       → finish a started WO
  POST /api/v1/backstage/production/<wo_id>/advance-step/ → next step
  POST /api/v1/backstage/production/quick-finish/         → plan + finish in one step
  POST /api/v1/backstage/production/<wo_id>/void/         → void work order
  POST /api/v1/backstage/closing/                    → finalize day closing
  POST /api/v1/backstage/pos/cash/open/              -> open cash shift
  POST /api/v1/backstage/pos/cash/close/             -> close cash shift
  POST /api/v1/backstage/pos/cash/movement/          → register cash movement
  GET  /api/v1/backstage/pos/cash/report/            → X/Z readings + shift history
  POST /api/v1/backstage/pos/sale/review/            → validate POS checkout without commit
  POST /api/v1/backstage/pos/sale/recent/cancel/     → cancel recent POS sale
"""

from __future__ import annotations

import json
import logging
from datetime import date

from django.contrib.auth import login, logout
from django.core.exceptions import ObjectDoesNotExist
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import exceptions
from rest_framework.permissions import AllowAny
from rest_framework.renderers import BaseRenderer, JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView
from shopman.utils.monetary import format_money

from shopman.backstage import station_trust
from shopman.backstage.api._production_filters import report_filters
from shopman.backstage.constants import POS_CHANNEL_REF
from shopman.backstage.models import SignInMethod, SignInOutcome
from shopman.backstage.parsing import as_bool
from shopman.backstage.projections.cash_session import build_cash_session_report
from shopman.backstage.projections.closing import build_day_closing
from shopman.backstage.projections.order_queue import build_operator_order, build_two_zone_queue, payment_link_notice
from shopman.backstage.projections.pos import (
    build_open_tab,
    build_pos,
    build_pos_customer_lookup,
    build_pos_customer_lookup_by_ref,
    build_pos_customer_search,
    build_pos_shift_summary,
    build_pos_tabs,
)
from shopman.backstage.projections.production import (
    build_production_blind_map,
    build_production_board,
    build_production_dashboard,
    build_production_forecast,
    build_production_kds,
    build_production_mise_en_place,
    build_production_reports,
    build_production_weighing,
    build_qc_kiosk,
)
from shopman.backstage.services import (
    closing as closing_service,
)
from shopman.backstage.services import (
    orders as orders_service,
)
from shopman.backstage.services import (
    pos as pos_service,
)
from shopman.backstage.services import (
    production as production_service,
)
from shopman.backstage.services import sign_in_audit
from shopman.backstage.services.exceptions import (
    OrderConflict,
    OrderError,
    POSError,
    POSTerminalAmbiguous,
    ProductionConflict,
    ProductionError,
)
from shopman.backstage.services.production import ProductionOrderShortError, ProductionStockShortError
from shopman.shop.services import cancellation as cancellation_service
from shopman.shop.services import fiscal as fiscal_service
from shopman.shop.services import notification as notification_service
from shopman.shop.services import pos as pos_tabs_service
from shopman.shop.services.pos import PosCustomerConflict, PosRecentSaleNotFound
from shopman.shop.services.pos_intent import PosIntentError

from .permissions import HasBackstagePermission, IsBackstageOperator, IsTrustedStation
from .projections import projection_data

logger = logging.getLogger(__name__)

#: Backend de sessão de quem se identifica por PIN ou crachá. A loja tem dois
#: configurados — OTP de telefone (cliente) e senha (staff) — e ``login()`` só
#: adivinha qual gravar quando foi ele mesmo quem autenticou.
MODEL_BACKEND = "django.contrib.auth.backends.ModelBackend"


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _actor(request) -> str:
    """O nome de quem agiu — que é simplesmente quem está logado.

    Tinha um ramo a mais: procurava um "operador ativo" guardado na sessão e só
    caía no usuário da sessão se não achasse. Existiam DUAS identidades, e a
    função escolhia entre elas. Agora a sessão É do operador (D1-B), então não há
    escolha a fazer: quem está logado é quem agiu.
    """
    user = getattr(request, "user", None)
    return getattr(user, "username", None) or "operator"


def _production_actor(request) -> str:
    """Audit attribution for production actions, matching the retired HTMX floor
    (``production:<username>``) so the event trail stays consistent post-cutover."""
    return f"production:{_actor(request)}"


def _production_error_response(exc: ProductionError) -> Response | None:
    """Structured error envelope for production error states.

    The floor app reproduces the material/order shortage modals from this
    payload (mirrors the POS error envelope shape ``{detail, error: {code,…}}``),
    and state conflicts (fornada fechada/estornada em outra tela) come out as
    409 ``state_conflict`` so the kiosk can refresh instead of guessing.
    Returns ``None`` for other errors so callers fall through to the generic
    400 handling.
    """
    if isinstance(exc, ProductionConflict):
        return Response(
            {"detail": str(exc), "error": {"code": "state_conflict"}},
            status=409,
        )
    if isinstance(exc, ProductionStockShortError):
        return Response(
            {
                "detail": str(exc),
                "error": {
                    "code": "material_shortage",
                    "work_order_ref": exc.work_order_ref,
                    "missing": [
                        {
                            "sku": item.sku,
                            "needed": str(item.needed),
                            "available": str(item.available),
                            "shortage": str(item.shortage),
                        }
                        for item in exc.missing
                    ],
                },
            },
            status=409,
        )
    if isinstance(exc, ProductionOrderShortError):
        return Response(
            {
                "detail": str(exc),
                "error": {
                    "code": "order_shortage",
                    "work_order_ref": exc.work_order_ref,
                    "required": str(exc.required),
                    "requested": str(exc.requested),
                    "order_refs": list(exc.order_refs),
                },
            },
            status=409,
        )
    return None


def _cash_shift_result(shift) -> dict:
    # Fechamento cego: o operador vê só o que contou, nunca o esperado nem a
    # diferença. Os dois são provados pelo livro (``cashman``) e lidos pela
    # retaguarda (Admin, fechamento do dia), jamais pelo terminal.
    from shopman.cashman import services as cash
    from shopman.cashman.models import Entry

    float_q = sum(entry.amount_q for entry in cash.timeline(shift) if entry.kind == Entry.Kind.FLOAT_IN)
    return {
        "id": shift.pk,
        "terminal_ref": shift.terminal.ref,
        "operator": shift.opened_by.get_username(),
        "status": shift.status,
        "opened_at": shift.opened_at.isoformat() if shift.opened_at else "",
        "closed_at": shift.closed_at.isoformat() if shift.closed_at else "",
        "opening_amount_q": float_q,
        "blind_closing_amount_q": cash.counted(shift),
    }


def _pos_payload_with_runtime(request, body: dict) -> dict:
    """Attach the active POS runtime context that browser surfaces should not invent."""
    payload = dict(body or {})
    cash_shift = _open_cash_shift_for_request(request)
    if cash_shift:
        # O servidor CONHECE o turno do operador — o browser nunca decide a
        # atribuição de caixa (um id forjado/null desviaria a venda do turno).
        payload["cash_shift_id"] = cash_shift.pk
        payload["pos_terminal_ref"] = cash_shift.terminal.ref
    return payload


def _open_cash_shift_for_request(request):
    """O turno ABERTO do operador no ``cashman`` — é o pk dele que vai em ``cash_shift_id``."""
    try:
        return pos_service.current_shift()
    except Exception:
        logger.debug("pos_runtime_payload_enrichment_failed user=%s", _actor(request), exc_info=True)
        return None


def _cash_shift_required_response() -> Response:
    return Response(
        {
            "detail": "Abra o caixa antes de revisar ou finalizar uma venda.",
            "error": {
                "code": "cash_shift_required",
                "message": "Abra o caixa antes de revisar ou finalizar uma venda.",
                "field": "cash_shift_id",
                "focus": "cash",
                "recovery": "Abra um turno de caixa neste terminal e tente novamente.",
            },
        },
        status=409,
    )


def _pos_sale_review_payload(review) -> dict:
    return {
        "intent_version": review.intent_version,
        "tab_ref": review.tab_ref,
        "subtotal_q": review.subtotal_q,
        "subtotal_display": f"R$ {format_money(review.subtotal_q)}",
        "discount_q": review.discount_q,
        "discount_display": f"R$ {format_money(review.discount_q)}",
        # Os dois escopos, para o bloco de totais nomear cada um: o desconto que
        # o operador deu nos ITENS e o que deu na VENDA. A soma é `discount_q`.
        "line_discount_q": review.line_discount_q,
        "line_discount_display": f"R$ {format_money(review.line_discount_q)}",
        "order_discount_q": review.order_discount_q,
        "order_discount_display": f"R$ {format_money(review.order_discount_q)}",
        "delivery_fee_q": review.delivery_fee_q,
        "delivery_fee_display": f"R$ {format_money(review.delivery_fee_q)}",
        "total_q": review.total_q,
        "total_display": f"R$ {format_money(review.total_q)}",
        "payment_method": review.payment_method,
        "payment_collection": review.payment_collection,
        "tender_total_q": review.tender_total_q,
        "tender_total_display": f"R$ {format_money(review.tender_total_q)}",
        "tender_count": review.tender_count,
        "tendered_q": review.tendered_q,
        "tendered_amount_display": f"R$ {format_money(review.tendered_q)}",
        "change_q": review.change_q,
        "change_display": f"R$ {format_money(review.change_q)}",
        "requires_manager_approval": review.requires_manager_approval,
        "manager_approval_threshold_q": review.manager_approval_threshold_q,
        "approval_reasons": list(review.approval_reasons),
        "receipt_channels": list(review.receipt_channels),
        "fiscal_tax_id_requested": review.fiscal_tax_id_requested,
        "warnings": list(review.warnings),
        # Entrega: a taxa vem RESOLVIDA (com a origem, para a tela se explicar) e
        # os horários vêm do expediente do dia. A tela pergunta; não inventa.
        "delivery_fee_source": review.delivery_fee_source,
        "delivery_distance_km": review.delivery_distance_km,
        "delivery_date": review.delivery_date,
        "delivery_slots": list(review.delivery_slots),
        "delivery_earliest_slot": review.delivery_earliest_slot,
    }


# ── Read endpoints ────────────────────────────────────────────────────


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="POS terminal projection",
        responses={200: OpenApiResponse(description="Products, tabs, payment methods, shift summary.")},
    ),
)
class POSView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def get(self, request):
        from shopman.backstage.services.operator import operator_card, pin_must_change
        # A ESTAÇÃO diz qual gaveta é esta — o cookie de confiança carrega o ref. É o
        # que permite a loja de duas gavetas ler o quadro certo em cada balcão, em vez
        # de os dois disputarem o primeiro em ordem alfabética.
        pos = build_pos(operator=request.user, terminal_ref=station_trust.station_ref(request))
        shift = build_pos_shift_summary()
        query = request.query_params.get("q", "")
        tabs = build_pos_tabs(query=query)
        # Quem opera é quem está logado — não há mais um cartão de "operador
        # ativo" na sessão para consultar ao lado da conta do dispositivo.
        return Response({
            "pos": projection_data(pos),
            "shift": projection_data(shift),
            "tabs": projection_data(tabs),
            "operator": operator_card(request.user),
            "pin_must_change": pin_must_change(request.user),
        })


class POSPaymentStatusView(APIView):
    """GET /pos/payment/<ref>/status/ — polling do estado de pagamento (PIX no PDV).

    O status endpoint do storefront é gateado pela sessão de checkout do CLIENTE
    (anônima) — o operador (staff) não se encaixa. Este é o equivalente operador,
    gateado por operate_pos, para o POS ver a confirmação do PIX chegar sem sair
    do balcão. Reusa build_payment_status (por-order, is_paid/is_cancelled/…).
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def get(self, request, ref: str):
        from django.http import Http404
        from shopman.orderman.models import Order

        from shopman.shop.projections.payment_status import build_payment_status
        from shopman.shop.services import customer_orders

        try:
            order = Order.objects.get(ref=ref)
        except Order.DoesNotExist as exc:
            raise Http404("Order not found") from exc

        # Resolve timers vencidos (auto-cancel de PIX / confirmação) antes de
        # reportar. Camada shop — backstage NUNCA importa storefront (CLAUDE.md).
        try:
            customer_orders.resolve_payment_timeout_if_due(order)
            customer_orders.resolve_confirmation_timeout_if_due(order)
        except Exception:
            logger.warning("pos.payment_status: resolve_timeouts falhou order=%s", ref, exc_info=True)

        return Response(projection_data(build_payment_status(order)))


# ── Generic operator identification (PIN / badge) — shared by all surfaces ──
# (The former POS-specific operator/unlock|lock views were folded into the generic
#  endpoints below; the POS surface now uses them with perm=operate_pos.)
# The device session is the station trust (IsBackstageOperator); these establish
# WHO is operating (active operator) for the Opção C authorization layer. They are
# gated on the device session only — never on an active operator (chicken-egg).

# Permissions a surface may ask the operator to satisfy at unlock (whitelist, so a
# client can only restrict — never widen — who may unlock there).
_OPERATOR_UNLOCK_PERMS = {
    "cashman.operate_pos",
    "backstage.operate_kds",
    "backstage.operate_production",
    "backstage.operate_purchase",
    "shop.manage_orders",
    # Campanha (surfaces/marketing-nuxt): sem esta entrada a tela de destravar
    # rejeita a permissão e o app fica trancado para sempre com o gate ligado.
    "shop.manage_campaigns",
    # B.I. (surfaces/bi-nuxt, ADR-021): mesma armadilha da campanha acima.
    "backstage.view_bi",
}


def _validated_unlock_perm(raw) -> tuple[str | None, bool]:
    perm = (str(raw or "").strip()) or None
    if perm is not None and perm not in _OPERATOR_UNLOCK_PERMS:
        return None, False
    return perm, True


class OperatorSessionView(APIView):
    """Estado da antessala: qual estação é esta, e quem (se alguém) está operando.

    Gate de ESTAÇÃO, não de sessão: quando o balcão está travado não há ninguém
    logado, e exigir sessão aqui deixaria a tela sem saber sequer que precisa
    pedir PIN.
    """

    permission_classes = [IsTrustedStation]

    def get(self, request):
        from shopman.backstage.services.operator import operator_card, pin_must_change
        from shopman.backstage.station_trust import station_ref

        operador = request.user if getattr(request.user, "is_authenticated", False) else None
        return Response({
            # `station` substituiu `device_user`: o que a tela precisa saber é de
            # QUE BALCÃO ela é, não com que conta a máquina entrou — porque não
            # há mais conta de máquina.
            "station": station_ref(request),
            "operator": operator_card(operador) if operador else None,
            "locked": operador is None,
            "pin_must_change": pin_must_change(operador),
        })


def _login_username_key(group, request):
    """Chave de rate-limit pela conta-alvo do login.

    O BFF envia JSON (onde `request.POST` fica vazio); o teste e forms enviam
    form-encoded. Lê os dois para que o limite por-username funcione em produção —
    sem isso, JSON colapsaria todas as contas num único bucket global.
    """
    username = request.POST.get("username")
    if not username and "json" in (request.content_type or ""):
        try:
            username = (json.loads(request.body or b"{}") or {}).get("username")
        except (ValueError, TypeError):
            username = None
    return (str(username or "").strip().lower()) or "anon"


@method_decorator(
    ratelimit(key="ip", rate="30/m", method="POST", block=False), name="dispatch"
)
@method_decorator(
    ratelimit(key=_login_username_key, rate="5/m", method="POST", block=False), name="dispatch"
)
class OperatorLoginView(APIView):
    """Login de operador NO PRÓPRIO app (sem bounce pro Django admin).

    Reusa a auth do Django (mesma credencial do admin): valida usuário+senha e abre a
    sessão DAQUELA PESSOA (o cookie é escopado ao domínio de operador pelo middleware).
    O front mostra um formulário e já entra — uma tela, um submit, sem sair do app. Só
    concede sessão a staff.

    É o caminho de quem tem senha: quem provisiona a estação, e o operador de um
    dispositivo pessoal. No balcão, o caminho normal é o PIN/crachá — mas a sessão
    que sai daqui é a mesma coisa, a identidade de uma pessoa. Não existe login
    "do dispositivo": o dispositivo é reconhecido por confiança de dispositivo.

    Freio contra brute-force de senha staff: limite por-username (ataque a uma conta)
    de 5/min e teto por-IP de 30/min — generoso porque os dispositivos da loja
    compartilham o IP (NAT). Ambos `block=False`: o handler devolve 429 amigável.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        from django.contrib.auth import authenticate

        from shopman.backstage.services.operator import operator_card

        if getattr(request, "limited", False):
            return Response(
                {
                    "detail": "Muitas tentativas de login. Aguarde um minuto e tente de novo.",
                    "error": {"code": "operator_login_rate_limited"},
                },
                status=429,
            )

        body = request.data or {}
        username = str(body.get("username") or "").strip()
        password = str(body.get("password") or "")
        if not username or not password:
            return Response({"detail": "Informe usuário e senha."}, status=400)

        user = authenticate(request, username=username, password=password)
        if user is None or not user.is_staff:
            return Response(
                {"detail": "Usuário ou senha inválidos.", "error": {"code": "operator_login_invalid"}},
                status=403,
            )
        # Quem sabe por qual porta a pessoa entrou é quem abre a porta: o
        # backend de autenticação não distingue senha de PIN nem de crachá. A
        # linha da trilha quem grava é o receiver do `user_logged_in`.
        sign_in_audit.mark_method(request, SignInMethod.PASSWORD)
        login(request, user)
        # `operator`, e não `device_user`: entrar com senha é identificar-se como
        # aquela pessoa. Não existe mais conta de máquina para nomear aqui.
        return Response({"ok": True, "operator": operator_card(user)})


class OperatorEligibleView(APIView):
    """Operators who may unlock this surface (the lock-screen picker)."""

    permission_classes = [IsTrustedStation]

    def get(self, request):
        from shopman.backstage.services.operator import eligible_operators, operator_card

        perm, ok = _validated_unlock_perm(request.query_params.get("perm"))
        if not ok:
            return Response({"detail": "Permissão de operador inválida."}, status=400)
        return Response({"operators": [operator_card(u) for u in eligible_operators(perm=perm)]})


class OperatorUnlockView(APIView):
    """Establish the active operator by PIN (operator_id + pin) or badge (token).

    Optional ``perm`` (the surface's capability) restricts who may unlock here.

    Gate de ESTAÇÃO, e não de sessão: é AQUI que o balcão travado cria uma, e
    exigir sessão para criar sessão é a porta que não abre de manhã. A
    autorização real deste endpoint não é o gate — é provar o PIN ou o crachá.
    """

    permission_classes = [IsTrustedStation]

    def post(self, request):
        from django.contrib.auth import get_user_model

        from shopman.backstage.services import operator as operator_service

        body = request.data or {}
        perm, ok = _validated_unlock_perm(body.get("perm"))
        if not ok:
            return Response({"detail": "Permissão de operador inválida."}, status=400)

        badge = str(body.get("badge") or "").strip()
        if badge:
            metodo = SignInMethod.BADGE
            tentado = ""
            # Crachá que não bate não tem conta a nomear, e é isso mesmo que a
            # linha deve dizer: ninguém a ser avisado, só o log registrando que
            # alguém passou um crachá que não existe.
            alvo = None
            operator = operator_service.resolve_operator_by_badge(badge, required_perm=perm)
        else:
            metodo = SignInMethod.PIN
            operator_id = str(body.get("operator_id") or "").strip()
            pin = str(body.get("pin") or "")
            operator = (
                get_user_model().objects.filter(pk=operator_id, is_active=True).first()
                if operator_id else None
            )
            tentado = operator.get_username() if operator is not None else ""
            # Guardado ANTES da verificação: se o PIN falhar, `operator` vira
            # None e some a única referência à conta-alvo — que é justamente
            # quem precisa ser avisado de que alguém errou o PIN dela.
            alvo = operator
            if operator is not None and not operator_service.verify_operator_pin(operator, pin, required_perm=perm):
                operator = None

        if operator is None:
            # A recusa de PIN/crachá NÃO passa por `authenticate()`, então não
            # existe `user_login_failed` para ouvir: é aqui, na única view que a
            # produz, que ela vira linha. Mesma função de gravação do sucesso —
            # duas origens para um fato que o Django só anuncia pela metade, e
            # não dois caminhos de trilha.
            #
            # Crachá recusado não tem conta a nomear (o token não bateu com
            # ninguém), e é isso mesmo que a linha deve dizer.
            sign_in_audit.record(
                user=alvo,
                username=tentado or sign_in_audit.UNKNOWN_SUBJECT,
                method=metodo,
                outcome=SignInOutcome.FAILED,
                request=request,
                reason="operator_unlock_invalid",
            )
            return Response(
                {"detail": "Identificação inválida.", "error": {"code": "operator_unlock_invalid"}},
                status=403,
            )
        # `login()` de verdade, e não um cartão guardado na sessão: a partir daqui
        # `request.user` É a pessoa, e toda permissão passa a ser dela por
        # construção. Era a existência de DUAS identidades que abria o buraco —
        # sempre havia um caminho que perguntava para a errada.
        #
        # A chave de sessão cicla no login (Django troca ao mudar de usuário), e
        # isso é desejável: nada do turno anterior atravessa a troca de operador.
        # A identidade da ESTAÇÃO sobrevive porque não mora na sessão — mora no
        # cookie de confiança de dispositivo, que o ciclo não toca.
        # ``backend=`` explícito porque quem provou a identidade foi o PIN/crachá, e
        # não um backend de autenticação: com dois configurados (OTP de cliente,
        # senha de staff) o Django não adivinha qual gravar na sessão e levanta
        # ``ValueError``. Sem isto, o destrave respondia 500 no balcão.
        sign_in_audit.mark_method(request, metodo)
        login(request, operator, backend=MODEL_BACKEND)
        return Response({"ok": True, "operator": operator_service.operator_card(operator)})


class OperatorLockView(APIView):
    """Trava a estação: a pessoa sai, o dispositivo fica.

    Com uma identidade só, travar é ``logout``. A sessão inteira vai embora —
    incluindo o que o turno anterior tenha deixado nela — e o dispositivo continua
    reconhecido pelo cookie de estação, que é o que faz a tela de identificação
    aparecer em vez de uma tela de login.
    """

    permission_classes = [IsBackstageOperator]

    def post(self, request):
        logout(request)
        return Response({"ok": True})


class OperatorBadgeLostView(APIView):
    """O operador declara que perdeu o crachá, provando o PIN.

    Ativo, não reativo: quem perde o crachá às 6h não espera o ladrão usar.
    Mesmo efeito do "não fui eu" — sessões caem, crachá morre, PIN fica de pé.

    Gate de ESTAÇÃO e não de sessão, igual à troca de PIN: quem chega sem crachá
    está na tela de destrave, ainda sem sessão. **Provar o PIN é a autorização** —
    o crachá é de quem sabe o PIN daquela conta. PIN errado conta para o lockout.
    """

    permission_classes = [IsTrustedStation]

    def post(self, request):
        from shopman.backstage.services import operator as operator_service

        body = request.data or {}
        # Confirmação ANTES do PIN: um cliente que esqueceu a flag não pode
        # gastar uma tentativa do lockout de quem nem pediu nada.
        if str(body.get("confirm") or "").lower() not in ("1", "true", "yes"):
            return Response(
                {
                    "ok": False,
                    "needs_confirmation": True,
                    "detail": (
                        "Seu crachá será invalidado e as sessões abertas da sua conta "
                        "serão encerradas. Seu PIN continua valendo. Um gerente emite "
                        "outro crachá."
                    ),
                },
                status=409,
            )

        pin = str(body.get("pin") or "")
        if not pin:
            return Response({"detail": "Informe o seu PIN.", "field": "pin"}, status=400)

        alvo = operator_service.resolve_target_for_pin_change(request, body.get("operator_id"))
        if alvo is None:
            return Response(
                {"detail": "Operador não identificado.", "error": {"code": "no_credential"}},
                status=400,
            )

        # `required_perm=None`: o crachá é da PESSOA, não da tela. Exigir a
        # permissão desta superfície deixaria quem opera só a Produção sem poder
        # matar o próprio crachá a partir do balcão em que está.
        if not operator_service.verify_operator_pin(alvo, pin, required_perm=None):
            # Errar o PIN aqui é tentar matar o crachá de alguém: vira linha, e o
            # dono é avisado como em qualquer recusa.
            sign_in_audit.record(
                user=alvo,
                method=SignInMethod.PIN,
                outcome=SignInOutcome.FAILED,
                request=request,
                reason="badge_lost_invalid",
            )
            return Response(
                {"detail": "PIN inválido.", "error": {"code": "operator_pin_invalid"}},
                status=403,
            )

        try:
            resultado = sign_in_audit.revoke_access(
                # Provar o PIN É ser o dono — a mesma autorização da troca de PIN.
                user=alvo, requested_by=alvo,
                reason=sign_in_audit.REASON_LOST, request=request,
            )
        except sign_in_audit.RevokeError as exc:
            return Response({"detail": str(exc), "error": {"code": exc.code}}, status=400)

        return Response({"ok": True, **resultado})


class OperatorPinChangeView(APIView):
    """Operator changes their OWN PIN, proving the current one.

    Knowing the current PIN *is* the authorization: you can only rotate a PIN you
    already hold. Target is the active operator (post-unlock), or an explicit
    ``operator_id`` (the lock-screen forced-change flow, where the temp PIN is the
    "current"). A wrong current PIN counts toward lockout.
    """

    permission_classes = [IsTrustedStation]

    def post(self, request):
        from shopman.doorman.models import PinCredentialError

        from shopman.backstage.services import operator as operator_service

        body = request.data or {}
        current_pin = str(body.get("current_pin") or "")
        new_pin = str(body.get("new_pin") or "")
        if not current_pin or not new_pin:
            return Response({"detail": "Informe o PIN atual e o novo PIN."}, status=400)

        target = operator_service.resolve_target_for_pin_change(request, body.get("operator_id"))
        if target is None:
            return Response(
                {"detail": "Operador não identificado.", "error": {"code": "no_credential"}},
                status=400,
            )

        try:
            operator_service.change_own_pin(target, current_pin, new_pin)
        except operator_service.PinChangeError as exc:
            status = 423 if exc.code == "locked" else 400
            return Response({"detail": str(exc), "error": {"code": exc.code}}, status=status)
        except PinCredentialError as exc:
            return Response({"detail": str(exc), "error": {"code": "pin_policy"}}, status=400)
        return Response({"ok": True})


class StationProvisionView(APIView):
    """Torna ESTE dispositivo uma estação da loja — ou tira essa condição dele.

    É o que faltava para tudo o mais existir: sem provisionamento, nenhum
    dispositivo é reconhecido, o balcão amanhece sem antessala e a única entrada é
    senha de gestor todo dia. O gate da estação é a chave da antessala; isto é
    quem entrega a chave.

    O ato é de GESTÃO e acontece UMA vez por dispositivo: alguém com
    ``cashman.manage_operators`` entra com senha naquele balcão e diz "este
    computador é o pdv-main". A partir daí o cookie HttpOnly durável responde por
    ele, revogável no Admin (lista de dispositivos) ou aqui mesmo, com a máquina
    na mão. É o mesmo caminho do quadro de menu, que já roda em produção — nada
    de token em URL, nada de re-digitar a cada duas semanas.

    ``GET`` responde o que a tela de provisionamento precisa: que estação este
    dispositivo é hoje (``""`` quando nenhuma) e os terminais disponíveis.
    """

    permission_classes = [HasBackstagePermission]
    required_permission = station_trust.PROVISION_PERM

    def get(self, request):
        from shopman.cashman.models import Terminal

        return Response({
            "station": station_trust.station_ref(request),
            "terminals": [
                {"ref": t.ref, "label": t.label or t.ref}
                for t in Terminal.objects.filter(is_active=True).order_by("ref")
            ],
        })

    def post(self, request):
        from shopman.cashman.models import Terminal

        ref = str((request.data or {}).get("terminal_ref") or "").strip()
        if not Terminal.objects.filter(ref=ref, is_active=True).exists():
            # Um ref inexistente gravaria uma confiança que nunca resolve terminal:
            # o dispositivo passaria no gate e cairia no `Terminal.default()`, que é a
            # gaveta errada. Recusar aqui é mais barato que caçar isso no balcão.
            return Response(
                {"detail": "Terminal não encontrado.", "error": {"code": "terminal_unknown"}},
                status=400,
            )
        resposta = Response({"ok": True, "station": ref})
        station_trust.provision(request, resposta, ref)
        return resposta

    def delete(self, request):
        ref = str(request.query_params.get("terminal_ref") or station_trust.station_ref(request)).strip()
        if not ref:
            return Response({"detail": "Este dispositivo não é uma estação."}, status=400)
        resposta = Response({"ok": True, "station": ""})
        station_trust.revoke(request, resposta, ref)
        return resposta


class OperatorPinResetView(APIView):
    """Manager resets an operator's PIN → temp PIN + forced change on first use.

    Gated by ``cashman.manage_operators``, que é a permissão de gerir operadores —
    conferida, como todas, contra quem está operando. O PIN temporário volta uma
    vez só: o gerente o lê para o operador, e só o digest HMAC fica guardado.
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.manage_operators"

    def post(self, request):
        from django.contrib.auth import get_user_model
        from shopman.doorman.models import PinCredentialError

        from shopman.backstage.services import operator as operator_service

        body = request.data or {}
        user_model = get_user_model()
        target = None
        raw_id = str(body.get("user_id") or body.get("operator_id") or "").strip()
        username = str(body.get("username") or "").strip()
        if raw_id:
            target = user_model.objects.filter(pk=raw_id, is_staff=True).first()
        elif username:
            target = user_model.objects.filter(username=username, is_staff=True).first()

        try:
            temp_pin = operator_service.reset_operator_pin(target, temp_pin=body.get("temp_pin"))
        except operator_service.PinChangeError as exc:
            # `superuser_target` é recusa de AUTORIZAÇÃO, não pedido malformado: quem
            # tem `manage_operators` não tem, por isso, poder sobre a conta que
            # administra o sistema. 403 é o código honesto.
            status = {"no_target": 404, "superuser_target": 403}.get(exc.code, 400)
            return Response({"detail": str(exc), "error": {"code": exc.code}}, status=status)
        except PinCredentialError as exc:
            return Response({"detail": str(exc), "error": {"code": "pin_policy"}}, status=400)
        return Response({"ok": True, "temp_pin": temp_pin, "must_change": True})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Production board",
        responses={200: OpenApiResponse(description="Work orders for the selected date.")},
    ),
)
class ProductionBoardView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_production"

    def get(self, request):
        selected = _parse_date(request.query_params.get("date"))
        position_ref = request.query_params.get("position", "")
        board = build_production_board(
            selected_date=selected,
            position_ref=position_ref,
        )
        return Response({"board": projection_data(board)})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Production forecast board (airport-style panel for the store team)",
        responses={200: OpenApiResponse(description="Per-batch forecast: quantities, ETA and status.")},
    ),
)
class ProductionForecastView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_production"

    def get(self, request):
        selected = _parse_date(request.query_params.get("date"))
        forecast = build_production_forecast(selected_date=selected)
        return Response({"forecast": projection_data(forecast)})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Production KDS (started work orders)",
        responses={200: OpenApiResponse(description="Live KDS board for production.")},
    ),
)
class ProductionKDSView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_production"

    def get(self, request):
        selected = _parse_date(request.query_params.get("date"))
        position_ref = request.query_params.get("position", "")
        kds = build_production_kds(
            selected_date=selected,
            position_ref=position_ref,
        )
        return Response({"kds": projection_data(kds)})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="QC kiosk (day's batches + quality catalogs)",
        responses={200: OpenApiResponse(description="QC kiosk projection for the fournil.")},
    ),
)
class ProductionQCView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_production"

    def get(self, request):
        selected = _parse_date(request.query_params.get("date"))
        kiosk = build_qc_kiosk(selected_date=selected)
        return Response({"qc": projection_data(kiosk)})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Mise en place (aggregated material needs for the day)",
        responses={200: OpenApiResponse(description="Aggregated ingredient list for open work orders.")},
    ),
)
class ProductionMiseEnPlaceView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_production"

    def get(self, request):
        selected = _parse_date(request.query_params.get("date"))
        expand = str(request.query_params.get("expand", "")).lower() in ("1", "true", "yes")
        mise_en_place = build_production_mise_en_place(
            selected_date=selected,
            expand=expand,
        )
        return Response({"mise_en_place": projection_data(mise_en_place)})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Weighing tickets (per-prep scaled ingredients + blind codes)",
        responses={200: OpenApiResponse(description="Per-prep weighing tickets for the day.")},
    ),
)
class ProductionWeighingView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_production"

    def get(self, request):
        selected = _parse_date(request.query_params.get("date"))
        weighing = build_production_weighing(
            selected_date=selected,
            position_ref=request.query_params.get("position", ""),
            base_recipe=request.query_params.get("base_recipe", ""),
        )
        return Response({"weighing": projection_data(weighing)})


class ProductionReportsCSVRenderer(BaseRenderer):
    """Renderer pass-through do CSV pronto (``export_reports_csv`` já emite BOM UTF-8).

    Registrado na view de relatórios para o ``?format=csv`` canônico do DRF
    selecionar o download em vez de cair no 404 da negociação de conteúdo.
    """

    media_type = "text/csv"
    format = "csv"
    charset = None
    render_style = "binary"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if isinstance(data, bytes):
            return data
        # Erros (403 etc.) chegam como dict do exception handler — vira JSON legível.
        return json.dumps(data).encode("utf-8")


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Production reports (history, operator productivity, recipe waste)",
        responses={200: OpenApiResponse(description="Report rows for the requested filters (or CSV with ?format=csv).")},
    ),
)
class ProductionReportsView(APIView):
    """Relatórios de produção — persona GESTOR (perm fina, não o gate de chão)."""

    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.view_production_reports"
    renderer_classes = [JSONRenderer, ProductionReportsCSVRenderer]

    def get(self, request):
        filters = report_filters(request)
        if request.accepted_renderer.format == "csv":
            csv_bytes = production_service.export_reports_csv(filters["report_kind"], filters)
            filename = f"producao_{filters['report_kind']}_{filters['date_from']}_{filters['date_to']}.csv"
            return Response(
                csv_bytes,
                content_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        reports = build_production_reports(filters)
        return Response({"reports": projection_data(reports)})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Production management KPIs (average yield, capacity, late orders)",
        responses={200: OpenApiResponse(description="Day-level management dashboard for production.")},
    ),
)
class ProductionManagementView(APIView):
    """KPIs de gestão do dia — persona GESTOR (perm fina, não o gate de chão)."""

    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.view_production_reports"

    def get(self, request):
        selected = _parse_date(request.query_params.get("date"))
        dashboard = build_production_dashboard(
            selected_date=selected,
            position_ref=request.query_params.get("position", ""),
        )
        return Response({"management": projection_data(dashboard)})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Blind code ↔ prep map (manager-only correlation of weighing labels)",
        responses={200: OpenApiResponse(description="The day's blind codes with their preps.")},
    ),
)
class ProductionBlindMapView(APIView):
    """Mapa código-cego ↔ preparo — persona GESTOR; as telas de chão são cegas."""

    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.view_production_reports"

    def get(self, request):
        selected = _parse_date(request.query_params.get("date"))
        blind_map = build_production_blind_map(
            selected_date=selected,
            position_ref=request.query_params.get("position", ""),
            base_recipe=request.query_params.get("base_recipe", ""),
        )
        return Response({"blind_map": projection_data(blind_map)})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Day closing snapshot",
        responses={200: OpenApiResponse(description="Items pending closing decision.")},
    ),
)
class OperationEpisodeAnswerView(APIView):
    """O operador responde o que houve — uma escolha, não um formulário.

    Corpo: ``{"kind_ref": "falta-de-energia"}`` para explicar, ou
    ``{"kind_ref": ""}`` para dizer que não houve nada (falso alarme).
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.perform_closing"

    def post(self, request, episode_id: int):
        from shopman.backstage.services.episodes import answer

        kind_ref = str(request.data.get("kind_ref", "") or "").strip()
        note = str(request.data.get("note", "") or "").strip()
        try:
            episode = answer(
                episode_id,
                kind_ref=kind_ref,
                actor=request.user.get_username(),
                note=note,
            )
        except ObjectDoesNotExist:
            return Response(
                {"detail": "Episódio ou motivo não encontrado.", "field": "kind_ref"},
                status=404,
            )
        return Response({"ok": True, "status": episode.status})


class DayClosingView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.perform_closing"

    def get(self, request):
        closing = build_day_closing()
        return Response({"closing": projection_data(closing)})

    def post(self, request):
        """Finalize the day closing.

        Body: { "quantities": { "<sku>": "<qty>", ... } }
        """
        quantities = request.data.get("quantities", {}) if hasattr(request, "data") else {}
        if not isinstance(quantities, dict):
            return Response({"detail": "Envie as quantidades como um objeto (sku: quantidade)."}, status=400)

        closing = build_day_closing()
        if closing.already_closed:
            return Response({"detail": "Fechamento de hoje já foi realizado."}, status=409)

        try:
            closing_date = closing_service.perform_day_closing(
                user=request.user,
                items=list(closing.items),
                quantities_by_sku={str(k): str(v) for k, v in quantities.items()},
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("day_closing_perform_failed user=%s", _actor(request), exc_info=True)
            return Response({"detail": str(exc) or "Falha no fechamento."}, status=400)

        return Response({"ok": True, "closing_date": closing_date.isoformat()})


def _reconcile_payment_if_due(order) -> None:
    """Pergunta ao gateway (throttled) se este pedido de cartão já foi pago.

    Mesma função que a volta do Stripe usa na loja — um dono só para a regra,
    duas portas de entrada. Degrada em silêncio: a tela do operador não pode
    cair porque o provedor não respondeu.
    """
    try:
        from shopman.shop.services import payment as payment_service

        payment_service.reconcile_with_gateway_if_due(order)
    except Exception:
        logger.warning("order_detail.gateway_reconcile degraded ref=%s", order.ref, exc_info=True)


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Operator order detail",
        responses={200: OpenApiResponse(description="Full operator order projection.")},
    ),
)
class OrderDetailView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_orders"

    def get(self, request, ref: str):
        order = orders_service.find_order(ref)
        if order is None:
            return Response({"detail": "Pedido não encontrado."}, status=404)
        # ⚠️ O OPERADOR TAMBÉM PRECISA PODER PERGUNTAR AO GATEWAY.
        #
        # A reconciliação contra webhook perdido nasceu só no acompanhamento do
        # cliente, e isso deixou a verdade do Gestor pendurada no navegador de
        # outra pessoa: cliente que paga e fecha a aba (ou paga em outro
        # aparelho) some do circuito, e o card fica em "Aguardando pagamento…"
        # sem que exista, na loja, um gesto capaz de resolver. O worker resgata
        # em minutos; abrir o pedido resolve agora.
        #
        # Custo: o mesmo throttle de ``GATEWAY_RECHECK_SECONDS`` do cliente, e
        # só para cartão em aberto. A fila (``OrderQueueView``) segue fora
        # disto de propósito — ela relê o board inteiro o tempo todo, e uma
        # chamada por card viraria enxurrada no provedor.
        _reconcile_payment_if_due(order)
        proj = build_operator_order(order, user=request.user)
        return Response({"order": projection_data(proj)})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Operator order queue (two-zone view)",
        responses={200: OpenApiResponse(description="Active and recent orders for operator.")},
    ),
)
class OrderQueueView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_orders"

    def get(self, request):
        queue = build_two_zone_queue()
        return Response({"queue": projection_data(queue)})


# ── Order action endpoints ────────────────────────────────────────────


class _OrderActionBase(APIView):
    """Shared base for order action endpoints (advance/confirm/reject/cancel)."""

    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_orders"

    def _get_order(self, ref: str):
        order = orders_service.find_order(ref)
        if order is None:
            return None, Response({"detail": "Pedido não encontrado."}, status=404)
        return order, None


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Advance order to next status",
        responses={200: OpenApiResponse(description="Order advanced.")},
    ),
)
class OrderAdvanceView(_OrderActionBase):
    def post(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        # ``change_out``: troco que o entregador leva da gaveta no despacho de
        # entrega em dinheiro (reais; "0" = levou sem troco). Ausente em pedido
        # que pede troco → 409 com a sugestão, para a tela perguntar.
        body = request.data or {}
        change_out = body.get("change_out")
        equipment = body.get("equipment") or []
        if not isinstance(equipment, list):
            equipment = [equipment]
        try:
            orders_service.advance_order(
                order,
                actor=_actor(request),
                operator=request.user,
                change_out_raw=None if change_out is None else str(change_out),
                equipment=[str(ref) for ref in equipment],
            )
        except orders_service.OrderChangeOutRequired as exc:
            return Response(
                {"detail": str(exc), "code": "change_out_required", "suggested_q": exc.suggested_q},
                status=409,
            )
        except OrderError as exc:
            return Response({"detail": str(exc) or "Ação inválida."}, status=400)
        return Response({"ok": True, "ref": ref})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Confirm pending order",
        responses={
            200: OpenApiResponse(description="Order confirmed."),
            409: OpenApiResponse(description="Order already left the pending state."),
        },
    ),
)
class OrderConfirmView(_OrderActionBase):
    def post(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        try:
            orders_service.confirm_order(order, actor=_actor(request))
        except OrderConflict as exc:
            return Response({"detail": str(exc)}, status=409)
        except OrderError as exc:
            return Response({"detail": str(exc) or "Falha ao aceitar o pedido."}, status=400)
        return Response({"ok": True, "ref": ref})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Reject pending order",
        responses={
            200: OpenApiResponse(description="Order rejected."),
            409: OpenApiResponse(description="Order already left the pending state."),
        },
    ),
)
class OrderRejectView(_OrderActionBase):
    def post(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        reason = (request.data.get("reason") or "").strip() if hasattr(request, "data") else ""
        if not reason:
            return Response({"detail": "Motivo da recusa é obrigatório."}, status=400)
        cancellation_code = (request.data.get("cancellation_code") or "").strip()
        try:
            orders_service.reject_order(
                order,
                reason=reason,
                actor=_actor(request),
                rejected_by="operator",
                cancellation_code=cancellation_code,
            )
        except OrderConflict as exc:
            return Response({"detail": str(exc)}, status=409)
        except OrderError as exc:
            return Response({"detail": str(exc) or "Falha ao recusar."}, status=400)
        return Response({"ok": True, "ref": ref})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Cancel order",
        responses={200: OpenApiResponse(description="Order cancelled.")},
    ),
)
class OrderCancelView(_OrderActionBase):
    """Cancelamento pelo operador — três camadas, cada uma respondendo o que é dela.

    A régua (``snapshot.lifecycle.transitions``) diz se a transição é possível
    para ESTE pedido; ``operator_cancel_policy`` diz se é permitida AGORA,
    olhando o ciclo do pagamento; e aqui se responde se ESTE ator pode.

    Cancelar um pedido em estado avançado (``ready``/``completed``) é de gerente:
    ``shop.manage_orders`` sozinho continua cancelando o que sempre cancelou
    (``new``/``accepted``/``preparing``), que é o trabalho do Caixa. E pedido
    PAGO exige segunda assinatura, com ou sem estado avançado — é a mesma régua
    que o PDV já aplica em ``POSCancelRecentSaleView``, agora valendo para todo
    caminho de operador em vez de só naquele endpoint.
    """

    def post(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err

        policy = cancellation_service.operator_cancel_policy(order)
        if not policy.allowed:
            return Response({"detail": policy.reason}, status=409)

        if cancellation_service.is_advanced_cancel(order) and not request.user.has_perm(
            cancellation_service.ADVANCED_CANCEL_PERMISSION
        ):
            return Response(
                {
                    "detail": f"Cancelar pedido em {order.get_status_display()} é do gerente.",
                    "error": {"code": "cancel_requires_manager"},
                },
                status=403,
            )

        if policy.requires_approval:
            try:
                # O validador levanta com código próprio (`manager_approval_required`
                # x `manager_approval_invalid`) e devolve o User que assinou — a
                # tela distingue "falta gerente" de "PIN errado" sem ler a frase.
                pos_tabs_service.validate_manager_override(
                    request.data.get("manager_approval"),
                    operator_username=_username(request),
                    action="cancel_paid_order",
                )
            except PosIntentError as exc:
                return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)

        # The operator's typed/preset text (may be blank). It rides through as the
        # customer-facing note; the audit reason falls back to a generic label.
        operator_reason = (request.data.get("reason") or "").strip()
        reason = operator_reason or "Cancelado pelo operador"
        cancellation_code = (request.data.get("cancellation_code") or "").strip()
        try:
            orders_service.cancel_order(
                order,
                reason=reason,
                actor=_actor(request),
                cancellation_code=cancellation_code,
                customer_note=operator_reason,
            )
        except OrderConflict as exc:
            return Response({"detail": str(exc)}, status=409)
        except OrderError as exc:
            return Response({"detail": str(exc) or "Falha ao cancelar."}, status=400)
        return Response({"ok": True, "ref": ref})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Valid cancellation reasons for an order (marketplace-aware)",
        responses={200: OpenApiResponse(description="Reason list.")},
    ),
)
class OrderCancellationReasonsView(_OrderActionBase):
    def get(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        return Response({"reasons": orders_service.cancellation_reasons(order)})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Settle delivery cash-on-delivery into the operator's open shift",
        responses={200: OpenApiResponse(description="Cash settled.")},
    ),
)
class OrderSettleDeliveryCashView(_OrderActionBase):
    def post(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        try:
            change_back = (request.data or {}).get("change_back")
            equipment_back = str((request.data or {}).get("equipment_back", "")).lower() in {"1", "true", "on", "yes"}
            amount_q = orders_service.settle_delivery_cash(
                order,
                operator=request.user,
                amount_raw=str(request.data.get("amount", "")),
                actor=_actor(request),
                change_back_raw=None if change_back is None else str(change_back),
                equipment_back=equipment_back,
            )
        except OrderError as exc:
            return Response({"detail": str(exc) or "Falha no acerto de dinheiro."}, status=400)
        return Response({"ok": True, "ref": ref, "amount_q": amount_q})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Courier returned the equipment (card machine) taken at dispatch",
        responses={200: OpenApiResponse(description="Equipment marked as returned.")},
    ),
)
class OrderEquipmentBackView(_OrderActionBase):
    def post(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        try:
            custody = orders_service.mark_equipment_returned(order, actor=_actor(request))
        except OrderError as exc:
            return Response({"detail": str(exc) or "Falha ao registrar a volta da maquininha."}, status=400)
        return Response({"ok": True, "ref": ref, "equipment": list(custody.equipment), "back_at": custody.back_at})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Requeue fiscal (NFC-e) emission for an order",
        responses={200: OpenApiResponse(description="Fiscal emission requeued.")},
    ),
)
class OrderRequeueFiscalView(_OrderActionBase):
    def post(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        try:
            orders_service.requeue_fiscal_emission(order, actor=_actor(request))
        except OrderError as exc:
            return Response({"detail": str(exc) or "Falha ao reprocessar fiscal."}, status=400)
        return Response({"ok": True, "ref": ref})


def _resend_payment_link_response(order) -> Response:
    """Reenvia o aviso do link e responde no dialeto da casa.

    Uma função para as duas portas (PDV e gestor): a regra mora no service, a
    recusa sai como ``{detail, error: {code, message}}`` — ``detail`` para quem
    só lê o canônico, ``error.code`` para a tela distinguir "venceu" de
    "cedo demais" sem casar a frase em português.
    """
    try:
        notification_service.resend_payment_link(order)
    except notification_service.NotificationResendRefused as exc:
        return Response(
            {"detail": exc.message, "error": {"code": exc.code, "message": exc.message}},
            status=exc.status,
        )
    return Response(
        {"ok": True, "ref": order.ref, "detail": "Link reenviado ao cliente.", "payment_link_notice": payment_link_notice(order)}
    )


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Resend the payment-link notice to the customer",
        responses={
            200: OpenApiResponse(description="Notice queued again."),
            409: OpenApiResponse(description="Refused: no link, cancelled, paid, expired, pending or too soon."),
        },
    ),
)
class OrderResendPaymentLinkView(_OrderActionBase):
    """O cliente disse "não chegou": o gestor manda de novo a MESMA URL, enquanto vale."""

    def post(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        return _resend_payment_link_response(order)


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Datas e janelas combináveis para o pedido (agendamento do PDV)",
        responses={200: OpenApiResponse(description="Available dates and readiness-annotated windows.")},
    ),
)
class POSScheduleView(APIView):
    """As datas e janelas combináveis — perguntado na ABERTURA, não no pagamento.

    ``GET ?date=YYYY-MM-DD&skus=BF,CR``. Os SKUs vêm porque a janela oferecível
    depende do que está no carrinho: prometer 09:00 com uma baguete de tradição
    dentro é quebra de contrato com quem aparece às 9h.
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def get(self, request):
        from shopman.backstage.projections.pos import build_pos_schedule

        skus = [
            sku
            for raw in str(request.GET.get("skus") or "").split(",")
            if (sku := raw.strip())
        ]
        return Response({
            "ok": True,
            **build_pos_schedule(
                delivery_date=str(request.GET.get("date") or "").strip(), skus=skus
            ),
        })


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Recent POS sales with fiscal state (print/resend/requeue home)",
        responses={200: OpenApiResponse(description="Recent sales list.")},
    ),
)
class POSRecentSalesView(APIView):
    """Últimas vendas do balcão — a casa da DANFE depois que a tela da venda passou."""

    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def get(self, request):
        from shopman.backstage.projections.pos import build_pos_recent_sales

        return Response({"ok": True, **build_pos_recent_sales()})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="DANFE NFC-e bytes (ESC/POS, base64) for the counter agent",
        responses={200: OpenApiResponse(description="DANFE payload.")},
    ),
)
class POSDanfeEscposView(APIView):
    """O servidor compõe a DANFE em bobina; o navegador relaia ao agente do balcão.

    O carimbo "2ª via" é decisão DESTE lado: a primeira composição grava
    ``danfe_printed_at`` em ``Order.data`` e toda composição seguinte sai
    carimbada. Antes a tela chutava por heurística (venda completa + e-mail
    enviado) e errava nos dois sentidos.
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def get(self, request, ref: str):
        import base64

        from shopman.backstage.services.receipt_escpos import danfe_nfce
        from shopman.shop.views.fiscal_danfe import build_danfe

        doc = build_danfe(ref)
        if doc is None:
            return Response({"detail": "Pedido não encontrado."}, status=404)
        if not doc.emitted:
            return Response({"detail": "NFC-e ainda não autorizada para este pedido."}, status=409)
        reprint = _stamp_first_print(ref, "danfe_printed_at")
        payload = danfe_nfce(doc, reprint=reprint)
        return Response({
            "ok": True,
            "payload_b64": base64.b64encode(payload).decode("ascii"),
            "title": f"danfe:{ref}",
            "reprint": reprint,
        })


def _stamp_first_print(order_ref: str, key: str) -> bool:
    """Registra a primeira composição de um papel e responde "isto é 2ª via?".

    A marca vive em ``Order.data`` (``receipt_printed_at``/``danfe_printed_at``,
    documentadas em docs/reference/data-schemas.md). Marca na COMPOSIÇÃO, não na
    confirmação do papel: o que importa é que um papel daquele pedido já saiu
    para o mundo uma vez — a partir daí, todo seguinte circula como segunda via.
    """
    from django.utils import timezone
    from shopman.orderman.models import Order

    order = Order.objects.filter(ref=order_ref).first()
    if order is None:
        return False
    data = order.data or {}
    if data.get(key):
        return True
    data[key] = timezone.now().isoformat()
    order.data = data
    order.save(update_fields=["data", "updated_at"])
    return False


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Non-fiscal sale receipt bytes (ESC/POS, base64) for the counter agent",
        responses={200: OpenApiResponse(description="Receipt payload.")},
    ),
)
class POSSaleReceiptEscposView(APIView):
    """Recibo não fiscal da venda, composto no servidor a partir do que ela gravou.

    Mesmo desenho da DANFE em bobina: o servidor compõe os bytes, o navegador
    relaia ao agente do balcão. Quando o agente falha, a tela cai no diálogo de
    impressão do navegador — mas avisando, nunca em silêncio. A decisão de
    "2ª via" também é daqui (``receipt_printed_at`` em ``Order.data``).
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def get(self, request, ref: str):
        import base64

        from shopman.orderman.models import Order

        from shopman.shop.models import Shop

        order = Order.objects.filter(ref=ref).prefetch_related("items").first()
        if order is None:
            return Response({"detail": "Pedido não encontrado."}, status=404)
        shop = Shop.objects.first()
        shop_name = (getattr(shop, "brand_name", "") or getattr(shop, "name", "") or "") if shop else ""
        reprint = _stamp_first_print(ref, "receipt_printed_at")
        from shopman.backstage.services.receipt_escpos import sale_receipt

        payload = sale_receipt(order, shop_name=shop_name, reprint=reprint)
        return Response({
            "ok": True,
            "payload_b64": base64.b64encode(payload).decode("ascii"),
            "title": f"recibo:{ref}",
            "reprint": reprint,
        })


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Order ticket bytes (ESC/POS, base64) for the counter agent",
        responses={200: OpenApiResponse(description="Order ticket payload.")},
    ),
)
class OrderTicketEscposView(APIView):
    """A filipeta de UM pedido remoto, composta no servidor.

    Mesmo desenho do recibo e da DANFE em bobina — o servidor compõe, o
    navegador relaia ao agente do balcão — e mesma decisão de 2ª via deste lado
    (``ticket_printed_at`` em ``Order.data``). A permissão, porém, é a do
    GESTOR: a filipeta é documento do pedido, não do caixa, e quem imprime a
    semana é quem cuida da fila.
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_orders"

    def get(self, request, ref: str):
        import base64

        from shopman.orderman.models import Order

        from shopman.backstage.services import order_ticket as tickets

        order = Order.objects.filter(ref=ref).prefetch_related("items").first()
        if order is None:
            return Response({"detail": "Pedido não encontrado."}, status=404)
        reprint = _stamp_first_print(ref, "ticket_printed_at")
        payload = tickets.ticket_bytes(order, reprint=reprint)
        return Response({
            "ok": True,
            "payload_b64": base64.b64encode(payload).decode("ascii"),
            "title": f"filipeta:{ref}",
            "reprint": reprint,
        })


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Orders committed within a period (order-ticket batch preview)",
        responses={200: OpenApiResponse(description="Orders in the period, panel-ordered.")},
    ),
)
class OrderTicketBatchView(APIView):
    """O que SAIRIA no lote — a conferência do intervalo antes de a bobina andar.

    Olhar não é imprimir: esta rota não carimba nada. Ela existe porque um
    intervalo digitado errado só se descobre quando o papel já está no chão, e
    a tela precisa poder dizer "vão sair 34 filipetas" antes do gesto.
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_orders"

    def get(self, request):
        from shopman.backstage.services import order_ticket as tickets

        date_from, date_to = tickets.parse_period(
            request.GET.get("date_from"), request.GET.get("date_to")
        )
        orders = tickets.orders_for_period(date_from, date_to)
        return Response({
            "ok": True,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "count": len(orders),
            "max_batch": tickets.MAX_BATCH,
            "orders": tickets.preview_rows(orders),
        })


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Order-ticket batch bytes (ESC/POS, base64) for a committed period",
        responses={200: OpenApiResponse(description="Consecutive order tickets on one roll.")},
    ),
)
class OrderTicketBatchEscposView(APIView):
    """A semana inteira em filipetas consecutivas na bobina — UM trabalho só.

    Os bytes saem concatenados de propósito: cada filipeta termina no corte
    parcial do ESC/POS, então um POST ao agente rende N papéis destacáveis, na
    ordem em que vão para o painel. Mandar N requisições faria a ordem depender
    da rede.

    Carimba cada pedido individualmente: compor é ter soltado o papel no mundo,
    e a filipeta seguinte daquele pedido sai marcada como 2ª via — a mesma
    regra do recibo, aplicada pedido a pedido dentro do lote.
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_orders"

    def get(self, request):
        import base64

        from shopman.backstage.services import order_ticket as tickets

        date_from, date_to = tickets.parse_period(
            request.GET.get("date_from"), request.GET.get("date_to")
        )
        orders = tickets.orders_for_period(date_from, date_to)
        if len(orders) > tickets.MAX_BATCH:
            return Response(
                {"detail": str(tickets.BatchTooLarge(len(orders))), "count": len(orders)},
                status=409,
            )

        from django.db import transaction

        shop_name = tickets.shop_display_name()
        payload = bytearray()
        refs: list[str] = []
        reprints = 0
        # ⚠️ Tudo ou nada. Sem a transação, uma exceção no meio do lote deixaria
        # os pedidos já percorridos carimbados sem que papel nenhum tivesse
        # saído — e a tentativa seguinte os imprimiria como "2a VIA" de uma
        # primeira via que nunca existiu.
        with transaction.atomic():
            for order in orders:
                reprint = _stamp_first_print(order.ref, "ticket_printed_at")
                reprints += 1 if reprint else 0
                payload += tickets.ticket_bytes(order, shop_name=shop_name, reprint=reprint)
                refs.append(order.ref)

        return Response({
            "ok": True,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "count": len(refs),
            "reprint_count": reprints,
            "refs": refs,
            "payload_b64": base64.b64encode(bytes(payload)).decode("ascii"),
            "title": f"filipetas:{date_from.isoformat()}:{date_to.isoformat()}",
        })


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Update customer counter profile (fiscal prefs, notes, restrictions)",
        responses={200: OpenApiResponse(description="Profile updated.")},
    ),
)
class POSCustomerProfileView(APIView):
    """Preferências do cliente editáveis por quem está com a mão na massa.

    O gravador passivo (`_remember_fiscal_prefs`) só liga; AQUI o operador liga
    E desliga explicitamente — "nunca mais" é gesto de cadastro, e este é o
    cadastro que o balcão alcança. Parcial: só as chaves presentes mudam.
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def post(self, request, ref: str):
        try:
            from shopman.guestman.models import Customer
        except ImportError:
            return Response({"detail": "Guestman indisponível."}, status=503)
        customer = Customer.objects.filter(ref=ref).first()
        if customer is None:
            return Response({"detail": "Cliente não encontrado."}, status=404)

        body = request.data or {}
        updates: list[str] = []
        metadata = dict(customer.metadata or {})

        if "fiscal_prefs" in body:
            incoming = body.get("fiscal_prefs") or {}
            if not isinstance(incoming, dict):
                return Response({"detail": "fiscal_prefs inválido.", "field": "fiscal_prefs"}, status=400)
            prefs = dict(metadata.get("fiscal_prefs") or {})
            for key in ("cpf_na_nota", "email_receipt"):
                if key in incoming:
                    prefs[key] = bool(incoming[key])
            metadata["fiscal_prefs"] = prefs
            customer.metadata = metadata
            updates.append("metadata")

        if "dietary_restrictions" in body:
            metadata["preferences"] = str(body.get("dietary_restrictions") or "").strip()
            customer.metadata = metadata
            if "metadata" not in updates:
                updates.append("metadata")

        if "notes" in body:
            customer.notes = str(body.get("notes") or "").strip()
            updates.append("notes")

        if not updates:
            return Response({"detail": "Nada para atualizar."}, status=400)
        customer.save(update_fields=[*updates, "updated_at"])
        return Response({
            "ok": True,
            "fiscal_prefs": dict((customer.metadata or {}).get("fiscal_prefs") or {}),
            "notes": customer.notes,
            "dietary_restrictions": str((customer.metadata or {}).get("preferences") or ""),
        })


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Resend the NFC-e by email via the fiscal provider",
        responses={200: OpenApiResponse(description="Email queued at provider.")},
    ),
)
class POSResendFiscalEmailView(APIView):
    """Reenvio da nota por e-mail — o Focus entrega DANFE + XML; nós só pedimos."""

    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def post(self, request, ref: str):
        from shopman.orderman.models import Order

        from shopman.shop.fiscal import fiscal_pool

        order = Order.objects.filter(ref=ref).first()
        if order is None:
            return Response({"detail": "Pedido não encontrado."}, status=404)
        if not (order.data or {}).get("nfce_access_key"):
            return Response({"detail": "NFC-e ainda não autorizada para este pedido."}, status=409)
        email = str((request.data or {}).get("email") or "").strip()
        if not email:
            data = order.data or {}
            email = str((data.get("receipt") or {}).get("email") or (data.get("customer") or {}).get("email") or "").strip()
        if not email:
            return Response({"detail": "Informe o e-mail de destino.", "field": "email"}, status=400)
        backend = fiscal_pool.get_backend()
        send = getattr(backend, "send_email", None)
        if send is None:
            return Response({"detail": "Backend fiscal não suporta envio de e-mail."}, status=501)
        ok, message = send(reference=ref, emails=[email])
        if not ok:
            return Response({"detail": message}, status=502)
        return Response({"ok": True, "detail": message})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Resend the payment-link notice from the POS",
        responses={
            200: OpenApiResponse(description="Notice queued again."),
            409: OpenApiResponse(description="Refused: no link, cancelled, paid, expired, pending or too soon."),
        },
    ),
)
class POSResendPaymentLinkView(APIView):
    """Reenvio do link pelo balcão — ao lado do "Copiar link", na tela de resultado."""

    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def post(self, request, ref: str):
        from shopman.orderman.models import Order

        order = Order.objects.filter(ref=ref).first()
        if order is None:
            return Response({"detail": "Pedido não encontrado."}, status=404)
        return _resend_payment_link_response(order)


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Dispatch (or re-dispatch) the external courier ride",
        responses={200: OpenApiResponse(description="Courier dispatch queued.")},
    ),
)
class OrderCourierDispatchView(_OrderActionBase):
    def post(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        try:
            orders_service.courier_dispatch(order, actor=_actor(request))
        except OrderError as exc:
            return Response({"detail": str(exc) or "Falha ao despachar."}, status=400)
        return Response({"ok": True, "ref": ref})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Cancel the active external courier ride",
        responses={200: OpenApiResponse(description="Courier ride cancelled.")},
    ),
)
class OrderCourierCancelView(_OrderActionBase):
    def post(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        reason_id = request.data.get("reason_id")
        try:
            orders_service.courier_cancel(
                order,
                actor=_actor(request),
                reason_id=int(reason_id) if reason_id is not None else None,
            )
        except (TypeError, ValueError):
            return Response({"detail": "reason_id inválido."}, status=400)
        except OrderError as exc:
            return Response({"detail": str(exc) or "Falha ao cancelar a corrida."}, status=400)
        return Response({"ok": True, "ref": ref})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Quote the external courier ride without dispatching",
        responses={200: OpenApiResponse(description="Courier quote.")},
    ),
)
class OrderCourierQuoteView(_OrderActionBase):
    def post(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        try:
            quote = orders_service.courier_quote(order)
        except OrderError as exc:
            return Response({"detail": str(exc) or "Cotação indisponível."}, status=400)
        return Response({"ok": True, "ref": ref, "quote": quote})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Save the operator's kitchen note on an order",
        responses={200: OpenApiResponse(description="Note saved.")},
    ),
)
class OrderNotesView(_OrderActionBase):
    def post(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        notes = str(request.data.get("notes", "") or "")
        orders_service.save_kitchen_note(order, notes=notes)
        return Response({"ok": True, "ref": ref})


def _operator_identity(request) -> tuple[int, str]:
    """A quem creditar a retirada de um pedido — que é quem está logado.

    Tinha dois caminhos: o "operador ativo" guardado na sessão, e a conta do
    dispositivo como reserva. Com uma identidade, os dois passaram a devolver a
    mesma pessoa; ficou o que sempre foi a intenção.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return 0, "operador"
    return user.pk, (user.get_full_name().strip() or user.get_username())


class OrderAssignView(_OrderActionBase):
    def post(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        operator_id, operator_name = _operator_identity(request)
        orders_service.assign_order(
            order, operator_id=operator_id, operator_name=operator_name, actor=_actor(request)
        )
        return Response({"ok": True, "ref": ref, "assigned_operator": operator_name})


class OrderUnassignView(_OrderActionBase):
    def post(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        orders_service.unassign_order(order, actor=_actor(request))
        return Response({"ok": True, "ref": ref})


class OrderCommentView(_OrderActionBase):
    def post(self, request, ref: str):
        order, err = self._get_order(ref)
        if err:
            return err
        note = str(request.data.get("note", "") or "")
        try:
            orders_service.add_comment(order, note=note, actor=_actor(request))
        except OrderError as exc:
            return Response({"detail": str(exc) or "Comentário inválido."}, status=400)
        return Response({"ok": True, "ref": ref})


# ── Production action endpoints ───────────────────────────────────────


def _expected_rev(request) -> int | None:
    """A revisão que a TELA leu, quando ela a informa.

    ⚠️ `None` NÃO é zero: ele significa "não confira", que é o contrato documentado do
    craftsman para uso standalone (last-write-wins). Zero é uma revisão legítima — a de
    uma fornada recém-criada —, e confundir os dois faria toda mutação sem `rev` recusar
    exatamente as fornadas novas.

    Valor ilegível também vira `None` em vez de 400: o `rev` é reforço de concorrência,
    e derrubar o gesto do forneiro por causa de um campo que a tela dele talvez nem
    mande seria trocar uma corrida rara por uma parede diária.
    """
    bruto = (request.data if hasattr(request, "data") else {}) or {}
    valor = bruto.get("expected_rev", bruto.get("rev"))
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


class _ProductionActionBase(APIView):
    """Gate compartilhado das ações de produção — superfície E coluna.

    ⚠️ A ESCRITA da produção não consultava a permissão por coluna. O operador tocava
    "Planejar" e a cadeia inteira — `apply_planned` → `set_planned_quantity` →
    `CraftPlanning` → sinal `production_changed` → o handler do stockman criando o
    Quant planejado — conferia **só** `backstage.operate_production`. Nenhum ponto
    perguntava por `shop.edit_production_planned`. Idem para start e finish, e finish
    é a escrita `kind=MAKE` no ledger de estoque.

    O resolvedor de coluna já existia e já era testado (`resolve_production_access`);
    ele só governava a LEITURA. É buraco de arquitetura de gate, não de exposição
    ativa hoje — os dois grupos que recebem `operate_production` também recebem as
    colunas. Mas é o mesmo padrão do tile da Central: o dia em que alguém fizer um
    grant customizado, ele morde.

    Cada view declara em `production_column` a coluna que ESCREVE; a recusa nomeia a
    permissão que falta, em vez de dizer só "proibido". **Sem permissão nova.**
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_production"

    #: A coluna do quadro que esta view escreve ("planned", "started", "finished").
    #: Vazio = a ação não escreve coluna, e o gate de superfície basta.
    production_column: str = ""

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        coluna = self.production_column
        if not coluna:
            return
        from shopman.backstage.projections.production import resolve_production_access

        acesso = resolve_production_access(request.user)
        if not getattr(acesso, f"can_edit_{coluna}", False):
            raise exceptions.PermissionDenied(
                f"Falta a permissão de editar a coluna {coluna} da produção "
                f"(shop.edit_production_{coluna})."
            )


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Plan (or adjust) production for a recipe/date (matrix cell)",
        responses={200: OpenApiResponse(description="Planned quantity set.")},
    ),
)
class WorkOrderPlanView(_ProductionActionBase):
    production_column = "planned"

    def post(self, request):
        recipe_id = request.data.get("recipe_id") or request.data.get("recipe")
        quantity = request.data.get("quantity")
        target_date = request.data.get("target_date")
        if not (recipe_id and target_date and quantity is not None):
            return Response(
                {"detail": "recipe_id, target_date e quantity são obrigatórios."},
                status=400,
            )
        source = (request.data.get("source") or "").strip()
        try:
            output_sku, wo_ref, qty, result = production_service.apply_planned(
                recipe_id=recipe_id,
                quantity=str(quantity).strip(),
                target_date_value=str(target_date).strip(),
                position_ref=str(request.data.get("position_ref") or "").strip(),
                operator_ref=str(request.data.get("operator_ref") or "").strip(),
                reason=str(request.data.get("reason") or "").strip(),
                actor=_production_actor(request),
                # `bool("false")` e True, e este e o `force` que CONTORNA a checagem de
                # insumos: um cliente que mande a string desliga o guardrail achando
                # que o ligou. Ver `shopman/backstage/parsing.py`.
                force=as_bool(request.data, "force", default=False),
                source_ref="formula:suggestion" if source == "suggested" else "production_matrix",
                expected_rev=_expected_rev(request),
            )
        except ProductionError as exc:
            shortage = _production_error_response(exc)
            if shortage is not None:
                return shortage
            return Response({"detail": str(exc) or "Falha ao planejar produção."}, status=400)
        except ValueError as exc:
            return Response({"detail": str(exc) or "Dados de planejamento inválidos."}, status=400)
        return Response({
            "ok": True,
            "result": result,
            "output_sku": output_sku,
            "wo_ref": wo_ref,
            "quantity": str(qty),
        })


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Start a planned work order",
        responses={200: OpenApiResponse(description="Work order started.")},
    ),
)
class WorkOrderStartView(_ProductionActionBase):
    production_column = "started"

    def post(self, request, wo_id: int):
        try:
            wo_ref, quantity = production_service.apply_start(
                work_order_id=wo_id,
                quantity=str(request.data.get("quantity") or "").strip(),
                position_id=str(request.data.get("position_id") or "").strip(),
                operator_ref=str(request.data.get("operator_ref") or "").strip(),
                note=str(request.data.get("note") or "").strip(),
                actor=_production_actor(request),
                expected_rev=_expected_rev(request),
            )
        except ProductionError as exc:
            conflict = _production_error_response(exc)
            if conflict is not None:
                return conflict
            return Response({"detail": str(exc) or "Falha ao iniciar produção."}, status=400)
        except ValueError as exc:
            return Response({"detail": str(exc) or "Dados inválidos."}, status=400)
        return Response({"ok": True, "wo_ref": wo_ref, "quantity": str(quantity)})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Finish a started work order (force overrides material shortage)",
        responses={200: OpenApiResponse(description="Work order finished.")},
    ),
)
class WorkOrderFinishView(_ProductionActionBase):
    production_column = "finished"

    def post(self, request, wo_id: int):
        try:
            partition = request.data.get("partition")
            wo_ref, quantity = production_service.apply_finish(
                work_order_id=wo_id,
                quantity=str(request.data.get("quantity") or "").strip(),
                actor=_production_actor(request),
                # `bool("false")` e True, e este e o `force` que CONTORNA a checagem de
                # insumos: um cliente que mande a string desliga o guardrail achando
                # que o ligou. Ver `shopman/backstage/parsing.py`.
                force=as_bool(request.data, "force", default=False),
                # Classificação da fornada (refs de QualityGrade). Opcional: o
                # operador fecha sem pensar e cai no grau padrão do catálogo.
                quality=str(request.data.get("quality") or "").strip(),
                # Partição explícita (ADR-017): [{quantity, quality_grade_ref,
                # quality_defect_ref, loss}]. Quando presente, `quality` é
                # ignorado; grupo com loss=true é perda declarada com motivo.
                partition=partition if isinstance(partition, list) else None,
                expected_rev=_expected_rev(request),
            )
        except ProductionError as exc:
            shortage = _production_error_response(exc)
            if shortage is not None:
                return shortage
            return Response({"detail": str(exc) or "Falha ao concluir produção."}, status=400)
        except ValueError as exc:
            return Response({"detail": str(exc) or "Dados inválidos."}, status=400)
        return Response({"ok": True, "wo_ref": wo_ref, "quantity": str(quantity)})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Advance work order step",
        responses={200: OpenApiResponse(description="Step advanced.")},
    ),
)
class WorkOrderAdvanceStepView(_ProductionActionBase):
    production_column = "started"
    def post(self, request, wo_id: int):
        try:
            new_index = production_service.apply_advance_step(
                work_order_id=wo_id,
                actor=_production_actor(request),
            )
        except ProductionError as exc:
            return Response({"detail": str(exc) or "Falha ao avançar passo."}, status=400)
        return Response({"ok": True, "wo_id": wo_id, "step_index": new_index})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Quick-finish a recipe (plan + finish in one step)",
        responses={200: OpenApiResponse(description="Work order finished.")},
    ),
)
class WorkOrderQuickFinishView(_ProductionActionBase):
    production_column = "finished"

    def post(self, request):
        recipe_id = request.data.get("recipe_id")
        quantity = request.data.get("quantity")
        # position_id opcional: sem ele a fornada cai na posição padrão (o
        # quiosque de QC não escolhe forno; o grid do gestor continua enviando).
        position_id = request.data.get("position_id")
        if not (recipe_id and quantity):
            return Response(
                {"detail": "recipe_id e quantity são obrigatórios."},
                status=400,
            )
        try:
            partition = request.data.get("partition")
            _, wo_ref, qty = production_service.apply_quick_finish(
                recipe_id=recipe_id,
                quantity=quantity,
                position_id=position_id,
                actor=_production_actor(request),
                # Fornada avulsa fechada pelo quiosque de QC: mesma
                # partição do finish normal (ADR-017 §4).
                partition=partition if isinstance(partition, list) else None,
                # `bool("false")` e True, e este e o `force` que CONTORNA a checagem de
                # insumos: um cliente que mande a string desliga o guardrail achando
                # que o ligou. Ver `shopman/backstage/parsing.py`.
                force=as_bool(request.data, "force", default=False),
                # Trava de replay do GESTO. Esta é a única operação composta da
                # produção (cria a WO e a fecha na mesma requisição), então a
                # chave do core — que inclui o pk da WO — nasce diferente a cada
                # tentativa e nunca alcança a trava. Ver `apply_quick_finish`.
                client_request_id=str(request.data.get("client_request_id") or "").strip(),
            )
        except ProductionError as exc:
            shortage = _production_error_response(exc)
            if shortage is not None:
                return shortage
            return Response({"detail": str(exc) or "Falha ao finalizar."}, status=400)
        return Response({"ok": True, "wo_ref": wo_ref, "quantity": str(qty)})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Void (cancel) a work order",
        responses={200: OpenApiResponse(description="Work order voided.")},
    ),
)
class WorkOrderVoidView(_ProductionActionBase):
    production_column = "finished"

    def post(self, request, wo_id: int):
        reason = (request.data.get("reason") or "Estornado pelo operador").strip()
        try:
            ref = production_service.apply_void(
                wo_id,
                actor=_production_actor(request),
                reason=reason,
                expected_rev=_expected_rev(request),
            )
        except ProductionError as exc:
            conflict = _production_error_response(exc)
            if conflict is not None:
                return conflict
            return Response({"detail": str(exc) or "Falha ao estornar."}, status=400)
        return Response({"ok": True, "wo_ref": ref})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Declare oven-in for a work order (arm = enfornou)",
        responses={200: OpenApiResponse(description="Oven run opened.")},
    ),
)
class WorkOrderOvenArmView(_ProductionActionBase):
    def post(self, request, wo_id: int):
        try:
            run = production_service.apply_oven_arm(
                work_order_id=wo_id,
                planned_seconds=request.data.get("planned_seconds"),
                operator_ref=str(request.data.get("operator_ref") or "").strip(),
                actor=_production_actor(request),
            )
        except ProductionError as exc:
            return Response({"detail": str(exc) or "Falha ao registrar o enfornar."}, status=400)
        return Response({"ok": True, "run_id": run.pk})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Declare oven-out for a work order (Concluir = retirou)",
        responses={200: OpenApiResponse(description="Oven run concluded (or nothing to measure).")},
    ),
)
class WorkOrderOvenConcludeView(_ProductionActionBase):
    def post(self, request, wo_id: int):
        try:
            run = production_service.apply_oven_conclude(
                work_order_id=wo_id,
                actor=_production_actor(request),
            )
        except ProductionError as exc:
            return Response({"detail": str(exc) or "Falha ao registrar o retirar."}, status=400)
        return Response({"ok": True, "measured": run is not None})


# ── POS cash shift endpoints ──────────────────────────────────────────


#: Escopo da trava das mutações de dinheiro do caixa, na `IdempotencyKey` do
#: orderman — a mesma tabela do commit de sessão, do replay de webhook e do submit
#: do PDV. Nenhum modelo novo, nenhuma migração.
CASH_IDEMPOTENCY_SCOPE = "pos.cash"


def _falha_do_caixa(exc, padrao: str) -> Response:
    """A resposta certa quando uma mutação de caixa não deu.

    ⚠️ O ``except Exception`` de cada view devolvia 400 para tudo, e engolia a
    ambiguidade de gaveta antes que ela chegasse a qualquer lugar. 400 diz "seu pedido
    está errado"; aqui o pedido está certo e o ESTADO da loja é que é ambíguo — mais de
    uma gaveta ativa e ninguém disse qual. O operador não tem o que corrigir no que
    mandou, então a resposta é 409, com o campo que falta nomeado.
    """
    if isinstance(exc, POSTerminalAmbiguous):
        return Response({"detail": str(exc), "field": "terminal_ref"}, status=409)
    return Response({"detail": str(exc) or padrao}, status=400)


def _cash_idempotent(request, *, acao: str, executar):
    """Roda uma mutação de dinheiro UMA vez por `client_request_id`.

    ⚠️ As oito mutações de dinheiro do caixa declaravam `idempotency="none"` e não
    tinham trava nenhuma. O operador lança uma sangria de R$ 200, a rede do salão
    oscila (é a mesma do kiosk e do KDS), o botão não responde, ele toca de novo —
    e o livro-caixa aceita as duas linhas. O livro é IMUTÁVEL de propósito, então o
    conserto não é apagar: é um ajuste, com o gerente, no fechamento, com o dono
    perguntando por que faltam R$ 200.

    E não havia segunda linha de defesa: as `UniqueConstraint` que o cashman
    acrescentou depois de um TOCTOU real cobrem só os `kind` que têm `order_ref`.
    Sangria, suprimento, fundo de troco, devolução e acerto de conta são exatamente
    os que não têm. A trava de banco que salvou a venda não alcançava o caixa.

    **Replay é SILENCIOSO aqui, e a diferença com o recibo de Compras é o que a
    chave significa.** Lá a chave é a NOTA — estável para sempre —, então um envio
    repetido meses depois merece ser contado ao operador. Aqui a chave é ESTE GESTO:
    a tela a descarta no sucesso, então um segundo envio com a mesma chave só pode
    ser retry da mesma sangria. Responder o mesmo resultado é a leitura certa dele.

    Sem chave não há o que travar — mesma régua do submit da venda. A tela sempre
    manda uma; quem chama a API crua sem chave está dizendo que cada envio é uma
    operação.
    """
    from shopman.shop.services.remote_mutations import (
        RemoteMutationInProgress,
        run_idempotent_mutation,
    )

    chave = str(request.data.get("client_request_id") or "").strip()
    if not chave:
        return executar()

    def _executar_para_o_claim():
        resposta = executar()
        return ({"status": resposta.status_code, "data": resposta.data}, resposta.status_code)

    try:
        resultado = run_idempotent_mutation(
            scope=f"{CASH_IDEMPOTENCY_SCOPE}.{acao}",
            key=chave,
            execute=_executar_para_o_claim,
            # Só a resposta BEM-SUCEDIDA vira replay. Guardar um 400 faria o
            # operador que corrigiu o valor receber o erro antigo de volta.
            cache_response=lambda corpo, codigo: codigo < 300,
        )
    except RemoteMutationInProgress:
        return Response(
            {
                "detail": "Este lançamento já está sendo registrado. Aguarde um instante.",
                "error": {
                    "code": "cash_mutation_in_progress",
                    "message": "Este lançamento já está sendo registrado.",
                    "focus": "cash",
                    "recovery": "Aguarde a confirmação antes de tentar de novo.",
                },
            },
            status=409,
        )

    corpo = resultado.response_body or {}
    return Response(corpo.get("data"), status=int(corpo.get("status") or 200))


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Open cash shift",
        responses={200: OpenApiResponse(description="Cash shift opened.")},
    ),
)
class POSCashOpenView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def post(self, request):
        # A trava de replay do dinheiro — ver `_cash_idempotent`.
        def _executar():
            amount = request.data.get("opening_amount", "0")
            try:
                session = pos_service.open_cash_shift(
                    operator=request.user,
                    opening_amount_raw=str(amount),
                    terminal_ref=str(request.data.get("terminal_ref") or ""),
                )
            except POSError as exc:
                message = str(exc) or "Falha ao abrir caixa."
                terminal_occupied = "Terminal POS" in message and "turno aberto" in message
                return Response(
                    {
                        "detail": message,
                        "error": {
                            "code": "cash_terminal_occupied" if terminal_occupied else "cash_shift_open_failed",
                            "message": message,
                            "field": "terminal_ref" if terminal_occupied else "opening_amount",
                            "focus": "cash",
                            "recovery": (
                                "Use o operador correto, feche o turno atual no gestor ou selecione outro terminal antes de vender."
                                if terminal_occupied
                                else "Corrija os dados de abertura do caixa e tente novamente."
                            ),
                        },
                    },
                    status=409 if terminal_occupied else 400,
                )
            except Exception as exc:
                logger.debug("pos_cash_shift_open_failed user=%s", _actor(request), exc_info=True)
                return _falha_do_caixa(exc, "Falha ao abrir caixa.")
            return Response({"ok": True, "shift_id": session.pk, "terminal_ref": session.terminal.ref})

        return _cash_idempotent(
            request, acao="open_cash_shift", executar=lambda: _executar()
        )


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Close cash shift",
        responses={200: OpenApiResponse(description="Cash shift closed.")},
    ),
)
class POSCashCloseView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def post(self, request):
        # A trava de replay do dinheiro — ver `_cash_idempotent`.
        def _executar():
            from shopman.backstage.services.exceptions import POSPermissionError

            amount = request.data.get("closing_amount", "0")
            notes = (request.data.get("notes") or "").strip()
            try:
                result = pos_service.close_cash_shift(
                    actor_user=request.user,
                    closing_amount_raw=str(amount),
                    notes=notes,
                    terminal_ref=str(request.data.get("terminal_ref") or ""),
                )
            except POSPermissionError as exc:
                # Fechar o caixa é da gerência (decisão de 21/08). O balcão precisa
                # distinguir "sem permissão" de "falhou" para pedir a gerente em vez
                # de tentar de novo — por isso o código estável, não só o 400.
                return Response(
                    {"detail": str(exc), "error": {"code": "cash_close_forbidden", "message": str(exc)}},
                    status=403,
                )
            except Exception as exc:
                logger.debug("pos_cash_shift_close_failed user=%s", _actor(request), exc_info=True)
                return _falha_do_caixa(exc, "Falha ao fechar caixa.")
            return Response({"ok": True, "result": _cash_shift_result(result) if result else None})

        return _cash_idempotent(
            request, acao="close_cash_shift", executar=lambda: _executar()
        )


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Register cash movement (sangria/suprimento)",
        responses={200: OpenApiResponse(description="Movement registered.")},
    ),
)
class POSMovementView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def post(self, request):
        # A trava de replay do dinheiro — ver `_cash_idempotent`.
        def _executar():
            kind = (request.data.get("kind") or "").strip()
            amount = request.data.get("amount", "0")
            reason = (request.data.get("reason") or "").strip()
            if kind not in {"sangria", "suprimento"}:
                return Response({"detail": "kind deve ser 'sangria' ou 'suprimento'."}, status=400)
            try:
                entry = pos_service.register_cash_movement(
                    operator=request.user,
                    movement_type=kind,
                    amount_raw=str(amount),
                    reason=reason,
                    manager_approval=request.data.get("manager_approval"),
                    terminal_ref=_terminal_do_pedido(request),
                )
            # O desafio de PIN da retirada precisa chegar à tela COM o código, para o
            # PDV abrir o diálogo do gerente em vez de mostrar um toast sem saída.
            except PosIntentError as exc:
                return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)
            except Exception as exc:
                logger.debug("pos_cash_movement_failed user=%s kind=%s", _actor(request), kind, exc_info=True)
                return _falha_do_caixa(exc, "Falha ao registrar movimento.")
            return Response({"ok": True, "entry_id": getattr(entry, "pk", None)})

        return _cash_idempotent(
            request, acao="cash_movement", executar=lambda: _executar()
        )


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Cash movement receipt bytes (ESC/POS, base64) for the counter agent",
        responses={200: OpenApiResponse(description="Receipt payload.")},
    ),
    post=extend_schema(
        tags=["backstage"],
        summary="Record whether the receipt actually printed",
        responses={200: OpenApiResponse(description="Result recorded.")},
    ),
)
class POSCashReceiptView(APIView):
    """O papel da sangria: o servidor compõe, a tela relaia, o balcão responde.

    ⚠️ O `POST` existe porque **só o balcão sabe se imprimiu** — quem manda ao
    agente é o navegador. Sem ele, o registro ficaria "sem confirmação" para
    sempre e papel que faltou pareceria papel que alguém escondeu.
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def get(self, request, entry_id: int):
        reprint = str(request.query_params.get("reprint") or "").lower() in {"1", "true", "on"}
        try:
            payload = pos_service.cash_movement_receipt_payload(
                operator=request.user,
                entry_id=entry_id,
                reprint=reprint,
                terminal_ref=str(request.query_params.get("terminal_ref") or ""),
            )
        except PosIntentError as exc:
            return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)
        except Exception as exc:
            logger.debug("pos_receipt_payload_failed user=%s", _actor(request), exc_info=True)
            return Response({"detail": str(exc) or "Falha ao montar o comprovante."}, status=400)
        return Response(payload)

    def post(self, request, entry_id: int):
        try:
            result = pos_service.record_receipt_result(
                operator=request.user,
                entry_id=entry_id,
                status=(request.data.get("status") or "").strip(),
                detail=request.data.get("detail") or "",
                terminal_ref=str(request.data.get("terminal_ref") or ""),
            )
        except PosIntentError as exc:
            return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)
        except Exception as exc:
            logger.debug("pos_receipt_result_failed user=%s", _actor(request), exc_info=True)
            return Response({"detail": str(exc) or "Falha ao registrar o comprovante."}, status=400)
        return Response({"ok": True, "receipt_status": str((result.payload or {}).get("status") or "")})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Register a no-sale cash drawer opening",
        responses={200: OpenApiResponse(description="Opening recorded.")},
    ),
)
class POSCashDrawerOpenView(APIView):
    """Abertura de gaveta sem venda — o único momento que não deixa rastro só.

    O chute físico é do navegador (o agente vive na loopback do balcão, fora do
    alcance do servidor). O papel deste endpoint é o registro: quem abriu,
    quando e por quê. A tela só chuta depois do ``ok`` daqui, para não existir
    gaveta aberta sem linha na trilha.
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def post(self, request):
        reason = (request.data.get("reason") or "").strip()
        try:
            pos_service.register_drawer_opening(
                operator=request.user, reason=reason, terminal_ref=_terminal_do_pedido(request)
            )
        except PosIntentError as exc:
            return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)
        except Exception as exc:
            logger.debug("pos_drawer_open_failed user=%s", _actor(request), exc_info=True)
            return _falha_do_caixa(exc, "Falha ao registrar abertura.")
        return Response({"ok": True})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Record that someone opened the drawer-lock PIN screen",
        responses={200: OpenApiResponse(description="Attempt recorded.")},
    ),
)
class POSCashDrawerUnlockAttemptView(APIView):
    """Alguém abriu a tela de PIN da trava — inclusive quem desistiu.

    A saída de emergência é escondida de propósito (mostrar o botão ensina o
    bypass), e por isso quem a PROCURA é sinal. Registrar só o destrave que deu
    certo apagaria o padrão que mais interessa: quem tenta e desiste.
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def post(self, request):
        try:
            pos_service.record_unlock_attempt(
                operator=request.user,
                outcome=str(request.data.get("outcome") or "opened"),
                terminal_ref=_terminal_do_pedido(request),
            )
        except PosIntentError as exc:
            return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)
        except Exception as exc:
            logger.debug("pos_drawer_unlock_attempt_failed user=%s", _actor(request), exc_info=True)
            return _falha_do_caixa(exc, "Falha ao registrar a tentativa.")
        return Response({"ok": True})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Report a drawer left open between sales",
        responses={200: OpenApiResponse(description="Alert raised.")},
    ),
)
class POSCashDrawerLeftOpenView(APIView):
    """A gaveta ficou aberta entre vendas, além do limiar configurado.

    A trava cobre o instante da venda; isto cobre a hora morta. Quem conta o
    tempo é a página (o sensor vive na loopback do balcão), e o limiar vem da
    projeção — decisão do dono, não constante de código.
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def post(self, request):
        try:
            pos_service.report_drawer_left_open(
                operator=request.user,
                minutes=request.data.get("minutes") or 0,
                terminal_ref=_terminal_do_pedido(request),
            )
        except PosIntentError as exc:
            return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)
        except Exception as exc:
            logger.debug("pos_drawer_left_open_failed user=%s", _actor(request), exc_info=True)
            return _falha_do_caixa(exc, "Falha ao registrar a gaveta aberta.")
        return Response({"ok": True})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Record how long the drawer stayed open and how the block ended",
        responses={200: OpenApiResponse(description="Block recorded.")},
    ),
)
class POSCashDrawerBlockView(APIView):
    """O bloqueio por gaveta aberta terminou: quanto durou e como acabou.

    Com a trava dura, quem libera é o mundo físico — o bloqueio cai quando o
    sensor diz que a gaveta fechou. Isso torna a duração mensurável pela
    primeira vez: no desenho antigo o PIN cortava a medição no meio.

    Não segura nada: a venda já andou quando isto é chamado, e o dado de B.I.
    nunca pode custar uma venda.
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def post(self, request):
        try:
            pos_service.record_drawer_block(
                operator=request.user,
                duration_ms=request.data.get("duration_ms"),
                outcome=str(request.data.get("outcome") or "closed"),
                drawer_raw=str(request.data.get("drawer_raw") or ""),
                terminal_ref=_terminal_do_pedido(request),
            )
        except PosIntentError as exc:
            return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)
        except Exception as exc:
            logger.debug("pos_drawer_block_failed user=%s", _actor(request), exc_info=True)
            return _falha_do_caixa(exc, "Falha ao registrar o bloqueio.")
        return Response({"ok": True})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Report that the drawer sensor stopped answering on a calibrated station",
        responses={200: OpenApiResponse(description="Blindness recorded.")},
    ),
)
class POSCashDrawerBlindView(APIView):
    """A trava da gaveta caiu numa estação que TINHA medição.

    A trava falha aberta de propósito — sensor ruim nunca pode parar o balcão
    com fila de cliente na frente. O preço dessa escolha era a fuga mais barata
    contra ela: puxar o cabo da gaveta desligava a proteção para sempre, em
    silêncio. Este endpoint é o barulho. A venda já seguiu quando ele é
    chamado; ele não segura nada e não pode segurar.
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def post(self, request):
        try:
            pos_service.report_drawer_blind(
                operator=request.user,
                reason=str(request.data.get("reason") or ""),
                terminal_ref=_terminal_do_pedido(request),
            )
        except PosIntentError as exc:
            return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)
        except Exception as exc:
            logger.debug("pos_drawer_blind_failed user=%s", _actor(request), exc_info=True)
            return _falha_do_caixa(exc, "Falha ao registrar o sensor cego.")
        return Response({"ok": True})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Manager unlocks the next sale while the drawer is still open",
        responses={200: OpenApiResponse(description="Unlock recorded.")},
    ),
)
class POSCashDrawerUnlockView(APIView):
    """A trava da gaveta é do PDV; o destrave passa por aqui para ficar no livro.

    O PDV recusa iniciar a próxima venda enquanto SABE que a gaveta está aberta
    (quem lê o sensor é a página, pelo agente do balcão; o servidor não alcança).
    O gerente libera com PIN, mesmo desafio da sangria, e a liberação vira
    lançamento ``drawer_unlock`` com quem, para quem e quando. Sem este
    registro, o destrave seria a única exceção do caixa que não deixa rastro.
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def post(self, request):
        try:
            pos_service.unlock_drawer(
                operator=request.user,
                manager_approval=request.data.get("manager_approval"),
                drawer_raw=str(request.data.get("drawer_raw") or ""),
                duration_ms=request.data.get("duration_ms"),
                outcome=str(request.data.get("outcome") or "manager_override"),
                terminal_ref=_terminal_do_pedido(request),
            )
        # O desafio de PIN precisa chegar à tela COM o código, para o PDV abrir o
        # diálogo do gerente em vez de mostrar um toast sem saída.
        except PosIntentError as exc:
            return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)
        except Exception as exc:
            logger.debug("pos_drawer_unlock_failed user=%s", _actor(request), exc_info=True)
            return _falha_do_caixa(exc, "Falha ao liberar a gaveta.")
        return Response({"ok": True})


def _terminal_do_pedido(request) -> str:
    """Em qual gaveta esta mutação acontece.

    O corpo tem prioridade porque é AFIRMAÇÃO de quem chama; o cookie da estação é o
    contexto ambiente do dispositivo. Com uma gaveta só — o caso de hoje — os dois
    caminham juntos. Com duas, é isto que impede o operador do balcão 1 de lançar
    sangria na gaveta do balcão 2 sem erro nenhum.
    """
    corpo = request.data if hasattr(request, "data") else {}
    do_corpo = str((corpo or {}).get("terminal_ref") or "").strip()
    return do_corpo or station_trust.station_ref(request)


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Request change (exact amount, optional denominations) without leaving the counter",
        responses={200: OpenApiResponse(description="Change request registered.")},
    ),
)
class POSChangeRequestView(APIView):
    """O operador pede troco em vez de atravessar a loja com dinheiro.

    O trajeto até o cofre é a janela clássica de desvio: parte tem câmera, parte
    não, e a falta só apareceria no fechamento. Aqui o dinheiro fica no balcão e
    alguém traz o troco até ele.

    ⚠️ Um pedido não é movimento de caixa: a linha ``change_requested`` tem
    efeito zero no livro — a troca é net zero.
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def post(self, request):
        # A trava de replay do dinheiro — ver `_cash_idempotent`.
        def _executar():
            try:
                entry = pos_service.request_change(
                    operator=request.user,
                    amount_raw=str(request.data.get("amount", "0")),
                    denominations=request.data.get("denominations") or [],
                    note=request.data.get("note") or "",
                    terminal_ref=_terminal_do_pedido(request),
                )
            except PosIntentError as exc:
                return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)
            except Exception as exc:
                logger.debug("pos_change_request_failed user=%s", _actor(request), exc_info=True)
                return _falha_do_caixa(exc, "Falha ao pedir troco.")
            return Response({"ok": True, "request_ref": str(entry.pk)})

        return _cash_idempotent(
            request, acao="request_change", executar=lambda: _executar()
        )


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Serve a pending change request (manager PIN, drawer opens, net zero)",
        responses={200: OpenApiResponse(description="Change request served.")},
    ),
)
class POSChangeRequestServeView(APIView):
    """O gerente atende o pedido no balcão, com PIN, à vista das duas pessoas.

    Mesmo gate da sangria (``cashman.adjust_shift``, validado no service):
    a gaveta vai abrir com dinheiro dentro e quem mexe nela é alguém de fora do
    turno. Sem a segunda assinatura, atender viraria um jeito de abrir a gaveta
    sem testemunha.
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def post(self, request, request_ref: str):
        # A trava de replay do dinheiro — ver `_cash_idempotent`.
        def _executar(request_ref, ):
            try:
                pos_service.serve_change_request(
                    operator=request.user,
                    request_ref=request_ref,
                    manager_approval=request.data.get("manager_approval"),
                    terminal_ref=_terminal_do_pedido(request),
                )
            # O desafio de PIN precisa chegar à tela COM o código, para o PDV abrir o
            # diálogo do gerente em vez de mostrar um toast sem saída.
            except PosIntentError as exc:
                return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)
            except Exception as exc:
                logger.debug("pos_change_request_serve_failed user=%s", _actor(request), exc_info=True)
                return _falha_do_caixa(exc, "Falha ao atender o pedido.")
            return Response({"ok": True})

        return _cash_idempotent(
            request, acao="serve_change_request", executar=lambda: _executar(request_ref)
        )


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Cancel a pending change request",
        responses={200: OpenApiResponse(description="Change request cancelled.")},
    ),
)
class POSChangeRequestCancelView(APIView):
    """Achou troco na gaveta: o pedido morre aqui.

    Sem esta saída o pendente fica pendurado e a lista vira ruído — e lista em
    que ninguém acredita devolve o balcão à caminhada até o cofre.
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def post(self, request, request_ref: str):
        # A trava de replay do dinheiro — ver `_cash_idempotent`.
        def _executar(request_ref, ):
            try:
                pos_service.cancel_change_request(
                    operator=request.user,
                    request_ref=request_ref,
                    terminal_ref=_terminal_do_pedido(request),
                )
            except PosIntentError as exc:
                return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)
            except Exception as exc:
                logger.debug("pos_change_request_cancel_failed user=%s", _actor(request), exc_info=True)
                return _falha_do_caixa(exc, "Falha ao cancelar o pedido.")
            return Response({"ok": True})

        return _cash_idempotent(
            request, acao="cancel_change_request", executar=lambda: _executar(request_ref)
        )


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Hand back the cash of a cancelled sale from this shift's drawer",
        responses={200: OpenApiResponse(description="Cash refund recorded.")},
    ),
)
class POSCashRefundView(APIView):
    """Devolver o dinheiro de uma venda cancelada, pela gaveta de quem devolve.

    Cancelar não é devolver. O cancel pelo gestor (de noite, de casa) deixa a
    devolução pendente; quem entrega as notas é quem está com a gaveta aberta,
    e é nesse instante que o Payman e o livro registram, juntos.
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def post(self, request, order_ref: str):
        # A trava de replay do dinheiro — ver `_cash_idempotent`.
        def _executar(order_ref, ):
            try:
                refunded_q = pos_service.refund_cash(
                    operator=request.user,
                    order_ref=order_ref,
                    manager_approval=request.data.get("manager_approval"),
                    terminal_ref=_terminal_do_pedido(request),
                )
            except PosIntentError as exc:
                return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)
            except Exception as exc:
                logger.debug("pos_cash_refund_failed user=%s", _actor(request), exc_info=True)
                return _falha_do_caixa(exc, "Falha ao devolver o dinheiro.")
            return Response({"ok": True, "refunded_q": refunded_q})

        return _cash_idempotent(
            request, acao="refund_cash", executar=lambda: _executar(order_ref)
        )


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="House accounts — customers with an open balance",
        responses={200: OpenApiResponse(description="Account balances.")},
    ),
)
class POSAccountBalancesView(APIView):
    """Quem deve quanto (derivado dos intents ``account`` autorizados). Só leitura."""

    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def get(self, request):
        from shopman.backstage.projections.pos import account_balances

        return Response({"accounts": [projection_data(row) for row in account_balances()]})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Settle (part of) a customer's house account",
        responses={200: OpenApiResponse(description="Settlement recorded.")},
    ),
)
class POSAccountSettleView(APIView):
    """O acerto: captura FIFO por venda inteira; em dinheiro, a gaveta aberta recebe."""

    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def post(self, request, customer_ref: str):
        # A trava de replay do dinheiro — ver `_cash_idempotent`.
        def _executar(customer_ref, ):
            body = request.data or {}
            try:
                settlement = pos_service.settle_account(
                    operator=request.user,
                    customer_ref=customer_ref,
                    amount_raw=str(body.get("amount", "")),
                    method=str(body.get("method", "")),
                    terminal_ref=_terminal_do_pedido(request),
                )
            except POSError as exc:
                return Response({"detail": str(exc)}, status=400)
            return Response(
                {
                    "ok": True,
                    "customer_ref": settlement.customer_ref,
                    "method": settlement.method,
                    "settled_q": settlement.settled_q,
                    "remaining_q": settlement.remaining_q,
                    "intent_refs": list(settlement.intent_refs),
                }
            )

        return _cash_idempotent(
            request, acao="settle_account", executar=lambda: _executar(customer_ref)
        )


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Cash session report — X/Z readings and today's shift history",
        responses={200: OpenApiResponse(description="Cash session report.")},
    ),
)
class POSCashReportView(APIView):
    """Leitura X (turno aberto), leituras Z (turnos fechados) e histórico do dia.

    Gate `cashman.audit_shift`, e a razão MUDOU — vale registrar as duas, porque
    são perguntas diferentes:

    1. **Contagem cega.** A projection nunca expõe o ESPERADO nem a variância,
       nem no X nem no Z. Isso continua verdade e continua sendo por construção;
       não é este gate que garante.
    2. **Privacidade do faturamento.** O relatório mostra `sales_total`,
       `counted_total` e a quebra por método — quanto a casa vendeu hoje. Isso é
       questão financeira, e a decisão do dono é que ela não fica visível para
       quem opera, **nem para o gerente**: ele opera, autoriza exceção e fecha o
       turno contando às cegas; quem vê a apuração é quem audita.

    O balcão não perde o que precisa: a antesala segue mostrando a CONTAGEM de
    vendas do próprio turno, que é operação, não apuração.
    """

    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.audit_shift"

    def get(self, request):
        report = build_cash_session_report(
            operator=request.user,
            terminal_ref=str(request.query_params.get("terminal_ref") or ""),
        )
        return Response({"report": projection_data(report)})


# ── POS tab (comanda) endpoints ───────────────────────────────────────


def _actor_pos(request) -> str:
    # ``_actor`` e não ``request.user``: com a flag do operador ativo ligada,
    # ``request.user`` é a conta do dispositivo. A venda saía com
    # ``actor="pos:admin"`` e ``operator_username="joyce"`` ao mesmo tempo — a
    # mesma request afirmando duas autorias.
    return f"pos:{_actor(request)}"


def _username (request) -> str:
    return _actor(request)


def _fiscal_expected(order_ref: str | None) -> bool:
    """A venda recém-fechada vai ter NFC-e? Quem responde é a regra fiscal."""
    if not order_ref:
        return False
    try:
        from shopman.orderman.models import Order

        return fiscal_service.emission_expected(Order.objects.get(ref=order_ref))
    except ObjectDoesNotExist:
        return False


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Register a new POS tab (comanda)",
        responses={200: OpenApiResponse(description="Tab created.")},
    ),
)
class POSTabCreateView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def post(self, request):
        tab_ref = (request.data.get("tab_ref") or "").strip()
        label = (request.data.get("label") or "").strip()
        if not tab_ref:
            return Response({"detail": "Referência da comanda é obrigatória."}, status=400)
        try:
            tab = pos_tabs_service.register_pos_tab(tab_ref=tab_ref, label=label)
        except Exception as exc:
            logger.debug("pos_tab_create_failed tab_ref=%s", tab_ref, exc_info=True)
            return Response({"detail": str(exc) or "Falha ao criar comanda."}, status=400)
        return Response({"ok": True, "tab": tab})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Open or load a POS tab",
        responses={200: OpenApiResponse(description="Tab payload (items + customer + tab_ref).")},
    ),
)
class POSTabOpenView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def post(self, request, tab_ref: str):
        try:
            session = pos_tabs_service.open_pos_tab(
                channel_ref=POS_CHANNEL_REF,
                tab_ref=tab_ref,
                actor=_actor_pos(request),
                operator_username=_username(request),
            )
        except Exception as exc:
            logger.debug("pos_tab_open_failed tab_ref=%s", tab_ref, exc_info=True)
            return Response({"detail": str(exc) or "Falha ao abrir comanda."}, status=400)
        return Response(build_open_tab(session))


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Save the POS cart on its tab",
        responses={200: OpenApiResponse(description="Tab saved.")},
    ),
)
class POSTabSaveView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def post(self, request):
        body = request.data if hasattr(request, "data") else {}
        try:
            result = pos_tabs_service.save_pos_tab(
                channel_ref=POS_CHANNEL_REF,
                payload=body,
                actor=_actor_pos(request),
                operator_username=_username(request),
            )
        except PosIntentError as exc:
            return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        except Exception as exc:
            logger.debug("pos_tab_save_failed user=%s", _actor(request), exc_info=True)
            return Response({"detail": str(exc) or "Falha ao salvar comanda."}, status=400)
        return Response({
            "ok": True,
            "tab_ref": result.tab_ref,
            "tab_display": result.tab_display,
            "session_key": result.session_key,
        })


@extend_schema_view(
    delete=extend_schema(
        tags=["backstage"],
        summary="Clear a POS tab (abandon session)",
        responses={200: OpenApiResponse(description="Tab cleared.")},
    ),
)
class POSTabClearView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def delete(self, request, session_key: str):
        try:
            cleared = pos_tabs_service.clear_pos_tab(
                channel_ref=POS_CHANNEL_REF,
                session_key=session_key,
                operator_username=_username(request),
            )
        except Exception as exc:
            logger.debug("pos_tab_clear_failed session_key=%s", session_key, exc_info=True)
            return Response({"detail": str(exc) or "Falha ao liberar comanda."}, status=400)
        if not cleared:
            return Response({"detail": "Comanda não encontrada."}, status=404)
        return Response({"ok": True})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Move lines between POS tabs (transfer/split/merge)",
        responses={200: OpenApiResponse(description="Lines moved.")},
    ),
)
class POSTabMoveLinesView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def post(self, request):
        body = request.data if hasattr(request, "data") else {}
        try:
            result = pos_tabs_service.move_pos_tab_lines(
                channel_ref=POS_CHANNEL_REF,
                from_session_key=str(body.get("from_session_key") or "").strip(),
                to_session_key=str(body.get("to_session_key") or "").strip(),
                to_tab_ref=str(body.get("to_tab_ref") or "").strip(),
                line_ids=body.get("line_ids") or [],
                close_source_when_empty=as_bool(body, "close_source_when_empty", default=False),
                actor=_actor_pos(request),
                operator_username=_username(request),
            )
        except PosIntentError as exc:
            return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)
        except Exception as exc:
            logger.debug("pos_tab_move_lines_failed user=%s", _actor(request), exc_info=True)
            return Response({"detail": str(exc) or "Falha ao mover itens entre comandas."}, status=400)
        return Response({
            "ok": True,
            "source_closed": result.source_closed,
            "source": None if result.source is None else build_open_tab(result.source),
            "target": build_open_tab(result.target),
        })


class POSTabRenameView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def post(self, request):
        body = request.data if hasattr(request, "data") else {}
        try:
            session = pos_tabs_service.rename_pos_tab(
                channel_ref=POS_CHANNEL_REF,
                session_key=str(body.get("session_key") or "").strip(),
                new_tab_ref=str(body.get("new_tab_ref") or "").strip(),
                actor=_actor_pos(request),
                operator_username=_username(request),
            )
        except PosIntentError as exc:
            return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)
        except Exception as exc:
            logger.debug("pos_tab_rename_failed user=%s", _actor(request), exc_info=True)
            return Response({"detail": str(exc) or "Falha ao renomear comanda."}, status=400)
        return Response({"ok": True, "tab": build_open_tab(session)})


class POSTabFireView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def post(self, request):
        body = request.data if hasattr(request, "data") else {}
        try:
            result = pos_tabs_service.fire_pos_tab(
                channel_ref=POS_CHANNEL_REF,
                session_key=str(body.get("session_key") or "").strip(),
                line_ids=body.get("line_ids") or [],
                client_request_id=str(body.get("client_request_id") or "").strip(),
                actor=_actor_pos(request),
                operator_username=_username(request),
            )
        except PosIntentError as exc:
            return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)
        except Exception as exc:
            logger.debug("pos_tab_fire_failed user=%s", _actor(request), exc_info=True)
            return Response({"detail": str(exc) or "Falha ao enviar à cozinha."}, status=400)
        return Response({
            "ok": True,
            "fired_count": result.fired_count,
            "fired_lines": list(result.fired_lines),
            "tab": build_open_tab(result.session),
        })


class POSTabUnfireView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def post(self, request):
        body = request.data if hasattr(request, "data") else {}
        try:
            result = pos_tabs_service.cancel_fired_pos_tab_lines(
                channel_ref=POS_CHANNEL_REF,
                session_key=str(body.get("session_key") or "").strip(),
                line_ids=body.get("line_ids") or [],
                actor=_actor_pos(request),
                operator_username=_username(request),
            )
        except PosIntentError as exc:
            return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)
        except Exception as exc:
            logger.debug("pos_tab_unfire_failed user=%s", _actor(request), exc_info=True)
            return Response({"detail": str(exc) or "Falha ao cancelar envio à cozinha."}, status=400)
        return Response({
            "ok": True,
            "cancelled": result.cancelled,
            "trimmed": result.trimmed,
            "fired_lines": list(result.fired_lines),
            "tab": build_open_tab(result.session),
        })


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Look up customer by ref or phone",
        responses={200: OpenApiResponse(description="Customer projection or null.")},
    ),
)
class POSCustomerLookupView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def get(self, request):
        ref = (request.query_params.get("ref") or "").strip()
        phone = (request.query_params.get("phone") or "").strip()
        # `ref` vence: é a chave exata do cadastro (cliente sem telefone existe).
        if ref:
            customer = build_pos_customer_lookup_by_ref(ref)
        elif phone:
            customer = build_pos_customer_lookup(phone)
        else:
            return Response({"customer": None})
        if customer is None:
            return Response({"customer": None})
        return Response({"customer": projection_data(customer)})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Search customers by any unique key (name/phone/CPF/email)",
        responses={200: OpenApiResponse(description="List of matching customers.")},
    ),
)
class POSCustomerSearchView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def get(self, request):
        query = (request.query_params.get("q") or "").strip()
        results = build_pos_customer_search(query)
        return Response({"results": [projection_data(result) for result in results]})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Resolve or create a customer just-in-time (get-or-create)",
        responses={200: OpenApiResponse(description="The resolved/created customer lookup.")},
    ),
)
class POSCustomerResolveView(APIView):
    """Just-in-time get-or-create: when the operator defines a customer on the
    counter, resolve them (phone/CPF/email) or create the record NOW, returning
    the same lookup projection as customer_lookup (ref + memory + addresses)."""

    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def post(self, request):
        body = request.data or {}
        try:
            customer = pos_tabs_service.resolve_or_create_customer(
                # ⚠️ O cliente JÁ ASSOCIADO viaja. Sem ele, um telefone digitado
                # no formulário de edição achava um único candidato e trocava o
                # dono do pedido em silêncio — a detecção de conflito existia e
                # nunca era alcançada.
                ref=str(body.get("customer_ref") or "").strip(),
                name=str(body.get("customer_name") or "").strip(),
                phone=str(body.get("customer_phone") or "").strip(),
                tax_id=str(body.get("customer_tax_id") or "").strip(),
                email=str(body.get("customer_email") or "").strip(),
                contact_correction=as_bool(body, "customer_contact_correction", default=False),
                operator_username=_username(request),
            )
        except PosCustomerConflict as exc:
            # A gêmea na tela lê `candidates`: quem está na comanda, quem é dono
            # do valor digitado, e por qual campo discordam.
            return Response(
                {
                    "detail": str(exc),
                    "field": exc.field or None,
                    "error": {
                        "code": "customer_conflict",
                        "field": exc.field,
                        "candidates": exc.candidates,
                    },
                },
                status=422,
            )
        except ValueError as exc:
            return Response(
                {"detail": str(exc) or "Cadastro conflitante.", "error": {"code": "customer_conflict"}},
                status=422,
            )
        if not customer:
            return Response({"customer": None})
        # A resposta carrega SEMPRE a projeção do cliente resolvido, chaveada
        # pelo ref: o re-lookup por telefone devolvia null para cliente sem
        # telefone (cadastro só com CPF) e o front descartava o cadastro recém-
        # criado. `created` distingue "achei" de "criei agora" na tela.
        lookup = build_pos_customer_lookup_by_ref(customer.get("ref") or "")
        return Response({
            "customer": projection_data(lookup) if lookup else None,
            "created": bool(customer.get("created")),
        })


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Review POS sale intent without committing",
        responses={200: OpenApiResponse(description="Checkout review and normalized totals.")},
    ),
)
class POSReviewSaleView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def post(self, request):
        body = request.data if hasattr(request, "data") else {}
        if _open_cash_shift_for_request(request) is None:
            return _cash_shift_required_response()
        try:
            review = pos_tabs_service.review_sale(
                channel_ref=POS_CHANNEL_REF,
                payload=_pos_payload_with_runtime(request, body),
                operator_username=_username(request),
            )
        except PosIntentError as exc:
            return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=422)
        return Response({"ok": True, "review": _pos_sale_review_payload(review)})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Close POS sale (commit cart as order)",
        responses={200: OpenApiResponse(description="Order created.")},
    ),
)
class POSCloseSaleView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def post(self, request):
        body = request.data if hasattr(request, "data") else {}
        if _open_cash_shift_for_request(request) is None:
            return _cash_shift_required_response()
        try:
            result = pos_tabs_service.close_sale(
                channel_ref=POS_CHANNEL_REF,
                payload=_pos_payload_with_runtime(request, body),
                actor=_actor_pos(request),
                operator_username=_username(request),
            )
        except PosIntentError as exc:
            return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)
        except ValueError as exc:
            return Response({"detail": str(exc) or "Falha ao finalizar venda."}, status=422)
        order_ref = getattr(result, "order_ref", None)
        return Response({
            "ok": True,
            "order_ref": order_ref,
            "tab_ref": getattr(result, "tab_ref", None),
            "payment": getattr(result, "payment", None) or {},
            "fiscal_expected": _fiscal_expected(order_ref),
        })


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Cancel a recent POS sale",
        responses={200: OpenApiResponse(description="Recent POS sale cancelled.")},
    ),
)
class POSCancelRecentSaleView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "cashman.operate_pos"

    def post(self, request):
        order_ref = (request.data.get("order_ref") or "").strip()
        reason = (request.data.get("reason") or "").strip()
        if not order_ref:
            return Response({"detail": "Referência do pedido não informada."}, status=422)
        try:
            # Cancelar venda fechada é exceção auditada: sempre sob PIN de gerente,
            # mesmo dentro da janela otimista do operador.
            aprovador = pos_tabs_service.validate_manager_override(
                request.data.get("manager_approval"),
                operator_username=_username(request),
                action="cancel_recent_sale",
            )
            # Quem assina é quem o VALIDADOR devolveu, não o que veio no corpo.
            # Reler o payload dava certo enquanto a única porta era username+PIN;
            # com crachá o username chega vazio e a segunda assinatura sumiria —
            # exatamente o "validar A e persistir B" que o docstring do validador
            # descreve como buraco pronto para o primeiro refactor.
            approved_by_username = aprovador.get_username() if aprovador else ""
            if reason:
                pos_tabs_service.reopen_recent_order_for_correction(
                    order_ref=order_ref,
                    actor=_actor_pos(request),
                    reason=reason,
                    approved_by_username=approved_by_username,
                )
            else:
                pos_tabs_service.cancel_recent_order(
                    order_ref=order_ref,
                    actor=_actor_pos(request),
                    approved_by_username=approved_by_username,
                )
        except PosIntentError as exc:
            return Response({"detail": exc.message, "error": exc.as_dict()}, status=exc.status)
        except PosRecentSaleNotFound as exc:
            return Response({"detail": str(exc)}, status=404)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=422)
        return Response({"ok": True, "order_ref": order_ref})
