"""Os grupos RBAC do deployment, aplicados a partir do descritor da Instância.

O job de release roda `migrate && setup_groups` em todo deploy. Este comando lia
uma lista própria de 13 grupos escrita em Python, e o descritor
(`config/instances/<ref>.json`, seção `rbac_personas`) declarava os mesmos grupos:
duas fontes para a mesma pergunta, e numa Instância que não fosse a Nelson o
release instalava os grupos da Nelson por cima dos dela.

Agora a fonte é uma só: as personas do descritor configurado em
`SHOPMAN_INSTANCE_DESCRIPTOR`. A lista de permissões de cada persona, e o porquê
de cada uma, mora no descritor e no guia `docs/guides/rbac-personas.md`.

Continua `set`, não `add`: dono também TIRA. Permissão retirada do descritor sai
do banco no próximo deploy, e o log diz qual saiu. ⚠️ A contrapartida é a mesma
de antes: concessão feita à mão no Admin num grupo declarado é revogada no
próximo deploy. Grupo que o descritor não declara não é tocado.

Ao final, a mesma porta instala os grupos comerciais ausentes
(`setup_commercial_groups`), reaproveitando o hook de release que já existe.

Ver `shopman/shop/tests/test_group_permission_parity.py`, que falha se uma
permission gateando superfície não for concedida a ninguém.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from config.instance_descriptors import (
    UnsafeDescriptor,
    configured_descriptor,
    sync_personas,
)


class Command(BaseCommand):
    help = "Aplica as personas RBAC do descritor da Instância e os grupos comerciais ausentes."

    def handle(self, *args, **options):
        from django.contrib.auth.models import Group
        from django.db import transaction

        try:
            descriptor = configured_descriptor()
            with transaction.atomic():
                reports = sync_personas(descriptor["bootstrap"]["rbac_personas"])
        except (OSError, KeyError, ValueError, UnsafeDescriptor) as exc:
            raise CommandError(f"setup_groups: {exc}") from exc

        self.stdout.write(f"Instância: {descriptor['instance']['ref']}")
        for report in reports:
            verb = "criado" if report["created"] else "atualizado"
            # A contagem sai do BANCO, não da lista declarada.
            count = Group.objects.get(name=report["name"]).permissions.count()
            line = f"  {report['name']}: {verb} ({count} permissões)"
            if report["revoked"]:
                line += f"; revogadas: {', '.join(report['revoked'])}"
            self.stdout.write(line)

        # O banco vivo não roda `seed`. Este hook de release é a porta
        # idempotente que garante os grupos comerciais iniciais sem reverter as
        # edições feitas depois pelo Gestor.
        call_command("setup_commercial_groups", stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS("setup_groups: OK"))
