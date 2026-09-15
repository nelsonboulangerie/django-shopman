"""Read-only rollout preflight. This command never enables the global gate."""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice

from shopman.backstage.models import AdminTwoFactorEnrollment
from shopman.backstage.services.admin_two_factor import RECOVERY_NAME


class Command(BaseCommand):
    help = "Confere autenticação e recuperação de todos os staff ativos antes do rollout."

    def handle(self, *args, **options):
        users = get_user_model().objects.filter(is_active=True, is_staff=True)
        missing = []
        for user in users:
            totp = TOTPDevice.objects.filter(user=user, confirmed=True, last_used_at__isnull=False).exists()
            recovery = StaticDevice.objects.filter(user=user, confirmed=True, name=RECOVERY_NAME,
                                                   last_used_at__isnull=False, token_set__isnull=False).exists()
            if not (totp and recovery and AdminTwoFactorEnrollment.objects.filter(user=user).exists()):
                missing.append(user.get_username())
        if missing or not users.exists():
            raise CommandError("Rollout pendente: " + (", ".join(missing) or "nenhum staff ativo"))
        self.stdout.write("Prontidão confirmada: todos os staff ativos validaram autenticador e recuperação. Nenhuma configuração foi alterada.")
