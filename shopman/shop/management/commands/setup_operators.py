"""O elenco de dev/staging: as pessoas que operam a loja, ligadas a GRUPOS.

Existe separado do ``seed`` por um motivo prático: o ``seed`` recria o catálogo
e milhares de pedidos falsos, e no staging isso é destrutivo. As PESSOAS,
porém, precisam ser recriadas ou corrigidas com frequência — depois de um
``setup_groups``, ao testar uma permissão nova, quando alguém perde acesso. Este
comando faz só isso, é idempotente, e não encosta em nenhum dado de negócio.

⚠️ **Grupo, nunca permissão avulsa.** O ``seed`` antigo concedia
``user_permissions`` direto: a gerente recebia sete permissões copiadas à mão
que imitavam o grupo "Gerente" sem serem ele. O efeito é que a tela de Grupos do
Admin mentia — mostrava gente sem grupo nenhum operando o sistema inteiro — e
qualquer mudança em ``setup_groups`` não alcançava ninguém. Aqui a associação é
por grupo e as permissões diretas são LIMPAS, para não sobrar um acesso que
ninguém consegue explicar de onde veio.

⚠️ **PIN 1234 e senha fraca são de dev.** Por isso o ``--yes`` obrigatório: é
uma frase que alguém digita de propósito, não algo que um job de release possa
disparar sozinho.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

DEV_PIN = "1234"
ADMIN_PASSWORD = "admin"

#: username, nome, sobrenome, grupos, é superusuário?
#:
#: Sobrenome vazio é deliberado: são pessoas de verdade da casa, e inventar um
#: sobrenome seria pior do que deixar em branco. Preencher pelo Admin quando
#: alguém souber.
#:
#: O elenco cobre os papéis que a loja tem de verdade, um por grupo, para que
#: testar "o que o gerente enxerga" seja entrar como o gerente — e não imaginar.
CAST: tuple[tuple[str, str, str, tuple[str, ...], bool], ...] = (
    # O dono: audita o dinheiro. Superusuário porque é quem administra o sistema,
    # E no grupo "Dono" porque o grupo não pode nascer vazio — sem ninguém nele,
    # a apuração fica invisível até para quem mandou trancá-la.
    ("admin", "Dono", "da Casa", ("Dono",), True),
    # O gestor: opera, autoriza exceção, fecha o dia. NÃO audita — ele conta às
    # cegas como todo mundo (ver docs/guides/rbac-personas.md).
    ("joyce", "Joyce", "", ("Gerente",), False),
    # Loja: balcão e PDV.
    ("fran", "Fran", "", ("Caixa",), False),
    # Produção: cozinha e fornadas.
    ("diofer", "Diofer", "", ("Cozinha",), False),
)


class Command(BaseCommand):
    help = "Cria/atualiza o elenco de operadores de dev/staging, ligado a grupos. Exige --yes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes",
            action="store_true",
            help=f"Confirma que este NÃO é o ambiente de produção (senha e PIN {DEV_PIN} são de dev).",
        )

    def handle(self, *args, **options):
        if not options["yes"]:
            raise CommandError(
                f"Este comando cria contas com PIN {DEV_PIN} e senha '{ADMIN_PASSWORD}'. "
                "Se este ambiente não é produção, repita com --yes."
            )

        from shopman.doorman.models import PinCredential

        # Os grupos são pré-requisito: associar a um grupo que não existe falharia
        # no meio, deixando metade do elenco pronto. Idempotente, custa milissegundos.
        call_command("setup_groups", verbosity=0)

        User = get_user_model()
        grupos = {g.name: g for g in Group.objects.all()}

        with transaction.atomic():
            for username, first, last, nomes_de_grupo, superuser in CAST:
                faltando = [n for n in nomes_de_grupo if n not in grupos]
                if faltando:
                    raise CommandError(
                        f"Grupo(s) {faltando} não existem — `setup_groups` mudou e este elenco não acompanhou."
                    )

                user, criado = User.objects.update_or_create(
                    username=username,
                    defaults={
                        "first_name": first,
                        "last_name": last,
                        "is_staff": True,
                        "is_active": True,
                        "is_superuser": superuser,
                    },
                )

                if superuser:
                    user.set_password(ADMIN_PASSWORD)
                else:
                    # Identidade só-PIN: a confiança do dispositivo entra pelo
                    # `admin`; quem opera se identifica pelo PIN, não por senha.
                    user.set_unusable_password()
                user.save(update_fields=["password"])

                # Permissão avulsa some: o grupo passa a ser a única resposta para
                # "por que essa pessoa consegue fazer isso?".
                user.user_permissions.clear()
                user.groups.set([grupos[n] for n in nomes_de_grupo])
                PinCredential.set_for(user, DEV_PIN)

                verbo = "criado" if criado else "atualizado"
                self.stdout.write(f"  {username}: {verbo} → {', '.join(nomes_de_grupo)}")

        self.stdout.write(self.style.SUCCESS(f"setup_operators: OK (PIN {DEV_PIN} para todos)"))
