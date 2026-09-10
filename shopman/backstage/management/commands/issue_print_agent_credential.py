"""Issue a one-time relay bearer without storing or projecting the secret."""

from django.core.management.base import BaseCommand, CommandError
from shopman.cashman.models import Terminal

from shopman.backstage.models import PrintAgentCredential


class Command(BaseCommand):
    help = "Emite uma credencial do relay de impressão e mostra o segredo uma única vez."

    def add_arguments(self, parser):
        parser.add_argument("--terminal", required=True)
        parser.add_argument("--label", default="")

    def handle(self, *args, **options):
        terminal = Terminal.objects.filter(ref=options["terminal"], is_active=True).first()
        if terminal is None:
            raise CommandError("Terminal ativo não encontrado.")
        credential, bearer = PrintAgentCredential.issue(terminal=terminal, label=options["label"])
        self.stdout.write(f"credential_ref={credential.ref}")
        self.stdout.write(f"bearer={bearer}")
        self.stderr.write("Guarde o bearer agora: o servidor persiste somente o digest HMAC.")
