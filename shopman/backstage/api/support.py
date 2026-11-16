"""Backstage API — Suporte (helpdesk interno).

GET  /api/v1/backstage/support/tickets/            lista (próprios ou todos)
POST /api/v1/backstage/support/tickets/            abre o chamado
GET  /api/v1/backstage/support/tickets/<ref>/      detalhe + thread
POST /api/v1/backstage/support/tickets/<ref>/messages/
POST /api/v1/backstage/support/tickets/<ref>/triage/
POST /api/v1/backstage/support/tickets/<ref>/decision/
POST /api/v1/backstage/support/tickets/<ref>/link-dev/

A captura é determinística: o ticket nasce com o contexto que o cliente manda e
o texto do requester. A classificação é sugestão; o estado e a aprovação são
determinísticos. A IA (ID3A) não aparece nesta camada.
"""

from __future__ import annotations

import json
import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.models import SupportDecision, SupportMessage, SupportTicket

User = get_user_model()

DEV_REF_RE = re.compile(r"^DEV-\d{4}-\d{3}$")
MAX_CONTEXT_BYTES = 8_000
MAX_CONTEXT_KEYS = 24


class SupportPermission(BasePermission):
    """Gate por capability `shop.*`; a ausência é 403, nunca 404 silencioso."""

    required_permission = ""

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.has_perm(self.required_permission)
        )


class CanCreateSupportTicket(SupportPermission):
    required_permission = "shop.create_support_ticket"


class CanTriageSupportTicket(SupportPermission):
    required_permission = "shop.triage_support_tickets"


class CanApproveSupportRequest(SupportPermission):
    required_permission = "shop.approve_support_requests"


class CanLinkSupportDev(SupportPermission):
    required_permission = "shop.link_support_dev"


def _can_view(user, ticket: SupportTicket) -> bool:
    if user.is_superuser:
        return True
    if ticket.requester_id == user.pk:
        return True
    return user.has_perm("shop.view_all_support_tickets")


def _role(user) -> str:
    if user.has_perm("shop.approve_support_requests"):
        return "owner"
    if user.has_perm("shop.triage_support_tickets"):
        return "manager"
    return "operator"


def _ticket_payload(ticket: SupportTicket, *, include_thread: bool = False) -> dict:
    data = {
        "ref": ticket.ref,
        "audience": ticket.audience,
        "type": ticket.type,
        "status": ticket.status,
        "priority": ticket.priority,
        "subject": ticket.subject,
        "description": ticket.description,
        "context": ticket.context,
        "requester": ticket.requester.username if ticket.requester_id else None,
        "requester_role": ticket.requester_role,
        "assignee": ticket.assignee.username if ticket.assignee_id else None,
        "sla_due": ticket.sla_due.isoformat() if ticket.sla_due else None,
        "review_at": ticket.review_at.isoformat() if ticket.review_at else None,
        "approved_by": ticket.approved_by.username if ticket.approved_by_id else None,
        "approved_at": ticket.approved_at.isoformat() if ticket.approved_at else None,
        "approval_basis": ticket.approval_basis,
        "ledger_ref": ticket.ledger_ref,
        "resolution": ticket.resolution,
        "created_at": ticket.created_at.isoformat(),
        "updated_at": ticket.updated_at.isoformat(),
        "closed_at": ticket.closed_at.isoformat() if ticket.closed_at else None,
    }
    if include_thread:
        data["messages"] = [
            _message_payload(message)
            for message in ticket.messages.select_related("author")
        ]
        data["decisions"] = [
            _decision_payload(decision)
            for decision in ticket.decisions.select_related("decided_by")
        ]
    return data


def _message_payload(message: SupportMessage) -> dict:
    return {
        "id": message.pk,
        "author": message.author.username if message.author_id else None,
        "body": message.body,
        "internal_note": message.internal_note,
        "channel": message.channel,
        "ai_meta": message.ai_meta,
        "created_at": message.created_at.isoformat(),
    }


def _decision_payload(decision: SupportDecision) -> dict:
    return {
        "id": decision.pk,
        "decided_by": decision.decided_by.username,
        "decision": decision.decision,
        "reason": decision.reason,
        "created_at": decision.created_at.isoformat(),
    }


