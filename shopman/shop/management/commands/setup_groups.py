"""Os grupos RBAC do deployment — este comando é o dono único deles.

Antes, quatro grupos nasciam aqui e o quinto ("Rules Managers") nascia numa data
migration. Duas fontes para a mesma pergunta, e a pior das duas ganhava: o job de
release do deploy roda `migrate`, **não** roda este comando, então os grupos existiam
por acidente de história e este arquivo — o que tem teste de paridade — nunca rodava
em produção. Ao resetar as migrações isso viraria perda silenciosa de RBAC.

Agora: grupo é dado de deployment, mora aqui, e o release job chama
`migrate && setup_groups`. Idempotente por construção (`get_or_create` + `add`).

Ver `tests/test_group_permission_parity.py`, que falha se uma permission gateando
superfície não for concedida a ninguém — o guarda contra "permission existe, e ninguém
a tem, e o app fica inalcançável".
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Cria/atualiza os grupos do deployment: Caixa, Cozinha, Gerente, Admin de Catálogo, Rules Managers."

    def handle(self, *args, **options):
        from django.contrib.auth.models import Group, Permission
        from django.contrib.contenttypes.models import ContentType

        def _perm(app_label, model, codename):
            ct, _ = ContentType.objects.get_or_create(app_label=app_label, model=model)
            p, _ = Permission.objects.get_or_create(content_type=ct, codename=codename)
            return p

        def shop_shop(c):
            return _perm("shop", "shop", c)

        def shop_kdst(c):
            return _perm("backstage", "kdsticket", c)

        def shop_cash(c):
            return _perm("cashman", "shift", c)

        def shop_dclo(c):
            return _perm("backstage", "dayclosing", c)

        def shop_rule(c):
            return _perm("shop", "ruleconfig", c)

        groups = {
            "Caixa": [
                shop_cash("operate_pos"),
                shop_shop("manage_orders"),
            ],
            "Cozinha": [
                shop_kdst("operate_kds"),
                shop_dclo("operate_production"),
                shop_shop("manage_production"),
                shop_shop("view_production_planned"),
                shop_shop("edit_production_planned"),
                shop_shop("view_production_started"),
                shop_shop("edit_production_started"),
                shop_shop("view_production_finished"),
                shop_shop("edit_production_finished"),
            ],
            "Gerente": [
                shop_shop("manage_orders"),
                # Campanha (surfaces/marketing-nuxt): publicar em nome da marca é
                # decisão de gestão. Sem esta linha a permissão existe mas ninguém
                # a tem, e o app fica inalcançável.
                shop_shop("manage_campaigns"),
                shop_cash("operate_pos"),
                shop_cash("adjust_shift"),
                shop_cash("manage_operators"),
                shop_dclo("perform_closing"),
                shop_dclo("operate_production"),
                # B.I. (ADR-021): leitura analítica cross-suite é persona de gestão.
                shop_dclo("view_bi"),
                # …e o que alimenta o B.I. (lotes de importação, vendas históricas)
                # se lê no Admin com a mesma persona: trilha, somente leitura.
                _perm("backstage", "importbatch", "view_importbatch"),
                _perm("backstage", "historicalsale", "view_historicalsale"),
                _perm("backstage", "dailysalesfact", "view_dailysalesfact"),
                # …e ajustam a régua dos alarmes do B.I.; o disparo só se lê.
                *[_perm("backstage", "bialertrule", f"{verb}_bialertrule") for verb in ("view", "add", "change")],
                _perm("backstage", "bialertevent", "view_bialertevent"),
                # …e curam os de-paras (a máquina propõe, o gestor confirma). Sem
                # apagar: rejeitar é estado, e a trilha de quem confirmou fica.
                *[
                    _perm("backstage", model, f"{verb}_{model}")
                    for model in ("productalias", "categoryalias", "paymentmethodalias")
                    for verb in ("view", "add", "change")
                ],
                shop_shop("view_reports"),
                shop_shop("manage_customers"),
                shop_shop("view_production_suggested"),
                shop_shop("edit_production_suggested"),
                shop_shop("view_production_planned"),
                shop_shop("edit_production_planned"),
                shop_shop("view_production_started"),
                shop_shop("edit_production_started"),
                shop_shop("view_production_finished"),
                shop_shop("edit_production_finished"),
                shop_shop("view_production_unsold"),
                shop_shop("edit_production_unsold"),
            ],
            "Admin de Catálogo": [
                shop_shop("manage_catalog"),
                shop_rule("manage_rules"),
            ],
            # Portão de segurança do WP-GAP-06, não uma persona: `manage_rules` gateia
            # edição de RuleConfig, que executa expressão. O grupo nasce **sem membros**
            # de propósito — quem for mexer em regra se adiciona deliberadamente. Por
            # isso ele existe mesmo vazio: sem o grupo, não há onde se adicionar.
            "Rules Managers": [
                shop_rule("manage_rules"),
            ],
            # Mesmo espírito do grupo acima: um PORTÃO, não uma persona.
            #
            # `audit_shift` ("esperado, contado, diferença") existia desde o
            # começo do caixa e nenhum grupo a concedia — ela só chegava a um
            # superusuário, ou a quem alguém lembrasse de marcar na mão. Uma
            # permissão sem lugar onde se conceder é uma permissão que ninguém
            # administra: some do Admin e reaparece como "por que não consigo
            # ver isso?" seis meses depois.
            #
            # O grupo é DELIBERADAMENTE só o financeiro. Quem audita e também
            # opera entra em "Dono" **e** "Gerente" — permissões somam, e
            # separá-las deixa a pergunta "quem vê dinheiro?" com uma resposta
            # só, legível numa tela do Admin.
            #
            # ⚠️ O `Gerente` NÃO entra aqui, e não é esquecimento: ele opera,
            # autoriza exceção e fecha o turno contando às cegas. Quem sabe o
            # esperado não conta às cegas — confere um gabarito.
            "Dono": [
                shop_cash("audit_shift"),
            ],
        }

        for name, perms in groups.items():
            group, created = Group.objects.get_or_create(name=name)
            for perm in perms:
                group.permissions.add(perm)
            verb = "criado" if created else "atualizado"
            perm_count = len(perms)
            self.stdout.write(f"  {name}: {verb} ({perm_count} permissões)")

        self.stdout.write(self.style.SUCCESS("setup_groups: OK"))
