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

from django.core.management.base import BaseCommand, CommandError


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

        def _ver(app_label, *models):
            """Os ``view_<model>`` do Django — a permissão de ABRIR a tela no Admin.

            O Admin não é a superfície de operação (isso vive nos apps Nuxt), mas é
            onde se confere e se ajusta. E ele fala Django: quem decide se
            `/admin/offerman/product/` abre é ``offerman.view_product``, não uma
            permissão nossa de nome bonito. Enquanto nenhum grupo concedia esses
            ``view_*``, o Admin era, na prática, só-superusuário — o menu oferecia
            26 telas à Fran e as 26 respondiam 403.

            Sem ``models``, pega o app inteiro: escopo novo de configuração nasce
            alcançável por quem já alcança os outros, em vez de nascer 403.
            """
            from django.apps import apps as django_apps

            # A lista sai do REGISTRO de models, não de um `startswith("view_")`:
            # meia dúzia de permissões custom deste projeto se chamam `view_algo`
            # (`view_bi`, `view_production_reports`, `view_dayclosing_management`) e
            # não são a permissão de abrir uma tela. Varrer por prefixo as pegaria
            # junto, concedendo em silêncio o que alguém decidiu não conceder.
            nomes = models or tuple(m._meta.model_name for m in django_apps.get_app_config(app_label).get_models())
            codenames = [f"view_{m}" for m in nomes]
            found = list(Permission.objects.filter(content_type__app_label=app_label, codename__in=codenames))
            if len(found) != len(codenames):
                faltando = set(codenames) - {p.codename for p in found}
                raise CommandError(
                    f"`view_*` de {app_label} não existe(m): {sorted(faltando)} — rode `migrate` antes, "
                    "ou o model saiu e esta lista não acompanhou."
                )
            return found

        def _escrever(app_label, *models):
            """``add_`` e ``change_``. Apagar fica de fora de propósito: no Admin,
            remover linha é ação de dono, e quase tudo aqui tem estado em vez de
            sumiço (produto sai de vitrine, promoção expira, pedido cancela)."""
            codenames = [f"{verb}_{m}" for m in models for verb in ("add", "change")]
            found = list(Permission.objects.filter(content_type__app_label=app_label, codename__in=codenames))
            if len(found) != len(codenames):
                raise CommandError(f"add/change de {app_label}{list(models)} não existe(m) — rode `migrate` antes.")
            return found

        groups = {
            "Caixa": [
                shop_cash("operate_pos"),
                shop_shop("manage_orders"),
            ],
            "Cozinha": [
                # No Admin ele CONFERE o que fabrica — ficha técnica, ordem, insumo,
                # saldo, lote. Mexer acontece no app de Produção, que é onde a mão
                # está suja; aqui é a consulta de quem precisa lembrar do gramo.
                *_ver("craftsman"),
                *_ver("buyman"),
                *_ver("stockman"),
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
                # ── O que ela alcança no Admin ──────────────────────────────
                # A persona do Admin é ela. Ler tudo o que é operação e
                # configuração; escrever no que é do dia a dia (catálogo,
                # cliente, promoção, texto).
                #
                # ⚠️ Dinheiro fica de fora, e não é esquecimento: `payman`
                # (cobranças) e a apuração do turno são do Dono. É a mesma régua
                # do fechamento cego — ela opera, autoriza exceção e conta às
                # cegas; quem vê dinheiro é quem audita.
                *_ver("offerman"), *_escrever("offerman", "product", "collection", "listing"),
                shop_shop("manage_catalog"),
                *_ver("guestman"), *_escrever("guestman", "customer"),
                *_ver("customer_loyalty"),
                *_ver("storefront"),
                *_ver("craftsman"),
                *_ver("buyman"),
                *_ver("stockman"),
                *_ver("orderman"),
                *_ver("backstage"),
                # A configuração inteira se lê; muda o que é do turno dela.
                # Regra de preço continua atrás de `manage_rules` (WP-GAP-06):
                # ela executa expressão, e isso é portão de segurança.
                *_ver("shop"), *_escrever("shop", "promotion", "coupon", "omotenashicopy"),
                # O terminal do balcão ("Equipamentos") — ela cadastra a estação.
                *_ver("cashman", "terminal"), *_escrever("cashman", "terminal"),
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
                _perm("backstage", "biscenarioreport", "view_biscenarioreport"),
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
                # `manage_catalog`/`manage_rules` dizem o que ele pode MUDAR. Abrir
                # a tela é outra permissão — sem estas linhas o grupo inteiro
                # respondia 403 na porta, inclusive na de regras que ele governa.
                *_ver("offerman"), *_escrever("offerman", "product", "collection", "listing"),
                *_ver("shop", "ruleconfig", "promotion", "coupon"),
            ],
            # Portão de segurança do WP-GAP-06, não uma persona: `manage_rules` gateia
            # edição de RuleConfig, que executa expressão. O grupo nasce **sem membros**
            # de propósito — quem for mexer em regra se adiciona deliberadamente. Por
            # isso ele existe mesmo vazio: sem o grupo, não há onde se adicionar.
            "Rules Managers": [
                shop_rule("manage_rules"),
                # Idem: sem `view_ruleconfig` a permissão de editar regra não abria
                # a lista de regras. Portão que não abre porta nenhuma é decoração.
                *_ver("shop", "ruleconfig"),
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
                # Cobrança é dinheiro, e dinheiro é deste portão: Pix, cartão e o
                # que a maquininha respondeu se conferem aqui, não na tela de quem
                # opera o balcão (decisão do dono, 22/08/2026).
                *_ver("payman"),
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