class SupportTicketCreateSerializer(serializers.Serializer):
    subject = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
    description = serializers.CharField()
    type = serializers.ChoiceField(
        choices=SupportTicket.TYPE_CHOICES,
        required=False,
        default=SupportTicket.TYPE_QUESTION,
    )
    audience = serializers.ChoiceField(
        choices=SupportTicket.AUDIENCE_CHOICES,
        required=False,
        default=SupportTicket.AUDIENCE_INTERNAL,
    )
    context = serializers.DictField(required=False)
    client_uuid = serializers.UUIDField(required=False, allow_null=True)

    def validate_context(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("O contexto precisa ser um objeto.")
        if len(value) > MAX_CONTEXT_KEYS:
            raise serializers.ValidationError(
                f"O contexto aceita no máximo {MAX_CONTEXT_KEYS} chaves."
            )
        try:
            encoded = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise serializers.ValidationError("O contexto não é JSON.") from exc
        if len(encoded.encode("utf-8")) > MAX_CONTEXT_BYTES:
            raise serializers.ValidationError(
                f"O contexto passa de {MAX_CONTEXT_BYTES} bytes."
            )
        return value


class SupportMessageCreateSerializer(serializers.Serializer):
    body = serializers.CharField()
    internal_note = serializers.BooleanField(required=False, default=False)


class SupportTriageSerializer(serializers.Serializer):
    type = serializers.ChoiceField(
        choices=SupportTicket.TYPE_CHOICES, required=False
    )
    priority = serializers.ChoiceField(
        choices=SupportTicket.PRIORITY_CHOICES, required=False
    )
    assignee_id = serializers.IntegerField(required=False, allow_null=True)

    def validate_assignee_id(self, value):
        if value is None:
            return None
        if not User.objects.filter(pk=value, is_active=True).exists():
            raise serializers.ValidationError("Responsável inexistente.")
        return value


class SupportDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=SupportDecision.DECISION_CHOICES)
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    review_at = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        if attrs["decision"] in (
            SupportDecision.DECISION_REJECT,
            SupportDecision.DECISION_DEFER,
        ) and not attrs.get("reason"):
            raise serializers.ValidationError(
                {"reason": "Recusar ou adiar exige motivo."}
            )
        if (
            attrs["decision"] == SupportDecision.DECISION_DEFER
            and not attrs.get("review_at")
        ):
            raise serializers.ValidationError(
                {"review_at": "Adiar exige a data de revisão."}
            )
        return attrs


class SupportLinkDevSerializer(serializers.Serializer):
    dev_ref = serializers.CharField(max_length=20)

    def validate_dev_ref(self, value):
        if not DEV_REF_RE.match(value):
            raise serializers.ValidationError(
                "O compromisso usa o formato DEV-AAAA-NNN."
            )
        return value


def _sla_for(ticket_type: str):
    days = 3 if ticket_type in (
        SupportTicket.TYPE_REQUEST,
        SupportTicket.TYPE_IDEA,
        SupportTicket.TYPE_DECISION,
    ) else 1
    return timezone.now() + timedelta(days=days)


class SupportTicketListCreateView(APIView):
    permission_classes = [IsAuthenticated, CanCreateSupportTicket]

    def get(self, request):
        tickets = SupportTicket.objects.select_related(
            "requester", "assignee", "approved_by"
        )
        if not request.user.has_perm("shop.view_all_support_tickets"):
            tickets = tickets.filter(requester=request.user)
        if request.query_params.get("mine") == "1":
            tickets = tickets.filter(requester=request.user)
        status = request.query_params.get("status")
        if status:
            tickets = tickets.filter(status=status)
        ticket_type = request.query_params.get("type")
        if ticket_type:
            tickets = tickets.filter(type=ticket_type)
        return Response(
            {"tickets": [_ticket_payload(ticket) for ticket in tickets[:200]]}
        )

    def post(self, request):
        serializer = SupportTicketCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)

        client_uuid = data.pop("client_uuid", None)
        if client_uuid:
            existing = SupportTicket.objects.filter(client_uuid=client_uuid).first()
            if existing and existing.requester_id != request.user.pk:
                raise ValidationError(
                    {"client_uuid": "Este UUID já pertence a outro chamado."}
                )
            if existing:
                return Response(
                    _ticket_payload(existing, include_thread=True), status=200
                )

        status = SupportTicket.STATUS_NEW
        approved_at = None
        approval_basis = ""
        if (
            request.user.has_perm("shop.approve_support_requests")
            and data["type"] == SupportTicket.TYPE_REQUEST
        ):
            status = SupportTicket.STATUS_APPROVED
            approved_at = timezone.now()
            approval_basis = "solicitado pelo dono"
        elif data["type"] in (
            SupportTicket.TYPE_IDEA,
            SupportTicket.TYPE_DECISION,
        ):
            status = SupportTicket.STATUS_TRIAGE

        ticket = SupportTicket.objects.create(
            requester=request.user,
            requester_role=_role(request.user),
            status=status,
            approved_by=request.user if approved_at else None,
            approved_at=approved_at,
            approval_basis=approval_basis,
            sla_due=_sla_for(data["type"]),
            client_uuid=client_uuid,
            **data,
        )
        return Response(
            _ticket_payload(ticket, include_thread=True), status=201
        )


class SupportTicketDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, ref):
        ticket = get_object_or_404(SupportTicket, ref=ref)
        if not _can_view(request.user, ticket):
            raise PermissionDenied("Chamado de outra pessoa.")
        return Response(_ticket_payload(ticket, include_thread=True))


class SupportTicketMessageView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, ref):
        ticket = get_object_or_404(SupportTicket, ref=ref)
        if not _can_view(request.user, ticket):
            raise PermissionDenied("Chamado de outra pessoa.")
        serializer = SupportMessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data["internal_note"] and not request.user.has_perm(
            "shop.triage_support_tickets"
        ):
            raise PermissionDenied("Nota interna é da equipe de triagem.")
        message = SupportMessage.objects.create(
            ticket=ticket, author=request.user, **data
        )
        if (
            ticket.status == SupportTicket.STATUS_WAITING_REQUESTER
            and ticket.requester_id == request.user.pk
        ):
            ticket.status = SupportTicket.STATUS_TRIAGE
            ticket.save(update_fields=["status", "updated_at"])
        return Response(_message_payload(message), status=201)


class SupportTicketTriageView(APIView):
    permission_classes = [IsAuthenticated, CanTriageSupportTicket]

    def post(self, request, ref):
        ticket = get_object_or_404(SupportTicket, ref=ref)
        if ticket.status in (
            SupportTicket.STATUS_APPROVED,
            SupportTicket.STATUS_REJECTED,
            SupportTicket.STATUS_IN_DEV,
            SupportTicket.STATUS_RESOLVED,
            SupportTicket.STATUS_CLOSED,
        ):
            raise ValidationError(
                {"detail": "Chamado já saiu da triagem."}
            )
        serializer = SupportTriageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        for field in ("type", "priority"):
            if field in data:
                setattr(ticket, field, data[field])
        if "assignee_id" in data:
            ticket.assignee_id = data["assignee_id"]
        if ticket.type in (
            SupportTicket.TYPE_REQUEST,
            SupportTicket.TYPE_IDEA,
            SupportTicket.TYPE_DECISION,
        ):
            ticket.status = SupportTicket.STATUS_WAITING_OWNER
        elif ticket.status == SupportTicket.STATUS_NEW:
            ticket.status = SupportTicket.STATUS_TRIAGE
        ticket.save()
        return Response(_ticket_payload(ticket, include_thread=True))


class SupportTicketDecisionView(APIView):
    permission_classes = [IsAuthenticated, CanApproveSupportRequest]

    def post(self, request, ref):
        ticket = get_object_or_404(SupportTicket, ref=ref)
        if ticket.status not in (
            SupportTicket.STATUS_NEW,
            SupportTicket.STATUS_TRIAGE,
            SupportTicket.STATUS_WAITING_OWNER,
        ):
            raise ValidationError(
                {"detail": "Chamado não está aguardando decisão."}
            )
        serializer = SupportDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        decision = data["decision"]
        SupportDecision.objects.create(
            ticket=ticket,
            decided_by=request.user,
            decision=decision,
            reason=data.get("reason", ""),
        )
        if decision == SupportDecision.DECISION_APPROVE:
            ticket.status = SupportTicket.STATUS_APPROVED
            ticket.approved_by = request.user
            ticket.approved_at = timezone.now()
            ticket.approval_basis = data.get("reason") or "aprovado pelo dono"
        elif decision == SupportDecision.DECISION_REJECT:
            ticket.status = SupportTicket.STATUS_REJECTED
            ticket.resolution = data["reason"]
            ticket.closed_at = timezone.now()
        else:
            ticket.status = SupportTicket.STATUS_DEFERRED
            ticket.review_at = data["review_at"]
        ticket.save()
        return Response(_ticket_payload(ticket, include_thread=True))


class SupportTicketLinkDevView(APIView):
    permission_classes = [IsAuthenticated, CanLinkSupportDev]

    def post(self, request, ref):
        ticket = get_object_or_404(SupportTicket, ref=ref)
        if ticket.status not in (
            SupportTicket.STATUS_APPROVED,
            SupportTicket.STATUS_IN_DEV,
        ):
            raise ValidationError(
                {"detail": "Só chamado aprovado vira compromisso de dev."}
            )
        serializer = SupportLinkDevSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket.ledger_ref = serializer.validated_data["dev_ref"]
        ticket.status = SupportTicket.STATUS_IN_DEV
        ticket.save(update_fields=["ledger_ref", "status", "updated_at"])
        return Response(_ticket_payload(ticket, include_thread=True))
