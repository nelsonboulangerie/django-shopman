"""Admin/Unfold integration guardrails for operational Backstage surfaces."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib import admin
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from shopman.craftsman import craft
from shopman.craftsman.contrib.admin_unfold import admin as craftsman_admin
from shopman.craftsman.contrib.admin_unfold.admin import (
    WORK_ORDER_DATE_FROM_PARAM,
    WORK_ORDER_DATE_TO_PARAM,
)
from shopman.craftsman.models import Recipe, RecipeItem, WorkOrder
from shopman.offerman.models import Product
from shopman.orderman.admin import OrderAdmin
from shopman.orderman.models import Order, OrderItem
from shopman.refs.models import Ref

from shopman.backstage.admin import navigation
from shopman.shop.models import Shop


class AdminNavigationTests(TestCase):
    def test_sidebar_prioritizes_live_operation_and_backoffice_tools(self) -> None:
        from django.test import override_settings

        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser("admin", "admin@example.com", "pw")

        # Pedidos, PDV e Produção são apps Nuxt headless (env-gated). O
        # Fechamento (antesala do PDV, WP-ADM-3) entra com deep-link;
        # "Produção ao vivo" (Produção, WP-ADM-7d) é o único item de produção
        # e carrega o badge de OPs iniciadas.
        with override_settings(
            SHOPMAN_ORDERS_BASE_URL="https://gestor.example.com",
            SHOPMAN_POS_BASE_URL="https://pos.example.com",
            SHOPMAN_PRODUCTION_BASE_URL="https://prod.example.com",
        ):
            groups = admin.site.get_sidebar_list(request)
        titles = [group["title"] for group in groups]

        # "Aplicativos": os itens abrem os apps do operador, FORA do Admin.
        # "Operação ao vivo" não dizia o que era nem para onde levava.
        self.assertEqual(titles[0], "Aplicativos")
        self.assertIn("Catálogo", titles)
        self.assertIn("Produção", titles)
        self.assertIn("Auditoria", titles)
        self.assertNotIn("Regras", titles)

        live = [item for item in groups[0]["items"] if item["has_permission"]]
        live_items = [item["title"] for item in live]
        self.assertEqual(live_items[:4], ["Pedidos", "Fechamento", "PDV", "Produção ao vivo"])
        self.assertNotIn("Produção", live_items)
        closing_item = next(item for item in live if item["title"] == "Fechamento")
        self.assertEqual(closing_item["link"], "https://pos.example.com/session/closing")
        producao_item = next(item for item in live if item["title"] == "Produção ao vivo")
        self.assertEqual(producao_item["link"], "https://prod.example.com")

        with override_settings(SHOPMAN_PRODUCTION_BASE_URL="https://prod.example.com"):
            raw_live = navigation.get_sidebar_navigation(request)[0]["items"]
        raw_producao = next(item for item in raw_live if item["title"] == "Produção ao vivo")
        self.assertEqual(
            raw_producao["badge"],
            "shopman.backstage.admin.navigation.badge_started_work_orders",
        )

    def test_pos_nav_item_hidden_without_url_shown_when_configured(self) -> None:
        """POS é Nuxt headless: sem SHOPMAN_POS_BASE_URL o item some (sem link morto);
        configurado, aponta para a superfície Nuxt."""
        from django.test import override_settings

        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser("posnav", "posnav@example.com", "pw")

        with override_settings(SHOPMAN_POS_BASE_URL=""):
            groups = admin.site.get_sidebar_list(request)
            live = {item["title"]: item for item in groups[0]["items"]}
            self.assertNotIn("PDV", live)

        with override_settings(
            SHOPMAN_POS_BASE_URL="https://pos.example.com",
            SHOPMAN_PRODUCTION_BASE_URL="",
        ):
            groups = admin.site.get_sidebar_list(request)
            live = {item["title"]: item for item in groups[0]["items"]}
            self.assertIn("PDV", live)
            self.assertEqual(live["PDV"]["link"], "https://pos.example.com")

        # WP-ADM-7d: sem base URL do Produção o grupo fica só com o que se cadastra
        # e se consulta; "Relatórios" (superfície Nuxt) é env-gated e some.
        production_group = next(group for group in groups if group["title"] == "Produção")
        production_items = [item["title"] for item in production_group["items"] if item["has_permission"]]
        self.assertNotIn("Relatórios", production_items)
        self.assertIn("Fichas técnicas", production_items)

        audit_group = next(group for group in groups if group["title"] == "Auditoria")
        audit_items = [item["title"] for item in audit_group["items"] if item["has_permission"]]
        self.assertIn("Cobranças", audit_items)

    def test_production_reports_nav_item_is_env_gated_to_producao(self) -> None:
        """WP-ADM-7d: "Relatórios" do grupo Produção aponta p/ o Produção
        (/reports) e some sem SHOPMAN_PRODUCTION_BASE_URL (sem link morto)."""
        from django.test import override_settings

        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser("prodnav", "prodnav@example.com", "pw")

        with override_settings(SHOPMAN_PRODUCTION_BASE_URL="https://prod.example.com"):
            groups = admin.site.get_sidebar_list(request)
        production_group = next(group for group in groups if group["title"] == "Produção")
        items = {item["title"]: item for item in production_group["items"] if item["has_permission"]}

        self.assertIn("Relatórios", items)
        self.assertEqual(items["Relatórios"]["link"], "https://prod.example.com/reports")

    def test_orders_and_kds_nav_items_are_env_gated(self) -> None:
        """Pedidos e KDS são apps Nuxt headless: sem base URL somem (sem link morto);
        configurados, apontam para a superfície Nuxt."""
        from django.test import override_settings

        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser("opsnav", "opsnav@example.com", "pw")

        with override_settings(SHOPMAN_ORDERS_BASE_URL="", SHOPMAN_KDS_BASE_URL=""):
            live = {item["title"]: item for item in admin.site.get_sidebar_list(request)[0]["items"]}
            self.assertNotIn("Pedidos", live)
            self.assertNotIn("KDS", live)

        with override_settings(
            SHOPMAN_ORDERS_BASE_URL="https://gestor.example.com",
            SHOPMAN_KDS_BASE_URL="https://kds.example.com",
        ):
            live = {item["title"]: item for item in admin.site.get_sidebar_list(request)[0]["items"]}
            self.assertEqual(live["Pedidos"]["link"], "https://gestor.example.com")
            self.assertEqual(live["KDS"]["link"], "https://kds.example.com")

    def test_configuration_left_the_operation_menu_for_a_destination(self) -> None:
        """Config e dado deixam de disputar o mesmo menu.

        O WP-2 juntou toda a config num grupo só e criou uma gaveta de vinte itens
        de sete assuntos. O WP-ADM-R3 quebrou a gaveta em grupos temáticos — melhor,
        mas ainda no mesmo plano dos dados, o que obrigava a decidir "isso é ajuste
        ou é dado?" ANTES de procurar. Para "Promoções" essa pergunta não tem
        resposta óbvia, e a dúvida custava a busca inteira.

        Agora o menu conta o que ESTÁ ACONTECENDO e a Configuração mostra o que dá
        para MUDAR — o padrão de Shopify, Stripe, Linear e Notion. O menu de
        operação não pode ter tela de ajuste de volta, e o caminho para a
        Configuração precisa existir.
        """
        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser("cfg", "cfg@example.com", "pw")

        groups = admin.site.get_sidebar_list(request)
        titles = {group["title"] for group in groups}
        all_items_by_title = {
            item["title"]: item for group in groups for item in group["items"]
        }
        all_items = set(all_items_by_title)

        # Configuração expande como os outros grupos: o menu tem UM comportamento.
        # Os subitens são os sete ESCOPOS, não as 33 telas — o Unfold só tem dois
        # níveis, e listar as telas aqui recriaria a gaveta, sem descrição nem busca.
        self.assertIn("Configuração", titles)
        config_group = next(g for g in groups if g["title"] == "Configuração")
        config_items = [i["title"] for i in config_group["items"] if i["has_permission"]]
        hub_url = reverse("admin_console_settings_hub")

        self.assertEqual(config_items[0], "Todos os ajustes")
        self.assertEqual(config_group["items"][0]["link"], hub_url)
        self.assertEqual(
            config_items[1:],
            [
                "A loja", "Como vendemos", "Como entregamos", "O que dizemos",
                "Produção e estoque", "Equipamentos", "Quem entra",
            ],
        )
        # Cada escopo é uma TELA própria, não âncora: âncora fazia os oito subitens
        # compartilharem caminho, o Unfold acendia todos e clicar não parecia navegar.
        for item in config_group["items"][1:]:
            self.assertNotIn("#", item["link"], item["link"])
            self.assertTrue(item["link"].startswith(hub_url), item["link"])
            self.assertNotEqual(item["link"], hub_url)

        # E nenhuma tela de ajuste sobrou solta no menu de operação.
        for gone in (
            "Loja e contato", "Marca e aparência", "Horários e operação", "Cardápio",
            "Pedidos e entrega", "Fidelidade", "PDV e alertas", "Integrações",
            "Canais", "Regras de preço", "Promoções", "Cupons", "Faixas de preço",
            "Zonas de entrega", "Faixas de distância", "Textos da interface",
            "Modelos de mensagem", "Estações KDS", "Terminais do PDV", "Usuários",
        ):
            self.assertNotIn(gone, all_items, f"{gone} deveria morar na Configuração")

    def test_settings_hub_groups_configuration_by_scope(self) -> None:
        """Dentro do destino, o eixo é ESCOPO — o que a loja é, como vende, como
        entrega, o que diz, o que fabrica, com que equipamento, quem entra. É o
        eixo que Stripe (Pessoal/Conta/Produto) e Linear (Account/Features/
        Administration/Teams) usam; agrupar por "ser config" não distingue nada,
        porque ali tudo é config."""
        from shopman.backstage.projections.settings_hub import build_settings_hub

        hub = build_settings_hub()
        group_titles = [group["title"] for group in hub["groups"]]

        self.assertEqual(
            group_titles,
            [
                "A loja",
                "Como vendemos",
                "Como entregamos",
                "O que dizemos",
                "Produção e estoque",
                "Equipamentos",
                "Quem entra",
            ],
        )

        # Todo cartão diz o que controla: uma grade de títulos sem texto é só um
        # menu deitado, e não resolve o "não sei se o que procuro está aqui".
        for group in hub["groups"]:
            for card in group["cards"]:
                self.assertTrue(card["description"].strip(), card["label"])

    def test_settings_hub_search_finds_a_screen_by_subject(self) -> None:
        """Busca por assunto, sem acento e sem saber o nome exato da tela."""
        from shopman.backstage.projections.settings_hub import build_settings_hub

        found = {
            card["label"]
            for group in build_settings_hub(q="producao")["groups"]
            for card in group["cards"]
        }

        self.assertIn("Produção", found)
        self.assertIn("Defeitos de fornada", found)
        self.assertNotIn("Cupons", found)

    def test_sidebar_badges_count_operational_attention(self) -> None:
        Order.objects.create(
            ref="NAV-NEW",
            channel_ref="web",
            session_key="nav-session",
            status=Order.Status.NEW,
            total_q=1000,
            data={"payment": {"method": "cash"}},
        )

        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser("admin2", "admin2@example.com", "pw")

        self.assertEqual(navigation.badge_new_orders(request), "1")

    def test_tabs_never_point_at_a_screen_the_menu_already_lists(self) -> None:
        """Aba e menu disputando a mesma tela quebram o "onde estou".

        O Unfold marca como ativo todo item do menu que participe do grupo de abas
        da página atual (`_get_is_tab_active`). Com Produtos, Coleções e Vitrines no
        menu E na mesma aba, os três acendiam juntos. A aba passa a servir só para a
        vizinhança que o menu NÃO mostra: hoje, os grupos que vivem na Configuração.
        """
        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser("tabs", "tabs@example.com", "pw")
        menu_paths = {
            item["link"].split("?")[0]
            for group in admin.site.get_sidebar_list(request)
            for item in group["items"]
        }

        for tab in settings.UNFOLD["TABS"]:
            for item in tab["items"]:
                self.assertNotIn(
                    str(item["link"]),
                    menu_paths,
                    f"{item['title']} está na aba E no menu: os dois vão acender juntos",
                )

    def test_production_operation_never_returns_to_tabs(self) -> None:
        """WP-ADM-7d: painel/planejamento/relatório de produção vivem no Produção."""
        tab_titles = [
            item["title"] for tab in settings.UNFOLD["TABS"] for item in tab["items"]
        ]
        for operational in ("Painel", "Planejamento", "Relatórios", "Pesagem"):
            self.assertNotIn(operational, tab_titles)
        self.assertEqual(str(WorkOrder._meta.verbose_name_plural), "ordens de produção")


# O console Admin/Unfold de produção (matriz, planejamento, painel, pesagem,
# compromissos e relatórios) foi removido no WP-ADM-7d: a superfície canônica
# é o Produção (surfaces/production-nuxt) via api/v1/backstage/production/*
# (paridade fechada no WP-ADM-7b). A cobertura vive em
# test_api_production_reports.py e nos testes da API de produção. O KPI de
# produção do dashboard saiu no WP-ADM-8 (landing de config/auditoria).


class OrderAdminSemanticsTests(TestCase):
    def test_order_admin_distinguishes_lines_from_units(self) -> None:
        order = Order.objects.create(
            ref="ADM-ORDER",
            channel_ref="web",
            session_key="adm-order-session",
            status=Order.Status.ACCEPTED,
            total_q=3000,
            data={"payment": {"method": "cash"}},
        )
        OrderItem.objects.create(
            order=order,
            line_id="1",
            sku="CIABATTA",
            name="Ciabatta",
            qty=3,
            unit_price_q=1000,
            line_total_q=3000,
        )
        OrderItem.objects.create(
            order=order,
            line_id="2",
            sku="BAGUETTE",
            name="Baguette",
            qty=10,
            unit_price_q=0,
            line_total_q=0,
        )

        model_admin = OrderAdmin(Order, admin.site)

        self.assertEqual(model_admin.items_count_display(order), "2")
        self.assertEqual(model_admin.units_count_display(order), "13")


class WorkOrderAdminSemanticsTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_superuser("wo-admin", "wo-admin@example.com", "pw")
        Shop.objects.create(name="Loja Operacional")
        self.client.force_login(self.user)

    def test_work_order_admin_defaults_to_today_range_filter(self) -> None:
        response = self.client.get(reverse("admin:craftsman_workorder_changelist"))

        self.assertEqual(response.status_code, 302)
        today = timezone.localdate().isoformat()
        self.assertIn(f"{WORK_ORDER_DATE_FROM_PARAM}={today}", response["Location"])
        self.assertIn(f"{WORK_ORDER_DATE_TO_PARAM}={today}", response["Location"])
        self.assertNotIn("target_date__year", response["Location"])

    def test_work_order_admin_keeps_focus_on_changelist(self) -> None:
        today = timezone.localdate().isoformat()

        response = self.client.get(
            reverse("admin:craftsman_workorder_changelist"),
            {
                WORK_ORDER_DATE_FROM_PARAM: today,
                WORK_ORDER_DATE_TO_PARAM: today,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Produção do dia")
        self.assertNotContains(response, "Todas as OPs do dia")
        self.assertNotContains(response, "Agenda vencida")

    def test_work_order_admin_navigation_uses_unfold_row_actions(self) -> None:
        model_admin = admin.site._registry[WorkOrder]

        self.assertNotIn("operation_link_display", model_admin.list_display)
        self.assertIn("production_board_row", model_admin.actions_row)
        # WP-ADM-7d: a visão de compromissos saiu com o console de produção;
        # os pedidos vinculados aparecem no board do Produção.
        self.assertNotIn("commitments_row", model_admin.actions_row)
        # Execução (concluir/anular) saiu do Admin: vive no Produção (WP-ADM-5).
        self.assertNotIn("close_wo_row", model_admin.actions_row)
        self.assertNotIn("void_wo_row", model_admin.actions_row)
        self.assertFalse(model_admin.actions)

    def test_work_order_admin_expandable_row_shows_event_history(self) -> None:
        model_admin = admin.site._registry[WorkOrder]
        section = model_admin.list_sections[0]

        self.assertEqual(section.related_name, "events")
        self.assertEqual(str(section.verbose_name), "Histórico operacional")
        self.assertEqual(section.created_at.short_description, "Registrado em")

    def test_work_order_admin_displays_operator_quantities_without_decimal_noise(self) -> None:
        recipe = Recipe.objects.create(
            ref="wo-qty-ciabatta",
            name="Ciabatta",
            output_sku="CIABATTA",
            batch_size=10,
        )
        work_order = craft.plan(recipe, Decimal("14.000"), date=date.today())
        craft.finish(work_order, finished=Decimal("12.000"), expected_rev=0)
        work_order.refresh_from_db()
        model_admin = admin.site._registry[WorkOrder]

        planned = str(model_admin.planned_display(work_order))
        produced = str(model_admin.produced_display(work_order))
        loss = str(model_admin.loss_display(work_order))

        self.assertIn("14 un.", planned)
        self.assertIn("12 un.", produced)
        self.assertIn("2 un.", loss)
        self.assertNotIn("<span", planned)
        self.assertNotIn("14.00", planned)
        self.assertNotIn("12.00", produced)

    def test_work_order_admin_commitments_show_only_committed_units(self) -> None:
        recipe = Recipe.objects.create(
            ref="wo-commit-ciabatta",
            name="Ciabatta",
            output_sku="CIABATTA",
            batch_size=10,
        )
        work_order = craft.plan(recipe, Decimal("14.000"), date=date.today())
        model_admin = admin.site._registry[WorkOrder]

        with (
            patch.object(craftsman_admin, "_committed_order_refs", return_value=("O-1", "O-2")),
            patch.object(craftsman_admin, "_committed_qty_for_work_order", return_value=Decimal("14.000")),
        ):
            commitment = str(model_admin.commitments_display(work_order))

        self.assertIn("14 un.", commitment)
        self.assertNotIn("ped.", commitment)
        self.assertNotIn("<span", commitment)


class RecipeAdminSemanticsTests(TestCase):
    def test_recipe_admin_edits_ingredients_as_canonical_tabular_inline(self) -> None:
        Product.objects.create(sku="FARINHA-T65", name="Farinha T65", unit="kg")
        recipe = Recipe.objects.create(
            ref="massa-base",
            name="Massa Base",
            output_sku="MASSA-BASE",
            batch_size=10,
        )
        model_admin = admin.site._registry[Recipe]
        inline = model_admin.inlines[0]
        form = craftsman_admin.RecipeItemInlineForm()
        recipe_form = craftsman_admin.RecipeAdminForm()
        sku_choices = dict(form.fields["input_sku"].choices)

        self.assertEqual(inline, craftsman_admin.RecipeItemInline)
        self.assertEqual(str(inline.verbose_name_plural), "Ingredientes")
        self.assertEqual(
            tuple(inline.fields),
            ("sort_order", "input_sku", "quantity", "unit", "is_optional", "diet", "allergens_text"),
        )
        self.assertEqual(inline.ordering_field, "sort_order")
        self.assertTrue(inline.hide_ordering_field)
        self.assertIsInstance(form.fields["input_sku"].widget, craftsman_admin.UnfoldAdminSelect2Widget)
        self.assertIsInstance(form.fields["unit"].widget, craftsman_admin.UnfoldAdminSelectWidget)
        self.assertIsInstance(recipe_form.fields["output_sku"].widget, craftsman_admin.UnfoldAdminSelect2Widget)
        self.assertEqual(str(Recipe._meta.verbose_name), "ficha técnica")
        self.assertEqual(str(Recipe._meta.verbose_name_plural), "fichas técnicas")
        self.assertEqual(str(Recipe._meta.get_field("output_sku").verbose_name), "SKU produzido")
        self.assertEqual(str(recipe_form.fields["output_sku"].label), "SKU produzido")
        self.assertEqual(str(recipe_form.fields["batch_size"].label), "Rendimento base")
        self.assertEqual(str(Recipe._meta.get_field("batch_size").verbose_name), "Rendimento base")
        self.assertIn("ficha técnica base", str(Recipe._meta.get_field("batch_size").help_text))
        flattened_fieldsets = _flatten_fieldsets(model_admin.fieldsets)
        self.assertIn("steps_text", flattened_fieldsets)
        self.assertIn("max_started_minutes", flattened_fieldsets)
        self.assertIn("capacity_per_day", flattened_fieldsets)
        self.assertIn("requires_batch_tracking", flattened_fieldsets)
        self.assertNotIn("steps", flattened_fieldsets)
        self.assertNotIn("meta", flattened_fieldsets)
        self.assertIn("FARINHA-T65", sku_choices)
        self.assertIn("MASSA-BASE", sku_choices)
        self.assertIn(("kg", "kg"), RecipeItem._meta.get_field("unit").choices)
        self.assertNotIn(("zufts", "zufts"), RecipeItem._meta.get_field("unit").choices)

        item = RecipeItem(recipe=recipe, input_sku="FARINHA-T65", quantity=Decimal("1"), unit="zufts")
        with self.assertRaises(ValidationError):
            item.full_clean()

        mismatched = RecipeItem(recipe=recipe, input_sku="FARINHA-T65", quantity=Decimal("100"), unit="g")
        with self.assertRaises(ValidationError):
            mismatched.full_clean()

    def test_recipe_admin_maps_operational_fields_to_structured_recipe_data(self) -> None:
        Product.objects.create(sku="CIABATTA", name="Ciabatta", unit="un")

        form = craftsman_admin.RecipeAdminForm(data={
            "ref": "ciabatta-v1",
            "name": "Ciabatta",
            "is_active": "on",
            "output_sku": "CIABATTA",
            "batch_size": "12",
            "steps_text": "Mistura\nModelagem\nForno",
            "max_started_minutes": "90",
            "capacity_per_day": "120",
            "requires_batch_tracking": "on",
            "shelf_life_days": "1",
        })

        self.assertTrue(form.is_valid(), form.errors)
        recipe = form.save()

        self.assertEqual(recipe.steps, ["Mistura", "Modelagem", "Forno"])
        self.assertEqual(recipe.meta["max_started_minutes"], 90)
        self.assertEqual(recipe.meta["capacity_per_day"], "120")
        self.assertEqual(recipe.meta["requires_batch_tracking"], True)
        self.assertEqual(recipe.meta["shelf_life_days"], 1)


def test_legacy_admin_operational_templates_removed():
    root = Path(__file__).resolve().parents[3]

    assert not (root / "shopman/shop/templates/admin/shop/production.html").exists()
    assert not (root / "shopman/shop/templates/admin/shop/closing.html").exists()


def _flatten_fieldsets(fieldsets) -> list[str]:
    result: list[str] = []
    for _, options in fieldsets:
        for field in options.get("fields", ()):
            if isinstance(field, (tuple, list)):
                result.extend(field)
            else:
                result.append(field)
    return result


class CustomerBulkTaggingTests(TestCase):
    """Etiquetar em massa na changelist de clientes.

    ⚠️ Sem isto, etiquetar é um cliente por vez — e o público por etiqueta só vale a pena
    quando dá para marcar trinta corredores de uma vez. Recurso com custo de uso que ninguém
    paga fica com etiqueta vazia, que é o estado que a contagem no seletor do Marketing
    denuncia ("corredores (ninguém)").
    """

    def setUp(self) -> None:
        # A `Shop` é exigência do OnboardingMiddleware: sem ela o Admin desvia e o teste
        # vê 404 em vez da tela.
        Shop.objects.create(name="Loja")
        self._phone_seq = 0
        self.user = User.objects.create_superuser("chefe", "chefe@example.com", "pw")
        self.client.force_login(self.user)
        self.url = reverse("admin:guestman_customer_changelist")

    def _customers(self, *refs):
        """⚠️ Telefone único por chamada: é ele a identidade, e dois iguais dão UNIQUE.

        Contador de instância, não `hash(ref)`: o hash de str é randomizado por processo
        (PYTHONHASHSEED), então um teste que passa hoje colidiria num run futuro — falha
        intermitente é pior que falha.
        """
        from shopman.guestman.models import Customer

        made = []
        for ref in refs:
            self._phone_seq += 1
            made.append(Customer.objects.create(
                ref=ref, first_name=ref, phone=f"+554398{self._phone_seq:07d}",
            ))
        return made

    def _act(self, customers, **extra):
        payload = {
            "action": "tag_selected",
            admin.helpers.ACTION_CHECKBOX_NAME: [str(c.pk) for c in customers],
            **extra,
        }
        return self.client.post(self.url, payload, follow=True)

    def test_the_action_asks_before_it_writes(self) -> None:
        """Primeiro POST abre a página de confirmação; nada é etiquetado ainda.

        ⚠️ E abre LIMPA. A primeira versão vinculava o form ao POST da seleção — que traz os
        checkboxes e nenhuma etiqueta — então a tela nascia em vermelho, "este campo é
        obrigatório", antes de a pessoa digitar. Ralhar com quem não fez nada ensina a
        ignorar o vermelho, e aí o vermelho que importa também passa batido. Este teste só
        verificava que a página renderizava, e por isso não pegou.
        """
        customers = self._customers("CLI-A1", "CLI-A2")

        response = self._act(customers)

        self.assertContains(response, "Etiquetar clientes")
        self.assertNotContains(response, "obrigatório")
        self.assertEqual(list(customers[0].tags.all()), [])

    def test_it_tags_every_selected_customer(self) -> None:
        customers = self._customers("CLI-B1", "CLI-B2")

        self._act(customers, _tag_confirm="1", tags="corredores, vizinho", mode="add")

        for customer in customers:
            self.assertEqual(
                sorted(customer.tags.values_list("name", flat=True)),
                ["corredores", "vizinho"],
            )

    def test_it_also_removes(self) -> None:
        """Tirar etiqueta errada de trinta pessoas tem de ser tão fácil quanto pôr."""
        (customer,) = self._customers("CLI-C1")
        customer.tags.add("corredores", "vizinho")

        self._act([customer], _tag_confirm="1", tags="corredores", mode="remove")

        self.assertEqual(list(customer.tags.values_list("name", flat=True)), ["vizinho"])

    def test_the_comma_is_the_separator_not_the_space(self) -> None:
        """⚠️ "sem glúten" é UMA etiqueta.

        O `parse_tags` do taggit quebra em espaço quando não há vírgula, e viraria "sem" e
        "glúten" — duas etiquetas que não significam nada. O separador desta tela é a
        vírgula, e é isso que o placeholder mostra.
        """
        (customer,) = self._customers("CLI-D1")

        self._act([customer], _tag_confirm="1", tags="sem glúten", mode="add")

        self.assertEqual(list(customer.tags.values_list("name", flat=True)), ["sem glúten"])

    def test_an_empty_tag_list_writes_nothing_and_says_so(self) -> None:
        (customer,) = self._customers("CLI-E1")

        response = self._act([customer], _tag_confirm="1", tags="  ,  ", mode="add")

        self.assertEqual(list(customer.tags.all()), [])
        self.assertContains(response, "ao menos uma etiqueta")

    def test_it_shows_which_tags_already_exist(self) -> None:
        """Reusar em vez de reinventar: sem a lista nascem "corredores" e "corredor"."""
        (other,) = self._customers("CLI-F0")
        other.tags.add("corredores")
        (customer,) = self._customers("CLI-F1")

        response = self._act([customer])

        self.assertContains(response, "corredores")

    def test_a_customer_tag_never_reaches_the_product_keywords(self) -> None:
        """A fronteira do namespace, exercitada pela tela e não só pelo model."""
        from taggit.models import Tag

        (customer,) = self._customers("CLI-G1")

        self._act([customer], _tag_confirm="1", tags="integral", mode="add")

        self.assertEqual(Tag.objects.filter(name="integral").count(), 0)


class RefBulkRenameTests(TestCase):
    """Renomear valores de referências em massa pela changelist de refs.

    A ação já existia sem teste de tela: só o `RefBulk.rename` era exercitado, e a página
    intermediária — que é onde a pessoa lê e decide — não era vista por ninguém.
    """

    def setUp(self) -> None:
        # A `Shop` é exigência do OnboardingMiddleware: sem ela o Admin desvia e o teste
        # vê 404 em vez da tela.
        Shop.objects.create(name="Loja")
        self.user = User.objects.create_superuser("chefe-refs", "refs@example.com", "pw")
        self.client.force_login(self.user)
        self.url = reverse("admin:refs_ref_changelist")

    def _refs(self, value, *target_ids):
        return [
            Ref.objects.create(
                ref_type="SKU",
                value=value,
                target_type="offerman.Product",
                target_id=target_id,
            )
            for target_id in target_ids
        ]

    def _act(self, refs, **extra):
        payload = {
            "action": "rename_value_action",
            admin.helpers.ACTION_CHECKBOX_NAME: [str(ref.pk) for ref in refs],
            **extra,
        }
        return self.client.post(self.url, payload, follow=True)

    def test_the_action_asks_before_it_writes(self) -> None:
        """Primeiro POST abre a página de confirmação — e abre LIMPA.

        ⚠️ O form era vinculado ao POST da SELEÇÃO, que traz os checkboxes e nenhum valor
        novo, então a tela nascia em vermelho ("este campo é obrigatório") antes de a pessoa
        digitar. Ralhar com quem não fez nada ensina o operador a ignorar o vermelho, e aí o
        vermelho que importa também passa batido. Sem a asserção de tela limpa, o teste
        passa com a tela em vermelho — foi exatamente o que aconteceu.
        """
        refs = self._refs("CROISSANT", "1", "2")

        response = self._act(refs)

        self.assertContains(response, "Renomear o valor de")
        self.assertNotContains(response, "obrigatório")
        # O título da tela é o mesmo que a aba mostra — um dono só, e em português.
        self.assertNotContains(response, "Rename ref values")
        # Independente de locale: o form da primeira renderização nem sequer é vinculado.
        self.assertFalse(response.context["form"].is_bound)
        self.assertEqual(Ref.objects.filter(value="CROISSANT").count(), 2)

    def test_it_renames_every_selected_ref(self) -> None:
        refs = self._refs("CROISSANT", "1", "2")

        self._act(refs, _rename_confirm="1", new_value="CROISSANT-FR")

        self.assertEqual(Ref.objects.filter(value="CROISSANT-FR").count(), 2)
        self.assertEqual(Ref.objects.filter(value="CROISSANT").count(), 0)

    def test_confirming_without_a_value_writes_nothing_and_says_so(self) -> None:
        """O vermelho continua existindo — só que agora quando é merecido."""
        refs = self._refs("BAGUETE", "3")

        response = self._act(refs, _rename_confirm="1", new_value="   ")

        self.assertEqual(Ref.objects.filter(value="BAGUETE").count(), 1)
        self.assertContains(response, "não pode ser vazio")
