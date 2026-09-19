from __future__ import annotations

import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from shopman.doorman.conf import get_adapter
from shopman.doorman.models import VerificationCode

_EVIDENCE_REF = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:/-]{2,119}\Z")


class Command(BaseCommand):
    help = (
        "Reconcilia uma entrega OTP interrompida usando evidência operacional; "
        "não consulta nem altera provedores."
    )

    def add_arguments(self, parser):
        parser.add_argument("--code-id", required=True)
        parser.add_argument("--outcome", required=True, choices=("accepted", "rejected"))
        parser.add_argument("--evidence-ref", required=True)

    def handle(self, *args, **options):
        evidence_ref = str(options["evidence_ref"] or "").strip()
        if not _EVIDENCE_REF.fullmatch(evidence_ref):
            raise CommandError(
                "evidence-ref deve ser um identificador operacional sem dados pessoais."
            )

        code_hint = VerificationCode.objects.filter(pk=options["code_id"]).first()
        if code_hint is None:
            raise CommandError("Código OTP não encontrado.")

        adapter = get_adapter()
        with transaction.atomic(durable=True):
            locked_customer = None
            if code_hint.customer_id is not None:
                locked_customer = adapter.lock_active_customer_by_uuid(
                    code_hint.customer_id
                )
            code = (
                VerificationCode.objects.select_for_update()
                .filter(pk=options["code_id"])
                .first()
            )
            if code is None:
                raise CommandError("Código OTP não encontrado.")
            if code.customer_id != code_hint.customer_id:
                raise CommandError("O vínculo do código mudou; reinicie a conferência.")
            if (
                code.status != VerificationCode.Status.PENDING
                or code.delivery_started_at is None
            ):
                raise CommandError("A entrega OTP não está pendente de reconciliação.")
            customer_still_authorized = locked_customer is not None and (
                code.purpose != VerificationCode.Purpose.LOGIN
                or adapter.login_target_belongs_to_customer(
                    locked_customer,
                    code.target_value,
                )
            )
            if (
                options["outcome"] == "accepted"
                and code.customer_id is not None
                and not customer_still_authorized
            ):
                raise CommandError(
                    "A conta ou o contato mudou; reconcilie esta entrega como rejected."
                )

            reconciled_at = timezone.now()
            code.delivery_reconciled_at = reconciled_at
            code.delivery_evidence_ref = evidence_ref
            update_fields = [
                "status",
                "delivery_reconciled_at",
                "delivery_evidence_ref",
            ]
            if options["outcome"] == "accepted":
                code.status = VerificationCode.Status.SENT
                if code.sent_at is None:
                    code.sent_at = reconciled_at
                    update_fields.append("sent_at")
            else:
                code.status = VerificationCode.Status.FAILED
            code.save(update_fields=update_fields)

        self.stdout.write(
            self.style.SUCCESS(
                "Entrega OTP reconciliada; a cerca de exclusão foi atualizada."
            )
        )
