"""Reconcile a fail-closed ManyChat resolution without mutating the provider."""

from django.core.management.base import BaseCommand, CommandError
from shopman.guestman.contrib.manychat.resolver import ManychatSubscriberResolver
from shopman.guestman.models import Customer


class Command(BaseCommand):
    help = (
        "Confere no ManyChat uma resolução externa incerta e libera a exclusão "
        "somente quando o provedor confirma vínculo ou ausência."
    )

    def add_arguments(self, parser):
        parser.add_argument("--customer-ref", required=True)

    def handle(self, *args, **options):
        customer_ref = str(options["customer_ref"] or "").strip()
        customer = Customer.objects.filter(ref=customer_ref, is_active=True).first()
        if customer is None:
            raise CommandError("Cadastro ativo não encontrado.")

        outcome = ManychatSubscriberResolver.reconcile_pending(customer.pk)
        messages = {
            "clear": "Nenhuma verificação ManyChat estava pendente.",
            "linked": "Vínculo ManyChat confirmado e registrado; desvincule-o antes da exclusão.",
            "absent": "Ausência confirmada pelo ManyChat; a pendência foi liberada.",
        }
        if outcome == "uncertain":
            raise CommandError(
                "O ManyChat ainda não confirmou vínculo nem ausência; a exclusão continua bloqueada."
            )
        self.stdout.write(self.style.SUCCESS(messages[outcome]))
