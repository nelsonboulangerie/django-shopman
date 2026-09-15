"""Authorize enrollment; never print a provisioning secret or confirm an unproved device."""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from shopman.backstage.services.admin_two_factor import authorize_enrollment


class Command(BaseCommand):
    help = "Prepara inscrição no navegador, sem imprimir QR/segredo e sem revogar fatores atuais."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--force", action="store_true", help="Prepara substituição; preserva fatores atuais até a confirmação completa.")

    def handle(self, *args, **options):
        try:
            user = get_user_model().objects.get(username=options["username"])
            authorize_enrollment(user, replace=options["force"])
        except (get_user_model().DoesNotExist, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write("Inscrição preparada. O titular deve acessar /admin/2fa/enroll/, confirmar sua senha, validar o autenticador e guardar/testar os códigos de recuperação. A exigência global de 2FA não foi alterada.")
