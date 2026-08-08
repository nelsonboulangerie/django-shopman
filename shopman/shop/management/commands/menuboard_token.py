"""Gera a URL de quiosque de um menuboard — o que se digita UMA vez na TV.

O menuboard é superfície interna (ver ``shopman.shop.menuboard_access``). Uma TV
não faz login, então ela carrega um token assinado na própria URL: durável, preso
à ref daquele quadro, e gerado aqui.

    python manage.py menuboard_token tv-cafe
    python manage.py menuboard_token tv-cafe --base-url https://mkt.boulangerie.com.br

Revogar exige rotacionar ``SECRET_KEY`` — limitação assumida e documentada, porque
o que o token abre é um quadro de preços interno, não uma conta.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from shopman.shop.menuboard_access import KIOSK_PARAM, make_kiosk_token


class Command(BaseCommand):
    help = "Gera a URL de quiosque (com token) de um menuboard."

    def add_arguments(self, parser):
        parser.add_argument("ref", help="Ref do canal de exibição (ex.: tv-cafe).")
        parser.add_argument(
            "--base-url",
            default="",
            help="Origem pública (ex.: https://mkt.boulangerie.com.br). Vazio = só o caminho.",
        )

    def handle(self, *args, **options):
        from shopman.shop.models import Channel

        ref = (options["ref"] or "").strip()
        if not ref:
            raise CommandError("Informe a ref do quadro.")

        channel = Channel.objects.filter(ref=ref).first()
        if channel is None:
            raise CommandError(f"Não existe canal com ref '{ref}'.")
        if channel.commerce_policy != Channel.CommercePolicy.DISPLAY:
            raise CommandError(
                f"'{ref}' é canal de venda (commerce_policy={channel.commerce_policy}). "
                "Token de quiosque só faz sentido em canal de exibição."
            )

        token = make_kiosk_token(ref)
        path = f"/menuboard/{ref}/?{KIOSK_PARAM}={token}"
        base = (options["base_url"] or "").rstrip("/")

        self.stdout.write(self.style.SUCCESS(f"{base}{path}" if base else path))
        self.stdout.write(
            "\nAbra esta URL na TV uma vez. O token não expira; para revogar, "
            "rotacione SECRET_KEY."
        )
