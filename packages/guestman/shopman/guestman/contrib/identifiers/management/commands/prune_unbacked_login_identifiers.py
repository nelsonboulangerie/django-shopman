"""Acha (padrão) ou apaga (``--apply``) a chave de login que ficou sem contato.

Até o A4-1, trocar o telefone ou o e-mail apagava o ``ContactPoint`` e deixava
o ``CustomerIdentifier`` do valor antigo para trás. Desde que o porto de
identidade lê o identificador, essa sobra abre a conta por OTP para quem
receber o número reciclado. O ``post_delete`` do contato impede que nasçam
novas; este comando acha as que já existem.

"Sem contato" quer dizer: identificador de telefone, WhatsApp ou e-mail cujo
cadastro não tem mais nenhum ``ContactPoint`` da mesma família com o mesmo
valor. É a mesma régua do ``post_delete``.

Manual e, por padrão, só simulação: rodar ``--apply`` num ambiente com dado
real é decisão de quem responde por ele. A saída não mostra o valor inteiro.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Exists, OuterRef, Q


def _mask(value: str) -> str:
    if "@" in value:
        local, _sep, domain = value.partition("@")
        return f"{local[:1]}***@{domain}"
    return f"***{value[-4:]}" if len(value) > 4 else "***"


def unbacked_login_identifiers():
    from shopman.guestman.contrib.identifiers.models import CustomerIdentifier
    from shopman.guestman.contrib.identifiers.signals import LOGIN_FAMILIES
    from shopman.guestman.models import ContactPoint

    unbacked = Q(pk__in=[])
    for identifier_type, family in LOGIN_FAMILIES.items():
        backing = ContactPoint.objects.filter(
            customer_id=OuterRef("customer_id"),
            type__in=family,
            value_normalized=OuterRef("identifier_value"),
        )
        unbacked |= Q(identifier_type=identifier_type) & ~Q(Exists(backing))
    return (
        CustomerIdentifier.objects.filter(unbacked)
        .select_related("customer")
        .order_by("customer__ref", "identifier_type")
    )


class Command(BaseCommand):
    help = (
        "Lista (padrão) ou, com --apply, apaga identificadores de telefone, WhatsApp "
        "ou e-mail que nenhum contato do cadastro sustenta mais."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apaga de fato. Sem esta flag o comando só lista e não altera nada.",
        )

    def handle(self, *args, **options):
        with transaction.atomic():
            rows = list(unbacked_login_identifiers().select_for_update(of=("self",)))
            for ident in rows:
                self.stdout.write(
                    f"{ident.customer.ref} {ident.identifier_type} {_mask(ident.identifier_value)} "
                    f"(origem: {ident.source_system or 'sem origem'})"
                )
            if options["apply"]:
                from shopman.guestman.contrib.identifiers.models import CustomerIdentifier

                CustomerIdentifier.objects.filter(pk__in=[ident.pk for ident in rows]).delete()
                self.stdout.write(f"{len(rows)} identificador(es) sem contato apagado(s).")
                return
        self.stdout.write(
            f"Simulação: {len(rows)} identificador(es) sem contato. "
            "Nada foi alterado; para apagar, rode com --apply."
        )
