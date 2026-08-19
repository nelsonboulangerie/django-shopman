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


def dev_badge(username: str) -> str:
    """O código de barras do crachá de dev — previsível de propósito.

    Em produção o token é sorteado e só existe impresso no crachá. Aqui ele
    precisa ser DIGITÁVEL: sem isso, testar o leitor exigiria imprimir um
    crachá antes de saber se o leitor funciona, e foi por isso que a leitura
    parecia quebrada quando na verdade ninguém tinha crachá nenhum.
    """
    return f"CRACHA-{username.upper()}"

#: username, nome, sobrenome, grupos, é superusuário?, identidades que ele ABSORVE
#:
#: Sobrenome vazio é deliberado: são pessoas de verdade da casa, e inventar um
#: sobrenome seria pior do que deixar em branco. Preencher pelo Admin quando
#: alguém souber.
#:
#: O elenco cobre os papéis que a loja tem de verdade, um por grupo, para que
#: testar "o que o gerente enxerga" seja entrar como o gerente — e não imaginar.
CAST: tuple[tuple[str, str, str, tuple[str, ...], bool, tuple[str, ...]], ...] = (
    # O dono: audita o dinheiro. Superusuário porque é quem administra o sistema,
    # E no grupo "Dono" porque o grupo não pode nascer vazio — sem ninguém nele,
    # a apuração fica invisível até para quem mandou trancá-la.
    ("admin", "Dono", "da Casa", ("Dono",), True, ()),
    # O gestor: opera, autoriza exceção, fecha o dia. NÃO audita — ele conta às
    # cegas como todo mundo (ver docs/guides/rbac-personas.md).
    ("joyce", "Joyce", "", ("Gerente",), False, ("marina",)),
    # Loja: balcão e PDV.
    ("fran", "Fran", "", ("Caixa",), False, ("ana",)),
    # Produção: cozinha e fornadas.
    ("diofer", "Diofer", "", ("Cozinha",), False, ("joao",)),
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
            for username, first, last, nomes_de_grupo, superuser, absorve in CAST:
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
                self._emitir_cracha(user, username)

                herdadas, avisos = self._absorver(user, absorve)

                verbo = "criado" if criado else "atualizado"
                linha = f"  {username}: {verbo} → {', '.join(nomes_de_grupo)}"
                if herdadas:
                    linha += f" (herdou o histórico de {', '.join(herdadas)})"
                self.stdout.write(linha)
                # Os avisos saem DEPOIS da linha da pessoa. Antes eles eram
                # escritos de dentro do `_absorver`, ou seja, apareciam acima —
                # e quem lia atribuía a travessia à pessoa anterior da lista.
                for aviso in avisos:
                    self.stdout.write(aviso)

        self.stdout.write(self.style.SUCCESS(f"setup_operators: OK (PIN {DEV_PIN} para todos)"))
        self.stdout.write("  Crachás de dev (o código de barras é o próprio texto):")
        for username, *_ in CAST:
            self.stdout.write(f"    {username}: {dev_badge(username)}")

    def _emitir_cracha(self, user, username: str) -> None:
        """Grava o hash do crachá de dev, para a leitura ter o que casar.

        A máquina de ler crachá está pronta há tempo (captura no documento,
        janela de tempo, Enter consumido) — o que faltava era CRACHÁ. Sem token
        emitido, passar o leitor não acha ninguém, e a tela parece quebrada
        quando o que falta é o cadastro.
        """
        from shopman.doorman.models import PinCredential

        cred = PinCredential.objects.get(user=user)
        cred.set_badge(dev_badge(username))
        cred.save(update_fields=["badge_hash"])

    def _absorver(self, user, usernames: tuple[str, ...]) -> tuple[list[str], list[str]]:
        """A pessoa nova herda o histórico da conta antiga, que então some.

        O elenco antigo (`marina`, `ana`, `joao`) tinha permissões avulsas e
        nenhum grupo. Apagar direto jogaria fora o passado: turnos de caixa,
        linhas do livro, movimentos de estoque, fechamentos do dia — tudo
        aponta para o usuário que fez. Reatribuir preserva a trilha e é a
        associação honesta: quem era a gerente continua sendo a gerente.

        Genérico de propósito: percorre as relações que o Django conhece, em vez
        de uma lista escrita à mão que envelhece em silêncio quando alguém
        acrescenta um FK para `User`.

        ⚠️ É idempotente porque a conta antiga é APAGADA no fim: rodar de novo
        não acha ninguém para absorver.
        """
        from django.contrib.auth import get_user_model

        User = get_user_model()
        herdadas: list[str] = []
        avisos: list[str] = []

        for antigo_nome in usernames:
            antigo = User.objects.filter(username=antigo_nome).first()
            if antigo is None or antigo.pk == user.pk:
                continue

            for rel in User._meta.related_objects:
                campo = rel.field.name
                modelo = rel.related_model
                if rel.one_to_one:
                    # Credencial e vínculo de cliente são DA PESSOA, não do
                    # histórico: mover criaria duas para o mesmo dono (o O2O
                    # recusaria) e herdar PIN alheio seria pior ainda.
                    modelo.objects.filter(**{campo: antigo}).delete()
                    continue
                avisos.extend(self._reatribuir(modelo, campo, antigo, user))

            antigo.delete()
            herdadas.append(antigo_nome)

        return herdadas, avisos

    def _reatribuir(self, modelo, campo: str, antigo, novo) -> list[str]:
        """Troca o dono das linhas — inclusive nos livros IMUTÁVEIS.

        `stockman.Move` (e os livros que seguem o mesmo padrão) recusam
        `update()` de propósito: "para corrigir, crie um novo Move com delta
        inverso". A lei existe para impedir que alguém reescreva VALOR — e ela
        está certa.

        Aqui não se mexe em valor: troca-se a qual pessoa a linha aponta, porque
        as duas são a mesma pessoa e uma delas vai deixar de existir. A
        alternativa seria manter para sempre uma conta fantasma só para o FK ter
        onde apontar, que é pior: conta ativa sem grupo é acesso que ninguém
        explica.

        ⚠️ Só se faz isso porque este comando é de dev/staging e exige `--yes`.
        Em produção, identidade que operou o caixa **não** se reescreve — se um
        dia isto precisar rodar lá, o caminho é desativar a conta, não fundi-la.
        """
        from django.db.models import QuerySet

        # CONTAR ANTES. O `update()` do livro imutável levanta sem olhar se há
        # linha, então tentar-e-avisar anunciava travessia que nunca houve — o
        # log dizia "livro imutável reatribuído" para uma pessoa que herdou
        # zero lançamentos. Numa auditoria, isso é pior que não avisar.
        quantas = modelo.objects.filter(**{campo: antigo}).count()
        if not quantas:
            return []

        try:
            modelo.objects.filter(**{campo: antigo}).update(**{campo: novo})
            return []
        except ValueError:
            # O manager do modelo é que recusa; um QuerySet cru fala com a
            # tabela sem passar pela guarda. Explícito para o leitor saber que
            # a exceção foi lida e não engolida.
            QuerySet(model=modelo).filter(**{campo: antigo}).update(**{campo: novo})
            linhas = "linha" if quantas == 1 else "linhas"
            return [
                f"    ⚠️  {modelo._meta.label}.{campo}: {quantas} {linhas} "
                f"de livro imutável reatribuídas (dev/staging)"
            ]
