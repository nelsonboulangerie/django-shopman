from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from shopman.shop.models import PushSubscription


class Command(BaseCommand):
    help = "Desativa todas as assinaturas Web Push após rotação das chaves VAPID."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm-vapid-rotation",
            action="store_true",
            help="Confirma que o par VAPID foi rotacionado e os endpoints antigos perderam validade.",
        )

    def handle(self, *args, **options):
        if not options["confirm_vapid_rotation"]:
            raise CommandError("Use --confirm-vapid-rotation para confirmar a invalidação global.")
        changed = PushSubscription.objects.filter(disabled_at__isnull=True).update(
            disabled_at=timezone.now()
        )
        self.stdout.write(self.style.SUCCESS(f"{changed} assinatura(s) Web Push desativada(s)."))
