"""
Seed de produção — Nelson Boulangerie.

Popula loja (shop), catálogo (offerman), estoque (stockman), receitas (craftsman),
clientes (customers), canais (orderman) e pedidos com dados da Nelson.

Uso:
    python manage.py seed          # seed normal
    python manage.py seed --flush  # apaga tudo e recria

IMPORTANTE — Não-determinismo deliberado:
    Este seed usa random.choice, uuid4 e now() intencionalmente para gerar dados
    realistas a cada execução. Não é adequado como fixture de testes. Para testes
    determinísticos use TestCase com fixtures ou factories dedicadas.
"""
from __future__ import annotations

import os
import random
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from shopman.craftsman.models import Recipe, RecipeItem, WorkOrder, WorkOrderItem
from shopman.guestman.models import (
    ContactPoint,
    Customer,
    CustomerAddress,
    CustomerTag,
    PriceTier,
)
from shopman.offerman.models import (
    AvailabilityPolicy,
    Collection,
    CollectionItem,
    Listing,
    ListingItem,
    Product,
    ProductComponent,
)
from shopman.orderman.ids import generate_order_ref, generate_session_key
from shopman.orderman.models import (
    Directive,
    Fulfillment,
    FulfillmentItem,
    IdempotencyKey,
    Order,
    OrderEvent,
    OrderItem,
    Session,
    SessionItem,
)
from shopman.payman.models import PaymentIntent, PaymentTransaction
from shopman.stockman import stock
from shopman.stockman.models import Position, PositionKind, StockAlert

from shopman.backstage.models import (
    DayClosing,
    DayContext,
    KDSInstance,
    OperationArea,
    OperationChecklistRun,
    OperationChecklistTemplate,
    OperationChecklistTemplateTask,
    OperationEvidence,
    OperationMoment,
    OperationTaskRun,
    OperationTaskTemplate,
    OperatorAlert,
    POSTab,
)
from shopman.backstage.services.operations import (
    complete_checklist_run,
    complete_task_run,
    start_checklist_run,
    supervise_task_run,
)
from shopman.shop.management.commands import setup_operators
from shopman.shop.models import (
    Announcement,
    AnnouncementTemplate,
    Campaign,
    Channel,
    Coupon,
    OmotenashiCopy,
    Promotion,
    RuleConfig,
    Shop,
)
from shopman.shop.services.dietary_from_recipe import aggregate_dietary_from_recipe
from shopman.shop.services.nutrition_from_recipe import fill_nutrition_from_recipe


class Command(BaseCommand):
    help = "Popula o banco com dados de produção da Nelson Boulangerie"

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Apaga todos os dados antes de popular",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Permite --flush mesmo em produção (SHOPMAN_ENVIRONMENT=production).",
        )
        parser.add_argument(
            "--profile",
            choices=["demo", "qa"],
            default="demo",
            help=(
                "Perfil de dados dinâmicos. 'demo' (padrão) = histórico realista/aleatório "
                "de 35 dias, bom para telas vivas. 'qa' = conjunto determinístico com "
                "cenários nomeados garantidos (refs previsíveis QA-*), datas relativas a "
                "localdate(). A base estática (catálogo, canais, receitas, operadores) é "
                "idêntica nos dois. Ver docs/reference/qa-seed-scenarios.md."
            ),
        )

    def handle(self, *args, **options):
        from django.conf import settings
        from django.core.management.base import CommandError

        # Guard destrutivo: --flush apaga TUDO. Em produção, exige --force explícito
        # para não zerar a loja num comando distraído. Staging/dev seguem livres.
        if options["flush"] and not options["force"]:
            environment = str(getattr(settings, "SHOPMAN_ENVIRONMENT", "") or "").lower()
            if environment == "production":
                raise CommandError(
                    "Recusando `seed --flush` em produção (SHOPMAN_ENVIRONMENT=production): "
                    "isto apagaria TODOS os dados da loja. Se é mesmo o que você quer, "
                    "repita com --force."
                )

        # Dado sintético nunca notifica gente de verdade — em NENHUM ambiente.
        # (O staging roda DEBUG=False com credenciais reais; sem isto, as
        # directives de notificação dos pedidos seedados disparariam SMS.)
        from shopman.shop.adapters._external import suppress

        suppress("seed")

        # Perfil de dados dinâmicos. A base estática é idêntica; só os seeders
        # dinâmicos (pedidos, produção, comandas, caixa) divergem no branch abaixo.
        self.profile = options["profile"]

        # Determinismo do perfil qa: semente fixa do RNG ANTES de qualquer seeder,
        # para que a matriz de produção (jitter em _seed_recipes) e qualquer sorteio
        # da base saiam idênticos a cada `seed --flush --profile qa`. Os cenários
        # nomeados (QA-*) já têm refs literais, então não dependem disto — mas o RNG
        # semeado garante idempotência ampla. (secrets.* — refs de Order/Session —
        # não é semeável; por isso os cenários qa usam refs explícitos.)
        if self.profile == "qa":
            random.seed(20260713)

        admin_password = self._resolve_admin_password()

        if options["flush"]:
            self._flush()

        self.stdout.write(self.style.MIGRATE_HEADING("\n🥐 Populando Nelson Boulangerie...\n"))

        self._create_superuser(admin_password)
        self._seed_operators()
        self._seed_shop()
        self._seed_delivery_distance_bands()
        self._seed_delivery_zones()
        products = self._seed_catalog()
        positions = self._seed_positions()
        self._seed_stock(products, positions)
        self._seed_recipes()
        self._assert_catalog_remote_purchase_data()
        customers = self._seed_customers()
        self._seed_addresses(customers)
        channels = self._seed_channels()
        self._seed_display_channels()
        self._assert_storefront_products_orderable()
        self._seed_kds()

        # ── Fase dinâmica: diverge por perfil ──────────────────────────────
        # Base estática acima é idêntica nos dois perfis. Só pedidos, produção
        # operacional, comandas, caixa e alertas divergem.
        if self.profile == "qa":
            self._seed_qa_dynamic(products, customers, channels, positions)
        else:
            self._seed_demo_dynamic(products, customers, channels, positions)

        self.stdout.write(self.style.SUCCESS("\n✅ Seed Nelson completo!\n"))

    def _seed_demo_dynamic(self, products, customers, channels, positions):
        """Perfil demo: histórico realista/aleatório de 35 dias + board vivo.

        Comportamento histórico do seed — bom para telas "vivas" e apresentação.
        Ordem e chamadas preservadas byte-a-byte (sem regressão de demo).
        """
        self._seed_pos_tabs()
        self._seed_orders(products, customers, channels)
        self._seed_security_reliability_edges(products, customers, channels)
        self._seed_fiscal_example()
        self._seed_sessions(channels)
        self._seed_stock_alerts(products, positions)
        self._seed_operator_alerts()
        self._seed_promotions()
        self._seed_payments()
        self._seed_fulfillments()
        self._seed_directives()
        self._seed_loyalty(customers)
        # ⚠️ DEPOIS dos pedidos, de propósito: o insight é DERIVADO do histórico. Sem esta
        # chamada, o seed criava 1.169 pedidos e nenhum `CustomerInsight` — RFM dizia "lost"
        # para todo mundo, churn ficava no default e TODO público comportamental do Marketing
        # (campeões, em risco, recompra, favoritos) resolvia zero. A campanha alcançaria
        # ninguém e ninguém saberia por quê.
        self._seed_customer_insights()
        self._seed_campaigns()
        self._seed_notification_templates()
        self._seed_rule_configs()
        self._seed_omotenashi_copy()
        self._seed_day_closing()
        self._seed_cash_register()
        self._seed_operation_checklists()

        # B.I.: sem movimento de prateleira o painel de abastecimento nasce vazio.
        self._seed_bi_history(products, positions)

    def _seed_qa_dynamic(self, products, customers, channels, positions):
        """Perfil qa: conjunto determinístico com cenários nomeados garantidos.

        Cada cenário nasce com ref previsível (QA-*) e datas relativas a
        localdate(), para que testes/QA ancorem sem criar dado à mão. Idempotente:
        ``seed --flush --profile qa`` duas vezes produz o mesmo conjunto de refs.
        Ver docs/reference/qa-seed-scenarios.md.
        """
        # Config estática compartilhada com o demo (independente de pedidos): mesma
        # chamada, mesmo resultado — só não é "dinâmica" no sentido de aleatória.
        self._seed_stock_alerts(products, positions)
        self._seed_promotions()
        self._seed_campaigns()
        self._seed_notification_templates()
        self._seed_rule_configs()
        self._seed_omotenashi_copy()
        self._seed_loyalty(customers)
        self._seed_operation_checklists()

        # Cenários nomeados determinísticos (Fase 2 do SEED-DATA-QUALITY-PLAN).
        self._seed_qa_orders(products, customers, channels)
        self._seed_production_demand_history(products, channels, timezone.now())
        self._seed_qa_production_stuck_batch()
        self._seed_qa_pos_tabs()

        # Caixa/fechamento já são determinísticos e datados por localdate() — reuso.
        self._seed_cash_register()   # 1 turno aberto (hoje) + 1 fechado c/ divergência (ontem)
        self._seed_day_closing()

        # Comandas abertas (uma delas na tab 00001007 = comanda POS aberta com itens).
        self._seed_sessions(channels)

        # Attachers genéricos que operam sobre os pedidos já criados. Cada um filtra
        # por status e pula pedidos que já têm o artefato — então respeitam os estados
        # específicos dos cenários qa (pending fica pending, refunded fica refunded).
        self._seed_operator_alerts()
        self._seed_payments()
        self._seed_fulfillments()
        self._seed_directives()
        self._seed_fiscal_example()

        # Cenários de DISPONIBILIDADE da vitrine (cliente): roda por último, depois
        # de todo estoque/produção, para dirigir SKUs reais a cada estado da loja.
        self._seed_qa_storefront_availability(positions)

        # B.I.: sem movimento de prateleira o painel de abastecimento nasce
        # vazio. Vai depois da vitrine para não disputar os quants dela.
        self._seed_bi_history(products, positions)

    # SKUs canônicos de cada estado de vitrine no perfil qa (datas relativas).
    QA_STOREFRONT_STATES = {
        "sold_out": "KP",      # esgotado + "me avise" (vendável, sem plano)
        "low_stock": "ME",    # últimas unidades (≤ limiar)
        "planned": "PU",          # lista de espera / previsto (sem pronto, com plano)
        "paused": "TJ",       # pausado pelo operador (is_sellable=False)
    }

    def _seed_qa_storefront_availability(self, positions):
        """Deixa 4 SKUs reais em cada estado de disponibilidade da LOJA, para QA/
        testes da vitrine do cliente (o resto continua ``available``). Determinístico.
        """
        from shopman.offerman.models import Product
        from shopman.stockman.models import Quant

        vitrine = positions["vitrine"]
        today = timezone.localdate()

        def _zero_all(sku: str) -> None:
            # Zera TODO estoque de vitrine do SKU (pronto e planejado) — para o
            # estado nascer limpo, sem quant residual da produção de hoje/futura.
            for q in Quant.objects.filter(sku=sku, position=vitrine):
                if (q._quantity or 0) > 0:
                    stock.adjust(q, Decimal("0"), reason=f"QA vitrine {sku}")

        s = self.QA_STOREFRONT_STATES
        # 1) Esgotado → "me avise": sem pronto, sem plano.
        _zero_all(s["sold_out"])
        # 2) Últimas unidades: pronto = 2 (limiar padrão = 5).
        _zero_all(s["low_stock"])
        stock.receive(Decimal("2"), sku=s["low_stock"], position=vitrine,
                      reason=f"QA vitrine {s['low_stock']}: últimas unidades")
        # 3) Lista de espera / previsto: sem pronto, mas produção planejada amanhã.
        _zero_all(s["planned"])
        stock.receive(Decimal("10"), sku=s["planned"], position=vitrine,
                      target_date=today + timedelta(days=1),
                      reason=f"QA vitrine {s['planned']}: planejado")
        # 4) Pausado pelo operador: publicado, aparece, mas não vendável.
        Product.objects.filter(sku=s["paused"]).update(is_sellable=False)

        self.stdout.write("  ✅ Vitrine QA: esgotado/últimas/lista-de-espera/pausado")

    def _shop_operates_on(self, day: date) -> bool:
        """A loja abre neste dia? Pergunta ao calendário, nunca a um literal.

        O seed datava produção, encomenda e histórico com ``weekday() == 6``
        (domingo) copiado à mão do horário da Nelson. Copiar a resposta faz as
        duas fontes divergirem no instante em que o horário muda — no staging
        24/7 a loja abre domingo, e os literais deixariam o dia sem fornada
        planejada e sem histórico. ``Shop.opening_hours`` (+ feriados) é o dono
        único da pergunta.
        """
        from shopman.shop.services.business_calendar import is_open_on

        # Shop carregado uma vez: o histórico pergunta por 35 dias e a encomenda
        # por produto × 7 dias — sem cache seria uma query por pergunta.
        shop = getattr(self, "_calendar_shop", None)
        if shop is None:
            from shopman.shop.models import Shop

            shop = self._calendar_shop = Shop.load()
        return is_open_on(day, shop=shop)

    def _staging_autopilot_enabled(self) -> bool:
        """True quando este deployment roda o piloto automático de staging.

        Uma chave só para "staging se opera sozinho": o mesmo interruptor que
        liga o operador de mentira também abre a loja 24/7. Duas perguntas
        separadas divergiriam — loja fechada com piloto ligado é pedido que
        nunca sai do lugar.
        """
        from shopman.shop.services import staging_autopilot

        return staging_autopilot.is_enabled()

    # ────────────────────────────────────────────────────────────────
    # Shop
    # ────────────────────────────────────────────────────────────────

    def _seed_shop(self):
        # Feriados de fechamento SEMPRE à frente da data de hoje (próxima ocorrência do
        # dia fixo). Assim o seed nunca nasce com data passada — relativo a "hoje".
        today = timezone.localdate()

        def _next_occurrence(month: int, day: int) -> str:
            candidate = date(today.year, month, day)
            if candidate < today:
                candidate = date(today.year + 1, month, day)
            return candidate.isoformat()

        closed_dates = [
            {"date": _next_occurrence(12, 25), "label": "Natal"},
            {"date": _next_occurrence(12, 31), "label": "Réveillon"},
            {"date": _next_occurrence(1, 1), "label": "Confraternização Universal"},
        ]

        opening_hours = {
            "monday":    {"open": "09:00", "close": "18:00"},
            "tuesday":   {"open": "09:00", "close": "18:00"},
            "wednesday": {"open": "09:00", "close": "18:00"},
            "thursday":  {"open": "09:00", "close": "18:00"},
            "friday":    {"open": "09:00", "close": "18:00"},
            "saturday":  {"open": "09:00", "close": "18:00"},
            # sunday: fechado
        }

        # Staging com piloto automático: a loja abre a semana inteira, o dia
        # inteiro. Um testador que só tem a noite livre (ou o domingo) precisa
        # conseguir pedir — com o horário real da Nelson ele bate em "fechado"
        # e o aceite do pedido é adiado para a próxima abertura, que pode ser
        # no dia seguinte. Mesmo motivo para zerar os feriados.
        if self._staging_autopilot_enabled():
            opening_hours = {
                day: {"open": "00:00", "close": "23:59"}
                for day in (
                    "monday", "tuesday", "wednesday", "thursday",
                    "friday", "saturday", "sunday",
                )
            }
            closed_dates = []
            self.stdout.write(
                "  🤖 Piloto automático de staging: loja aberta 24/7, sem feriados."
            )

        _, created = Shop.objects.update_or_create(
            pk=1,
            defaults={
                "name": "Nelson Boulangerie",
                "legal_name": "N.H.K. Panificadora Ltda.",
                # CNPJ emitente da NFC-e: o adapter fiscal (Focus NFe) lê de Shop.document
                # como default (sem precisar de FOCUS_NFE_CNPJ_EMITENTE no ambiente).
                "document": "02119381000158",
                "brand_name": "Nelson Boulangerie",
                "short_name": "Nelson",
                "tagline": "Padaria Artesanal",
                "description": "Segue rigorosamente as normas da panificação artesanal francesa.",
                # A voz que a IA usa ao escrever para a Nelson — catálogo E anúncio, uma
                # fonte só. Antes vivia como literal no código do backstage, invisível
                # para quem opera, e a campanha não tinha voz nenhuma.
                "brand_voice": (
                    "Você escreve para a Nelson Boulangerie, uma padaria artesanal "
                    "brasileira que segue as normas da panificação francesa. Escreva em "
                    "português do Brasil, na primeira pessoa do plural (\"nós\", "
                    "\"conosco\"), nunca \"a gente\". Tom acolhedor e concreto, sem "
                    "superlativo vazio, sem emoji e sem travessão (—). Responda APENAS "
                    "com o texto pedido, sem aspas, sem rótulo e sem comentário."
                ),
                "food_safety_notice": (
                    "Produzido em cozinha compartilhada. Pode conter traços de leite, ovos, "
                    "castanha-do-brasil, castanha de caju, gergelim e pimenta-do-reino."
                ),
                "heading_font": "Instrument Sans",
                "body_font": "Instrument Sans",
                "border_radius": "soft",
                "primary_color": "#C5A55A",
                "secondary_color": "#2C1810",
                "accent_color": "#8B4513",
                "neutral_color": "#F5E6D3",
                "neutral_dark_color": "#1A0F0A",
                "formatted_address": "Av. Madre Leônia Milito, 446 - Bela Suíça, Londrina - PR, 86050-270",
                "route": "Av. Madre Leônia Milito",
                "street_number": "446",
                "neighborhood": "Bela Suíça",
                "city": "Londrina",
                "state_code": "PR",
                "postal_code": "86050-270",
                "country": "Brasil",
                "country_code": "BR",
                "latitude": -23.3045,
                "longitude": -51.1628,
                "phone": "554333231997",
                "email": "nelson@boulangerie.com.br",
                "default_ddd": "43",
                "social_links": [
                    "https://wa.me/554333231997",
                    "https://instagram.com/example",
                    "https://www.facebook.com/example",
                    "http://www.example.com.br",
                ],
                "cancellation_presets": [
                    "Item indisponível no momento",
                    "Sem um dos ingredientes hoje",
                    "Problema técnico no preparo",
                    "Fora do horário de atendimento",
                ],
                "kitchen_note_tags": [
                    "Bem assado",
                    "Pouco assado",
                    "Sem cebola",
                    "Embalar para presente",
                    "Cortar ao meio",
                ],
                "opening_hours": opening_hours,
                "defaults": {
                    "menu": {
                        "dynamic_collections": ["featured", "fresh_from_oven", "new_arrivals"],
                    },
                    "notifications": {"backend": "console"},
                    "rules": {
                        # Políticas de pedido/entrega em centavos. 0 = desligada.
                        "minimum_order_q": 0,        # sem mínimo geral (ticket baixo)
                        "delivery_minimum_q": 2500,  # R$ 25,00 mínimo só p/ entrega
                        "free_delivery_above_q": 0,  # frete grátis desligado
                        # Taxa de entrega quando a distância não pôde ser calculada (endereço
                        # sem geocode / loja sem coordenada): fallback em vez de bloquear.
                        "default_delivery_fee_q": 800,  # R$ 8,00 (faixa do meio)
                    },
                    "pos": {
                        # Nelson oferece NFC-e no balcão. O toggle 'Nota fiscal' aparece no
                        # PDV quando isto está on E o adapter fiscal está configurado.
                        "fiscal_toggle": True,
                    },
                    "pickup_slots": [
                        {"ref": "slot-09", "label": "A partir das 09h", "starts_at": "09:00"},
                        {"ref": "slot-12", "label": "A partir das 12h", "starts_at": "12:00"},
                        {"ref": "slot-15", "label": "A partir das 15h", "starts_at": "15:00"},
                    ],
                    "pickup_slot_config": {
                        "rounding_minutes": 30,
                        "history_days": 30,
                        "fallback_slot": "slot-09",
                    },
                    "max_preorder_days": 30,
                    "closed_dates": closed_dates,
                    "production": {
                        "suggestion": {
                            "seasons": {
                                "hot":  [10, 11, 12, 1, 2, 3],
                                "mild": [4, 5, 9],
                                "cold": [6, 7, 8],
                            },
                            "high_demand_multiplier": "1.2",
                            "safety_stock_percent": "0.20",
                        },
                    },
                    "stock_alerts": {
                        "cooldown_minutes": 60,  # mín. entre re-avisos do mesmo alerta
                    },
                    "loyalty": {
                        "points_per_real": 1,    # 1 ponto por R$ 1,00
                        "stamps_target": 10,     # cartela de 10 carimbos
                        "tiers": [
                            {"name": "bronze", "threshold": 0},
                            {"name": "silver", "threshold": 500},
                            {"name": "gold", "threshold": 2000},
                            {"name": "platinum", "threshold": 5000},
                        ],
                    },
                },
            },
        )
        self.stdout.write("  ✅ Shop criado" if created else "  ✅ Shop atualizado")

    # ────────────────────────────────────────────────────────────────
    # Delivery Zones
    # ────────────────────────────────────────────────────────────────

    def _seed_delivery_distance_bands(self):
        """Motor de precificação: taxa por faixa de distância (loja→endereço)."""
        from shopman.shop.models import DeliveryDistanceBand

        shop = Shop.objects.get(pk=1)
        bands = [
            {"max_distance_km": "3.00", "fee_q": 500, "sort_order": 10},    # até 3 km → R$ 5,00
            {"max_distance_km": "6.00", "fee_q": 800, "sort_order": 20},    # até 6 km → R$ 8,00
            {"max_distance_km": "10.00", "fee_q": 1200, "sort_order": 30},  # até 10 km → R$ 12,00
        ]
        created_count = 0
        for data in bands:
            _, created = DeliveryDistanceBand.objects.update_or_create(
                shop=shop,
                max_distance_km=data["max_distance_km"],
                defaults={k: v for k, v in data.items() if k != "max_distance_km"},
            )
            if created:
                created_count += 1
        self.stdout.write(
            f"  ✅ Faixas de distância: {len(bands)} configuradas ({created_count} novas). "
            "Acima de 10 km → fora da área."
        )

    def _seed_delivery_zones(self):
        """Exceções à distância: override (taxa fixa) e exclude (não entregar)."""
        from shopman.shop.models import DeliveryZone

        shop = Shop.objects.get(pk=1)
        # A taxa primária vem das faixas de distância; estas zonas são exceções.
        zones = [
            {
                "name": "Bairro Bela Suíça (cortesia)",
                "mode": DeliveryZone.MODE_OVERRIDE,
                "zone_type": DeliveryZone.ZONE_TYPE_NEIGHBORHOOD,
                "match_value": "Bela Suíça",
                "fee_q": 0,     # entrega grátis (sobrepõe a distância)
                "sort_order": 5,
            },
            {
                "name": "Fora de Londrina (Cambé/Ibiporã)",
                "mode": DeliveryZone.MODE_EXCLUDE,
                "zone_type": DeliveryZone.ZONE_TYPE_CEP_PREFIX,
                "match_value": "862",  # não entregamos nestes CEPs
                "fee_q": 0,
                "sort_order": 30,
            },
        ]
        created_count = 0
        for data in zones:
            _, created = DeliveryZone.objects.update_or_create(
                shop=shop,
                name=data["name"],
                defaults={k: v for k, v in data.items() if k != "name"},
            )
            if created:
                created_count += 1
        self.stdout.write(
            f"  ✅ Zonas de entrega (exceções): {len(zones)} configuradas ({created_count} novas)"
        )

    # ────────────────────────────────────────────────────────────────
    # Superuser
    # ────────────────────────────────────────────────────────────────

    def _resolve_admin_password(self) -> str:
        password = os.environ.get("ADMIN_PASSWORD")
        if password:
            normalized = password.strip().lower()
            if not settings.DEBUG and (len(password) < 12 or normalized in {"admin", "password", "shopman", "changeme"}):
                raise CommandError(
                    "ADMIN_PASSWORD inseguro para seed fora de DEBUG; "
                    "use uma senha forte e temporaria."
                )
            return password

        if settings.DEBUG:
            return "admin"

        raise CommandError(
            "ADMIN_PASSWORD precisa estar definido antes de rodar o seed fora de DEBUG."
        )

    def _create_superuser(self, password: str):
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser(
                username="admin",
                email="admin@example.com",
                password=password,
            )
            self.stdout.write("  ✅ Superuser 'admin' criado")
        else:
            self.stdout.write("  ⏭️  Superuser 'admin' ja existe")

    def _seed_operators(self):
        """Delega ao `setup_operators`: o elenco tem UM dono.

        Aqui viviam quatro pessoas com ``user_permissions`` copiadas à mão —
        ``marina`` tinha sete permissões que imitavam o grupo "Gerente" sem serem
        ele. Duas listas para a mesma pergunta ("quem pode o quê?") saem de
        sincronia no primeiro dia em que alguém mexe só numa: mudar o grupo
        "Gerente" não alcançava ninguém, e a tela de Grupos do Admin mostrava
        gente sem grupo nenhum operando o sistema inteiro.

        O comando irmão é idempotente e não toca em dado de negócio, então
        também serve para consertar acesso no staging **sem** rodar este seed —
        que recriaria o catálogo e milhares de pedidos falsos.
        """
        call_command("setup_operators", "--yes", verbosity=0)
        nomes = ", ".join(u for u, *_ in setup_operators.CAST)
        self.stdout.write(f"  ✅ Operadores em grupos, PIN {setup_operators.DEV_PIN}: {nomes}")

    # ────────────────────────────────────────────────────────────────
    # Flush
    # ────────────────────────────────────────────────────────────────

    def _flush(self):
        self.stdout.write("  Limpando dados anteriores...")

        def hard_delete(model):
            return model._base_manager.all()._raw_delete(model._base_manager.db)

        # Sequências de refs (ORDER_REF etc.): zerar para os pedidos recomeçarem do A00
        # a cada seed em vez de continuar de onde pararam num re-seed no mesmo dia.
        from shopman.refs.models import RefSequence

        RefSequence.objects.all().delete()

        # Contador sequencial de código de WorkOrder (WO-YYYY-NNNNN) vive numa tabela
        # PRÓPRIA do craftsman — diferente da RefSequence do shopman.refs acima. Sem
        # zerá-la, os códigos de produção continuam de onde pararam a cada re-seed
        # (WO-2026-00042 → 00043 …), quebrando a idempotência do perfil qa. Zerar aqui
        # faz o `--flush` recomeçar do WO-2026-00001 — estado limpo canônico.
        from shopman.craftsman.models.sequence import RefSequence as CraftRefSequence

        CraftRefSequence.objects.all().delete()

        # Payments
        hard_delete(PaymentTransaction)
        PaymentIntent.objects.all().delete()

        # Orderman
        for model in [
            FulfillmentItem,
            Fulfillment,
            Directive,
            OrderEvent,
            OrderItem,
            Order,
            SessionItem,
            Session,
            Channel,
        ]:
            model.objects.all().delete()

        # Offerman
        for model in [ListingItem, Listing, CollectionItem, Collection, ProductComponent, Product]:
            model.objects.all().delete()

        # Stockman
        from shopman.stockman.models import Hold, Move, Quant

        hard_delete(Move)
        for model in [StockAlert, Hold, Quant, Position]:
            model.objects.all().delete()

        # Craftsman
        from shopman.craftsman.models import WorkOrderEvent

        for model in [WorkOrderEvent, WorkOrder, RecipeItem, Recipe]:
            model.objects.all().delete()

        # Customers
        for model in [CustomerAddress, ContactPoint, Customer, PriceTier]:
            model.objects.all().delete()

        # KDS
        from shopman.backstage.models import KDSTicket

        OperationTaskRun.objects.all().delete()
        OperationChecklistRun.objects.all().delete()
        OperationChecklistTemplateTask.objects.all().delete()
        OperationChecklistTemplate.objects.all().delete()
        OperationTaskTemplate.objects.all().delete()
        OperatorAlert.objects.all().delete()
        KDSTicket.objects.all().delete()
        KDSInstance.objects.all().delete()
        POSTab.objects.all().delete()

        # Caixa (cashman): o livro é imutável pelo app (delete levanta), então o
        # flush apaga cru — antes do turno e do terminal, que o protegem por FK.
        from shopman.cashman.models import Entry as CashEntry
        from shopman.cashman.models import Shift as CashShiftLedger
        from shopman.cashman.models import Terminal as CashTerminal

        hard_delete(CashEntry)
        CashShiftLedger.objects.all().delete()
        CashTerminal.objects.all().delete()

        # Day closing
        DayClosing.objects.all().delete()

        # Shop
        Announcement.objects.all().delete()
        Campaign.objects.all().delete()
        AnnouncementTemplate.objects.all().delete()
        Coupon.objects.all().delete()
        Promotion.objects.all().delete()
        # Regras são config como qualquer outra (Shop, Channel, Promotion, Coupon): o
        # `--flush` apaga e o `_seed_rule_configs` recria o conjunto canônico. Sem
        # apagar, uma regra que saiu do RULE_CONFIGS sobrevive a todo re-seed — foi o
        # que aconteceu com `d1_discount`, cuja classe morreu no C6 (PR #152) e cuja
        # linha ficou no staging gritando "Could not import" a cada boot. A M2M
        # `channels` já foi levada junto com os Channels apagados acima.
        RuleConfig.objects.all().delete()
        Shop.objects.all().delete()

        # Tabelas de auditoria são dado também num seed local; `--flush` deixa limpo
        # de verdade. POR ÚLTIMO, de propósito: o simple_history grava uma linha de
        # tombstone a cada delete, então limpar antes das deleções acima deixaria a
        # history repovoada justamente pelo flush.
        for model in [
            Product.history.model,
            ListingItem.history.model,
            RuleConfig.history.model,
            OmotenashiCopy.history.model,
        ]:
            model.objects.all().delete()

        self.stdout.write("  ✅ Dados limpos")

    # ────────────────────────────────────────────────────────────────
    # Catálogo (Offerman)
    # ────────────────────────────────────────────────────────────────

    def _seed_catalog(self):
        self.stdout.write("  📦 Catálogo...")

        # Catálogo real Nelson Boulangerie
        # Fonte: https://github.com/pablondrina/nb-catalog — os MESMOS arquivos,
        # servidos pelo static site `nb-catalog-app` da DO (deploy_on_push) atrás
        # da Cloudflare, em vez do `raw.githubusercontent.com`. O raw não é CDN: o
        # GitHub limita hotlink, e se estrangular a loja fica sem foto nenhuma.
        # Ver docs/plans/CATALOG-IMAGES-OFF-GITHUB-PLAN.md (o peso dos arquivos —
        # 12,38 MB em 19 fotos — é o outro problema, resolvido na origem).
        IMG = "https://menu.nelsonboulangerie.com.br/img/products/loja"
        UNSPLASH = "https://images.unsplash.com"

        def unsplash(photo_id: str) -> str:
            return f"{UNSPLASH}/{photo_id}?auto=format&fit=crop&w=900&q=80"

        # (sku, name, desc, price_q, unit, shelf_life, available, image, weight_g, storage_tip)
        # Cardápio 2027 v2.0 (Notion, 25/07/2026) — o copo lidera; variedade nas
        # vagas "do dia"; balcão fora do menu; despensa com preço provisório.
        products_data = [
            # ── Bebidas · Quentes ──
            ("SS", "Espresso", "Café espresso puro, grão especial torrado artesanal", 800, "un", None, True,
             unsplash("photo-1508088405209-fbd63b6a4f50"), 0, ""),
            ("CD", "Café Coado", "Café coado na hora, grão especial torrado artesanal", 1200, "un", None, True,
             unsplash("photo-1541469406036-71229832e06e"), 0, ""),
            ("PS", "Cappuccino", "Espresso com leite vaporizado e espuma cremosa", 1200, "un", None, True,
             unsplash("photo-1506372023823-741c83b836fe"), 0, ""),
            ("MC", "Mochaccino", "Espresso com chocolate da casa e leite vaporizado", 1200, "un", None, True,
             unsplash("photo-1596078841242-12f73dc697c6"), 0, ""),
            ("THC", "Chá Camille", "Blend da casa, servido em bule", 1400, "un", None, True,
             unsplash("photo-1602603412313-ab713536e288"), 0, ""),
            ("THR", "Chá Rouge", "Blend da casa, servido em bule", 1400, "un", None, True,
             unsplash("photo-1563636680-28d36aeb83a4"), 0, ""),
            ("THS", "Chá Sophie", "Blend da casa, servido em bule", 1400, "un", None, True,
             unsplash("photo-1654713803623-3d2b9d39f6b3"), 0, ""),
            ("THB", "Chá Bleu", "Blend da casa, servido em bule", 1400, "un", None, True,
             unsplash("photo-1582786256312-079c49fb6980"), 0, ""),
            # ── Bebidas · Geladas ──
            ("CE", "Coffee Float", "Café gelado com sorvete", 1800, "un", None, True,
             unsplash("photo-1594631661960-34762327295a"), 0, ""),
            ("FP", "Frappé", "Batido gelado: café, chocolate ou frutas vermelhas", 1800, "un", None, True,
             unsplash("photo-1719953107038-da34352e407e"), 0, ""),
            ("AG", "Água", "Água mineral, com ou sem gás", 600, "un", None, True,
             unsplash("photo-1553564552-02656d6a2390"), 0, ""),
            # ── Bebidas · Especialidades na torneira ──
            ("CV", "Cream Soda do dia", "Cream soda artesanal da torneira, sabor do dia", 2100, "un", None, True,
             unsplash("photo-1605712916345-6ef6bcc2e29c"), 0, ""),
            ("SO", "Soda de Laranja", "Soda artesanal de laranja, feita na casa", 1400, "un", None, True,
             unsplash("photo-1598830853058-3474f6a66003"), 0, ""),
            # ── Padaria · Rústicos ──
            ("BF", "Baguette de Tradition", "Pão de tradição francesa e fermentação 100% natural (levain)", 1600, "un", 0, True,
             f"{IMG}/bf.webp", 250, "Congele inteira ou em pedaços. Reaqueça direto do freezer a 200°C por 8min"),
            ("CGO", "Pain de Campagne", "Fermentação natural (levain), trigo 50% integral e centeio orgânico. Fatiado na hora", 2200, "un", 2, True,
             f"{IMG}/cgr.webp", 500, "Guarde em saco de pano. Dura até 4 dias em temperatura ambiente"),
            ("CPX", "Campagne Passas & Castanhas", "Levain, trigo 50% integral e centeio orgânico, passas, castanhas de caju e do Pará", 3300, "un", 3, True,
             f"{IMG}/cpx.webp", 550, "Guarde em saco de pano. Dura até 5 dias em temperatura ambiente"),
            ("CI", "Ciabatta", "Pão aerado, clássico italiano com azeite extra virgem e fermentação 100% natural (levain)", 1800, "un", 0, True,
             f"{IMG}/ci.webp", 200, "Congele no mesmo dia. Reaqueça a 200°C por 8min"),
            ("BE", "Baguete Gergelim", "Baguete com fermentação 100% natural (levain), toque de azeite e gergelim", 1800, "un", 0, True,
             f"{IMG}/be.webp", 260, "Congele no mesmo dia. Reaqueça a 200°C por 8min"),
            # ── Padaria · Finos ──
            ("CT", "Croissant", "Clássico em pura manteiga. Simples e delicioso. Ótimo com geleias!", 1300, "un", 1, True,
             f"{IMG}/ct.webp", 80, "Reaqueça no forno a 180°C por 5min para recuperar a crocância"),
            ("PC", "Pain au Chocolat", "Croissant recheado com chocolate!", 1500, "un", 1, True,
             f"{IMG}/pc.webp", 90, "Reaqueça no forno a 180°C por 5min. Evite micro-ondas"),
            ("SK", "Shokupan", "Pão de forma japonês super macio, fatias grossas interfolhadas", 2800, "un", 2, True,
             unsplash("photo-1598373182308-3270495d2f58"), 450, "Mantenha em saco plástico fechado. Congela bem por até 30 dias"),
            ("KP", "Kuro Pan", "Pão japonês escuro, macio e levemente adocicado", 2200, "un", 2, True,
             unsplash("photo-1778472438579-91875c22ae79"), 350, "Mantenha em saco plástico fechado. Congela bem por até 30 dias"),
            ("ME", "Melonpan", "Clássico japonês amanteigado com cobertura crocante e levemente doce", 1200, "un", 1, True,
             f"{IMG}/me.webp", 100, "Melhor consumido no dia"),
            ("ANC", "Animalzinho", "O bichinho do dia: pão doce em formato de bicho", 1000, "un", 1, True,
             unsplash("photo-1698273501864-e6f6e33a67cd"), 90, "Melhor consumido no dia"),
            ("CO", "Cornet", "Pão amanteigado em formato de cone, recheio do dia", 1200, "un", 1, True,
             f"{IMG}/co.webp", 120, "Melhor consumido no dia. Reaqueça a 180°C por 5min"),
            # ── Padaria · Salgados ──
            ("CMO", "Croque Monsieur", "Clássico sanduíche francês gratinado com presunto e queijo gruyere", 2400, "un", 0, True,
             unsplash("photo-1621188988504-f2a8ff685801"), 250, "Servir quente, imediatamente"),
            ("CMA", "Croque Madame", "Croque monsieur com ovo pochado por cima", 2800, "un", 0, True,
             unsplash("photo-1621188988280-67c8d6e130a6"), 290, "Servir quente, imediatamente"),
            ("CCOM", "Croque Complet", "Croque com presunto, queijo, ovo e acompanhamento da casa", 3000, "un", 0, True,
             unsplash("photo-1531664412848-9610afed156c"), 320, "Servir quente, imediatamente"),
            ("QQ", "Queijo-Quente", "Queijo quente da casa, no shokupan", 2600, "un", 0, True,
             unsplash("photo-1528736235302-52922df5c122"), 250, "Servir quente, imediatamente"),
            ("JB", "Jambon-Beurre", "Baguette, manteiga e presunto — o clássico parisiense", 1800, "un", 0, True,
             unsplash("photo-1753798130695-3c060be80e83"), 250, "Melhor consumido na hora"),
            ("PG", "Pain Grillé", "Fatia grossa na chapa com manteiga da casa", 1600, "un", 0, True,
             unsplash("photo-1637376516923-e88d431a677d"), 150, "Servir quente, imediatamente"),
            ("TI", "Tábua de Iguarias da Casa", "Charcutaria, queijos e patês da casa, com pães", 5800, "un", 0, True,
             unsplash("photo-1640618491853-95b2c5041eda"), 500, "Servir na hora"),
            # ── Padaria · Doces ──
            ("PPU", "Pain Perdu", "Fatia de brioche dourada na chapa, calda e toque de canela", 1800, "un", 0, True,
             unsplash("photo-1484723091739-30a097e8f929"), 180, "Servir quente, imediatamente"),
            ("MS", "Melon Iced Sando", "Sanduíche gelado de frutas com chantilly, no shokupan", 2200, "un", 0, True,
             unsplash("photo-1746632732485-4cb341e4a4aa"), 200, "Conservar refrigerado. Consumir no dia"),
            ("MD", "Madeleine", "Bolinho clássico francês, simples e delicioso", 600, "un", 2, True,
             f"{IMG}/md.webp", 40, "Conserve em recipiente fechado por até 3 dias"),
            ("PU", "Purin à la Mode", "Pudim japonês com chantilly e frutas", 2000, "un", 1, True,
             unsplash("photo-1752245055475-8b7c3b4756ac"), 150, "Conservar refrigerado. Consumir no dia"),
            ("TJ", "Tea Jelly", "Gelatina delicada de chá da casa", 1800, "un", 1, True,
             unsplash("photo-1745236549258-a76c271299f7"), 150, "Conservar refrigerado. Consumir em até 2 dias"),
            # ── Balcão (à venda, fora do menu impresso) ──
            ("FE", "Fendu", "Pãozinho de tradição francesa e fermentação 100% natural (levain)", 600, "un", 0, True,
             f"{IMG}/fe.webp", 100, "Melhor consumido no dia. Congele por até 30 dias"),
            ("TB", "Tabatière", "Pãozinho de tradição francesa e fermentação 100% natural (levain)", 600, "un", 0, True,
             f"{IMG}/tb.webp", 100, "Melhor consumido no dia. Congele por até 30 dias"),
            ("MIB", "Mini Baguete", "Mini baguete com fermentação 100% natural (levain) e toque de azeite", 900, "un", 0, True,
             f"{IMG}/bap.webp", 120, "Congele no mesmo dia. Reaqueça a 200°C por 5min"),
            ("PH", "Pão de Hambúrguer", "Pão de tradição francesa e fermentação 100% natural (levain)", 600, "un", 0, True,
             f"{IMG}/ph.webp", 100, "Melhor consumido no dia. Congele por até 30 dias"),
            ("BRIOCHE-BURGER", "Brioche Burger Bun (pc. 2un.)", "Super leve, riquíssimo em ovos e manteiga", 1600, "un", 1, True,
             f"{IMG}/bbb.webp", 200, "Congele no mesmo dia. Reaqueça a 180°C por 5min"),
            ("PAO-HOTDOG", "Pão para Hot Dog (pc. 4un.)", "Pão amanteigado, bom para cachorro quente", 2800, "un", 1, True,
             f"{IMG}/pho.webp", 320, "Congele no mesmo dia por até 30 dias"),
            # ── Despensa (preços provisórios — metadata.price_tbd) ──
            ("MT", "Mostarda da Casa", "Mostarda artesanal feita na casa", 1800, "un", 30, True,
             unsplash("photo-1638324396220-432156cd9303"), 200, "Conservar refrigerado após aberto"),
            ("BK", "Bacon da Casa", "Bacon curado e defumado na casa (peça)", 2200, "un", 15, True,
             unsplash("photo-1766406838572-915da0343519"), 200, "Conservar refrigerado"),
            ("TP", "Tapenade", "Pasta provençal de azeitonas da casa", 2400, "un", 15, True,
             unsplash("photo-1750874695064-f851719d1858"), 170, "Conservar refrigerado após aberto"),
            ("PT", "Patê de Ratatouille", "Patê vegetal da casa", 2400, "un", 15, True,
             unsplash("photo-1777891257519-84d59a502ca1"), 170, "Conservar refrigerado após aberto"),
            ("CX", "Cornichons", "Picles franceses em conserva", 2800, "un", 90, True,
             unsplash("photo-1774456567094-726973275d34"), 200, "Conservar refrigerado após aberto"),
            ("GL", "Geleia St. Dalfour (mini)", "Geleia francesa 100% fruta, pote mini", 1600, "un", 180, True,
             unsplash("photo-1633084426862-3a8c25aa7ce5"), 28, "Conservar refrigerado após aberto"),
            ("QC", "Camembert", "Queijo camembert de leite de vaca", 3800, "un", 20, True,
             unsplash("photo-1624806992066-5ffcf7ca186b"), 250, "Conservar refrigerado"),
            ("QP", "Queijo Pomerode", "Queijo colonial artesanal de Pomerode", 3200, "un", 30, True,
             unsplash("photo-1756922245026-934ff1648d79"), 300, "Conservar refrigerado"),
            ("GR", "Café em Grão (250g)", "O grão da casa, torra artesanal", 4200, "un", 90, True,
             unsplash("photo-1559056199-641a0ac8b55e"), 250, "Conservar em local seco e fechado"),
            ("THL", "Chá da Casa (lata)", "Blend da casa em folhas, lata para levar", 4000, "un", 365, True,
             unsplash("photo-1760602180499-382146d5eb02"), 80, "Conservar em local seco e fechado"),
            ("LN", "Lata Nelson", "Lata de presente: madeleines sortidas e biscoitos da casa", 8900, "un", 30, True,
             unsplash("photo-1765850258842-af769210194f"), 400, "Conservar em local seco e fechado"),
            # ── Voltaram do Yooga (18/08) ──
            # O cardápio 2027 tinha colapsado famílias inteiras em produtos
            # rotativos ("Folhado do dia") e enxugado outras. O dono decidiu que
            # o que a casa fazia existe: variante com recheio ou preparo próprio
            # é produto, e volume baixo não desqualifica — a mini baguete de
            # gergelim vende pouco no balcão porque é de caixa presente.
            #
            # Nome e preço são dado real do Yooga (preço mais praticado nos 12
            # meses até 20/07/2026). Coleção, descrição, validade, peso e
            # conservação são proposta — o padrão da coleção, para revisão.
            # Imagem fica vazia de propósito: foto errada é pior que sem foto.
            ("SL", "Espresso Macchiato", "Espresso marcado com espuma de leite", 900, "un", None, True,
             "", 0, ""),
            ("CL", "Caffè Latte", "Espresso com leite vaporizado", 1300, "un", None, True,
             "", 0, ""),
            ("CQ", "Chocolate Quente", "Chocolate quente cremoso da casa", 1800, "un", None, True,
             "", 0, ""),
            ("MH", "Mocha", "Espresso com chocolate e leite vaporizado", 2000, "un", None, True,
             "", 0, ""),
            ("HI", "Chá Hibisco", "Chá gelado de hibisco", 1800, "un", None, True,
             "", 0, ""),
            ("CTV", "Chá Tônica Frutas Vermelhas", "Chá gelado de frutas vermelhas com tônica", 2600, "un", None, True,
             "", 0, ""),
            ("BH", "Bichon au Citron", "Folhado com creme de limão", 1800, "un", 1, True,
             "", 150, "Conservar refrigerado. Consumir no dia"),
            ("MA", "Maçã", "Doce de maçã da casa", 1200, "un", 1, True,
             "", 150, "Conservar refrigerado. Consumir no dia"),
            ("CM", "Croissant Mini", "Croissant menor, a mesma massa folhada", 800, "un", 1, True,
             "", 45, "Reaqueça no forno a 180°C por 5min para recuperar a crocância"),
            ("BCH", "Brioche Chocolat", "Brioche recheado com chocolate", 1000, "un", 1, True,
             "", 90, "Mantenha em saco plástico fechado. Congele por até 30 dias"),
            ("CN", "Chausson", "Folhado recheado, dobrado em meia-lua", 1600, "un", 1, True,
             "", 120, "Reaqueça no forno a 180°C por 5min para recuperar a crocância"),
            ("PR", "Pain aux Raisins", "Folhado em espiral com creme e passas", 1100, "un", 1, True,
             "", 110, "Reaqueça no forno a 180°C por 5min para recuperar a crocância"),
            ("COC", "Cornet de Chocolate", "Cornet recheado com chocolate", 1000, "un", 1, True,
             "", 90, "Mantenha em saco plástico fechado. Congele por até 30 dias"),
            ("CH", "Challah", "Pão trançado de massa enriquecida", 1600, "un", 1, True,
             "", 400, "Mantenha em saco plástico fechado. Congele por até 30 dias"),
            ("BN", "Brioche Nanterre", "Brioche em forma, massa amanteigada", 2200, "un", 1, True,
             "", 400, "Mantenha em saco plástico fechado. Congele por até 30 dias"),
            ("ANU", "Ursinho", "Doce moldado em ursinho, recheio de creme", 1400, "un", 1, True,
             "", 120, "Mantenha em saco plástico fechado. Congele por até 30 dias"),
            # Não está sendo feito no momento (dono, 18/08). Nasce fora de venda:
            # o produto existe, guarda a história, e volta com uma flag.
            ("ANP", "Porquinho", "Doce moldado em porquinho, recheio de creme", 1300, "un", 1, False,
             "", 120, "Mantenha em saco plástico fechado. Congele por até 30 dias"),
            ("KBB", "Kuro Pan Burger", "Kuro Pan em formato de bun para hambúrguer", 700, "un", 1, True,
             "", 90, "Mantenha em saco plástico fechado. Congele por até 30 dias"),
            ("MBBBG", "Mini Brioche Burger Bun com gergelim", "Bun de brioche menor, com gergelim", 500, "un", 1, True,
             "", 45, "Mantenha em saco plástico fechado. Congele por até 30 dias"),
            ("FA", "Forma Artesanal (6 fatias)", "Pão de forma artesanal, fatiado", 1800, "un", 0, True,
             "", 400, "Melhor consumido no dia. Congele por até 30 dias"),
            ("BAP", "Baguete Lanche", "Baguete no tamanho de lanche", 900, "un", 0, True,
             "", 150, "Melhor consumido no dia. Congele por até 30 dias"),
            ("BAX", "Italiano Rústico", "Pão italiano de casca grossa", 2000, "un", 0, True,
             "", 500, "Melhor consumido no dia. Congele por até 30 dias"),
            ("CF", "Baguette Campagne", "Baguete de massa campagne", 1500, "un", 0, True,
             "", 300, "Melhor consumido no dia. Congele por até 30 dias"),
            ("BA", "Bâtard", "Pão rústico curto, casca crocante", 1300, "un", 0, True,
             "", 300, "Melhor consumido no dia. Congele por até 30 dias"),
            ("CGR", "Pain de Campagne Redondo", "Campagne em formato redondo", 1800, "un", 0, True,
             "", 500, "Melhor consumido no dia. Congele por até 30 dias"),
            ("SE", "Vienna", "Pão vienense de massa macia", 1500, "un", 0, True,
             "", 200, "Melhor consumido no dia. Congele por até 30 dias"),
            ("PI", "Pita", "Pão pita, unidade", 400, "un", 0, True,
             "", 80, "Melhor consumido no dia. Congele por até 30 dias"),
            ("BEP", "Baguete Gergelim Pequena", "Baguete de gergelim menor, das caixas presente", 900, "un", 0, True,
             "", 120, "Melhor consumido no dia. Congele por até 30 dias"),
            ("FOA", "Focaccia Alecrim", "Focaccia com alecrim e azeite", 2800, "un", 0, True,
             "", 450, "Melhor consumido no dia. Congele por até 30 dias"),
            ("CBT", "Focaccia Cebola, Bacon e Tomilho", "Focaccia com cebola, bacon e tomilho", 3600, "un", 0, True,
             "", 500, "Melhor consumido no dia. Congele por até 30 dias"),
            ("FOC", "Focaccia Cebola Roxa", "Focaccia com cebola roxa", 3600, "un", 0, True,
             "", 500, "Melhor consumido no dia. Congele por até 30 dias"),
            ("MIF", "Mini Focaccia Alecrim", "Focaccia menor, com alecrim", 1300, "un", 0, True,
             "", 180, "Melhor consumido no dia. Congele por até 30 dias"),
            ("MICBT", "Mini Focaccia Cebola, Bacon e Tomilho", "Focaccia menor, com cebola, bacon e tomilho", 1800, "un", 0, True,
             "", 200, "Melhor consumido no dia. Congele por até 30 dias"),
            ("MIFOC", "Mini Focaccia Cebola Roxa", "Focaccia menor, com cebola roxa", 1300, "un", 0, True,
             "", 200, "Melhor consumido no dia. Congele por até 30 dias"),
            ("CPQ", "Croissant Presunto e Queijo", "Croissant recheado com presunto e queijo", 1500, "un", 0, True,
             "", 140, "Servir quente, imediatamente"),
            ("FF", "Folhado de Frango", "Folhado recheado com frango", 1800, "un", 0, True,
             "", 180, "Servir quente, imediatamente"),
            ("MFF", "Mini Folhado de Frango", "Folhado de frango menor", 900, "un", 0, True,
             "", 90, "Servir quente, imediatamente"),
            ("HO", "Hot Dog Vienna", "Cachorro-quente no pão vienense", 1400, "un", 0, True,
             "", 250, "Servir quente, imediatamente"),
            ("MIHO", "Mini Hot Dog Vienna", "Cachorro-quente menor", 700, "un", 0, True,
             "", 130, "Servir quente, imediatamente"),
            ("DL", "Deli Milho & Bacon", "Pão recheado com milho e bacon", 1700, "un", 0, True,
             "", 250, "Servir quente, imediatamente"),
            ("JO", "Caranguejo", "Salgado moldado em caranguejo", 1600, "un", 0, True,
             "", 180, "Servir quente, imediatamente"),
        ]

        # Keywords by product (for find_alternatives and search)
        keywords_map = {
            "BF": ["pao", "frances", "levain", "artesanal", "crocante"],
            "BE": ["pao", "frances", "levain", "gergelim", "azeite"],
            "CGO": ["pao", "campagne", "levain", "integral", "centeio"],
            "CPX": ["pao", "campagne", "levain", "passas", "castanhas", "especial"],
            "CI": ["pao", "italiano", "levain", "azeite", "aerado"],
            "CT": ["croissant", "folhado", "manteiga", "frances"],
            "CN": ["chausson", "folhado", "maca", "frances"],
            "BH": ["bichon", "limao", "folhado", "doce"],
            "PR": ["pain", "raisins", "passas", "folhado"],
            "DL": ["deli", "milho", "bacon", "salgado"],
            "HO": ["hotdog", "cachorro-quente", "vienna", "salgado"],
            "FOA": ["focaccia", "alecrim", "italiano", "azeite"],
            "HI": ["cha", "hibisco", "gelado", "bebida"],
            "CTV": ["cha", "tonica", "frutas-vermelhas", "gelado"],
            "PC": ["croissant", "folhado", "chocolate", "frances"],
            "ME": ["pao-doce", "japones", "crocante", "amanteigado"],
            "CO": ["pao-doce", "creme", "recheado", "amanteigado"],
            "MD": ["bolinho", "frances", "classico", "doce"],
            "CMO": ["lanche", "sanduiche", "frances", "presunto", "queijo", "gratinado"],
            "CMA": ["lanche", "sanduiche", "frances", "ovo", "queijo", "gratinado"],
            "SS": ["cafe", "espresso", "bebida", "quente"],
            "PS": ["cafe", "cappuccino", "leite", "bebida", "quente"],
            "FE": ["pao", "frances", "levain", "individual", "artesanal"],
            "TB": ["pao", "frances", "levain", "individual", "artesanal"],
            "MIB": ["pao", "frances", "levain", "mini", "individual"],
            "PH": ["pao", "hamburger", "levain", "individual"],
            "BRIOCHE-BURGER": ["brioche", "hamburger", "manteiga", "ovos"],
            "PAO-HOTDOG": ["pao", "hotdog", "manteiga", "salgado"],
            "CD": ["cafe", "coado", "filtrado", "bebida", "quente"],
            "MC": ["cafe", "mocha", "chocolate", "leite", "bebida", "quente"],
            "THC": ["cha", "blend", "bule", "bebida", "quente"],
            "THR": ["cha", "blend", "bule", "bebida", "quente"],
            "THS": ["cha", "blend", "bule", "bebida", "quente"],
            "THB": ["cha", "blend", "bule", "bebida", "quente"],
            "CE": ["cafe", "sorvete", "gelado", "bebida", "frio"],
            "FP": ["cafe", "frappe", "gelado", "batido", "bebida", "frio"],
            "AG": ["agua", "mineral", "bebida", "frio"],
            "CV": ["soda", "torneira", "artesanal", "bebida", "frio", "do-dia"],
            "SO": ["soda", "laranja", "torneira", "artesanal", "bebida", "frio"],
            "SK": ["pao", "forma", "japones", "macio", "fatiado", "shokupan"],
            "KP": ["pao", "japones", "escuro", "macio"],
            "ANC": ["pao-doce", "bichinho", "criancas", "do-dia"],
            "CCOM": ["lanche", "sanduiche", "frances", "ovo", "queijo", "gratinado"],
            "QQ": ["lanche", "sanduiche", "queijo", "shokupan", "quente"],
            "JB": ["lanche", "sanduiche", "frances", "presunto", "manteiga"],
            "PG": ["torrada", "chapa", "manteiga", "quente"],
            "TI": ["tabua", "charcutaria", "queijo", "pate", "compartilhar"],
            "PPU": ["doce", "rabanada", "chapa", "frances"],
            "MS": ["doce", "frutas", "chantilly", "japones", "gelado"],
            "PU": ["doce", "pudim", "japones", "sobremesa"],
            "TJ": ["doce", "gelatina", "cha", "sobremesa"],
            "MT": ["mercearia", "despensa", "mostarda", "artesanal", "pote"],
            "BK": ["mercearia", "despensa", "bacon", "defumado", "artesanal"],
            "TP": ["mercearia", "despensa", "tapenade", "azeitona", "pote"],
            "PT": ["mercearia", "despensa", "pate", "ratatouille", "vegetal", "pote"],
            "CX": ["mercearia", "despensa", "picles", "conserva", "frances"],
            "GL": ["mercearia", "despensa", "geleia", "fruta", "mini"],
            "QC": ["mercearia", "despensa", "queijo", "camembert", "frances"],
            "QP": ["mercearia", "despensa", "queijo", "colonial", "local"],
            "GR": ["mercearia", "despensa", "cafe", "grao", "torra"],
            "THL": ["mercearia", "despensa", "cha", "lata", "presente"],
            "LN": ["mercearia", "despensa", "presente", "lata", "biscoito", "madeleine"],
        }


        # PDP metadata for remote purchase confidence. These are display-ready,
        # approximate values; ingredients/nutrition are materialized separately.
        PDP_METADATA = {
            "BF": {
                "allergens": ["glúten"],
                "dietary_info": ["100% vegetal", "sem lactose"],
                "serves": "2 pessoas",
                "approx_dimensions": "aprox. 55 x 6 x 5 cm",
            },
            "BE": {
                "allergens": ["glúten", "gergelim"],
                "dietary_info": ["100% vegetal", "sem lactose"],
                "serves": "2 pessoas",
                "approx_dimensions": "aprox. 55 x 6 x 5 cm",
            },
            "MIB": {
                "allergens": ["glúten"],
                "dietary_info": ["100% vegetal", "sem lactose"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 26 x 5 x 4 cm",
            },
            "FE": {
                "allergens": ["glúten"],
                "dietary_info": ["100% vegetal", "sem lactose"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 12 x 8 x 5 cm",
            },
            "TB": {
                "allergens": ["glúten"],
                "dietary_info": ["100% vegetal", "sem lactose"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 12 x 8 x 5 cm",
            },
            "CGO": {
                "allergens": ["glúten"],
                "dietary_info": ["100% vegetal", "sem lactose"],
                "serves": "3 a 5 pessoas",
                "approx_dimensions": "aprox. 18 cm de diâmetro",
            },
            "CPX": {
                "allergens": ["glúten", "castanhas"],
                "dietary_info": ["100% vegetal", "sem lactose"],
                "serves": "4 a 6 pessoas",
                "approx_dimensions": "aprox. 28 x 16 x 10 cm",
            },
            "CI": {
                "allergens": ["glúten"],
                "dietary_info": ["100% vegetal", "sem lactose"],
                "serves": "1 a 2 pessoas",
                "approx_dimensions": "aprox. 20 x 10 x 4 cm",
            },
            "PH": {
                "allergens": ["glúten"],
                "dietary_info": ["100% vegetal", "sem lactose"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 10 cm de diâmetro",
            },
            "BRIOCHE-BURGER": {
                "allergens": ["glúten", "leite", "ovos"],
                "dietary_info": ["vegetariano"],
                "serves": "2 unidades",
                "approx_dimensions": "aprox. 10 cm de diâmetro cada",
            },
            "PAO-HOTDOG": {
                "allergens": ["glúten", "leite", "ovos"],
                "dietary_info": ["vegetariano"],
                "serves": "4 unidades",
                "approx_dimensions": "aprox. 16 x 5 x 4 cm cada",
            },
            "CT": {
                "allergens": ["glúten", "leite", "ovos"],
                "dietary_info": ["vegetariano"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 12 x 8 x 5 cm",
            },
            "PC": {
                "allergens": ["glúten", "leite", "ovos", "soja"],
                "dietary_info": ["vegetariano"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 11 x 7 x 4 cm",
            },
            "CO": {
                "allergens": ["glúten", "leite", "ovos"],
                "dietary_info": ["vegetariano"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 13 x 6 x 6 cm",
            },
            "ME": {
                "allergens": ["glúten", "leite", "ovos"],
                "dietary_info": ["vegetariano"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 10 cm de diâmetro",
            },
            "MD": {
                "allergens": ["glúten", "leite", "ovos"],
                "dietary_info": ["vegetariano"],
                "serves": "1 unidade",
                "approx_dimensions": "aprox. 8 x 5 x 3 cm",
            },
            "CMO": {
                "allergens": ["glúten", "leite"],
                "dietary_info": [],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 16 x 12 x 5 cm",
            },
            "CMA": {
                "allergens": ["glúten", "leite", "ovos"],
                "dietary_info": [],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 16 x 12 x 7 cm",
            },
            "SS": {
                "allergens": [],
                "dietary_info": ["100% vegetal", "sem glúten", "sem lactose"],
                "serves": "1 xícara de 40 ml",
            },
            "PS": {
                "allergens": ["leite"],
                "dietary_info": ["vegetariano", "sem glúten"],
                "serves": "1 xícara de 180 ml",
            },
            "CD": {
                "allergens": [],
                "dietary_info": ["100% vegetal"],
                "serves": "1 pessoa",
                "approx_dimensions": "xícara 180 ml",
            },
            "MC": {
                "allergens": ["leite"],
                "dietary_info": ["vegetariano"],
                "serves": "1 pessoa",
                "approx_dimensions": "xícara 180 ml",
            },
            "THC": {
                "allergens": [],
                "dietary_info": ["100% vegetal"],
                "serves": "1 bule (2 xícaras)",
                "approx_dimensions": "bule 400 ml",
            },
            "THR": {
                "allergens": [],
                "dietary_info": ["100% vegetal"],
                "serves": "1 bule (2 xícaras)",
                "approx_dimensions": "bule 400 ml",
            },
            "THS": {
                "allergens": [],
                "dietary_info": ["100% vegetal"],
                "serves": "1 bule (2 xícaras)",
                "approx_dimensions": "bule 400 ml",
            },
            "THB": {
                "allergens": [],
                "dietary_info": ["100% vegetal"],
                "serves": "1 bule (2 xícaras)",
                "approx_dimensions": "bule 400 ml",
            },
            "HI": {
                "allergens": [],
                "dietary_info": ["100% vegetal"],
                "serves": "1 pessoa",
                "approx_dimensions": "copo 300 ml",
            },
            "CTV": {
                "allergens": [],
                "dietary_info": ["100% vegetal"],
                "serves": "1 pessoa",
                "approx_dimensions": "copo 300 ml",
            },
            "CE": {
                "allergens": ["leite"],
                "dietary_info": ["vegetariano"],
                "serves": "1 pessoa",
                "approx_dimensions": "copo 300 ml",
            },
            "FP": {
                "allergens": ["leite"],
                "dietary_info": ["vegetariano"],
                "serves": "1 pessoa",
                "approx_dimensions": "copo 300 ml",
            },
            "AG": {
                "allergens": [],
                "dietary_info": ["100% vegetal"],
                "serves": "1 pessoa",
                "approx_dimensions": "garrafa 500 ml",
            },
            "CV": {
                "allergens": [],
                "dietary_info": ["100% vegetal"],
                "serves": "1 pessoa",
                "approx_dimensions": "copo 300 ml",
            },
            "SO": {
                "allergens": [],
                "dietary_info": ["100% vegetal"],
                "serves": "1 pessoa",
                "approx_dimensions": "copo 300 ml",
            },
            "FOA": {
                "allergens": ["glúten"],
                "dietary_info": ["100% vegetal", "sem lactose"],
                "serves": "4 a 6 pessoas",
                "approx_dimensions": "aprox. 24 x 18 x 4 cm",
            },
            "SK": {
                "allergens": ["glúten", "leite"],
                "dietary_info": ["vegetariano"],
                "serves": "6 fatias grossas",
                "approx_dimensions": "aprox. 18 x 10 x 10 cm",
            },
            "KP": {
                "allergens": ["glúten"],
                "dietary_info": ["vegetariano"],
                "serves": "2 a 3 pessoas",
                "approx_dimensions": "aprox. 18 x 10 x 8 cm",
            },
            "CN": {
                "allergens": ["glúten", "leite"],
                "dietary_info": ["vegetariano"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 12 x 10 cm",
            },
            "BH": {
                "allergens": ["glúten", "leite"],
                "dietary_info": ["vegetariano"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 12 x 10 cm",
            },
            "PR": {
                "allergens": ["glúten", "leite"],
                "dietary_info": ["vegetariano"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 12 x 10 cm",
            },
            "ANC": {
                "allergens": ["glúten", "leite", "ovos"],
                "dietary_info": ["vegetariano"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 10 x 8 cm",
            },
            "CCOM": {
                "allergens": ["glúten", "leite", "ovos"],
                "dietary_info": [],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 14 x 12 cm",
            },
            "QQ": {
                "allergens": ["glúten", "leite"],
                "dietary_info": ["vegetariano"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 14 x 12 cm",
            },
            "JB": {
                "allergens": ["glúten", "leite"],
                "dietary_info": [],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 26 x 6 cm",
            },
            "DL": {
                "allergens": ["glúten", "leite"],
                "dietary_info": [],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 16 x 6 cm",
            },
            "HO": {
                "allergens": ["glúten", "leite"],
                "dietary_info": [],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 16 x 6 cm",
            },
            "PG": {
                "allergens": ["glúten", "leite"],
                "dietary_info": ["vegetariano"],
                "serves": "1 pessoa",
                "approx_dimensions": "2 fatias grossas",
            },
            "TI": {
                "allergens": ["glúten", "leite"],
                "dietary_info": [],
                "serves": "2 a 3 pessoas",
                "approx_dimensions": "tábua com pães da casa",
            },
            "PPU": {
                "allergens": ["glúten", "leite", "ovos"],
                "dietary_info": ["vegetariano"],
                "serves": "1 pessoa",
                "approx_dimensions": "2 fatias",
            },
            "MS": {
                "allergens": ["glúten", "leite"],
                "dietary_info": ["vegetariano"],
                "serves": "1 pessoa",
                "approx_dimensions": "aprox. 12 x 10 cm",
            },
            "PU": {
                "allergens": ["leite", "ovos"],
                "dietary_info": ["vegetariano", "sem glúten"],
                "serves": "1 pessoa",
                "approx_dimensions": "taça individual",
            },
            "TJ": {
                "allergens": [],
                "dietary_info": ["vegetariano", "sem glúten"],
                "serves": "1 pessoa",
                "approx_dimensions": "taça individual",
            },
            "MT": {
                "allergens": ["mostarda"],
                "dietary_info": ["100% vegetal"],
                "serves": "pote 200 g",
                "approx_dimensions": "pote de vidro",
            },
            "BK": {
                "allergens": [],
                "dietary_info": [],
                "serves": "peça aprox. 200 g",
                "approx_dimensions": "embalado a vácuo",
            },
            "TP": {
                "allergens": [],
                "dietary_info": ["100% vegetal"],
                "serves": "pote 170 g",
                "approx_dimensions": "pote de vidro",
            },
            "PT": {
                "allergens": [],
                "dietary_info": ["100% vegetal"],
                "serves": "pote 170 g",
                "approx_dimensions": "pote de vidro",
            },
            "CX": {
                "allergens": [],
                "dietary_info": ["100% vegetal"],
                "serves": "vidro 200 g",
                "approx_dimensions": "vidro em conserva",
            },
            "GL": {
                "allergens": [],
                "dietary_info": ["100% vegetal"],
                "serves": "pote 28 g",
                "approx_dimensions": "pote mini de vidro",
            },
            "QC": {
                "allergens": ["leite"],
                "dietary_info": ["vegetariano"],
                "serves": "aprox. 250 g",
                "approx_dimensions": "caixa redonda",
            },
            "QP": {
                "allergens": ["leite"],
                "dietary_info": ["vegetariano"],
                "serves": "aprox. 300 g",
                "approx_dimensions": "peça embalada",
            },
            "GR": {
                "allergens": [],
                "dietary_info": ["100% vegetal"],
                "serves": "pacote 250 g",
                "approx_dimensions": "pacote com válvula",
            },
            "THL": {
                "allergens": [],
                "dietary_info": ["100% vegetal"],
                "serves": "lata 80 g",
                "approx_dimensions": "lata decorada",
            },
            "LN": {
                "allergens": ["glúten", "leite", "ovos"],
                "dietary_info": ["vegetariano"],
                "serves": "lata sortida",
                "approx_dimensions": "lata de presente",
            },
        }


        # NCM por produto (validar com o contador — ver docs/plans/FISCALMAN-PLAN.md).
        # CFOP/CSOSN/origem/PIS/COFINS NÃO vivem aqui: são resolvidos na emissão
        # pelo perfil fiscal (Fiscalman), a partir de `profile`. Todo o catálogo
        # atual é não-ST (perfil own_production → CFOP 5102/CSOSN 102, sem CEST).
        breads = {
            "BF", "BE", "MIB", "FE", "TB",
            "CGO", "CPX", "CI", "SK", "KP", "PH", "BRIOCHE-BURGER", "PAO-HOTDOG",
            "FOA", "CBT", "FOC", "MIF", "MICBT", "MIFOC",  # focaccia é pão
        }
        fiscal_ncm_by_sku = {
            # Folhados, doces e salgados de panificação/pastelaria (default).
            "default": "19059090",
            # Pães (NCM 1905.90.10).
            **dict.fromkeys(breads, "19059010"),
            # Bebidas preparadas na loja.
            "SS": "21011110",
            "CD": "21011110",
            "PS": "21011200",
            "MC": "21011200",
            "CE": "21011200",
            "FP": "21011200",
            "THC": "09024000",
            "THR": "09024000",
            "THS": "09024000",
            "THB": "09024000",
            "CV": "22021000",
            "SO": "22021000",
            "AG": "22011000",
            # Despensa (revenda/produção própria — validar com o contador).
            "MT": "21033010",
            "BK": "02101900",
            "TP": "20059900",
            "PT": "20059900",
            "CX": "20011000",
            "GL": "20079990",
            "QC": "04069020",
            "QP": "04061010",
            "GR": "09012100",
            "THL": "09022000",
            "LN": "19053100",
        }

        def fiscal_metadata_for_sku(sku: str) -> dict:
            return {
                "profile": "own_production",
                "ncm": fiscal_ncm_by_sku.get(sku, fiscal_ncm_by_sku["default"]),
                "unit": "UN",
            }

        # ⚠️ Voltaram do Yooga com código e preço reais, mas SEM ficha: alergênicos,
        # informação nutricional, dieta, porção e ingredientes são dado da casa —
        # e do tipo que ninguém inventa. Nascem despublicados de propósito; o
        # portão de completude lá embaixo é justamente quem cobra isso, e ele
        # está certo. Publicar é um passo do gestor, depois de preencher a ficha.
        sem_ficha = {
            # Os 41 seguem todos aqui, mesmo os que herdaram ficha dos "do dia".
            # Dois portões cobram, e os dois têm razão: o de completude quer
            # alergênicos e tabela nutricional (as fichas de "Folhado do dia" e
            # "Focaccia do dia" nunca tiveram as duas últimas — o que existia foi
            # herdado, o que não existia não se inventa), e o do storefront quer
            # compra web para todo produto publicado. Fabricar compra só para
            # passar no portão seria enganá-lo.
            "SL", "CL", "CQ", "MH", "MA", "CM", "BCH", "CN", "BH", "PR", "FOA",
            "DL", "HO", "HI", "CTV",
            "COC", "CH", "BN", "ANU", "ANP", "KBB", "MBBBG", "FA", "BAP",
            "BAX", "CF", "BA", "CGR", "SE", "PI", "BEP", "CBT", "FOC",
            "MIF", "MICBT", "MIFOC", "CPQ", "FF", "MFF", "MIHO", "JO",
        }

        products = {}
        for sku, name, desc, price_q, unit, shelf_life, sellable, image, weight_g, storage in products_data:
            p, _ = Product.objects.update_or_create(
                sku=sku,
                defaults={
                    "name": name,
                    "short_description": desc,
                    "base_price_q": price_q,
                    "unit": unit,
                    "shelf_life_days": shelf_life,
                    "is_published": sku not in sem_ficha,
                    "is_sellable": sellable,
                    "availability_policy": AvailabilityPolicy.PLANNED_OK,
                    "image_url": image,
                    "unit_weight_g": weight_g,
                    "storage_tip": storage,
                },
            )
            if sku in keywords_map:
                p.keywords.add(*keywords_map[sku])
            metadata = p.metadata if isinstance(p.metadata, dict) else {}
            existing_fiscal = metadata.get("fiscal") if isinstance(metadata.get("fiscal"), dict) else {}
            p.metadata = {
                **metadata,
                **PDP_METADATA.get(sku, {}),
                "fiscal": {
                    **fiscal_metadata_for_sku(sku),
                    **existing_fiscal,
                },
            }
            p.save(update_fields=["metadata"])
            products[sku] = p

        # Bundle: Combo Petit Dejeuner (Croissant + Mini Baguete)
        combo, _ = Product.objects.update_or_create(
            sku="COMBO-PETIT-DEJ",
            defaults={
                "name": "Combo Petit Déjeuner",
                "short_description": "Croissant + Mini Baguete (economia de R$ 3,00)",
                "base_price_q": 1900,
                "unit": "un",
                "is_published": True,
                "is_sellable": True,
                "availability_policy": AvailabilityPolicy.DEMAND_OK,
                "image_url": f"{IMG}/ct.webp",
            },
        )
        combo.keywords.add("combo", "cafe-da-manha", "promocao")
        combo.metadata = {
            **(combo.metadata if isinstance(combo.metadata, dict) else {}),
            "allergens": ["glúten", "leite", "ovos"],
            "dietary_info": ["vegetariano"],
            "serves": "1 pessoa",
            "approx_dimensions": "1 croissant + 1 mini baguete",
            "fiscal": {
                **fiscal_metadata_for_sku("COMBO-PETIT-DEJ"),
                **(
                    combo.metadata.get("fiscal", {})
                    if isinstance(combo.metadata, dict) and isinstance(combo.metadata.get("fiscal"), dict)
                    else {}
                ),
            },
        }
        combo.save(update_fields=["metadata"])
        products["COMBO-PETIT-DEJ"] = combo

        made_to_order_skus = [
            # bebidas preparadas na hora
            "SS", "CD", "PS", "MC",
            "THC", "THR", "THS", "THB",
            "CE", "FP",
            "CV", "SO", "AG",
            # montados na hora
            "CMO", "CMA", "CCOM",
            "QQ", "JB", "PG",
            "PPU", "TI",
        ]
        for sku in made_to_order_skus:
            product = products.get(sku)
            if product:
                product.availability_policy = AvailabilityPolicy.DEMAND_OK
                product.save(update_fields=["availability_policy"])

        # Direct-override ingredients + nutrition (products without Recipe).
        # Exercises the "manual override" path of the PDP data schema:
        # ``auto_filled=False`` in nutrition_facts blocks any later derivation.
        def nutrition(
            serving_size_g,
            servings_per_container,
            energy_kcal,
            carbohydrates_g,
            sugars_g,
            proteins_g,
            total_fat_g,
            saturated_fat_g,
            fiber_g,
            sodium_mg,
        ):
            return {
                "serving_size_g": serving_size_g,
                "servings_per_container": servings_per_container,
                "energy_kcal": energy_kcal,
                "carbohydrates_g": carbohydrates_g,
                "sugars_g": sugars_g,
                "proteins_g": proteins_g,
                "total_fat_g": total_fat_g,
                "saturated_fat_g": saturated_fat_g,
                "trans_fat_g": 0.0,
                "fiber_g": fiber_g,
                "sodium_mg": sodium_mg,
                "auto_filled": False,
            }

        DIRECT_OVERRIDES = {
            "BE": {
                "ingredients_text": (
                    "Farinha de trigo, água, fermento natural, gergelim, azeite extra virgem, sal. "
                    "CONTÉM: glúten e gergelim."
                ),
                "nutrition_facts": nutrition(100, 3, 265.0, 49.0, 1.5, 8.5, 3.8, 0.5, 3.1, 430.0),
            },
            "MIB": {
                "ingredients_text": (
                    "Farinha de trigo, água, fermento natural, azeite extra virgem, sal. "
                    "CONTÉM: glúten."
                ),
                "nutrition_facts": nutrition(100, 1, 245.0, 50.0, 1.4, 8.0, 1.4, 0.2, 2.5, 420.0),
            },
            "FE": {
                "ingredients_text": (
                    "Farinha de trigo, água, fermento natural, sal. "
                    "CONTÉM: glúten."
                ),
                "nutrition_facts": nutrition(100, 1, 240.0, 50.0, 1.2, 8.0, 1.0, 0.2, 2.4, 430.0),
            },
            "TB": {
                "ingredients_text": (
                    "Farinha de trigo, água, fermento natural, sal. "
                    "CONTÉM: glúten."
                ),
                "nutrition_facts": nutrition(100, 1, 240.0, 50.0, 1.2, 8.0, 1.0, 0.2, 2.4, 430.0),
            },
            "CGO": {
                "ingredients_text": (
                    "Farinha de trigo, farinha de trigo integral, água, fermento natural, farinha de centeio, sal. "
                    "CONTÉM: glúten."
                ),
                "nutrition_facts": nutrition(100, 5, 235.0, 46.0, 1.5, 8.3, 1.3, 0.2, 4.0, 390.0),
            },
            "CPX": {
                "ingredients_text": (
                    "Farinha de trigo, farinha de trigo integral, água, fermento natural, uvas-passas, "
                    "castanha de caju, castanha-do-pará, farinha de centeio, sal. "
                    "CONTÉM: glúten e castanhas."
                ),
                "nutrition_facts": nutrition(100, 6, 275.0, 48.0, 10.0, 8.0, 5.5, 0.8, 4.2, 340.0),
            },
            "PH": {
                "ingredients_text": (
                    "Farinha de trigo, água, fermento natural, azeite extra virgem, sal. "
                    "CONTÉM: glúten."
                ),
                "nutrition_facts": nutrition(100, 1, 245.0, 50.0, 1.4, 8.0, 1.4, 0.2, 2.5, 420.0),
            },
            "BRIOCHE-BURGER": {
                "ingredients_text": (
                    "Farinha de trigo, ovos, manteiga, leite, açúcar, fermento biológico, sal. "
                    "CONTÉM: glúten, leite e ovos."
                ),
                "nutrition_facts": nutrition(100, 2, 330.0, 46.0, 8.0, 9.0, 12.0, 7.0, 1.5, 360.0),
            },
            "PAO-HOTDOG": {
                "ingredients_text": (
                    "Farinha de trigo, ovos, manteiga, leite, açúcar, fermento biológico, sal. "
                    "CONTÉM: glúten, leite e ovos."
                ),
                "nutrition_facts": nutrition(80, 4, 265.0, 37.0, 6.0, 7.0, 9.5, 5.5, 1.2, 290.0),
            },
            "CO": {
                "ingredients_text": (
                    "Farinha de trigo, leite, ovos, manteiga, açúcar, creme de confeiteiro, fermento biológico, sal. "
                    "CONTÉM: glúten, leite e ovos."
                ),
                "nutrition_facts": nutrition(100, 1, 315.0, 43.0, 14.0, 7.0, 12.0, 7.0, 1.4, 250.0),
            },
            "ME": {
                "ingredients_text": (
                    "Farinha de trigo, leite, ovos, manteiga, açúcar, fermento biológico, sal. "
                    "CONTÉM: glúten, leite e ovos."
                ),
                "nutrition_facts": nutrition(100, 1, 335.0, 52.0, 15.0, 8.0, 10.0, 6.0, 1.5, 250.0),
            },
            "CMO": {
                "ingredients_text": (
                    "Pão de forma artesanal, molho bechamel, presunto, queijo gruyere, manteiga. "
                    "CONTÉM: glúten e leite."
                ),
                "nutrition_facts": nutrition(250, 1, 620.0, 42.0, 8.0, 28.0, 38.0, 22.0, 2.5, 1180.0),
            },
            "CMA": {
                "ingredients_text": (
                    "Pão de forma artesanal, molho bechamel, presunto, queijo gruyere, manteiga, ovo. "
                    "CONTÉM: glúten, leite e ovos."
                ),
                "nutrition_facts": nutrition(290, 1, 700.0, 43.0, 8.0, 34.0, 45.0, 24.0, 2.5, 1260.0),
            },
            "COMBO-PETIT-DEJ": {
                "ingredients_text": (
                    "Composto por Croissant Tradicional e Mini Baguete. "
                    "CONTÉM: glúten, leite e ovos."
                ),
                "nutrition_facts": nutrition(200, 1, 610.0, 74.0, 8.0, 14.0, 27.0, 16.0, 3.2, 620.0),
            },
            "SS": {
                "ingredients_text": "Café espresso. NÃO CONTÉM GLÚTEN.",
                "nutrition_facts": nutrition(40, 1, 2.0, 0.0, 0.0, 0.1, 0.0, 0.0, 0.0, 0.0),
            },
            "PS": {
                "ingredients_text": (
                    "Café espresso e leite integral vaporizado. "
                    "CONTÉM: leite. NÃO CONTÉM GLÚTEN."
                ),
                "nutrition_facts": nutrition(180, 1, 105.0, 9.0, 9.0, 6.0, 5.5, 3.4, 0.0, 85.0),
            },
            "CD": {
                "ingredients_text": (
                    "Café coado: água filtrada e café em grão da casa."
                ),
                "nutrition_facts": nutrition(200, 1, 5.0, 0.8, 0.0, 0.3, 0.0, 0.0, 0.0, 5.0),
            },
            "MC": {
                "ingredients_text": (
                    "Espresso, leite integral vaporizado e chocolate da casa. CONTÉM: leite."
                ),
                "nutrition_facts": nutrition(200, 1, 180.0, 22.0, 18.0, 7.0, 7.0, 4.5, 0.5, 80.0),
            },
            "THC": {
                "ingredients_text": (
                    "Infusão do blend Camille da casa."
                ),
                "nutrition_facts": nutrition(400, 2, 2.0, 0.4, 0.0, 0.0, 0.0, 0.0, 0.0, 2.0),
            },
            "THR": {
                "ingredients_text": (
                    "Infusão do blend Rouge da casa."
                ),
                "nutrition_facts": nutrition(400, 2, 2.0, 0.4, 0.0, 0.0, 0.0, 0.0, 0.0, 2.0),
            },
            "THS": {
                "ingredients_text": (
                    "Infusão do blend Sophie da casa."
                ),
                "nutrition_facts": nutrition(400, 2, 2.0, 0.4, 0.0, 0.0, 0.0, 0.0, 0.0, 2.0),
            },
            "THB": {
                "ingredients_text": (
                    "Infusão do blend Bleu da casa."
                ),
                "nutrition_facts": nutrition(400, 2, 2.0, 0.4, 0.0, 0.0, 0.0, 0.0, 0.0, 2.0),
            },
            "HI": {
                "ingredients_text": (
                    "Infusão gelada do blend do dia, levemente adoçada."
                ),
                "nutrition_facts": nutrition(300, 1, 40.0, 10.0, 9.0, 0.0, 0.0, 0.0, 0.0, 5.0),
            },
            "CTV": {
                "ingredients_text": (
                    "Infusão gelada do blend do dia, levemente adoçada."
                ),
                "nutrition_facts": nutrition(300, 1, 40.0, 10.0, 9.0, 0.0, 0.0, 0.0, 0.0, 5.0),
            },
            "CE": {
                "ingredients_text": (
                    "Café gelado da casa com sorvete de baunilha. CONTÉM: leite."
                ),
                "nutrition_facts": nutrition(300, 1, 220.0, 26.0, 22.0, 4.0, 11.0, 7.0, 0.0, 60.0),
            },
            "FP": {
                "ingredients_text": (
                    "Café ou chocolate ou frutas vermelhas, leite e gelo batidos. CONTÉM: leite."
                ),
                "nutrition_facts": nutrition(300, 1, 230.0, 30.0, 26.0, 5.0, 10.0, 6.5, 0.3, 70.0),
            },
            "CV": {
                "ingredients_text": (
                    "Água gaseificada, xarope artesanal do dia e creme. CONTÉM: leite."
                ),
                "nutrition_facts": nutrition(300, 1, 120.0, 30.0, 28.0, 0.0, 0.0, 0.0, 0.0, 15.0),
            },
            "SO": {
                "ingredients_text": (
                    "Água gaseificada e xarope artesanal de laranja da casa."
                ),
                "nutrition_facts": nutrition(300, 1, 90.0, 22.0, 20.0, 0.3, 0.0, 0.0, 0.2, 10.0),
            },
            "AG": {
                "ingredients_text": (
                    "Água mineral natural, com ou sem gás."
                ),
                "nutrition_facts": nutrition(500, 1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 10.0),
            },
            "CCOM": {
                "ingredients_text": (
                    "Pão de fermentação natural, presunto, queijo gruyere, molho bechamel, ovo e acompanhamento. CONTÉM: glúten, leite e ovos."
                ),
                "nutrition_facts": nutrition(320, 1, 620.0, 42.0, 6.0, 32.0, 36.0, 18.0, 2.5, 1250.0),
            },
            "QQ": {
                "ingredients_text": (
                    "Shokupan da casa, queijos selecionados e manteiga. CONTÉM: glúten e leite."
                ),
                "nutrition_facts": nutrition(250, 1, 520.0, 44.0, 6.0, 22.0, 28.0, 16.0, 2.0, 980.0),
            },
            "JB": {
                "ingredients_text": (
                    "Baguette de tradição, manteiga francesa e presunto. CONTÉM: glúten e leite."
                ),
                "nutrition_facts": nutrition(250, 1, 480.0, 52.0, 3.0, 22.0, 20.0, 11.0, 2.5, 1100.0),
            },
            "DL": {
                "ingredients_text": (
                    "Pão amanteigado da casa com o recheio do dia (deli de milho e bacon ou salsicha artesanal). CONTÉM: glúten e leite."
                ),
                "nutrition_facts": nutrition(180, 1, 380.0, 40.0, 5.0, 14.0, 18.0, 7.0, 1.8, 850.0),
            },
            "HO": {
                "ingredients_text": (
                    "Pão amanteigado da casa com o recheio do dia (deli de milho e bacon ou salsicha artesanal). CONTÉM: glúten e leite."
                ),
                "nutrition_facts": nutrition(180, 1, 380.0, 40.0, 5.0, 14.0, 18.0, 7.0, 1.8, 850.0),
            },
            "PG": {
                "ingredients_text": (
                    "Fatias grossas de pão da casa na chapa com manteiga. CONTÉM: glúten e leite."
                ),
                "nutrition_facts": nutrition(150, 1, 320.0, 40.0, 4.0, 9.0, 14.0, 8.0, 2.0, 480.0),
            },
            "TI": {
                "ingredients_text": (
                    "Seleção de charcutaria, queijos e patês da casa com pães. CONTÉM: glúten e leite."
                ),
                "nutrition_facts": nutrition(100, 5, 320.0, 12.0, 2.0, 16.0, 24.0, 12.0, 1.0, 900.0),
            },
            "PPU": {
                "ingredients_text": (
                    "Brioche da casa, ovos, leite, açúcar e canela, dourado na chapa. CONTÉM: glúten, leite e ovos."
                ),
                "nutrition_facts": nutrition(180, 1, 420.0, 48.0, 22.0, 11.0, 20.0, 11.0, 1.5, 320.0),
            },
            "MS": {
                "ingredients_text": (
                    "Shokupan da casa, chantilly e frutas frescas. CONTÉM: glúten e leite."
                ),
                "nutrition_facts": nutrition(200, 1, 310.0, 38.0, 24.0, 6.0, 15.0, 9.0, 1.5, 180.0),
            },
            "PU": {
                "ingredients_text": (
                    "Leite, ovos, açúcar e baunilha, com calda de caramelo, chantilly e frutas. CONTÉM: leite e ovos."
                ),
                "nutrition_facts": nutrition(150, 1, 260.0, 32.0, 28.0, 6.0, 12.0, 7.0, 0.0, 90.0),
            },
            "TJ": {
                "ingredients_text": (
                    "Infusão de chá da casa, açúcar e ágar."
                ),
                "nutrition_facts": nutrition(150, 1, 90.0, 21.0, 19.0, 1.0, 0.0, 0.0, 0.0, 15.0),
            },
            "MT": {
                "ingredients_text": (
                    "Grãos de mostarda, vinagre, especiarias e sal. CONTÉM: mostarda."
                ),
                "nutrition_facts": nutrition(10, 20, 8.0, 0.6, 0.2, 0.5, 0.4, 0.0, 0.2, 120.0),
            },
            "BK": {
                "ingredients_text": (
                    "Barriga suína curada e defumada na casa, sal e especiarias."
                ),
                "nutrition_facts": nutrition(30, 7, 160.0, 0.5, 0.0, 10.0, 13.0, 4.5, 0.0, 580.0),
            },
            "TP": {
                "ingredients_text": (
                    "Azeitonas pretas, alcaparras, azeite extra virgem e ervas."
                ),
                "nutrition_facts": nutrition(20, 8, 45.0, 1.0, 0.2, 0.4, 4.5, 0.7, 0.6, 180.0),
            },
            "PT": {
                "ingredients_text": (
                    "Berinjela, abobrinha, tomate, pimentão, cebola, azeite e ervas."
                ),
                "nutrition_facts": nutrition(20, 8, 25.0, 2.5, 1.2, 0.5, 1.5, 0.2, 0.8, 95.0),
            },
            "CX": {
                "ingredients_text": (
                    "Pepinos, vinagre, endro e especiarias."
                ),
                "nutrition_facts": nutrition(30, 7, 4.0, 0.7, 0.4, 0.2, 0.0, 0.0, 0.3, 240.0),
            },
            "GL": {
                "ingredients_text": (
                    "Frutas e suco de uva concentrado. 100% fruta."
                ),
                "nutrition_facts": nutrition(28, 1, 60.0, 15.0, 14.0, 0.1, 0.0, 0.0, 0.3, 5.0),
            },
            "QC": {
                "ingredients_text": (
                    "Leite de vaca pasteurizado, fermento lático, coalho e sal. CONTÉM: leite."
                ),
                "nutrition_facts": nutrition(30, 8, 90.0, 0.2, 0.2, 6.0, 7.0, 4.5, 0.0, 240.0),
            },
            "QP": {
                "ingredients_text": (
                    "Leite de vaca, fermento lático, coalho e sal. CONTÉM: leite."
                ),
                "nutrition_facts": nutrition(30, 10, 110.0, 0.5, 0.3, 7.0, 9.0, 5.5, 0.0, 200.0),
            },
            "GR": {
                "ingredients_text": (
                    "Café 100% arábica em grão, torra artesanal da casa."
                ),
                "nutrition_facts": nutrition(10, 25, 2.0, 0.0, 0.0, 0.3, 0.0, 0.0, 0.0, 0.0),
            },
            "THL": {
                "ingredients_text": (
                    "Blend de chás e botânicos da casa em folhas."
                ),
                "nutrition_facts": nutrition(2, 40, 1.0, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0),
            },
            "LN": {
                "ingredients_text": (
                    "Madeleines sortidas e biscoitos amanteigados da casa. CONTÉM: glúten, leite e ovos."
                ),
                "nutrition_facts": nutrition(40, 10, 190.0, 24.0, 12.0, 2.5, 9.5, 6.0, 0.6, 95.0),
            },
        }

        for sku, payload in DIRECT_OVERRIDES.items():
            if sku in products:
                p = products[sku]
                p.ingredients_text = payload["ingredients_text"]
                p.nutrition_facts = payload["nutrition_facts"]
                p.save(update_fields=["ingredients_text", "nutrition_facts"])

        # Despensa: preços provisórios até a lista do Pablo (rastreável no Admin).
        despensa_tbd_skus = [
            "MT", "BK", "TP", "PT",
            "CX", "GL", "QC", "QP",
            "GR", "THL", "LN",
        ]
        for sku in despensa_tbd_skus:
            p = products[sku]
            p.metadata["price_tbd"] = True
            p.save(update_fields=["metadata"])

        # Pães que aguentam o dia seguinte: a VALIDADE diz isso agora
        # (shelf_life_days=1 → o lote vence amanhã e sobrevive ao fechamento
        # de hoje). O antigo flag allows_next_day_sale morreu com o D-1 (C4).
        next_day_skus = ["BF", "CI", "FE", "TB", "PH"]
        for sku in next_day_skus:
            p = products[sku]
            p.shelf_life_days = 1
            p.save(update_fields=["shelf_life_days"])

        # Lead time de encomenda (Pablo, 2026-07-24): fermentação natural longa —
        # registrar DEMANDA (encomenda sem fornada planejada) exige antecedência.
        # Ver Product.metadata.lead_time_hours em docs/reference/data-schemas.md.
        lead_time_hours_by_sku = {
            "CGO": 24,
            "CPX": 24,
        }
        for sku, hours in lead_time_hours_by_sku.items():
            p = products[sku]
            p.metadata["lead_time_hours"] = hours
            p.save(update_fields=["metadata"])

        # Bundle components
        ProductComponent.objects.filter(parent=combo).delete()
        ProductComponent.objects.create(parent=combo, component=products["CT"], qty=Decimal("1"))
        ProductComponent.objects.create(parent=combo, component=products["MIB"], qty=Decimal("1"))

        # Collections — a taxonomia do Cardápio 2027: o copo lidera; `mercearia`
        # e `combos` existem mas ficam fora dos feeds (menu impresso/TVs).
        # `balcao` foi extinta (decisão do dono, 17/08): agrupava por ONDE o
        # produto era vendido, não pelo que ele é, e por isso nunca classificou
        # nada. Os 7 produtos dela foram redistribuídos.
        collection_refs = [
            "bebidas-quentes",
            "bebidas-geladas",
            "torneira",
            "rusticos",
            "finos",
            "salgados",
            "doces",
            "combos",
            "mercearia",
        ]
        # Limpa também as coleções da taxonomia anterior (refs que saíram).
        CollectionItem.objects.filter(
            collection__ref__in=collection_refs + ["macios", "folhados", "balcao", "despensa"]
        ).delete()
        Collection.objects.filter(ref__in=["macios", "folhados", "balcao", "despensa"]).delete()

        collections_by_ref = {}
        for order, (ref, name) in enumerate(
            [
                ("bebidas-quentes", "Bebidas quentes"),
                ("bebidas-geladas", "Bebidas geladas"),
                ("torneira", "Sodas artesanais"),
                ("rusticos", "Rústicos"),
                ("finos", "Finos"),
                ("salgados", "Salgados"),
                ("doces", "Doces"),
                ("combos", "Combos"),
                ("mercearia", "Mercearia"),
            ],
            start=1,
        ):
            collections_by_ref[ref], _ = Collection.objects.update_or_create(
                ref=ref,
                defaults={"name": name, "is_active": True, "sort_order": order},
            )

        collection_skus = {
            "bebidas-quentes": [
                "SS", "CD", "PS", "MC",
                "THC", "THR", "THS", "THB",
                # voltaram do Yooga (18/08)
                "SL", "CL", "CQ", "MH",
            ],
            "bebidas-geladas": ["CE", "FP", "AG",
                # voltaram do Yooga (18/08)
                "HI", "CTV",
            ],
            "torneira": ["CV", "SO"],
            "rusticos": [
                # Vindos da extinta "balcao" (17/08): três pães de casca e o pão
                # de hambúrguer, que o dono classificou aqui apesar da massa macia.
                "FE", "TB", "MIB", "PH",
                "BF", "CGO", "CPX", "CI",
                "BE",
                # voltaram do Yooga (18/08)
                "FA", "BAP", "BAX", "CF", "BA", "CGR", "SE", "PI", "BEP", "FOA", "CBT", "FOC", "MIF", "MICBT", "MIFOC",
            ],
            "finos": [
                # Vindos da extinta "balcao" (17/08): buns em pacote, massa
                # enriquecida, na mesma família dos pães japoneses daqui.
                "BRIOCHE-BURGER", "PAO-HOTDOG",
                "CT", "PC", "SK",
                "KP", "ME", "ANC", "CO",
                # voltaram do Yooga (18/08)
                "CM", "BCH", "CN", "PR", "COC", "CH", "BN", "ANU", "ANP", "KBB", "MBBBG",
            ],
            "salgados": [
                "CMO", "CMA", "CCOM",
                "QQ", "JB", "PG", "TI",
                # voltaram do Yooga (18/08)
                "CPQ", "FF", "MFF", "HO", "MIHO", "DL", "JO",
            ],
            "doces": ["PPU", "MS", "MD", "PU", "TJ",
                # voltaram do Yooga (18/08)
                "BH", "MA",
            ],
            # Bundle não é categoria de produto: o combo tem coleção própria
            # para não inflar Rústicos nem Finos com um item que é os dois.
            "combos": ["COMBO-PETIT-DEJ"],
            "mercearia": [
                "MT", "BK", "TP", "PT",
                "CX", "GL", "QC", "QP",
                "GR", "THL", "LN",
            ],
        }
        # ── As coleções "do dia" ──
        # O cardápio 2027 tinha "Folhado do dia" como PRODUTO, e isso custava
        # caro: a fornada precisa de output_sku real, o estoque precisa separar
        # sobra de falta por item, e os preços divergem (focaccia de alecrim
        # R$ 28, a de cebola/bacon/tomilho R$ 36). Aqui o rotativo é o que
        # sempre foi — uma curadoria —, e o produto por baixo é o de verdade.
        #
        # ⚠️ Vínculo SECUNDÁRIO: o produto continua morando na sua categoria.
        # "Chausson" é Finos e aparece em "Folhado do dia"; não é uma coisa ou
        # outra.
        colecoes_do_dia = [
            ("folhado-do-dia", "Folhado do dia", ["CN", "BH", "PR"]),
            ("focaccia-do-dia", "Focaccia do dia", ["FOA", "CBT", "FOC", "MIF", "MICBT", "MIFOC"]),
            ("salgado-do-dia", "Salgado do dia", ["DL", "HO", "MIHO", "FF", "MFF"]),
            ("cha-gelado-do-dia", "Chá gelado do dia", ["HI", "CTV"]),
        ]
        for ordem, (ref, nome, skus) in enumerate(colecoes_do_dia, start=len(collections_by_ref)):
            colecao, _ = Collection.objects.update_or_create(
                ref=ref,
                defaults={"name": nome, "is_active": True, "sort_order": ordem},
            )
            collections_by_ref[ref] = colecao
            for i, sku in enumerate(skus):
                CollectionItem.objects.update_or_create(
                    collection=colecao, product=products[sku],
                    defaults={"sort_order": i, "is_primary": False},
                )

        for ref, skus in collection_skus.items():
            for i, sku in enumerate(skus):
                CollectionItem.objects.create(
                    collection=collections_by_ref[ref], product=products[sku],
                    sort_order=i, is_primary=True,
                )

        # Listings
        pdv, _ = Listing.objects.update_or_create(
            ref="pdv",
            defaults={"name": "PDV", "is_active": True, "priority": 10},
        )
        ifood, _ = Listing.objects.update_or_create(
            ref="ifood",
            defaults={"name": "iFood", "is_active": True, "priority": 3},
        )
        web, _ = Listing.objects.update_or_create(
            ref="web",
            defaults={"name": "Loja online", "is_active": True, "priority": 7},
        )

        # Listing items (all products in all listings)
        # iFood uses pricing.policy="external": the marketplace controls final prices,
        # so listing prices are reference-only — no markup stored on our side.
        markup_map = {"pdv": 0, "ifood": 0, "web": 0}
        for listing_obj in [pdv, ifood, web]:
            ListingItem.objects.filter(listing=listing_obj).delete()
            markup = Decimal(markup_map[listing_obj.ref]) / 100
            for _sku, product in products.items():
                price_q = int(product.base_price_q * (1 + markup))
                ListingItem.objects.create(
                    listing=listing_obj,
                    product=product,
                    price_q=price_q,
                    is_published=True,
                    is_sellable=product.is_sellable,
                )

        self.stdout.write(
            f"  ✅ {len(products)} produtos "
            f"({Product.objects.filter(unit_weight_g__isnull=False).count()} com peso), "
            f"{len(collection_refs)} colecoes, 4 listagens"
        )
        return products

    # ────────────────────────────────────────────────────────────────
    # Estoque (Stockman)
    # ────────────────────────────────────────────────────────────────

    def _seed_positions(self):
        self.stdout.write("  📍 Posicoes de estoque...")

        # A sobra NÃO tem posição própria: o LOTE (validade/conformidade) diz
        # o que fica e o que perde no fechamento (C4). A antiga "ontem" morreu.
        positions = {}
        for ref, name, kind, saleable, default in [
            ("deposito", "Depósito", PositionKind.PHYSICAL, False, False),
            ("vitrine", "Vitrine / Exposição", PositionKind.PHYSICAL, True, False),
            ("producao", "Área de Produção", PositionKind.PHYSICAL, False, False),
            ("massa", "Massa", PositionKind.PROCESS, False, True),
            ("molde", "Molde", PositionKind.PROCESS, False, False),
            ("forno", "Forno", PositionKind.PROCESS, False, False),
        ]:
            p, _ = Position.objects.update_or_create(
                ref=ref,
                defaults={
                    "name": name,
                    "kind": kind,
                    "is_saleable": saleable,
                    "is_default": default,
                },
            )
            positions[ref] = p

        self.stdout.write("  ✅ 7 posicoes")
        return positions

    def _seed_stock(self, products, positions):
        self.stdout.write("  📊 Estoque inicial...")

        vitrine = positions["vitrine"]
        # Quantidades calibradas com as médias diárias REAIS auferidas dos XMLs de
        # NFC-e (acervo _MASTER: jun/2019 pré-pandemia ~816 un/dia; jun/2021 ~601
        # un/dia; sábado +24% — coberto pelo multiplicador 1.25 de sex/sáb).
        # Madeleine é ~11% do volume da casa; viennoiserie doce ~25%.
        # Ver docs/reports/seed_calibration_2026-07-24.md.
        stock_data = {
            # Rústicos — volumes herdam a calibração dos antecessores
            "BF": 22,
            "BE": 12,
            "CGO": 16,
            "CPX": 8,
            "CI": 24,
            # Finos
            "CT": 42,
            "PC": 36,
            "SK": 18,
            "KP": 8,
            "ME": 11,
            "ANC": 16,
            "CO": 20,
            # Salgados de vitrine
            "CMO": 10,
            "CMA": 8,
            "CCOM": 6,
            "QQ": 10,
            "JB": 10,
            "PG": 10,
            "TI": 4,
            # Doces
            "MD": 68,
            "PPU": 8,
            "MS": 8,
            "PU": 10,
            "TJ": 8,
            "COMBO-PETIT-DEJ": 8,
            # Balcão
            "FE": 20,
            "TB": 24,
            "MIB": 18,
            "PH": 20,
            "BRIOCHE-BURGER": 12,
            "PAO-HOTDOG": 12,
            # Bebidas com estoque físico (água engarrafada)
            "AG": 48,
            # Despensa
            "MT": 8,
            "BK": 6,
            "TP": 8,
            "PT": 8,
            "CX": 6,
            "GL": 24,
            "QC": 6,
            "QP": 6,
            "GR": 12,
            "THL": 10,
            "LN": 8,
        }

        for sku, qty in stock_data.items():
            if sku in products:
                stock.receive(
                    quantity=Decimal(str(qty)),
                    sku=sku,
                    position=vitrine,
                    reason=f"Estoque inicial seed Nelson: {sku}",
                )

        # Sobras de ontem no cenário novo: LOTES datados de ontem, na própria
        # vitrine (~5-8% da produção do dia). Quem decide o destino é a
        # validade: shelf_life 1 vence HOJE (o fechamento baixa como
        # perda_vencido), e o canal remoto respeita os gates de lote (C2).
        from datetime import timedelta as _td

        from shopman.stockman.models import Batch as _Batch

        yesterday = date.today() - _td(days=1)
        leftover_items = [
            ("BF", 2),
            ("FE", 2),
            ("TB", 3),
            ("CI", 2),
            ("PH", 3),
            ("MD", 5),
            ("CT", 3),
            ("PC", 2),
        ]
        for sku, qty in leftover_items:
            if sku not in products:
                continue
            shelf = products[sku].shelf_life_days or 0
            lot_ref = f"{sku}-{yesterday:%Y%m%d}-SOBRA"
            _Batch.objects.update_or_create(
                ref=lot_ref,
                defaults={
                    "sku": sku,
                    "production_date": yesterday,
                    "expiry_date": yesterday + _td(days=shelf),
                },
            )
            stock.receive(
                quantity=Decimal(str(qty)),
                sku=sku,
                position=positions["vitrine"],
                batch=lot_ref,
                reason=f"Sobra de ontem (lote datado): {sku}",
            )

        self.stdout.write(
            f"  ✅ Estoque para {len(stock_data)} produtos + {len(leftover_items)} sobras de ontem (lotes datados)"
        )

    # ────────────────────────────────────────────────────────────────
    # Receitas (Craftsman)
    # ────────────────────────────────────────────────────────────────

    def _seed_recipes(self):
        self.stdout.write("  📋 Receitas...")

        recipes_data = [
            {
                "ref": "massa-levain-clara",
                "name": "Massa Levain Clara",
                "output_sku": "MASSA-LEVAIN-CLARA",
                "batch_size": Decimal("10"),
                "items": [
                    ("FARINHA-T65", Decimal("5.000")),
                    ("AGUA-FILTRADA", Decimal("3.500")),
                    ("FERMENTO-NAT", Decimal("1.500")),
                    ("SAL", Decimal("0.100")),
                    ("MALTE", Decimal("0.020")),
                ],
            },
            {
                "ref": "massa-campagne",
                "name": "Massa Campagne",
                "output_sku": "MASSA-CAMPAGNE",
                "batch_size": Decimal("10"),
                "items": [
                    ("FARINHA-T65", Decimal("2.500")),
                    ("FARINHA-INT", Decimal("2.500")),
                    ("CENTEIO", Decimal("0.600")),
                    ("AGUA-FILTRADA", Decimal("3.500")),
                    ("FERMENTO-NAT", Decimal("1.500")),
                    ("SAL", Decimal("0.100")),
                ],
            },
            {
                "ref": "massa-alta-hidratacao",
                "name": "Massa Alta Hidratação",
                "output_sku": "MASSA-ALTA-HIDRATACAO",
                "batch_size": Decimal("10"),
                "items": [
                    ("FARINHA-T55", Decimal("5.000")),
                    ("AGUA-FILTRADA", Decimal("4.000")),
                    ("FERMENTO-NAT", Decimal("1.500")),
                    ("AZEITE", Decimal("0.250")),
                    ("SAL", Decimal("0.100")),
                ],
            },
            {
                "ref": "massa-paes-macios",
                "name": "Massa Pães Macios",
                "output_sku": "MASSA-PAES-MACIOS",
                "batch_size": Decimal("10"),
                "items": [
                    ("FARINHA-T55", Decimal("5.000")),
                    ("LEITE", Decimal("2.000")),
                    ("MANTEIGA-FR", Decimal("0.700")),
                    ("ACUCAR", Decimal("0.350")),
                    ("FERMENTO-BIO", Decimal("0.150")),
                    ("SAL", Decimal("0.100")),
                ],
            },
            {
                "ref": "massa-folhada",
                "name": "Massa Folhada",
                "output_sku": "MASSA-FOLHADA",
                "batch_size": Decimal("10"),
                "items": [
                    ("FARINHA-T45", Decimal("4.800")),
                    ("MANTEIGA-FR", Decimal("2.400")),
                    ("LEITE", Decimal("1.200")),
                    ("ACUCAR", Decimal("0.450")),
                    ("FERMENTO-BIO", Decimal("0.180")),
                    ("SAL", Decimal("0.090")),
                    ("OVOS", Decimal("0.300")),
                ],
            },
            {
                "ref": "massa-brioche",
                "name": "Massa Brioche",
                "output_sku": "MASSA-BRIOCHE",
                "batch_size": Decimal("10"),
                "items": [
                    ("FARINHA-T45", Decimal("4.000")),
                    ("MANTEIGA-FR", Decimal("2.000")),
                    ("OVOS", Decimal("1.200")),
                    ("ACUCAR", Decimal("0.600")),
                    ("FERMENTO-BIO", Decimal("0.160")),
                    ("SAL", Decimal("0.080")),
                ],
            },
            {
                # Preparo-base não-massa: a produção real tem recheios, cremes
                # e infusões prontos ANTES da montagem — não só massas.
                "ref": "recheio-maca",
                "name": "Recheio de Maçã",
                "output_sku": "RECHEIO-MACA",
                "batch_size": Decimal("5"),
                "items": [
                    ("MACA", Decimal("3.800")),
                    ("ACUCAR", Decimal("1.100")),
                    ("CANELA", Decimal("0.060")),
                    ("LIMAO", Decimal("0.120")),
                ],
            },
            {
                "ref": "baguete",
                "name": "Baguette de Tradition",
                "output_sku": "BF",
                "batch_size": Decimal("25"),
                "items": [
                    ("MASSA-LEVAIN-CLARA", Decimal("10.000")),
                ],
            },
            {
                "ref": "campagne",
                "name": "Pain de Campagne",
                "output_sku": "CGO",
                "batch_size": Decimal("10"),
                "items": [
                    ("MASSA-CAMPAGNE", Decimal("8.200")),
                ],
            },
            {
                "ref": "ciabatta",
                "name": "Ciabatta",
                "output_sku": "CI",
                "batch_size": Decimal("20"),
                "items": [
                    ("MASSA-ALTA-HIDRATACAO", Decimal("7.500")),
                ],
            },
            {
                "ref": "focaccia-dia",
                "name": "Focaccia do dia",
                "output_sku": "FOA",
                "batch_size": Decimal("8"),
                "items": [
                    ("MASSA-ALTA-HIDRATACAO", Decimal("5.200")),
                    ("ALECRIM", Decimal("0.030")),
                ],
            },
            {
                "ref": "shokupan",
                "name": "Shokupan",
                "output_sku": "SK",
                "batch_size": Decimal("12"),
                "items": [
                    ("MASSA-PAES-MACIOS", Decimal("6.400")),
                ],
            },
            {
                "ref": "kuro-pan",
                "name": "Kuro Pan",
                "output_sku": "KP",
                "batch_size": Decimal("8"),
                "items": [
                    ("MASSA-PAES-MACIOS", Decimal("4.600")),
                    ("CHOCOLATE-70", Decimal("0.400")),
                ],
            },
            {
                "ref": "croissant",
                "name": "Croissant Manteiga",
                "output_sku": "CT",
                "batch_size": Decimal("48"),
                "items": [
                    ("MASSA-FOLHADA", Decimal("8.500")),
                ],
            },
            {
                "ref": "pain-chocolat",
                "name": "Pain au Chocolat",
                "output_sku": "PC",
                "batch_size": Decimal("36"),
                "items": [
                    ("MASSA-FOLHADA", Decimal("6.500")),
                    ("CHOCOLATE-70", Decimal("0.720")),
                ],
            },
            {
                "ref": "animalzinho",
                "name": "Animalzinho",
                "output_sku": "ANC",
                "batch_size": Decimal("16"),
                "items": [
                    ("MASSA-BRIOCHE", Decimal("6.000")),
                ],
            },
            {
                "ref": "folhado-dia",
                "name": "Folhado do dia",
                "output_sku": "CN",
                "batch_size": Decimal("12"),
                "items": [
                    ("MASSA-FOLHADA", Decimal("4.600")),
                    ("RECHEIO-MACA", Decimal("0.810")),
                ],
            },
            {
                "ref": "madeleine",
                "name": "Madeleine",
                "output_sku": "MD",
                "batch_size": Decimal("24"),
                "items": [
                    ("FARINHA-T45", Decimal("0.500")),
                    ("MANTEIGA-FR", Decimal("0.500")),
                    ("OVOS", Decimal("0.400")),
                    ("ACUCAR", Decimal("0.300")),
                    ("LIMAO", Decimal("0.020")),
                ],
            },
        ]

        # Perfil de insumo (valores aproximados por 100g). Alimenta
        # RecipeItem.meta e, via signal, materializa no PDP:
        # - nutrition → Product.nutrition_facts (soma) + ingredients_text (label);
        # - allergens + diet → Product.metadata.allergens/dietary_info (WP-7):
        #   alérgenos = união; vegano só se TODOS vegan; "sem X" se NENHUM tem X.
        # Ref: TACO / USDA simplificado — valores didáticos.
        INGREDIENT_PROFILES = {
            "FARINHA-T65":  {"label": "Farinha de trigo T65",   "allergens": ["glúten"], "diet": "vegan", "nutrition": {"energy_kcal": 364, "carbohydrates_g": 76, "sugars_g": 0.3, "proteins_g": 10, "total_fat_g": 1.0, "saturated_fat_g": 0.2, "trans_fat_g": 0, "fiber_g": 2.7, "sodium_mg": 2}},
            "FARINHA-T55":  {"label": "Farinha de trigo T55",   "allergens": ["glúten"], "diet": "vegan", "nutrition": {"energy_kcal": 364, "carbohydrates_g": 76, "sugars_g": 0.3, "proteins_g": 10, "total_fat_g": 1.0, "saturated_fat_g": 0.2, "trans_fat_g": 0, "fiber_g": 2.7, "sodium_mg": 2}},
            "FARINHA-T45":  {"label": "Farinha de trigo T45",   "allergens": ["glúten"], "diet": "vegan", "nutrition": {"energy_kcal": 364, "carbohydrates_g": 76, "sugars_g": 0.3, "proteins_g": 10, "total_fat_g": 1.0, "saturated_fat_g": 0.2, "trans_fat_g": 0, "fiber_g": 2.7, "sodium_mg": 2}},
            "FARINHA-INT":  {"label": "Farinha de trigo integral", "allergens": ["glúten"], "diet": "vegan", "nutrition": {"energy_kcal": 340, "carbohydrates_g": 72, "sugars_g": 0.4, "proteins_g": 13, "total_fat_g": 2.5, "saturated_fat_g": 0.4, "trans_fat_g": 0, "fiber_g": 10.7, "sodium_mg": 2}},
            "CENTEIO":      {"label": "Farinha de centeio",     "allergens": ["glúten"], "diet": "vegan", "nutrition": {"energy_kcal": 338, "carbohydrates_g": 76, "sugars_g": 1.0, "proteins_g": 10, "total_fat_g": 1.7, "saturated_fat_g": 0.2, "trans_fat_g": 0, "fiber_g": 15.0, "sodium_mg": 2}},
            "AGUA-FILTRADA": {"label": "Água filtrada",         "allergens": [], "diet": "vegan", "nutrition": {"energy_kcal": 0,   "carbohydrates_g": 0,  "sugars_g": 0,   "proteins_g": 0,  "total_fat_g": 0,   "saturated_fat_g": 0,   "trans_fat_g": 0, "fiber_g": 0,    "sodium_mg": 0}},
            "FERMENTO-NAT": {"label": "Fermento natural (levain)", "allergens": ["glúten"], "diet": "vegan", "nutrition": {"energy_kcal": 220, "carbohydrates_g": 45, "sugars_g": 0.5, "proteins_g": 7,  "total_fat_g": 0.5, "saturated_fat_g": 0.1, "trans_fat_g": 0, "fiber_g": 1.8,  "sodium_mg": 5}},
            "FERMENTO-BIO": {"label": "Fermento biológico",     "allergens": [], "diet": "vegan", "nutrition": {"energy_kcal": 105, "carbohydrates_g": 12, "sugars_g": 0,   "proteins_g": 13, "total_fat_g": 1.5, "saturated_fat_g": 0.2, "trans_fat_g": 0, "fiber_g": 8.1,  "sodium_mg": 30}},
            "SAL":          {"label": "Sal marinho",            "allergens": [], "diet": "vegan", "nutrition": {"energy_kcal": 0,   "carbohydrates_g": 0,  "sugars_g": 0,   "proteins_g": 0,  "total_fat_g": 0,   "saturated_fat_g": 0,   "trans_fat_g": 0, "fiber_g": 0,    "sodium_mg": 38758}},
            "ACUCAR":       {"label": "Açúcar",                 "allergens": [], "diet": "vegan", "nutrition": {"energy_kcal": 387, "carbohydrates_g": 100, "sugars_g": 100, "proteins_g": 0, "total_fat_g": 0,   "saturated_fat_g": 0,   "trans_fat_g": 0, "fiber_g": 0,    "sodium_mg": 1}},
            "MANTEIGA-FR":  {"label": "Manteiga francesa",      "allergens": ["leite"], "diet": "vegetarian", "nutrition": {"energy_kcal": 717, "carbohydrates_g": 0.1, "sugars_g": 0.1, "proteins_g": 0.9, "total_fat_g": 81, "saturated_fat_g": 51,  "trans_fat_g": 3.3, "fiber_g": 0,  "sodium_mg": 11}},
            "LEITE":        {"label": "Leite integral",         "allergens": ["leite"], "diet": "vegetarian", "nutrition": {"energy_kcal": 61,  "carbohydrates_g": 4.8, "sugars_g": 4.8, "proteins_g": 3.2, "total_fat_g": 3.3, "saturated_fat_g": 1.9, "trans_fat_g": 0.1, "fiber_g": 0,  "sodium_mg": 40}},
            "OVOS":         {"label": "Ovos",                   "allergens": ["ovos"], "diet": "vegetarian", "nutrition": {"energy_kcal": 155, "carbohydrates_g": 1.1, "sugars_g": 1.1, "proteins_g": 13,  "total_fat_g": 11,  "saturated_fat_g": 3.3, "trans_fat_g": 0,   "fiber_g": 0,  "sodium_mg": 124}},
            "AZEITE":       {"label": "Azeite extra virgem",    "allergens": [], "diet": "vegan", "nutrition": {"energy_kcal": 884, "carbohydrates_g": 0,   "sugars_g": 0,   "proteins_g": 0,  "total_fat_g": 100, "saturated_fat_g": 14,  "trans_fat_g": 0,   "fiber_g": 0,  "sodium_mg": 2}},
            "MALTE":        {"label": "Malte",                  "allergens": ["glúten"], "diet": "vegan", "nutrition": {"energy_kcal": 360, "carbohydrates_g": 78, "sugars_g": 60,  "proteins_g": 10, "total_fat_g": 1.8, "saturated_fat_g": 0.3, "trans_fat_g": 0,   "fiber_g": 7,  "sodium_mg": 23}},
            "CHOCOLATE-70": {"label": "Chocolate amargo 70%",   "allergens": [], "diet": "vegan", "nutrition": {"energy_kcal": 598, "carbohydrates_g": 46, "sugars_g": 24,  "proteins_g": 7.8, "total_fat_g": 43, "saturated_fat_g": 24,  "trans_fat_g": 0,   "fiber_g": 11, "sodium_mg": 20}},
            "CEBOLA-ROXA":  {"label": "Cebola roxa",            "allergens": [], "diet": "vegan", "nutrition": {"energy_kcal": 40,  "carbohydrates_g": 9,   "sugars_g": 4.2, "proteins_g": 1.1, "total_fat_g": 0.1, "saturated_fat_g": 0,   "trans_fat_g": 0,   "fiber_g": 1.7, "sodium_mg": 4}},
            "AZEITONA":     {"label": "Azeitonas pretas",       "allergens": [], "diet": "vegan", "nutrition": {"energy_kcal": 115, "carbohydrates_g": 6.3, "sugars_g": 0,   "proteins_g": 0.8, "total_fat_g": 10.7, "saturated_fat_g": 1.4, "trans_fat_g": 0,  "fiber_g": 3.2, "sodium_mg": 735}},
            "ALECRIM":      {"label": "Alecrim",                "allergens": [], "diet": "vegan", "nutrition": {"energy_kcal": 131, "carbohydrates_g": 21, "sugars_g": 0,   "proteins_g": 3.3, "total_fat_g": 5.9, "saturated_fat_g": 2.8, "trans_fat_g": 0,   "fiber_g": 14, "sodium_mg": 26}},
            "GERGELIM":     {"label": "Gergelim",               "allergens": ["gergelim"], "diet": "vegan", "nutrition": {"energy_kcal": 573, "carbohydrates_g": 23, "sugars_g": 0.3, "proteins_g": 18,  "total_fat_g": 50, "saturated_fat_g": 7,   "trans_fat_g": 0,   "fiber_g": 12, "sodium_mg": 11}},
            "MACA":         {"label": "Maçã",                   "allergens": [], "diet": "vegan", "nutrition": {"energy_kcal": 52,  "carbohydrates_g": 14, "sugars_g": 10,  "proteins_g": 0.3, "total_fat_g": 0.2, "saturated_fat_g": 0,   "trans_fat_g": 0,   "fiber_g": 2.4, "sodium_mg": 1}},
            "CANELA":       {"label": "Canela",                 "allergens": [], "diet": "vegan", "nutrition": {"energy_kcal": 247, "carbohydrates_g": 81, "sugars_g": 2.2, "proteins_g": 4,   "total_fat_g": 1.2, "saturated_fat_g": 0.3, "trans_fat_g": 0,   "fiber_g": 53, "sodium_mg": 10}},
            "LIMAO":        {"label": "Limão",                  "allergens": [], "diet": "vegan", "nutrition": {"energy_kcal": 29,  "carbohydrates_g": 9,  "sugars_g": 2.5, "proteins_g": 1.1, "total_fat_g": 0.3, "saturated_fat_g": 0,   "trans_fat_g": 0,   "fiber_g": 2.8, "sodium_mg": 2}},
        }

        # Buyman Material master — os insumos viram Material first-class (sku sem
        # prefixo; identidade própria, não Product). unit + shelf-life conforme a
        # tabela aprovada em docs/plans/BUYMAN-PROCUREMENT-PLAN.md (todos frescos
        # mesmo). sku → (unit, shelf_life_days|None); None = não perecível.
        #
        # ⚠️ O SKU é um namespace só, dividido com o catálogo vendável: a água da
        # massa é AGUA-FILTRADA porque AGUA já é a garrafa de água mineral que se
        # vende no balcão. Nomes iguais fariam a venda e o consumo dividirem o
        # mesmo quant no ledger — ver shopman/shop/services/sku_namespace.py.
        from shopman.buyman.models import Material

        # A unidade aqui é a UNIDADE-BASE: aquela em que o livro conta o insumo no
        # momento da verdade (ADR-024 §Regra 1). Ovo e limão entram por peso porque
        # é assim que a produção os usa — "0,300 de OVOS" é 300 g de ovo, e a
        # anotação "≈ 6 ovos" é derivada na tela de mise-en-place, nunca gravada.
        # Canela e alecrim também são pesados: base kg, e a precisão de custo é
        # problema do eixo de compra, não da unidade-base.
        material_attrs = {
            "FARINHA-T65": ("kg", 180), "FARINHA-T55": ("kg", 180),
            "FARINHA-T45": ("kg", 180), "FARINHA-INT": ("kg", 120),
            "CENTEIO": ("kg", 120), "MALTE": ("kg", 365),
            "ACUCAR": ("kg", None), "SAL": ("kg", None), "GERGELIM": ("kg", 180),
            "AGUA-FILTRADA": ("l", None), "LEITE": ("l", 7), "AZEITE": ("l", 540),
            "FERMENTO-NAT": ("kg", 7), "FERMENTO-BIO": ("kg", 14),
            "MANTEIGA-FR": ("kg", 60), "OVOS": ("kg", 28),
            "CHOCOLATE-70": ("kg", 365), "AZEITONA": ("kg", 180),
            "CEBOLA-ROXA": ("kg", 30), "MACA": ("kg", 30), "LIMAO": ("kg", 21),
            "CANELA": ("kg", 365), "ALECRIM": ("kg", 14),
        }
        for sku, profile in INGREDIENT_PROFILES.items():
            unit, shelf = material_attrs.get(sku, ("un", None))
            Material.objects.update_or_create(
                sku=sku,
                defaults={
                    "name": profile.get("label", sku),
                    "unit": unit,
                    "shelf_life_days": shelf,
                    "metadata": {k: v for k, v in profile.items() if k != "label"},
                },
            )
        self.stdout.write(f"  ✅ {len(INGREDIENT_PROFILES)} insumos (Material)")

        # Saldo de abertura de insumo no depósito — estoque físico para a produção
        # poder consumir (consume da untangle emite issue sobre estes quants) e para
        # os guardrails de disponibilidade (Buyman WP-B5b) terem o que checar.
        # kind default (ADJUST = saldo de abertura), igual ao estoque de produto.
        deposito = Position.objects.filter(ref="deposito").first()
        for sku in INGREDIENT_PROFILES:
            stock.receive(
                quantity=Decimal("500"),
                sku=sku,
                position=deposito,
                reason="Saldo de abertura de insumo (seed)",
            )
        self.stdout.write(f"  ✅ estoque de abertura para {len(INGREDIENT_PROFILES)} insumos")

        def _recipe_item_unit(input_sku: str) -> str:
            """A ficha fala na unidade-base do insumo — explícito, não por default.

            Insumo pesado responde a própria base (hoje, kg em todos). Entrada que
            não é Material (pré-preparo, produto) fica em kg, que é como a massa é
            medida.

            ⚠️ Líquidos (AGUA-FILTRADA, LEITE, AZEITE) ainda nascem em kg apesar de
            a base ser `l`: declarar `l` aqui exige `density_g_per_ml` no perfil,
            senão o item é IGNORADO no cálculo de nutrição (ver
            `shopman/shop/services/nutrition_from_recipe.py::_item_quantity_grams`).
            É a Fase 1 de docs/plans/UNIT-CONVERSION-PLAN.md.
            """
            unit = material_attrs.get(input_sku, ("kg", None))[0]
            return unit if unit in ("kg", "g") else "kg"

        for rd in recipes_data:
            product = Product.objects.filter(sku=rd["output_sku"]).first()
            shelf_life_days = product.shelf_life_days if product else None
            recipe, _ = Recipe.objects.update_or_create(
                ref=rd["ref"],
                defaults={
                    "name": rd["name"],
                    "output_sku": rd["output_sku"],
                    "batch_size": rd["batch_size"],
                    "steps": self._production_steps_for_recipe(rd["ref"]),
                    "is_active": True,
                    "meta": {
                        "capacity_per_day": int(rd["batch_size"] * Decimal("3")),
                        "max_started_minutes": self._max_started_minutes_for_recipe(rd["ref"]),
                        "requires_batch_tracking": shelf_life_days is not None,
                        "shelf_life_days": shelf_life_days,
                    },
                },
            )
            RecipeItem.objects.filter(recipe=recipe).delete()
            for input_sku, qty in rd["items"]:
                meta = INGREDIENT_PROFILES.get(input_sku, {})
                RecipeItem.objects.create(
                    recipe=recipe,
                    input_sku=input_sku,
                    quantity=qty,
                    unit=_recipe_item_unit(input_sku),
                    meta=meta,
                )
            if product:
                fill_nutrition_from_recipe(product)
                aggregate_dietary_from_recipe(product)

        # Production data is intentionally time-relative. Re-running the seed on
        # another day creates the same operational story around that new date:
        # history behind, a busy current day, and planned work ahead.
        from shopman.craftsman.models import WorkOrderEvent

        today = timezone.localdate()
        tz_info = timezone.get_current_timezone()

        # base_qty = média diária REAL dos XMLs de NFC-e (jun/2019 + jun/2021);
        # sex/sáb ganham 1.25 abaixo (XMLs: sábado +24%). Madeleine é o campeão
        # absoluto (~11% das unidades da casa). Ver
        # docs/reports/seed_calibration_2026-07-24.md.
        production_plan = [
            # recipe_ref, base_qty, start, finish
            ("baguete", Decimal("22"), (4, 0), (6, 0)),
            ("campagne", Decimal("16"), (3, 40), (8, 0)),
            ("ciabatta", Decimal("24"), (5, 0), (7, 0)),
            ("shokupan", Decimal("18"), (5, 10), (7, 30)),
            ("kuro-pan", Decimal("8"), (5, 20), (8, 0)),
            ("croissant", Decimal("42"), (5, 0), (7, 30)),
            ("pain-chocolat", Decimal("36"), (5, 30), (8, 0)),
            ("animalzinho", Decimal("16"), (5, 30), (8, 30)),
            ("focaccia-dia", Decimal("10"), (7, 0), (10, 0)),
            ("folhado-dia", Decimal("30"), (8, 0), (11, 0)),
            ("madeleine", Decimal("68"), (9, 0), (13, 0)),
        ]
        recipes_by_ref = {r.ref: r for r in Recipe.objects.filter(ref__in=[row[0] for row in production_plan])}

        def at(day: date, hour_min: tuple[int, int]) -> datetime:
            return datetime.combine(day, time(hour_min[0], hour_min[1]), tzinfo=tz_info)

        def jittered(hour_min: tuple[int, int], minutes: int) -> tuple[int, int]:
            total = max(0, min(23 * 60 + 59, hour_min[0] * 60 + hour_min[1] + minutes))
            return total // 60, total % 60

        def recipe_snapshot(recipe: Recipe) -> dict:
            return {
                "batch_size": str(recipe.batch_size),
                "items": [
                    {"input_sku": item.input_sku, "quantity": str(item.quantity), "unit": item.unit}
                    for item in recipe.items.filter(is_optional=False).order_by("sort_order")
                ],
            }

        def reset_ledger(work_order: WorkOrder) -> None:
            work_order.events.all().delete()
            work_order.items.all().delete()

        def ensure_batch_traceability(work_order: WorkOrder, finished_qty: Decimal) -> None:
            if not (work_order.recipe.meta or {}).get("requires_batch_tracking"):
                return
            from shopman.stockman.models import Batch

            production_date = work_order.target_date or today
            shelf_life_days = (work_order.recipe.meta or {}).get("shelf_life_days")
            expiry_date = None
            if shelf_life_days not in (None, ""):
                expiry_date = production_date + timedelta(days=int(shelf_life_days))
            batch_ref = f"{work_order.output_sku}-{production_date:%Y%m%d}-{work_order.pk}"
            Batch.objects.update_or_create(
                ref=batch_ref,
                defaults={
                    "sku": work_order.output_sku,
                    "production_date": production_date,
                    "expiry_date": expiry_date,
                    "notes": f"Seed Nelson producao {work_order.ref}",
                },
            )
            work_order.meta = {
                **(work_order.meta or {}),
                "batch_ref": batch_ref,
                "batch_quantity": str(finished_qty),
                "expiry_date": expiry_date.isoformat() if expiry_date else "",
            }
            work_order.save(update_fields=["meta", "updated_at"])

        def add_event(work_order: WorkOrder, seq: int, kind: str, payload: dict, actor: str, created_at: datetime) -> None:
            event = WorkOrderEvent.objects.create(
                work_order=work_order,
                seq=seq,
                kind=kind,
                payload=payload,
                actor=actor,
            )
            WorkOrderEvent.objects.filter(pk=event.pk).update(created_at=created_at)

        def add_finished_items(work_order: WorkOrder, started_qty: Decimal, finished_qty: Decimal, recorded_at: datetime) -> None:
            coefficient = started_qty / work_order.recipe.batch_size
            for item in work_order.recipe.items.filter(is_optional=False).order_by("sort_order"):
                required = (item.quantity * coefficient).quantize(Decimal("0.001"))
                WorkOrderItem.objects.create(
                    work_order=work_order,
                    kind=WorkOrderItem.Kind.REQUIREMENT,
                    item_ref=item.input_sku,
                    quantity=required,
                    unit=item.unit,
                    recorded_at=recorded_at,
                    recorded_by="seed",
                )
                WorkOrderItem.objects.create(
                    work_order=work_order,
                    kind=WorkOrderItem.Kind.CONSUMPTION,
                    item_ref=item.input_sku,
                    quantity=required,
                    unit=item.unit,
                    recorded_at=recorded_at,
                    recorded_by="seed",
                )
            WorkOrderItem.objects.create(
                work_order=work_order,
                kind=WorkOrderItem.Kind.OUTPUT,
                item_ref=work_order.output_sku,
                quantity=finished_qty,
                unit="un",
                recorded_at=recorded_at,
                recorded_by="seed",
            )
            waste_qty = max(started_qty - finished_qty, Decimal("0"))
            if waste_qty > 0:
                WorkOrderItem.objects.create(
                    work_order=work_order,
                    kind=WorkOrderItem.Kind.WASTE,
                    item_ref=work_order.output_sku,
                    quantity=waste_qty,
                    unit="un",
                    recorded_at=recorded_at,
                    recorded_by="seed",
                    meta={"reason": "perda natural / não vendido"},
                )

        def upsert_work_order(
            *,
            scope: str,
            recipe: Recipe,
            target_date: date,
            planned_qty: Decimal,
            status: str,
            started_qty: Decimal | None = None,
            finished_qty: Decimal | None = None,
            start_at: datetime | None = None,
            finish_at: datetime | None = None,
            operator_ref: str = "",
            position_ref: str = "producao",
        ) -> WorkOrder:
            source_ref = f"seed:production:{scope}:{target_date.isoformat()}:{recipe.ref}"
            work_order = WorkOrder.objects.filter(source_ref=source_ref).first()
            if work_order is None:
                work_order = WorkOrder(source_ref=source_ref)
            work_order.recipe = recipe
            work_order.output_sku = recipe.output_sku
            work_order.quantity = planned_qty
            work_order.finished = finished_qty
            work_order.status = status
            work_order.target_date = target_date
            work_order.started_at = start_at
            work_order.finished_at = finish_at
            work_order.position_ref = position_ref
            work_order.operator_ref = operator_ref
            work_order.meta = {"seed": True, "scope": scope, "_recipe_snapshot": recipe_snapshot(recipe)}
            work_order.save()

            reset_ledger(work_order)
            add_event(
                work_order,
                0,
                WorkOrderEvent.Kind.PLANNED,
                {
                    "quantity": str(planned_qty),
                    "recipe": recipe.ref,
                    "output_sku": recipe.output_sku,
                    "target_date": target_date.isoformat(),
                    "source_ref": source_ref,
                    "position_ref": position_ref,
                    "operator_ref": operator_ref,
                },
                "seed",
                at(target_date, (3, 0)),
            )
            if status in (WorkOrder.Status.STARTED, WorkOrder.Status.FINISHED):
                effective_started = started_qty or planned_qty
                add_event(
                    work_order,
                    1,
                    WorkOrderEvent.Kind.STARTED,
                    {
                        "quantity": str(effective_started),
                        "operator_ref": operator_ref,
                        "position_ref": position_ref,
                        "note": "seed operacional",
                    },
                    "seed",
                    start_at or at(target_date, (5, 0)),
                )
            if status == WorkOrder.Status.FINISHED and finished_qty is not None:
                effective_started = started_qty or planned_qty
                add_event(
                    work_order,
                    2,
                    WorkOrderEvent.Kind.FINISHED,
                    {
                        "finished_qty": str(finished_qty),
                        "planned_qty": str(planned_qty),
                        "started_qty": str(effective_started),
                        "loss_qty": str(max(effective_started - finished_qty, Decimal("0"))),
                        "output_sku": recipe.output_sku,
                        "target_date": target_date.isoformat(),
                        "source_ref": source_ref,
                        "position_ref": position_ref,
                        "operator_ref": operator_ref,
                    },
                    "seed",
                    finish_at or at(target_date, (8, 0)),
                )
                add_finished_items(work_order, effective_started, finished_qty, finish_at or at(target_date, (8, 0)))
                ensure_batch_traceability(work_order, finished_qty)
            return work_order

        # Remove old seed rows outside the moving operational window. The active window
        # is overwritten below through stable source_ref values.
        stale_before = today - timedelta(days=45)
        WorkOrder.objects.filter(source_ref__startswith="seed:production:", target_date__lt=stale_before).delete()

        wo_count = 0
        history_count = 0
        future_count = 0

        # Current day: mixed statuses so the matrix is useful immediately.
        for index, (ref, qty, start_hm, finish_hm) in enumerate(production_plan):
            recipe = recipes_by_ref[ref]
            if index in (0, 1, 7, 9):
                status = WorkOrder.Status.FINISHED
            elif index in (2, 3, 4, 10, 11):
                status = WorkOrder.Status.STARTED
            else:
                status = WorkOrder.Status.PLANNED
            started = (qty + Decimal(str(index % 3))).quantize(Decimal("0.001"))
            finished = None
            finish_at = None
            if status == WorkOrder.Status.FINISHED:
                if ref == "croissant":
                    finished = max((started * Decimal("0.70")).quantize(Decimal("1")), Decimal("1"))
                else:
                    finished = max(started - Decimal(str((index % 4) + 1)), Decimal("1"))
                finish_at = at(today, finish_hm)
            start_at = at(today, start_hm) if status != WorkOrder.Status.PLANNED else None
            if status == WorkOrder.Status.STARTED and index == 2:
                start_at = timezone.now() - timedelta(minutes=self._max_started_minutes_for_recipe(ref) + 15)
            upsert_work_order(
                scope="today",
                recipe=recipe,
                target_date=today,
                planned_qty=qty,
                status=status,
                started_qty=started if status != WorkOrder.Status.PLANNED else None,
                finished_qty=finished,
                start_at=start_at,
                finish_at=finish_at,
                operator_ref=["chef:ana", "chef:joao", "chef:maria"][index % 3],
            )
            wo_count += 1

        # Future horizon: planned production for one week ahead.
        #
        # As WOs futuras precisam VIRAR estoque planejado no ledger do Stockman —
        # senão a loja oferece encomenda para os próximos dias úteis mas o gate de
        # estoque reprova 100%: não existe Quant com aquele ``target_date`` e o físico
        # de hoje é inválido para datas futuras (shelflife). O caminho canônico
        # craftsman→stockman é o signal ``production_changed(action="planned")``, que o
        # handler de contrib/stockman materializa como Quant planejado datado. O seed
        # constrói as WOs à mão (narrativa/matriz determinística, idempotente por
        # ``source_ref``), então emitimos o signal explicitamente. SÓ para o futuro: o
        # estoque vendável de hoje já vem de ``_seed_stock`` (vitrine) — emitir para
        # hoje/histórico dobraria o saldo.
        from shopman.craftsman.signals import production_changed

        for offset in range(1, 8):
            target = today + timedelta(days=offset)
            if not self._shop_operates_on(target):
                continue
            day_multiplier = Decimal("1.25") if target.weekday() in (4, 5) else Decimal("1")
            for index, (ref, qty, _start_hm, _finish_hm) in enumerate(production_plan):
                if offset > 2 and index % 3 == 2:
                    continue
                recipe = recipes_by_ref[ref]
                planned = (qty * day_multiplier).quantize(Decimal("1"))
                work_order = upsert_work_order(
                    scope=f"future-{offset}",
                    recipe=recipe,
                    target_date=target,
                    planned_qty=planned,
                    status=WorkOrder.Status.PLANNED,
                    operator_ref="chef:planejamento",
                )
                production_changed.send(
                    sender=WorkOrder,
                    product_ref=work_order.output_sku,
                    date=target,
                    action="planned",
                    work_order=work_order,
                )
                future_count += 1

        # Encomenda para o resto do catálogo fresco (além dos 14 heróis com receita
        # acima): todo produto vendável ``planned_ok`` — mini-baguetes, quiches,
        # focaccias individuais, pães de sanduíche, viennoiseries menores — também é
        # oferecido para os próximos dias úteis. Sem estoque planejado datado o gate de
        # encomenda reprova (o físico de hoje é inválido para data futura por
        # shelflife; ver shelflife.filter_valid_quants). Espelhamos a prateleira de
        # hoje como supply planejado nesses dias, na posição de produção — mesmo bucket
        # ``planned`` das WOs. Os SKUs com receita já receberam o seu via signal acima;
        # excluímos para não duplicar. Os ``demand_ok`` (café, sanduíches quentes)
        # vendem sem estoque (hold flutuante), então não precisam de supply planejado.
        from django.db.models import Sum
        from shopman.stockman.models import Quant

        producao_pos = Position.objects.filter(ref="producao").first()
        recipe_backed = {r.output_sku for r in Recipe.objects.all()}
        planned_extra = 0
        preorder_products = (
            Product.objects.filter(
                is_published=True, is_sellable=True, availability_policy="planned_ok",
            )
            .exclude(sku__in=recipe_backed)
        )
        for product in preorder_products:
            baseline = Quant.objects.filter(
                sku=product.sku, target_date__isnull=True, _quantity__gt=0,
            ).aggregate(t=Sum("_quantity"))["t"]
            if not baseline:
                continue  # sem prateleira física hoje = não estocado para venda direta
            for offset in range(1, 8):
                target = today + timedelta(days=offset)
                if not self._shop_operates_on(target):
                    continue
                day_multiplier = Decimal("1.25") if target.weekday() in (4, 5) else Decimal("1")
                stock.receive(
                    quantity=(baseline * day_multiplier).quantize(Decimal("1")),
                    sku=product.sku,
                    position=producao_pos,
                    target_date=target,
                    reason=f"Produção planejada (encomenda): {product.sku} {target.isoformat()}",
                    kind="make",  # Move.Kind.MAKE — produção
                )
                planned_extra += 1

        # Historical production: 35 relative days behind today for BI,
        # pickup slots and waste patterns.
        for days_ago in range(1, 36):
            target = today - timedelta(days=days_ago)
            if not self._shop_operates_on(target):
                continue
            weekday_multiplier = Decimal("1.20") if target.weekday() in (4, 5) else Decimal("1")
            for index, (ref, qty, start_hm, finish_hm) in enumerate(production_plan):
                recipe = recipes_by_ref[ref]
                jitter = random.randint(-12, 12)
                start = at(target, jittered(start_hm, jitter))
                finish = at(target, jittered(finish_hm, jitter + random.randint(-6, 10)))
                planned = (qty * weekday_multiplier).quantize(Decimal("1"))
                started = planned
                loss = Decimal(str((index + days_ago) % 4))
                finished = max(started - loss, Decimal("1"))
                upsert_work_order(
                    scope=f"history-{days_ago}",
                    recipe=recipe,
                    target_date=target,
                    planned_qty=planned,
                    status=WorkOrder.Status.FINISHED,
                    started_qty=started,
                    finished_qty=finished,
                    start_at=start,
                    finish_at=finish,
                    operator_ref=["chef:ana", "chef:joao", "chef:maria"][index % 3],
                )
                history_count += 1

        self.stdout.write(
            f"  ✅ {len(recipes_data)} receitas, {wo_count} ordens de hoje,"
            f" {future_count} futuras e {history_count} historico movel"
        )

    def _production_steps_for_recipe(self, ref: str) -> list[str]:
        if "croissant" in ref or "chocolat" in ref or "folhado" in ref:
            return ["Massa", "Laminação", "Forno"]
        if "focaccia" in ref:
            return ["Mistura", "Fermentação", "Cobertura", "Forno"]
        if "brioche" in ref or "animalzinho" in ref:
            return ["Mistura", "Descanso", "Forno"]
        if ref.startswith("massa-"):
            return ["Pesagem", "Mistura", "Fermentação"]
        if ref.startswith("recheio-"):
            return ["Pesagem", "Cocção", "Resfriamento"]
        return ["Mistura", "Fermentação", "Modelagem", "Forno"]

    def _max_started_minutes_for_recipe(self, ref: str) -> int:
        if "croissant" in ref or "chocolat" in ref or "folhado" in ref:
            return 150
        if "campagne" in ref:
            return 240
        if ref.startswith("massa-"):
            return 180
        if ref.startswith("recheio-"):
            return 90
        return 120

    def _assert_catalog_remote_purchase_data(self):
        from shopman.fiscalman.classification import from_metadata

        missing = []
        required_metadata = ("allergens", "dietary_info", "serves")
        listed_skus = ListingItem.objects.filter(
            listing__ref__in=("pdv", "ifood", "web"),
            listing__is_active=True,
            is_published=True,
        ).values_list("product__sku", flat=True).distinct()
        products = Product.objects.filter(
            sku__in=listed_skus,
            is_published=True,
        ).prefetch_related("keywords").order_by("sku")

        for product in products:
            gaps = []
            metadata = product.metadata if isinstance(product.metadata, dict) else {}
            for key in required_metadata:
                if key not in metadata:
                    gaps.append(f"metadata.{key}")
            fiscal = metadata.get("fiscal") if isinstance(metadata.get("fiscal"), dict) else {}
            if not fiscal:
                gaps.append("metadata.fiscal")
            else:
                # CFOP/CSOSN/origem/PIS-COFINS vêm do perfil fiscal (Fiscalman) na
                # emissão; por produto validamos só perfil + NCM (+ CEST se ST).
                classification = from_metadata(metadata)
                if classification.fiscal_profile is None:
                    gaps.append("metadata.fiscal.profile")
                for message in classification.errors():
                    gaps.append(f"metadata.fiscal ({message})")
            if product.unit_weight_g and not metadata.get("approx_dimensions"):
                gaps.append("metadata.approx_dimensions")
            if not product.keywords.exists():
                gaps.append("keywords")
            if not product.ingredients_text:
                gaps.append("ingredients_text")
            if not product.nutrition_facts:
                gaps.append("nutrition_facts")
            if gaps:
                missing.append(f"{product.sku}: {', '.join(gaps)}")

        if missing:
            raise CommandError(
                "Seed catalog remoto incompleto. Corrija os produtos publicados: "
                + "; ".join(missing)
            )

        self.stdout.write(f"  ✅ Dados remotos PDP: {products.count()} produtos completos")

    def _assert_storefront_products_orderable(self):
        from shopman.shop.projections import catalog_context

        blocked = []
        web_skus = ListingItem.objects.filter(
            listing__ref="web",
            listing__is_active=True,
            is_published=True,
            is_sellable=True,
            product__is_published=True,
            product__is_sellable=True,
        ).values_list("product__sku", flat=True).distinct()
        products = Product.objects.filter(
            sku__in=web_skus,
            is_published=True,
            is_sellable=True,
        ).order_by("sku")
        for product in products:
            raw_availability = catalog_context.availability_for_sku(product.sku, channel_ref="web")
            availability = catalog_context.storefront_availability(
                raw_availability,
                is_sellable=product.is_sellable,
            )
            if not availability or not availability.get("can_order"):
                blocked.append(product.sku)

        if blocked:
            raise CommandError(
                "Seed storefront incompleto. Produtos publicados/vendáveis sem compra web: "
                + ", ".join(blocked)
            )

        self.stdout.write(f"  ✅ Compra web: {products.count()} produtos vendáveis orderable")

    # ────────────────────────────────────────────────────────────────
    # Clientes (Customers)
    # ────────────────────────────────────────────────────────────────

    def _seed_customers(self):
        self.stdout.write("  👥 Clientes...")

        # Faixas de preço: qual tabela cada cliente enxerga (`PriceTier.listing_ref`).
        varejo, _ = PriceTier.objects.update_or_create(
            ref="varejo",
            defaults={"name": "Varejo"},
        )
        atacado, _ = PriceTier.objects.update_or_create(
            ref="atacado",
            defaults={"name": "Atacado"},
        )
        staff_tier, _ = PriceTier.objects.update_or_create(
            ref="staff",
            defaults={"name": "Funcionarios"},
        )

        customers_data = [
            ("CLI-001", "Maria", "Santos", "individual", varejo, "+5543991111111"),
            ("CLI-002", "Restaurante", "Sabor da Terra", "business", atacado, "+5543992222222"),
            ("CLI-003", "João", "Oliveira", "individual", varejo, "+5543993333333"),
            ("CLI-004", "Café", "Parisiense", "business", atacado, "+5543994444444"),
            ("CLI-005", "Ana", "Ferreira", "individual", varejo, "+5543995555555"),
            ("CLI-006", "Carlos", "Silva", "individual", staff_tier, "+5543996666666"),
            ("CLI-007", "Padaria", "do Bairro", "business", atacado, "+5543997777777"),
        ]

        customers = {}
        for ref, first, last, ctype, price_tier, phone in customers_data:
            extras = {}
            if ref == "CLI-001":
                extras["birthday"] = timezone.localdate()
            c, _ = Customer.objects.update_or_create(
                ref=ref,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "customer_type": ctype,
                    "price_tier": price_tier,
                    "phone": phone,
                    **extras,
                },
            )
            ContactPoint.objects.update_or_create(
                customer=c,
                type="whatsapp",
                value_normalized=phone,
                defaults={
                    "is_primary": True,
                    "value_display": phone,
                },
            )
            customers[ref] = c

        self._seed_customer_tags(customers)

        # Vínculos de login apontam para o uuid do Customer. Se a base perdeu os
        # clientes e ganhou uuids novos (reset parcial), o login antigo fica
        # órfão e o cliente perde o canal em tempo real sem nenhum aviso. Aqui o
        # seed se auto-cura religando por telefone; o que não dá para religar
        # fica para o comando dedicado decidir (--delete-unrepairable).
        try:
            from django.core.management import call_command

            call_command("cleanup_orphan_customer_links", verbosity=0)
        except Exception:
            self.stdout.write("  ⚠️  não foi possível revisar vínculos de login")

        consented = self._seed_marketing_consent(customers)

        self.stdout.write(
            f"  ✅ {len(customers)} clientes, 3 faixas de preço, {consented} com consentimento de marketing"
        )
        return customers

    def _seed_marketing_consent(self, customers: dict) -> int:
        """Consentimento de WhatsApp — sem isto a audiência de campanha alcança NINGUÉM.

        A F1 deu um dono ao consentimento (`CommunicationConsent`) e a audiência passou a
        exigi-lo, corretamente. Só que o seed não criava nenhum: qualquer disparo resolvia
        zero destinatários, e o gestor não tinha como distinguir "regra errada" de "base
        sem consentimento". Feature que não se pode experimentar não existe para quem usa.

        **Nem todos consentem, de propósito.** Dois clientes ficam de fora para que o
        filtro seja visível na tela: o resumo do anúncio mostra "3 na faixa, 1 alcançado",
        e essa diferença é a LGPD funcionando, não um bug.
        """
        from shopman.guestman import ConsentService

        # Quem NÃO consente: fica de fora do disparo, e é isso que prova o filtro.
        without = {"CLI-004", "CLI-006"}

        granted = 0
        for ref, customer in customers.items():
            if ref in without or not (customer.phone or "").strip():
                continue
            try:
                ConsentService.grant_consent(customer.ref, "whatsapp", source="seed")
                granted += 1
            except Exception:
                self.stdout.write(f"  ⚠️  consentimento não gravado para {ref}")
        return granted

    # ────────────────────────────────────────────────────────────────
    # Canais (Orderman)
    # ────────────────────────────────────────────────────────────────

    def _seed_channels(self):
        self.stdout.write("  📡 Canais...")

        channels = {}
        _pos_config = {
            "confirmation": {"mode": "immediate"},
            "payment": {"method": "cash", "timing": "external"},
            # No balcão o item já saiu fisicamente da vitrine: a venda NUNCA é
            # auto-rejeitada por estoque (o kernel reserva o que der, best-effort,
            # e o estoque reconcilia). A review avisa; não bloqueia. Mesma semântica
            # do marketplace (check_on_commit=False).
            # allow_untracked=False: canal de CLIENTE — typo de SKU não pode
            # virar pedido sem reserva (SKU fora do catálogo é recusado/alertado).
            # sells_nonconforming=True: no balcão o lote com desconto de
            # qualidade É vendido — a etiqueta explica (C2 do D1-RETIREMENT).
            "stock": {
                "check_on_commit": False,
                "allow_untracked": False,
                "sells_nonconforming": True,
            },
            "handle_label": "Comanda",
            "handle_placeholder": "Ex: 42",
        }
        _remote_stock = {
            "hold_ttl_minutes": 30,
            # Canais de CLIENTE não aceitam SKU fora do catálogo como pedido
            # sem reserva — typo de SKU falha limpo no gate de commit.
            "allow_untracked": False,
            # C2 (D1-RETIREMENT): o LOTE decide o que o canal remoto oferece.
            # Não conforme não sai no remoto (default explícito aqui por
            # legibilidade); afrouxar é decisão consciente por canal.
            "sells_nonconforming": False,
        }
        _remote_config = {
            # Aceite otimista em 1 min (alpha/staging): com estoque fantasma do
            # autosserviço não dá pra cobrar antes de confirmar disponibilidade,
            # então mantemos o aceite — mas curto, pra o cliente ver o QR rápido.
            # Reavaliar no go-live (janela de cancelamento do operador vs. espera).
            "confirmation": {"mode": "auto_confirm", "timeout_minutes": 1, "stale_new_alert_minutes": 10},
            "payment": {"method": ["pix", "card"], "timing": "post_commit", "timeout_minutes": 10},
            "stock": _remote_stock,
        }
        _marketplace_config = {
            # stale_new_alert < hold_ttl_minutes (20 < 30): o operador é cutucado
            # ENQUANTO a reserva de estoque ainda vale, não no exato minuto em que
            # ela expira (senão o alerta chega tarde demais para ser útil).
            "confirmation": {"mode": "manual", "stale_new_alert_minutes": 20},
            "payment": {"method": "external", "timing": "external"},
            # Marketplace: o pedido já foi comitado e PAGO no iFood. Não rejeitar
            # localmente por estoque/listing — aceitar e deixar o operador tratar
            # eventual falta (reserva o que der, best-effort). Rejeitar aqui
            # cancelaria um pedido de marketplace já pago.
            "stock": {**_remote_stock, "check_on_commit": False},
        }
        _whatsapp_config = {
            "confirmation": {"mode": "auto_confirm", "timeout_minutes": 5, "stale_new_alert_minutes": 10},
            "payment": {"method": ["pix", "card"], "timing": "post_commit", "timeout_minutes": 10},
            "notifications": {"backend": "manychat"},
            "stock": _remote_stock,
        }
        channels_data = [
            # (ref, name, display_order, is_active, config_overrides)
            # Canal = ORIGEM do pedido (por onde entra). Entrega/retirada é fulfillment
            # (ortogonal, por pedido) — não um canal. Por isso não há "Delivery Próprio":
            # um pedido para nossa entrega origina de PDV (telefone), WhatsApp ou Loja online.
            # display_order = ordem canônica das colunas no Gestor: PDV · Loja online · iFood · WhatsApp.
            # `short_name` (ChannelConfig) = rótulo da coluna estreita no Catálogo; só
            # quando o nome completo não cabe — "PDV"/"iFood" já são curtos.
            ("pdv", "PDV", 1, True, _pos_config),
            # Loja online: cliente acompanha de longe, então o preparo NÃO começa
            # sozinho ao pagar — o operador dá "Iniciar preparo" no gestor (a tela
            # do cliente só diz "Em preparo" quando alguém de fato encosta). PDV e
            # iFood ficam no default "auto" (operador presente / marketplace).
            ("web", "Loja online", 2, True, {
                **_remote_config,
                "short_name": "Site",
                "fulfillment": {"prep_start": "operator"},
            }),
            ("ifood", "iFood", 3, True, {
                **_marketplace_config,
                "pricing": {"policy": "external"},
                "editing": {"policy": "locked"},
            }),
            # WhatsApp fica INATIVO: não há nada implementado para ele ainda (nem entrada
            # de pedido, nem sync). Canal inativo some da matriz do Catálogo — ligar aqui
            # é o gesto único para trazê-lo de volta quando existir implementação.
            ("whatsapp", "WhatsApp", 4, False, _whatsapp_config),
        ]

        for ref, name, display_order, is_active, config_data in channels_data:
            ch, _ = Channel.objects.update_or_create(
                ref=ref,
                defaults={
                    "name": name,
                    "is_active": is_active,
                    "display_order": display_order,
                    "config": config_data,
                },
            )
            channels[ref] = ch

        self.stdout.write(f"  ✅ {len(channels)} canais")
        return channels

    def _seed_display_channels(self):
        """Canais de EXIBIÇÃO: mostram o catálogo sem transacionar.

        📺 Menuboards (TVs no salão) + 🛰 feeds (Google/Meta). Cada um compõe coleções
        reais (viram as seções/segmentos). Acoplamento frouxo por ref de coleção — não
        exige coleção-guarda-chuva. A pausa global do produto cascateia sobre eles, e o
        operador pode pausar um item em UM canal (`display.paused_skus`).

        Eram um model próprio (`Showcase`) até a ADR-018: superfície é canal, e o que
        distinguia as duas coisas era só *poder vender*. Isso virou
        `commerce_policy`, e o resto do que o Showcase guardava virou o aspecto
        `display` do `ChannelConfig`.

        **`prices_from` é o ponto todo.** Canal de exibição não vende, logo não tem
        preço próprio — mas mostra preço, e mostrar o errado vincula o fornecedor. Então
        ele aponta para quem transaciona:

        · TV do balcão → **PDV**. Está fisicamente na loja; tem de concordar com o caixa.
        · Google/Meta → **loja online**. É lá que quem clicou vai comprar.

        Enquanto todos os canais cobram igual, isto não muda um centavo na tela. É de
        propósito: a mudança é de FONTE, e existe para o dia em que o PDV tiver preço
        próprio — aí a TV acompanha o caixa em vez de anunciar tabela.
        """
        self.stdout.write("  📺 Canais de exibição...")

        pos_ref = getattr(settings, "SHOPMAN_POS_CHANNEL_REF", "pdv")
        web_ref = "web"

        # `short_name` = rótulo da coluna estreita na matriz do Catálogo. O nome
        # completo continua valendo no Admin, onde ele diz QUAL TV é ("TV do Café" vs
        # "TV do Salão") — informação que "TV1"/"TV2" perdem.
        #
        # `format` vazio = menuboard: ele é uma ROTA nossa, não um dialeto de terceiro.
        # Google e Meta têm dialeto (nome do campo, separador de label), e é isso que o
        # formato nomeia.
        channels_data = [
            # (ref, name, short_name, format, prices_from, [collection_refs])
            ("tv-salao", "TV do Salão", "TV2", "", pos_ref,
             ["rusticos", "finos", "salgados"]),
            ("tv-cafe", "TV do Café", "TV1", "", pos_ref,
             ["bebidas-quentes", "bebidas-geladas", "torneira", "doces"]),
            ("google-shopping", "Google Shopping", "Google", "google_merchant", web_ref,
             ["rusticos", "finos", "salgados", "doces"]),
            ("meta-catalog", "Catálogo Meta", "Meta", "meta_catalog", web_ref,
             ["rusticos", "finos", "salgados", "doces"]),
        ]

        for ref, name, short_name, fmt, prices_from, collections in channels_data:
            Channel.objects.update_or_create(
                ref=ref,
                defaults={
                    "name": name,
                    "commerce_policy": Channel.CommercePolicy.DISPLAY,
                    "is_active": True,
                    "config": {
                        "short_name": short_name,
                        "display": {
                            "format": fmt,
                            "collections": collections,
                            "prices_from": prices_from,
                            "paused_skus": [],
                        },
                    },
                },
            )

        self.stdout.write(f"  ✅ {len(channels_data)} canais de exibição")

    # ────────────────────────────────────────────────────────────────
    # Pedidos (Orderman)
    # ────────────────────────────────────────────────────────────────

    def _seed_orders(self, products, customers, channels):
        self.stdout.write("  🛒 Pedidos...")

        now = timezone.now()
        order_count = 0
        customer_list = list(customers.values())
        product_list = list(products.values())
        channel_list = [channels["pdv"], channels["web"], channels["whatsapp"]]

        # Seasonal demand multiplier based on current month
        current_month = now.month
        if current_month in (10, 11, 12, 1, 2, 3):   # hot season
            season_multiplier = 1.1
        elif current_month in (6, 7, 8):               # cold season
            season_multiplier = 1.2
        else:                                           # mild
            season_multiplier = 1.0

        for days_ago in range(35):  # 5 weeks of history
            day = now - timedelta(days=days_ago)
            weekday = day.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun

            # Dia sem expediente não gera pedido. Quem responde "a loja abre
            # nesse dia?" é o calendário (Shop.opening_hours + feriados), nunca
            # um literal aqui — no staging 24/7 a resposta muda, e um literal
            # deixaria buracos de domingo num histórico de loja que abre todo dia.
            if not self._shop_operates_on(day.date()):
                continue

            # Base order count
            base_orders = random.randint(8, 15) if days_ago < 2 else random.randint(5, 10)

            # Weekday multiplier
            if weekday in (4, 5):    # Fri, Sat — alta demanda
                day_mult = 1.3
            elif weekday == 0:        # Mon — dia mais fraco (padrão dos XMLs NFC-e)
                day_mult = 0.85
            else:
                day_mult = 1.0

            # Volume de exemplos reduzido à metade (0.5): o board de pedidos fica legível
            # para demo/QA sem inflar a tela. O histórico segue representativo dos padrões
            # de dia/estação — só menos denso.
            num_orders = max(1, int(base_orders * day_mult * season_multiplier * 0.5))

            for _ in range(num_orders):
                channel = random.choice(channel_list)
                customer = random.choice(customer_list)
                # Horário de operação: 9h–18h (último pedido até ~17h59)
                max_hour = 17

                if days_ago == 0:
                    # Only completed orders from earlier today (morning hours)
                    morning_ceiling = max(9, now.hour - 2)
                    if morning_ceiling <= 9:
                        continue  # loja abriu há pouco — sem histórico concluído ainda
                    hour = random.randint(9, morning_ceiling)
                    minute = random.randint(0, 59)
                    status = "completed"
                else:
                    hour = random.randint(9, max_hour)
                    minute = random.randint(0, 59)
                    status = "completed"

                order_time = day.replace(hour=hour, minute=minute, second=0, microsecond=0)

                # Random items
                num_items = random.randint(1, 4)
                selected_products = random.sample(product_list, min(num_items, len(product_list)))

                items_data = []
                total_q = 0
                for prod in selected_products:
                    qty = random.randint(1, 5)
                    price_q = prod.base_price_q
                    line_total_q = price_q * qty
                    total_q += line_total_q
                    items_data.append({
                        "sku": prod.sku,
                        "name": prod.name,
                        "qty": qty,
                        "unit_price_q": price_q,
                        "line_total_q": line_total_q,
                    })

                ref = self._new_order_ref(channel.ref, order_time.date())

                # Get customer phone from contact points
                cp = customer.contact_points.filter(type="whatsapp").first()
                handle_ref = cp.value_normalized if cp else ""

                order = Order.objects.create(
                    ref=ref,
                    channel_ref=channel.ref,
                    session_key=generate_session_key(),
                    status=status,
                    total_q=total_q,
                    handle_type="phone",
                    handle_ref=handle_ref,
                    created_at=order_time,
                    # ⚠️ `customer_ref` é o ELO que o histórico do cliente usa
                    # (`CustomerOrderHistoryService` filtra por `data__customer_ref`). Sem
                    # ele, 1.169 pedidos existiam e NENHUM era atribuível: todo
                    # `CustomerInsight` nascia vazio, RFM dizia "lost" para todo mundo e
                    # todo público comportamental do Marketing resolvia zero.
                    data={
                        "customer_ref": customer.ref,
                        "availability_decision": {"approved": True, "source": "seed", "decisions": []},
                    },
                    # ⚠️ `snapshot["items"]` é o que o HISTÓRICO do cliente lê
                    # (`CustomerOrderHistoryService` → `OrderSummary.items` → favoritos e
                    # recompra). Em produção quem grava é o `CommitService`, a partir da
                    # sessão; o seed cria o Order direto e pulava — então
                    # `favorite_products` nascia vazio e "comprou nos últimos N dias"
                    # resolvia ZERO, calado.
                    #
                    # Vai na CRIAÇÃO porque `snapshot` é campo SELADO: o orderman levanta
                    # `ImmutabilityError` em qualquer escrita posterior, e está certo.
                    snapshot={"items": items_data},
                )
                self._stamp_order(order, order_time)

                for _idx, item in enumerate(items_data):
                    OrderItem.objects.create(
                        order=order,
                        line_id=f"L-{uuid.uuid4().hex[:8]}",
                        sku=item["sku"],
                        name=item["name"],
                        qty=Decimal(str(item["qty"])),
                        unit_price_q=item["unit_price_q"],
                        line_total_q=item["line_total_q"],
                    )

                # Create events
                OrderEvent.objects.create(
                    order=order,
                    type="status_change",
                    seq=0,
                    payload={"new_status": "new"},
                    created_at=order_time,
                )

                if status in ("accepted", "preparing", "ready", "completed"):
                    OrderEvent.objects.create(
                        order=order,
                        type="status_change",
                        seq=1,
                        payload={"new_status": "accepted"},
                        created_at=order_time + timedelta(minutes=2),
                    )

                if status in ("preparing", "ready", "completed"):
                    OrderEvent.objects.create(
                        order=order,
                        type="status_change",
                        seq=2,
                        payload={"new_status": "preparing"},
                        created_at=order_time + timedelta(minutes=5),
                    )

                if status == "completed":
                    OrderEvent.objects.create(
                        order=order,
                        type="status_change",
                        seq=3,
                        payload={"new_status": "completed"},
                        created_at=order_time + timedelta(minutes=15),
                    )

                order_count += 1

        # ── Live orders — timestamps in minutes, not hours ────────────────
        # These represent what's happening RIGHT NOW in the kitchen/counter.
        from shopman.shop.handlers.production_order_sync import link_order_to_work_orders

        # Coluna "Entrada" (status new) fica VAZIA de propósito: assim dá para testar a
        # CHEGADA de pedidos novos ao vivo sem ruído. O board nasce com o que já está em
        # andamento (em preparo / confirmado / pronto). Cenários determinísticos de borda
        # (ex.: iFood parado) continuam em _seed_security_reliability_edges.
        live_specs = [
            ("preparing", random.randint(5, 15)),
            ("preparing", random.randint(5, 15)),
            ("accepted",  random.randint(2, 5)),
            ("accepted",  random.randint(2, 5)),
            ("ready",      1),
        ]

        for live_status, minutes_ago in live_specs:
            channel = random.choice(channel_list)
            customer = random.choice(customer_list)
            order_time = now - timedelta(minutes=minutes_ago)

            num_items = random.randint(1, 3)
            selected_products = random.sample(product_list, min(num_items, len(product_list)))

            items_data = []
            total_q = 0
            for prod in selected_products:
                qty = random.randint(1, 3)
                price_q = prod.base_price_q
                line_total_q = price_q * qty
                total_q += line_total_q
                items_data.append({
                    "sku": prod.sku,
                    "name": prod.name,
                    "qty": qty,
                    "unit_price_q": price_q,
                    "line_total_q": line_total_q,
                })

            ref = self._new_order_ref(channel.ref, order_time.date())
            cp = customer.contact_points.filter(type="whatsapp").first()
            handle_ref = cp.value_normalized if cp else ""

            order = Order.objects.create(
                ref=ref,
                channel_ref=channel.ref,
                session_key=generate_session_key(),
                status=live_status,
                total_q=total_q,
                handle_type="phone",
                handle_ref=handle_ref,
                created_at=order_time,
                # `customer_ref`: o elo que o histórico do cliente usa. Ver o gêmeo acima.
                data={
                    "customer_ref": customer.ref,
                    "availability_decision": {"approved": True, "source": "seed", "decisions": []},
                },
                # `snapshot["items"]`: o que o histórico do cliente lê. Ver o gêmeo acima.
                snapshot={"items": items_data},
            )
            self._stamp_order(order, order_time)

            for item in items_data:
                OrderItem.objects.create(
                    order=order,
                    line_id=f"L-{uuid.uuid4().hex[:8]}",
                    sku=item["sku"],
                    name=item["name"],
                    qty=Decimal(str(item["qty"])),
                    unit_price_q=item["unit_price_q"],
                    line_total_q=item["line_total_q"],
                )

            # Events: realistic minute progression
            OrderEvent.objects.create(
                order=order,
                type="status_change",
                seq=0,
                payload={"new_status": "new"},
                created_at=order_time,
            )

            if live_status in ("accepted", "preparing", "ready"):
                OrderEvent.objects.create(
                    order=order,
                    type="status_change",
                    seq=1,
                    payload={"new_status": "accepted"},
                    created_at=order_time + timedelta(minutes=1),
                )

            if live_status in ("preparing", "ready"):
                OrderEvent.objects.create(
                    order=order,
                    type="status_change",
                    seq=2,
                    payload={"new_status": "preparing"},
                    created_at=order_time + timedelta(minutes=2),
                )

                from shopman.shop.services.kds import dispatch
                tickets = dispatch(order)

                if live_status == "ready":
                    OrderEvent.objects.create(
                        order=order,
                        type="status_change",
                        seq=3,
                        payload={"new_status": "ready"},
                        created_at=order_time + timedelta(minutes=3),
                    )
                    for ticket in tickets:
                        ticket.status = "done"
                        ticket.completed_at = order_time + timedelta(minutes=3)
                        ticket.save(update_fields=["status", "completed_at"])

            if live_status in ("accepted", "preparing", "ready"):
                link_order_to_work_orders(order=order, event_type="status_changed", actor="seed")

            order_count += 1

        # Deterministic production-dependent order so Pedidos and Produção
        # always demonstrate the visual sync from WP-BS-9.
        produced_product = products.get("CT") or products.get("BF")
        if produced_product:
            customer = customer_list[0]
            channel = channels["pdv"]
            order_time = now - timedelta(minutes=6)
            ref = self._new_order_ref(channel.ref, order_time.date())
            sync_order = Order.objects.create(
                ref=ref,
                channel_ref=channel.ref,
                session_key=generate_session_key(),
                status=Order.Status.ACCEPTED,
                total_q=produced_product.base_price_q * 3,
                handle_type="phone",
                handle_ref=customer.contact_points.filter(type="whatsapp").values_list("value_normalized", flat=True).first() or "",
                created_at=order_time,
                data={
                    "customer": {"name": customer.name},
                    "payment": {"method": "cash"},
                    "fulfillment_type": "pickup",
                    "availability_decision": {"approved": True, "source": "seed", "decisions": []},
                },
            )
            self._stamp_order(sync_order, order_time)
            OrderItem.objects.create(
                order=sync_order,
                line_id=f"L-{uuid.uuid4().hex[:8]}",
                sku=produced_product.sku,
                name=produced_product.name,
                qty=Decimal("3"),
                unit_price_q=produced_product.base_price_q,
                line_total_q=produced_product.base_price_q * 3,
            )
            OrderEvent.objects.create(
                order=sync_order,
                type="status_change",
                seq=0,
                payload={"new_status": "new"},
                created_at=order_time,
            )
            OrderEvent.objects.create(
                order=sync_order,
                type="status_change",
                seq=1,
                payload={"new_status": "accepted"},
                created_at=order_time + timedelta(minutes=1),
            )
            link_order_to_work_orders(order=sync_order, event_type="status_changed", actor="seed")
            order_count += 1

        # ── iFood operational orders ──────────────────────────────────────────
        if "ifood" in channels:
            ifood_ch = channels["ifood"]
            prod_b = product_list[1] if len(product_list) > 1 else product_list[0]

            # iFood order: confirmed (in queue, being handled). Nenhum pedido "new" aqui —
            # a coluna Entrada nasce vazia para testar a chegada de pedidos ao vivo.
            ref_confirmed = self._new_order_ref(ifood_ch.ref, (now - timedelta(minutes=9)).date())
            order_accepted = Order.objects.create(
                ref=ref_confirmed,
                channel_ref=ifood_ch.ref,
                session_key=generate_session_key(),
                status="accepted",
                total_q=prod_b.base_price_q,
                handle_type="phone",
                handle_ref="",
                created_at=now - timedelta(minutes=9),
                data={
                    "customer": {"name": "Rafael iFood"},
                    "payment": {"method": "external", "timing": "external"},
                    "fulfillment_type": "delivery",
                    "availability_decision": {"approved": True, "source": "seed", "decisions": []},
                },
            )
            self._stamp_order(order_accepted, now - timedelta(minutes=9))
            OrderItem.objects.create(
                order=order_accepted,
                line_id=f"L-{uuid.uuid4().hex[:8]}",
                sku=prod_b.sku,
                name=prod_b.name,
                qty=Decimal("1"),
                unit_price_q=prod_b.base_price_q,
                line_total_q=prod_b.base_price_q,
            )
            OrderEvent.objects.create(
                order=order_accepted,
                type="status_change",
                seq=0,
                payload={"new_status": "new"},
                created_at=now - timedelta(minutes=9),
            )
            OrderEvent.objects.create(
                order=order_accepted,
                type="status_change",
                seq=1,
                payload={"new_status": "accepted"},
                created_at=now - timedelta(minutes=7),
            )
            link_order_to_work_orders(order=order_accepted, event_type="status_changed", actor="seed")

            order_count += 1
            self.stdout.write("  ✅ 1 pedido iFood operacional adicionado")

        production_history_count = self._seed_production_demand_history(products, channels, now)
        order_count += production_history_count

        self.stdout.write(
            f"  ✅ {order_count} pedidos (35 dias + live + iFood + historico producao)"
        )

    def _seed_fiscal_example(self):
        """Um pedido concluído com NFC-e de HOMOLOGAÇÃO já 'emitida' (exemplo ilustrativo).

        Serve de "lampejo": o cupom aparece em /fiscal/danfe/<ref>/ logo após o seed, sem
        depender de rede. É explicitamente HOMOLOGAÇÃO ("SEM VALOR FISCAL"). Para uma
        emissão REAL de ponta a ponta, configure FOCUS_NFE_CNPJ_EMITENTE e rode
        `manage.py fiscal_emit` — que sobrescreve com a nota autorizada de verdade.
        """
        from shopman.orderman.models import Order

        order = (
            Order.objects.filter(status="completed")
            .exclude(items=None)
            .order_by("-created_at")
            .first()
        )
        if order is None:
            return

        # Chave de acesso NFC-e (44 dígitos): cUF(41=PR)+AAMM+CNPJ+mod(65)+série+nNF+
        # tpEmis(2=homolog)+cNF+cDV. Formato realista; exemplo de homologação.
        now = timezone.now()
        chave = f"41{now:%y%m}99999999000191650010000012342{'87654321'}0"
        chave = "".join(ch for ch in chave if ch.isdigit())[:44].ljust(44, "0")
        qr_consulta = (
            "http://www.fazenda.pr.gov.br/nfce/qrcode?p="
            f"{chave}|2|2|1|A1B2C3D4E5F6A7B8C9D0E1F2A3B4C5D6E7F8A9B0"
        )

        data = order.data or {}
        data.setdefault("fiscal", {})["issue_document"] = True
        data.setdefault("customer", {}).setdefault("name", "Consumidor Final")
        data.setdefault("payment", {})["method"] = data.get("payment", {}).get("method") or "pix"
        data.update({
            "nfce_access_key": chave,
            "nfce_number": 1234,
            "nfce_series": "1",
            "nfce_protocol": f"141{now:%y}0000012345",
            "nfce_status": "autorizado",
            "nfce_danfe_url": f"https://homologacao.focusnfe.com.br/danfe/nfce/{chave}.pdf",
            "nfce_qrcode_url": qr_consulta,
            "nfce_xml_url": f"https://homologacao.focusnfe.com.br/notas/nfce/{chave}.xml",
        })
        order.data = data
        order.save(update_fields=["data", "updated_at"])
        self.stdout.write(f"  🧾 NFC-e exemplo (homologação) no pedido {order.ref} — /fiscal/danfe/{order.ref}/")

    def _seed_security_reliability_edges(self, products, customers, channels):
        """Deterministic edge scenarios for adversarial QA and Omotenashi drills."""
        self.stdout.write("  🧪 Cenários de segurança/confiabilidade...")

        now = timezone.now()
        web = channels.get("web")
        product = products.get("CT") or next(iter(products.values()), None)
        if web is None or product is None:
            self.stdout.write("  ⏭️  Sem canal web/produto para cenários de borda")
            return

        low_attention = customers.get("CLI-001")
        if low_attention:
            low_attention.metadata = {
                **(low_attention.metadata if isinstance(low_attention.metadata, dict) else {}),
                "seed_persona": "low_attention",
                "qa_notes": [
                    "tende a clicar duas vezes em confirmar",
                    "abandona pagamento PIX e volta pelo tracking",
                    "precisa de mensagens curtas e recuperação clara",
                ],
            }
            low_attention.save(update_fields=["metadata"])

        created = 0

        pending = self._create_edge_order(
            seed_key="security:payment-pending-near-expiry",
            channel_ref=web.ref,
            status=Order.Status.ACCEPTED,
            product=product,
            qty=Decimal("2"),
            customer=low_attention,
            created_at=now - timedelta(minutes=4),
            data={
                "customer": {"name": getattr(low_attention, "name", "Cliente distraído")},
                "payment": {
                    "method": "pix",
                    "amount_q": product.base_price_q * 2,
                    "expires_at": (now + timedelta(minutes=6)).replace(microsecond=0).isoformat(),
                },
                "fulfillment_type": "pickup",
                "edge_case": "low_attention_payment_pending",
                "availability_decision": {"approved": True, "source": "seed:edge", "decisions": []},
            },
        )
        if pending:
            self._attach_edge_payment_intent(
                pending,
                method=PaymentIntent.Method.PIX,
                status=PaymentIntent.Status.PENDING,
                gateway="efi",
                gateway_id="seed-edge-pix-pending",
                expires_at=now + timedelta(minutes=6),
            )
            created += 1

        expired = self._create_edge_order(
            seed_key="security:payment-expired-low-attention",
            channel_ref=web.ref,
            status=Order.Status.ACCEPTED,
            product=product,
            qty=Decimal("1"),
            customer=low_attention,
            created_at=now - timedelta(minutes=18),
            data={
                "customer": {"name": getattr(low_attention, "name", "Cliente distraído")},
                "payment": {
                    "method": "pix",
                    "amount_q": product.base_price_q,
                    "expires_at": (now - timedelta(minutes=3)).replace(microsecond=0).isoformat(),
                },
                "fulfillment_type": "pickup",
                "edge_case": "low_attention_payment_expired",
                "availability_decision": {"approved": True, "source": "seed:edge", "decisions": []},
            },
        )
        if expired:
            self._attach_edge_payment_intent(
                expired,
                method=PaymentIntent.Method.PIX,
                status=PaymentIntent.Status.PENDING,
                gateway="efi",
                gateway_id="seed-edge-pix-expired",
                expires_at=now - timedelta(minutes=3),
            )
            created += 1

        late_paid = self._create_edge_order(
            seed_key="security:payment-after-cancel",
            channel_ref=web.ref,
            status=Order.Status.CANCELLED,
            product=product,
            qty=Decimal("3"),
            customer=low_attention,
            created_at=now - timedelta(minutes=26),
            data={
                "customer": {"name": getattr(low_attention, "name", "Cliente distraído")},
                "payment": {
                    "method": "pix",
                    "amount_q": product.base_price_q * 3,
                    "expires_at": (now - timedelta(minutes=10)).replace(microsecond=0).isoformat(),
                },
                "fulfillment_type": "pickup",
                "cancellation_reason": "customer_requested",
                "edge_case": "late_payment_after_cancel",
                "availability_decision": {"approved": True, "source": "seed:edge", "decisions": []},
            },
        )
        if late_paid:
            self._attach_edge_payment_intent(
                late_paid,
                method=PaymentIntent.Method.PIX,
                status=PaymentIntent.Status.CAPTURED,
                gateway="efi",
                gateway_id="seed-edge-pix-after-cancel",
                captured_at=now - timedelta(minutes=5),
            )
            OperatorAlert.objects.get_or_create(
                type="payment_after_cancel",
                order_ref=late_paid.ref,
                defaults={
                    "severity": "critical",
                    "message": (
                        f"Pagamento capturado depois do cancelamento do pedido {late_paid.ref}. "
                        "Validar reembolso e comunicação com o cliente."
                    ),
                },
            )
            self._mark_edge_webhook_replay(
                scope="webhook:efi-pix",
                source="e2e",
                source_id="seed-edge-e2e-after-cancel",
                response_body={
                    "status": "processed",
                    "txid": f"seed-edge-pix-after-cancel-{late_paid.ref}",
                    "e2e_id": "seed-edge-e2e-after-cancel",
                },
                now=now,
            )
            created += 1

        # Cenário "iFood parado" (pedido NEW há 46min + alerta stale) foi omitido de
        # propósito: a coluna Entrada nasce 100% vazia para testar a chegada de pedidos
        # novos ao vivo. O comportamento do alerta stale_new_order segue coberto em testes.

        self.stdout.write(f"  ✅ {created} cenários determinísticos de borda")

    def _mark_edge_webhook_replay(
        self,
        *,
        scope: str,
        source: str,
        source_id: str,
        response_body: dict,
        now,
    ) -> None:
        from shopman.shop.services.webhook_idempotency import stable_webhook_key

        key = f"{source}:{stable_webhook_key(source_id)}"
        IdempotencyKey.objects.update_or_create(
            scope=scope,
            key=key,
            defaults={
                "status": "done",
                "response_code": 200,
                "response_body": response_body,
                "expires_at": now + timedelta(days=30),
            },
        )

    def _create_edge_order(
        self,
        *,
        seed_key: str,
        channel_ref: str,
        status: str,
        product,
        qty: Decimal,
        customer,
        created_at: datetime,
        data: dict,
        external_ref: str | None = None,
    ) -> Order | None:
        existing = Order.objects.filter(snapshot__seed_key=seed_key).first()
        if existing:
            return None

        total_q = int(qty * product.base_price_q)
        ref = self._new_order_ref(channel_ref, created_at.date())
        handle_ref = ""
        if customer is not None:
            handle_ref = (
                customer.contact_points.filter(type="whatsapp")
                .values_list("value_normalized", flat=True)
                .first()
                or customer.phone
                or ""
            )
            data.setdefault("customer_ref", customer.ref)

        order = Order.objects.create(
            ref=ref,
            channel_ref=channel_ref,
            session_key=f"seed-edge-{ref}",
            status=status,
            total_q=total_q,
            handle_type="phone" if handle_ref else "marketplace_order",
            handle_ref=handle_ref,
            external_ref=external_ref,
            snapshot={
                "seed": "nelson",
                "seed_namespace": "security_reliability_edges",
                "seed_key": seed_key,
            },
            data=data,
        )
        self._stamp_order(order, created_at)
        OrderItem.objects.create(
            order=order,
            line_id=f"L-{uuid.uuid4().hex[:8]}",
            sku=product.sku,
            name=product.name,
            qty=qty,
            unit_price_q=product.base_price_q,
            line_total_q=total_q,
            meta={"seed": "nelson", "source": "security_reliability_edges"},
        )
        OrderEvent.objects.create(
            order=order,
            type="status_change",
            seq=0,
            payload={"new_status": status, "source": "seed:edge"},
            created_at=created_at,
        )
        return order

    def _attach_edge_payment_intent(
        self,
        order: Order,
        *,
        method: str,
        status: str,
        gateway: str,
        gateway_id: str,
        expires_at=None,
        captured_at=None,
    ) -> None:
        intent = PaymentIntent.objects.create(
            ref=f"PI-EDGE-{uuid.uuid4().hex[:10].upper()}",
            order_ref=order.ref,
            method=method,
            status=status,
            amount_q=order.total_q,
            gateway=gateway,
            gateway_id=f"{gateway_id}-{order.ref}",
            expires_at=expires_at,
            captured_at=captured_at,
        )
        payment = dict((order.data or {}).get("payment") or {})
        payment["intent_ref"] = intent.ref
        if status == PaymentIntent.Status.CAPTURED:
            PaymentTransaction.objects.create(
                intent=intent,
                type=PaymentTransaction.Type.CAPTURE,
                amount_q=order.total_q,
                gateway_id=intent.gateway_id,
            )
        order.data = {**(order.data or {}), "payment": payment}
        order.save(update_fields=["data", "updated_at"])

    def _seed_production_demand_history(self, products, channels, now) -> int:
        """Stable same-weekday demand rows for Craftsman production suggestions."""
        pdv = channels["pdv"]
        # Demanda semanal ≈ produção típica de cada SKU (QA Pablo: o Sugerido
        # nasce de histórico + encomendas — deve sair PRÓXIMO do planejado,
        # nunca zerado/baixinho). 4 semanas com variação realista por SKU.
        def weeks(base: int) -> list[Decimal]:
            return [
                Decimal(str(max(1, round(base * factor))))
                for factor in (1.05, 1.15, 0.9, 1.1)
            ]

        # Espelha o production_plan calibrado com os XMLs de NFC-e (o Sugerido
        # deve sair PRÓXIMO do planejado — ver comentário acima).
        history = {
            "BF": weeks(22),
            "CGO": weeks(16),
            "CI": weeks(24),
            "SK": weeks(18),
            "KP": weeks(8),
            "CT": weeks(42),
            "PC": weeks(36),
            "ANC": weeks(16),
            "MD": weeks(68),
        }
        # Ancora no localdate (fuso da loja), não em now(): o backend de demanda
        # filtra o histórico por __week_day, que extrai o dia convertendo para
        # settings.TIME_ZONE. Perto da meia-noite UTC, now() cai no dia UTC — um
        # dia-da-semana adiante do fuso local — e a sugestão do mesmo-dia-da-semana
        # nasce zerada. localdate() faz histórico e consulta baterem no mesmo fuso.
        #
        # Duas âncoras porque a sugestão amostra o dia PLANEJADO: o padeiro
        # planeja hoje na tela e amanhã pelo comando, então os dois dias-da-semana
        # precisam de histórico. Uma âncora só deixaria metade dos casos de QA
        # com sugestão vazia.
        today = timezone.localdate()
        anchors = {today, today + timedelta(days=1)}
        created_or_updated = 0
        for sku, quantities in history.items():
            product = products.get(sku)
            if product is None:
                continue
            for anchor, (index, qty) in (
                (anchor, pair)
                for anchor in sorted(anchors)
                for pair in enumerate(quantities, start=1)
            ):
                order_time = timezone.make_aware(
                    datetime.combine(anchor - timedelta(days=7 * index), time(hour=10, minute=15))
                )
                seed_key = f"production-demand-history:{sku}:{anchor.weekday()}:{index}"
                # No perfil qa a ref precisa ser previsível/idempotente: _new_order_ref
                # sorteia sufixo via secrets (não-semeável), então usamos ref literal.
                if getattr(self, "profile", "demo") == "qa":
                    ref = f"QADH-{sku}-{anchor.weekday()}{index}"
                else:
                    ref = self._new_order_ref(pdv.ref, order_time.date())
                total_q = int(qty * product.base_price_q)
                order = Order.objects.filter(snapshot__seed_key=seed_key).first()
                if order is None:
                    order = Order.objects.create(
                        ref=ref,
                        channel_ref=pdv.ref,
                        session_key=f"seed-{ref}",
                        status=Order.Status.COMPLETED,
                        snapshot={
                            "seed": "nelson",
                            "source": "production_demand_history",
                            "seed_key": seed_key,
                        },
                        data={"availability_decision": {"approved": True, "source": "seed", "decisions": []}},
                        total_q=total_q,
                        completed_at=order_time,
                    )
                    self._stamp_order(order, order_time)
                    OrderEvent.objects.create(
                        order=order,
                        type="status_change",
                        seq=0,
                        payload={"new_status": "completed", "source": "seed"},
                        created_at=order_time,
                    )
                else:
                    Order.objects.filter(pk=order.pk).update(
                        status=Order.Status.COMPLETED,
                        completed_at=order_time,
                    )
                Order.objects.filter(pk=order.pk).update(created_at=order_time, updated_at=order_time)
                OrderItem.objects.update_or_create(
                    order=order,
                    line_id="production-history",
                    defaults={
                        "sku": sku,
                        "name": product.name,
                        "qty": qty,
                        "unit_price_q": product.base_price_q,
                        "line_total_q": total_q,
                        "meta": {"seed": "nelson", "source": "production_demand_history"},
                    },
                )
                created_or_updated += 1
        return created_or_updated

    # ────────────────────────────────────────────────────────────────
    # Cenários nomeados determinísticos (perfil qa) — Fase 2
    # ────────────────────────────────────────────────────────────────

    # Caminho linear canônico de status para reconstruir a trilha de eventos.
    _QA_STATUS_PATH = [
        Order.Status.NEW,
        Order.Status.ACCEPTED,
        Order.Status.PREPARING,
        Order.Status.READY,
        Order.Status.DISPATCHED,
        Order.Status.DELIVERED,
        Order.Status.COMPLETED,
    ]

    def _qa_line(self, product, qty: int, name: str | None = None) -> dict:
        return {
            "sku": product.sku,
            "name": name or product.name,
            "qty": qty,
            "unit_price_q": product.base_price_q,
            "line_total_q": product.base_price_q * qty,
        }

    def _qa_status_events(self, order: Order, created_at: datetime) -> None:
        """Reconstrói a trilha de eventos até o status atual (determinística)."""
        status = order.status
        if status == Order.Status.CANCELLED:
            path = [Order.Status.NEW, Order.Status.ACCEPTED, Order.Status.CANCELLED]
        elif status == Order.Status.RETURNED:
            path = [
                Order.Status.NEW, Order.Status.ACCEPTED, Order.Status.PREPARING,
                Order.Status.READY, Order.Status.DISPATCHED, Order.Status.DELIVERED,
                Order.Status.RETURNED,
            ]
        else:
            idx = self._QA_STATUS_PATH.index(status)
            path = self._QA_STATUS_PATH[: idx + 1]
        for seq, step in enumerate(path):
            OrderEvent.objects.create(
                order=order,
                type="status_change",
                seq=seq,
                payload={"new_status": step, "source": "seed:qa"},
                created_at=created_at + timedelta(minutes=seq),
            )

    def _make_qa_order(
        self,
        *,
        ref: str,
        channel_ref: str,
        status: str,
        items: list[dict],
        data: dict,
        minutes_ago: int,
        handle_ref: str = "",
        handle_type: str = "phone",
        external_ref: str | None = None,
    ) -> Order:
        now = timezone.now()
        created_at = now - timedelta(minutes=minutes_ago)
        total_q = sum(item["line_total_q"] for item in items)
        order_data = {
            "availability_decision": {"approved": True, "source": "seed:qa", "decisions": []},
            **data,
        }
        completed_at = created_at + timedelta(minutes=15) if status in (
            Order.Status.COMPLETED, Order.Status.DELIVERED,
        ) else None
        order = Order.objects.create(
            ref=ref,
            channel_ref=channel_ref,
            session_key=f"seed-qa-{ref}",
            status=status,
            total_q=total_q,
            handle_type=handle_type,
            handle_ref=handle_ref,
            external_ref=external_ref,
            completed_at=completed_at,
            snapshot={"seed": "nelson", "seed_namespace": "qa", "seed_key": ref},
            data=order_data,
        )
        self._stamp_order(order, created_at)
        for index, item in enumerate(items):
            OrderItem.objects.create(
                order=order,
                line_id=f"L-QA-{ref}-{index}",
                sku=item["sku"],
                name=item["name"],
                qty=Decimal(str(item["qty"])),
                unit_price_q=item["unit_price_q"],
                line_total_q=item["line_total_q"],
                meta={"seed": "nelson", "source": "qa"},
            )
        self._qa_status_events(order, created_at)
        return order

    def _seed_qa_orders(self, products, customers, channels):
        """Cria os pedidos-cenário nomeados do perfil qa (refs QA-*)."""
        self.stdout.write("  🎯 Cenários qa nomeados (pedidos)...")

        def pick(*skus):
            for sku in skus:
                if sku in products:
                    return products[sku]
            return next(iter(products.values()))

        croissant = pick("CT", "BF")
        baguete = pick("BF", "CT")
        pain = pick("PC", "SK", "CT")

        web = channels["web"].ref
        pdv = channels["pdv"].ref
        today = timezone.localdate()
        tomorrow = (today + timedelta(days=1)).isoformat()

        created = 0

        # ── QA-PREORDER-* — encomenda para amanhã (novo + confirmado) ─────────
        preorder_data = {
            "fulfillment_type": "delivery",
            "delivery_date": tomorrow,
            "delivery_time_slot": "manha",
            "is_preorder": True,
            "customer": {"name": "Cliente Encomenda QA"},
        }
        self._make_qa_order(
            ref="QA-PREORDER-01",
            channel_ref=web,
            status=Order.Status.NEW,
            items=[self._qa_line(croissant, 6), self._qa_line(baguete, 4)],
            data={**preorder_data},
            minutes_ago=12,
        )
        self._make_qa_order(
            ref="QA-PREORDER-02",
            channel_ref=web,
            status=Order.Status.ACCEPTED,
            items=[self._qa_line(pain, 8)],
            data={**preorder_data, "customer": {"name": "Cliente Encomenda Confirmada QA"}},
            minutes_ago=30,
        )
        created += 2

        # ── QA-PAID-READY-* — pago (PIX/cartão capturado) em ready/dispatched ──
        paid_pix = self._make_qa_order(
            ref="QA-PAID-READY-01",
            channel_ref=web,
            status=Order.Status.READY,
            items=[self._qa_line(croissant, 3), self._qa_line(pain, 2)],
            data={
                "fulfillment_type": "pickup",
                "customer": {"name": "Cliente Pago PIX QA"},
                "payment": {"method": "pix"},
            },
            minutes_ago=18,
        )
        self._attach_edge_payment_intent(
            paid_pix,
            method=PaymentIntent.Method.PIX,
            status=PaymentIntent.Status.CAPTURED,
            gateway="efi",
            gateway_id="seed-qa-pix-captured",
            captured_at=paid_pix.created_at + timedelta(minutes=3),
        )
        paid_card = self._make_qa_order(
            ref="QA-PAID-READY-02",
            channel_ref=web,
            status=Order.Status.DISPATCHED,
            items=[self._qa_line(baguete, 5)],
            data={
                "fulfillment_type": "delivery",
                "customer": {"name": "Cliente Pago Cartão QA"},
                "payment": {"method": "card"},
            },
            minutes_ago=22,
        )
        self._attach_edge_payment_intent(
            paid_card,
            method=PaymentIntent.Method.CARD,
            status=PaymentIntent.Status.CAPTURED,
            gateway="stripe",
            gateway_id="seed-qa-card-captured",
            captured_at=paid_card.created_at + timedelta(minutes=4),
        )
        created += 2

        # ── QA-RETURNED-01 — entregue, devolvido e estornado ──────────────────
        returned = self._make_qa_order(
            ref="QA-RETURNED-01",
            channel_ref=web,
            status=Order.Status.RETURNED,
            items=[self._qa_line(croissant, 4)],
            data={
                "fulfillment_type": "delivery",
                "customer": {"name": "Cliente Devolução QA"},
                "payment": {"method": "pix", "refunded": True},
                "return_reason": "produto danificado no transporte",
            },
            minutes_ago=180,
        )
        returned_intent = PaymentIntent.objects.create(
            ref="PI-QA-RETURNED-01",
            order_ref=returned.ref,
            method=PaymentIntent.Method.PIX,
            status=PaymentIntent.Status.REFUNDED,
            amount_q=returned.total_q,
            gateway="efi",
            gateway_id=f"seed-qa-refunded-{returned.ref}",
            captured_at=returned.created_at + timedelta(minutes=5),
        )
        PaymentTransaction.objects.create(
            intent=returned_intent,
            type=PaymentTransaction.Type.CAPTURE,
            amount_q=returned.total_q,
            gateway_id=returned_intent.gateway_id,
        )
        PaymentTransaction.objects.create(
            intent=returned_intent,
            type=PaymentTransaction.Type.REFUND,
            amount_q=returned.total_q,
            gateway_id=f"{returned_intent.gateway_id}-refund",
        )
        returned.data = {
            **(returned.data or {}),
            "payment": {**(returned.data or {}).get("payment", {}), "intent_ref": returned_intent.ref},
        }
        returned.save(update_fields=["data", "updated_at"])
        OperatorAlert.objects.get_or_create(
            type="order_returned",
            order_ref=returned.ref,
            defaults={
                "severity": "warning",
                "message": f"Pedido {returned.ref} devolvido e estornado — conferir motivo e estoque.",
            },
        )
        created += 1

        # ── QA-PIX-PENDING-01 — confirmado, PIX pendente (não pago) ───────────
        pix_pending = self._make_qa_order(
            ref="QA-PIX-PENDING-01",
            channel_ref=web,
            status=Order.Status.ACCEPTED,
            items=[self._qa_line(pain, 2), self._qa_line(baguete, 2)],
            data={
                "fulfillment_type": "pickup",
                "customer": {"name": "Cliente PIX Pendente QA"},
                "payment": {
                    "method": "pix",
                    "expires_at": (timezone.now() + timedelta(minutes=8)).replace(microsecond=0).isoformat(),
                },
            },
            minutes_ago=5,
        )
        self._attach_edge_payment_intent(
            pix_pending,
            method=PaymentIntent.Method.PIX,
            status=PaymentIntent.Status.PENDING,
            gateway="efi",
            gateway_id="seed-qa-pix-pending",
            expires_at=timezone.now() + timedelta(minutes=8),
        )
        created += 1

        # ── QA-IFOOD-01 — canal marketplace (fluxo de cancelamento iFood) ─────
        if "ifood" in channels:
            self._make_qa_order(
                ref="QA-IFOOD-01",
                channel_ref=channels["ifood"].ref,
                status=Order.Status.ACCEPTED,
                items=[self._qa_line(croissant, 2)],
                data={
                    "fulfillment_type": "delivery",
                    "customer": {"name": "Cliente iFood QA"},
                    "payment": {"method": "external", "timing": "external"},
                    "origin_channel": "ifood",
                },
                minutes_ago=9,
                handle_type="marketplace_order",
                external_ref="IFOOD-QA-0001",
            )
            created += 1

        # ── QA-NOTES-01 — pedido web com observação do cliente (order_notes) ──
        self._make_qa_order(
            ref="QA-NOTES-01",
            channel_ref=web,
            status=Order.Status.PREPARING,
            items=[self._qa_line(baguete, 3)],
            data={
                "fulfillment_type": "pickup",
                "customer": {"name": "Cliente Observação QA"},
                "order_notes": "Bem assadinha, por favor. Cortar ao meio.",
            },
            minutes_ago=8,
        )
        created += 1

        # ── QA-NAMED-ITEMS-01 — OrderItem.name preenchido (regressão SKU cru) ─
        self._make_qa_order(
            ref="QA-NAMED-ITEMS-01",
            channel_ref=pdv,
            status=Order.Status.PREPARING,
            items=[
                self._qa_line(croissant, 2, name="Croissant Tradicional"),
                self._qa_line(pain, 1, name="Pain au Chocolat"),
            ],
            data={
                "fulfillment_type": "pickup",
                "customer": {"name": "Cliente Itens Nomeados QA"},
            },
            minutes_ago=6,
        )
        created += 1

        self.stdout.write(f"  ✅ {created} pedidos-cenário qa (refs QA-*)")

    def _seed_qa_production_stuck_batch(self):
        """WorkOrder iniciada ONTEM e ainda em andamento (fornada de dia anterior presa).

        Cenário do QA: uma fornada que ficou 'started' virando o dia. Identificável
        pelo source_ref ``seed:production:qa-stuck:*``. As WOs de hoje (cada estado) e
        o histórico já vêm de _seed_recipes (base estática determinística no qa).
        """
        from shopman.craftsman.models import WorkOrderEvent

        recipe = Recipe.objects.filter(ref="baguete").first()
        if recipe is None:
            return
        yesterday = timezone.localdate() - timedelta(days=1)
        tz_info = timezone.get_current_timezone()
        source_ref = f"seed:production:qa-stuck:{yesterday.isoformat()}:{recipe.ref}"
        started_at = datetime.combine(yesterday, time(5, 0), tzinfo=tz_info)

        work_order = WorkOrder.objects.filter(source_ref=source_ref).first()
        if work_order is None:
            work_order = WorkOrder(source_ref=source_ref)
        work_order.recipe = recipe
        work_order.output_sku = recipe.output_sku
        work_order.quantity = Decimal("30")
        work_order.finished = None
        work_order.status = WorkOrder.Status.STARTED
        work_order.target_date = yesterday
        work_order.started_at = started_at
        work_order.finished_at = None
        work_order.position_ref = "producao"
        work_order.operator_ref = "chef:ana"
        work_order.meta = {"seed": True, "scope": "qa-stuck", "qa_scenario": "stuck_previous_day_batch"}
        work_order.save()
        work_order.events.all().delete()
        for seq, (kind, when, payload) in enumerate([
            (WorkOrderEvent.Kind.PLANNED, datetime.combine(yesterday, time(3, 0), tzinfo=tz_info),
             {"quantity": "30", "recipe": recipe.ref, "output_sku": recipe.output_sku,
              "target_date": yesterday.isoformat(), "source_ref": source_ref}),
            (WorkOrderEvent.Kind.STARTED, started_at,
             {"quantity": "30", "operator_ref": "chef:ana", "note": "seed qa: fornada presa"}),
        ]):
            event = WorkOrderEvent.objects.create(
                work_order=work_order, seq=seq, kind=kind, payload=payload, actor="seed",
            )
            WorkOrderEvent.objects.filter(pk=event.pk).update(created_at=when)

        self.stdout.write("  ✅ 1 fornada presa de ontem (qa-stuck, started)")

    def _seed_qa_pos_tabs(self):
        """Comandas POS do perfil qa: base + uma com item JÁ disparado à cozinha."""
        self.stdout.write("  🧾 Comandas qa (POS)...")

        # Base de tabs (rows POSTab) — inclui 00001007 que _seed_sessions usa como
        # comanda aberta com itens.
        self._seed_pos_tabs()

        from shopman.shop.services.kds import fire_lines

        # Comanda com item já disparado à cozinha (KDS ticket criado).
        fired_tab = "00002001"
        POSTab.objects.update_or_create(
            ref=fired_tab,
            defaults={"label": "QA Disparada", "is_active": True},
        )
        session_key = f"seed-qa-postab-{fired_tab}"
        session, _ = Session.objects.update_or_create(
            channel_ref="pdv",
            state="open",
            handle_type="pos_tab",
            handle_ref=fired_tab,
            defaults={
                "session_key": session_key,
                "pricing_policy": "internal",
                "edit_policy": "open",
                "data": {
                    "origin_channel": "pos",
                    "fulfillment_type": "pickup",
                    "tab_ref": fired_tab,
                    "tab_display": fired_tab.lstrip("0"),
                    "pos_operator": "seed",
                },
            },
        )
        lines = [
            {"line_id": f"L-QA-{fired_tab}-0", "sku": "CT", "name": "Croissant Tradicional",
             "qty": 2, "unit_price_q": 1300, "line_total_q": 2600},
            {"line_id": f"L-QA-{fired_tab}-1", "sku": "PC", "name": "Pain au Chocolat",
             "qty": 1, "unit_price_q": 1500, "line_total_q": 1500},
        ]
        session.update_items(lines)
        # Dispara à cozinha: cria KDSTicket(s) para as linhas roteáveis.
        fire_lines(session_key=session.session_key, lines=lines)

        self.stdout.write("  ✅ Comanda qa 00002001 com item disparado à cozinha")

    def _stamp_order(self, order: Order, created_at: datetime):
        Order.objects.filter(pk=order.pk).update(created_at=created_at, updated_at=created_at)
        order.created_at = created_at
        order.updated_at = created_at

    def _new_order_ref(self, channel_ref: str, business_date: date) -> str:
        for _attempt in range(20):
            ref = generate_order_ref(channel_ref=channel_ref, business_date=business_date)
            if not Order.objects.filter(ref=ref).exists():
                return ref
        raise CommandError(f"Nao foi possivel gerar ORDER_REF unico para canal {channel_ref!r}.")

    def _seed_pos_tabs(self):
        self.stdout.write("  🧾 POS tabs...")

        tabs = [
            ("00001007", "1007"),
            ("00001008", "1008"),
            ("00001009", "1009"),
            ("00001010", "1010"),
            ("00001011", "1011"),
            ("00001012", "1012"),
        ]
        for ref, label in tabs:
            POSTab.objects.update_or_create(
                ref=ref,
                defaults={"label": label, "is_active": True},
            )

        self.stdout.write(f"  ✅ {len(tabs)} POS tabs cadastradas")

    # ────────────────────────────────────────────────────────────────
    # Sessoes abertas (Orderman)
    # ────────────────────────────────────────────────────────────────

    def _seed_sessions(self, channels):
        self.stdout.write("  📝 Sessoes abertas...")

        for channel_ref, items in [
            ("pdv", [
                {"line_id": uuid.uuid4().hex[:8], "sku": "CT", "name": "Croissant Tradicional", "qty": 2, "unit_price_q": 1300, "line_total_q": 2600},
                {"line_id": uuid.uuid4().hex[:8], "sku": "PC", "name": "Pain au Chocolat", "qty": 1, "unit_price_q": 1500, "line_total_q": 1500},
            ]),
            ("web", [
                {"line_id": uuid.uuid4().hex[:8], "sku": "BF", "name": "Baguete Francesa", "qty": 3, "unit_price_q": 1300, "line_total_q": 3900},
                {"line_id": uuid.uuid4().hex[:8], "sku": "FOA", "name": "Focaccia Alecrim", "qty": 1, "unit_price_q": 2800, "line_total_q": 2800},
            ]),
            ("whatsapp", [
                {"line_id": uuid.uuid4().hex[:8], "sku": "BF", "name": "Baguete Francesa", "qty": 10, "unit_price_q": 1300, "line_total_q": 13000},
                {"line_id": uuid.uuid4().hex[:8], "sku": "CT", "name": "Croissant Tradicional", "qty": 20, "unit_price_q": 1300, "line_total_q": 26000},
            ]),
        ]:
            ch = channels[channel_ref]
            from shopman.shop.config import ChannelConfig

            cfg = ChannelConfig.for_channel(ch)
            defaults = {
                "session_key": generate_session_key(),
                "state": "open",
                "pricing_policy": cfg.pricing.policy,
                "edit_policy": cfg.editing.policy,
            }
            if channel_ref == "pdv":
                tab_ref = "00001007"
                defaults["handle_type"] = "pos_tab"
                defaults["handle_ref"] = tab_ref
                defaults["data"] = {
                    "origin_channel": "pos",
                    "fulfillment_type": "pickup",
                    "tab_ref": tab_ref,
                    "tab_display": tab_ref.lstrip("0"),
                    "pos_operator": "seed",
                    "last_touched_at": timezone.now().isoformat(),
                }
                session, _ = Session.objects.update_or_create(
                    channel_ref=ch.ref,
                    state="open",
                    handle_type="pos_tab",
                    handle_ref=tab_ref,
                    defaults=defaults,
                )
            else:
                session = Session.objects.create(
                    channel_ref=ch.ref,
                    **defaults,
                )
            session.update_items(items)

        self.stdout.write("  ✅ 3 sessoes abertas")

    # ────────────────────────────────────────────────────────────────
    # Alertas de estoque (Stockman)
    # ────────────────────────────────────────────────────────────────

    def _seed_stock_alerts(self, products, positions):
        self.stdout.write("  🔔 Alertas de estoque...")

        vitrine = positions["vitrine"]
        alerts_data = [
            ("BF", 10),
            ("MIB", 12),
            ("FE", 15),
            ("CT", 15),
            ("PC", 12),
            ("SK", 6),
            ("FOA", 4),
            ("CI", 8),
        ]

        for sku, min_qty in alerts_data:
            if sku in products:
                StockAlert.objects.update_or_create(
                    sku=sku,
                    position=vitrine,
                    defaults={
                        "min_quantity": Decimal(str(min_qty)),
                    },
                )

        self.stdout.write(f"  ✅ {len(alerts_data)} alertas configurados")

    def _seed_operator_alerts(self):
        self.stdout.write("  🚨 Alertas operacionais...")

        from shopman.shop.handlers.production_alerts import (
            check_late_started_orders,
            create_stock_short_alert,
            ensure_late_check_scheduled,
            maybe_create_low_yield_alert,
        )

        ensure_late_check_scheduled()
        today = timezone.localdate()
        created_late = check_late_started_orders(selected_date=today)
        created_yield = 0
        for work_order in WorkOrder.objects.filter(
            source_ref__startswith="seed:production:today:",
            status=WorkOrder.Status.FINISHED,
        ):
            if maybe_create_low_yield_alert(work_order):
                created_yield += 1

        shortage_target = (
            WorkOrder.objects.filter(
                source_ref__startswith="seed:production:today:",
                output_sku="CT",
            )
            .order_by("created_at")
            .first()
        )
        if shortage_target:
            create_stock_short_alert(
                work_order_ref=shortage_target.ref,
                output_sku=shortage_target.output_sku,
                error="sementes de validação: manteiga francesa abaixo do ponto de reposição",
            )

        active_count = OperatorAlert.objects.filter(acknowledged=False).count()
        self.stdout.write(
            f"  ✅ Alertas operacionais ativos: {active_count}"
            f" ({created_late} atraso, {created_yield} rendimento)"
        )

    # ────────────────────────────────────────────────────────────────
    # Enderecos de clientes (Customers)
    # ────────────────────────────────────────────────────────────────

    def _seed_addresses(self, customers):
        self.stdout.write("  📍 Enderecos de clientes...")

        addresses_data = [
            ("CLI-001", [
                {"label": "home", "formatted_address": "Rua Belo Horizonte, 540, Apto 12 - Centro, Londrina - PR, 86020-060",
                 "route": "Rua Belo Horizonte", "street_number": "540", "complement": "Apto 12",
                 "neighborhood": "Centro", "city": "Londrina", "state": "Paraná",
                 "state_code": "PR", "postal_code": "86020-060",
                 "latitude": Decimal("-23.3103000"), "longitude": Decimal("-51.1628000"), "is_default": True},
                {"label": "work", "formatted_address": "Av. Higienópolis, 350, Sala 201 - Higienópolis, Londrina - PR, 86020-080",
                 "route": "Av. Higienópolis", "street_number": "350", "complement": "Sala 201",
                 "neighborhood": "Higienópolis", "city": "Londrina", "state": "Paraná",
                 "state_code": "PR", "postal_code": "86020-080",
                 "latitude": Decimal("-23.3065000"), "longitude": Decimal("-51.1650000"), "is_default": False},
            ]),
            ("CLI-002", [
                {"label": "work", "formatted_address": "Rua Marselha, 191 - Jardim Piza, Londrina - PR, 86041-140",
                 "route": "Rua Marselha", "street_number": "191", "complement": "",
                 "neighborhood": "Jardim Piza", "city": "Londrina", "state": "Paraná",
                 "state_code": "PR", "postal_code": "86041-140",
                 "latitude": Decimal("-23.2960000"), "longitude": Decimal("-51.1520000"), "is_default": True},
            ]),
            ("CLI-003", [
                {"label": "home", "formatted_address": "Rua Paranaguá, 800, Bl B Apto 5 - Centro, Londrina - PR, 86020-030",
                 "route": "Rua Paranaguá", "street_number": "800", "complement": "Bl B Apto 5",
                 "neighborhood": "Centro", "city": "Londrina", "state": "Paraná",
                 "state_code": "PR", "postal_code": "86020-030",
                 "latitude": Decimal("-23.3080000"), "longitude": Decimal("-51.1595000"), "is_default": True},
            ]),
            ("CLI-004", [
                {"label": "work", "formatted_address": "Av. Madre Leônia Milito, 900 - Bela Suíça, Londrina - PR, 86050-270",
                 "route": "Av. Madre Leônia Milito", "street_number": "900", "complement": "",
                 "neighborhood": "Bela Suíça", "city": "Londrina", "state": "Paraná",
                 "state_code": "PR", "postal_code": "86050-270",
                 "latitude": Decimal("-23.3040000"), "longitude": Decimal("-51.1630000"), "is_default": True},
            ]),
            ("CLI-005", [
                {"label": "home", "formatted_address": "Rua Santos, 450, Apto 3 - Centro, Londrina - PR, 86020-040",
                 "route": "Rua Santos", "street_number": "450", "complement": "Apto 3",
                 "neighborhood": "Centro", "city": "Londrina", "state": "Paraná",
                 "state_code": "PR", "postal_code": "86020-040",
                 "latitude": Decimal("-23.3115000"), "longitude": Decimal("-51.1610000"), "is_default": True},
                {"label": "other", "label_custom": "Casa da mae",
                 "formatted_address": "Rua Pernambuco, 120 - Centro, Londrina - PR, 86020-120",
                 "route": "Rua Pernambuco", "street_number": "120", "complement": "",
                 "neighborhood": "Centro", "city": "Londrina", "state": "Paraná",
                 "state_code": "PR", "postal_code": "86020-120",
                 "latitude": Decimal("-23.3090000"), "longitude": Decimal("-51.1575000"), "is_default": False},
            ]),
            ("CLI-006", [
                {"label": "home", "formatted_address": "Av. Juscelino Kubitschek, 1200 - Ipiranga, Londrina - PR, 86010-540",
                 "route": "Av. Juscelino Kubitschek", "street_number": "1200", "complement": "",
                 "neighborhood": "Ipiranga", "city": "Londrina", "state": "Paraná",
                 "state_code": "PR", "postal_code": "86010-540",
                 "latitude": Decimal("-23.3150000"), "longitude": Decimal("-51.1500000"), "is_default": True},
            ]),
            ("CLI-007", [
                {"label": "work", "formatted_address": "Av. Ayrton Senna, 600 - Gleba Palhano, Londrina - PR, 86050-460",
                 "route": "Av. Ayrton Senna", "street_number": "600", "complement": "",
                 "neighborhood": "Gleba Palhano", "city": "Londrina", "state": "Paraná",
                 "state_code": "PR", "postal_code": "86050-460",
                 "latitude": Decimal("-23.3280000"), "longitude": Decimal("-51.1870000"), "is_default": True},
            ]),
        ]

        count = 0
        for ref, addrs in addresses_data:
            if ref not in customers:
                continue
            customer = customers[ref]
            for addr in addrs:
                label_custom = addr.pop("label_custom", "")
                _, created = CustomerAddress.objects.get_or_create(
                    customer=customer,
                    formatted_address=addr["formatted_address"],
                    defaults={
                        "label": addr["label"],
                        "label_custom": label_custom,
                        "route": addr["route"],
                        "street_number": addr["street_number"],
                        "complement": addr["complement"],
                        "neighborhood": addr["neighborhood"],
                        "city": addr["city"],
                        "state": addr["state"],
                        "state_code": addr["state_code"],
                        "postal_code": addr["postal_code"],
                        "latitude": addr["latitude"],
                        "longitude": addr["longitude"],
                        "is_default": addr["is_default"],
                    },
                )
                if created:
                    count += 1

        self.stdout.write(f"  ✅ {count} enderecos de clientes")

    # ────────────────────────────────────────────────────────────────
    # Promotions e Coupons (Shop)
    # ────────────────────────────────────────────────────────────────

    def _seed_promotions(self):
        self.stdout.write("  🏷️  Promotions e coupons...")

        now = timezone.now()

        # Promotion 1: Semana do Pão — 15% off pães rústicos (auto, sem cupom)
        Promotion.objects.update_or_create(
            ref="semana-do-pao",
            defaults={
                "name": "Semana do Pão",
                "type": Promotion.PERCENT,
                "value": 15,
                "valid_from": now,
                "valid_until": now + timedelta(days=7),
                "collections": ["rusticos"],
                "is_active": True,
            },
        )

        # Promotion for NELSON10 coupon (10% off geral)
        promo_nelson10, _ = Promotion.objects.update_or_create(
            ref="nelson10",
            defaults={
                "name": "Desconto Nelson 10%",
                "type": Promotion.PERCENT,
                "value": 10,
                "valid_from": now,
                "valid_until": now + timedelta(days=30),
                "is_active": True,
            },
        )

        # Promotion for PRIMEIRACOMPRA coupon (R$5 off, min R$30)
        promo_primeira, _ = Promotion.objects.update_or_create(
            ref="primeira-compra",
            defaults={
                "name": "Primeira Compra",
                "type": Promotion.FIXED,
                "value": 500,
                "valid_from": now,
                "valid_until": now + timedelta(days=30),
                "min_order_q": 3000,
                "is_active": True,
            },
        )

        # Promotion for FUNCIONARIO coupon (20% off, restricted to staff group)
        promo_funcionario, _ = Promotion.objects.update_or_create(
            ref="funcionario",
            defaults={
                "name": "Desconto Funcionário",
                "type": Promotion.PERCENT,
                "value": 20,
                "valid_from": now,
                "valid_until": now + timedelta(days=365),
                "customer_segments": ["staff"],
                "is_active": True,
            },
        )

        # Promotion: Parabéns! — 10% off no dia do aniversário
        Promotion.objects.update_or_create(
            ref="aniversario",
            defaults={
                "name": "Parabéns! Desconto de aniversário",
                "type": Promotion.PERCENT,
                "value": 10,
                "valid_from": now,
                "valid_until": now + timedelta(days=365),
                "birthday_only": True,
                "is_active": True,
            },
        )

        # Coupons
        Coupon.objects.update_or_create(
            code="NELSON10",
            defaults={"promotion": promo_nelson10, "max_uses": 1, "is_active": True},
        )
        Coupon.objects.update_or_create(
            code="PRIMEIRACOMPRA",
            defaults={"promotion": promo_primeira, "max_uses": 1, "is_active": True},
        )
        Coupon.objects.update_or_create(
            code="FUNCIONARIO",
            defaults={"promotion": promo_funcionario, "max_uses": 0, "is_active": True},
        )

        self.stdout.write("  ✅ 5 promotions, 3 coupons")

    # ────────────────────────────────────────────────────────────────
    # Payments (PaymentIntent + PaymentTransaction)
    # ────────────────────────────────────────────────────────────────

    def _seed_payments(self):
        self.stdout.write("  💳 Payments...")

        orders = Order.objects.filter(status__in=["completed", "delivered"])
        count = 0
        linked = 0

        for i, order in enumerate(orders):
            existing_intent = PaymentIntent.objects.filter(order_ref=order.ref).order_by("-created_at").first()
            if existing_intent:
                if self._attach_order_payment_link(order, existing_intent):
                    linked += 1
                continue

            method = PaymentIntent.Method.PIX if i % 10 < 7 else PaymentIntent.Method.CARD
            gateway = "efi" if method == PaymentIntent.Method.PIX else "stripe"
            intent_ref = f"PI-{uuid.uuid4().hex[:12].upper()}"

            intent = PaymentIntent(
                ref=intent_ref,
                order_ref=order.ref,
                method=method,
                status=PaymentIntent.Status.CAPTURED,
                amount_q=order.total_q,
                gateway=gateway,
                gateway_id=f"gw-{uuid.uuid4().hex[:16]}",
                captured_at=order.created_at + timedelta(minutes=5),
            )
            intent.save()

            PaymentTransaction.objects.create(
                intent=intent,
                type=PaymentTransaction.Type.CAPTURE,
                amount_q=order.total_q,
                gateway_id=intent.gateway_id,
            )
            if self._attach_order_payment_link(order, intent):
                linked += 1
            count += 1

        self.stdout.write(f"  ✅ {count} payment intents + transactions ({linked} order links)")

    def _attach_order_payment_link(self, order: Order, intent: PaymentIntent) -> bool:
        payment = dict((order.data or {}).get("payment") or {})
        next_payment = {
            **payment,
            "method": intent.method,
            "intent_ref": intent.ref,
            "gateway": intent.gateway,
        }
        if payment == next_payment:
            return False
        order.data = {**(order.data or {}), "payment": next_payment}
        order.save(update_fields=["data", "updated_at"])
        return True

    # ────────────────────────────────────────────────────────────────
    # Fulfillments
    # ────────────────────────────────────────────────────────────────

    def _seed_fulfillments(self):
        self.stdout.write("  📦 Fulfillments...")

        count = 0

        # Completed/delivered orders: fulfilled
        for order in Order.objects.filter(status__in=["completed", "delivered"]):
            if Fulfillment.objects.filter(order=order).exists():
                continue

            is_delivery = order.channel_ref in ("whatsapp", "web")

            if is_delivery:
                tracking_code = f"BR{uuid.uuid4().hex[:12].upper()}"
                fulfillment = Fulfillment(
                    order=order,
                    status=Fulfillment.Status.DELIVERED,
                    tracking_code=tracking_code,
                    carrier="correios",
                    dispatched_at=order.created_at + timedelta(minutes=10),
                    delivered_at=order.created_at + timedelta(hours=2),
                )
            else:
                fulfillment = Fulfillment(
                    order=order,
                    status=Fulfillment.Status.DELIVERED,
                    delivered_at=order.created_at + timedelta(minutes=15),
                )

            # Bypass transition validation for seed
            fulfillment.save()

            # Create FulfillmentItems
            for item in order.items.all():
                FulfillmentItem.objects.create(
                    fulfillment=fulfillment,
                    order_item=item,
                    qty=item.qty,
                )

            count += 1

        # Preparing orders: fulfillment in progress
        for order in Order.objects.filter(status="preparing"):
            if Fulfillment.objects.filter(order=order).exists():
                continue

            is_delivery = order.channel_ref in ("whatsapp", "web")

            fulfillment = Fulfillment(
                order=order,
                status=Fulfillment.Status.IN_PROGRESS,
            )
            if is_delivery:
                fulfillment.carrier = "correios"

            fulfillment.save()
            count += 1

        self.stdout.write(f"  ✅ {count} fulfillments")

    # ────────────────────────────────────────────────────────────────
    # Directives
    # ────────────────────────────────────────────────────────────────

    def _seed_directives(self):
        self.stdout.write("  📋 Directives...")

        # Stock holds and payments are now handled inline (services.availability +
        # services.stock + services.payment), not via directives. Only notification
        # and fulfillment remain as async directives.
        NOTIFICATION_SEND = "notification.send"
        FULFILLMENT_CREATE = "fulfillment.create"

        count = 0
        for order in Order.objects.filter(status__in=["completed", "delivered", "preparing", "accepted"]):
            if Directive.objects.filter(payload__order_ref=order.ref).exists():
                continue

            is_terminal = order.status in ("completed", "delivered")
            directive_status = "done" if is_terminal else "queued"
            base_time = order.created_at

            Directive.objects.create(
                topic=NOTIFICATION_SEND,
                status=directive_status,
                payload={"order_ref": order.ref, "template": "order_accepted"},
                available_at=base_time + timedelta(minutes=2),
            )

            if is_terminal:
                Directive.objects.create(
                    topic=FULFILLMENT_CREATE,
                    status="done",
                    payload={"order_ref": order.ref},
                    available_at=base_time + timedelta(minutes=3),
                )

            count += 1

        self.stdout.write(f"  ✅ Directives para {count} pedidos")

    # ────────────────────────────────────────────────────────────────
    # Loyalty (fidelidade)
    # ────────────────────────────────────────────────────────────────

    def _seed_loyalty(self, customers):
        self.stdout.write("  🎖️  Loyalty...")

        try:
            from shopman.guestman.contrib.loyalty.service import LoyaltyService
        except ImportError:
            self.stdout.write("  ⏭️  Loyalty app nao instalado")
            return

        loyalty_data = [
            # (customer_ref, points_to_earn, stamps, tier_desc, redeem_points)
            ("CLI-001", 350, 7, "frequente", 100),
            ("CLI-002", 200, 4, "atacado", 0),
            ("CLI-003", 120, 3, "regular", 0),
            ("CLI-004", 80, 2, "cafe", 0),
            ("CLI-005", 45, 1, "novo", 0),
        ]

        count = 0
        for ref, points, stamps, _desc, redeem in loyalty_data:
            if ref not in customers:
                continue

            account = LoyaltyService.enroll(ref)
            if account.lifetime_points > 0:
                count += 1
                continue

            # Earn points in batches to simulate history
            batch_size = points // 3 or 1
            remaining = points
            order_num = 1
            while remaining > 0:
                earn = min(batch_size, remaining)
                LoyaltyService.earn_points(
                    customer_ref=ref,
                    points=earn,
                    description=f"Pedido #{order_num}",
                    reference=f"seed:order-{order_num}",
                    created_by="seed",
                )
                remaining -= earn
                order_num += 1

            # Add stamps
            for i in range(stamps):
                LoyaltyService.add_stamp(
                    customer_ref=ref,
                    description=f"Compra #{i + 1}",
                    reference=f"seed:stamp-{i + 1}",
                )

            # Redeem points (if specified)
            if redeem > 0:
                LoyaltyService.redeem_points(
                    customer_ref=ref,
                    points=redeem,
                    description="Resgate de pontos",
                    reference="seed:redeem-1",
                    created_by="seed",
                )

            count += 1

        self.stdout.write(f"  ✅ {count} contas de fidelidade")

    # ────────────────────────────────────────────────────────────────
    # KDS (Kitchen Display System)
    # ────────────────────────────────────────────────────────────────

    def _seed_kds(self):
        self.stdout.write("  🖥️  KDS...")

        # Get collections for KDS routing
        col_salgados = Collection.objects.filter(ref="salgados").first()
        col_bebidas_quentes = Collection.objects.filter(ref="bebidas-quentes").first()
        col_bebidas_geladas = Collection.objects.filter(ref="bebidas-geladas").first()

        # Remove old KDS instances that no longer exist
        KDSInstance.objects.filter(ref__in=["paes", "folhados", "salgados"]).delete()

        # KDS Lanches — Prep: montagem de lanches e salgados na hora
        kds_lanches, _ = KDSInstance.objects.update_or_create(
            ref="lanches",
            defaults={
                "name": "Lanches",
                "type": "prep",
                "target_time_minutes": 8,
                "sound_enabled": True,
                "is_active": True,
            },
        )
        kds_lanches.collections.clear()
        for col in [col_salgados]:
            if col:
                kds_lanches.collections.add(col)

        # KDS Cafés — Prep: bebidas quentes e frias
        kds_cafes, _ = KDSInstance.objects.update_or_create(
            ref="cafes",
            defaults={
                "name": "Cafés",
                "type": "prep",
                "target_time_minutes": 3,
                "sound_enabled": True,
                "is_active": True,
            },
        )
        kds_cafes.collections.clear()
        for col in [col_bebidas_quentes, col_bebidas_geladas]:
            if col:
                kds_cafes.collections.add(col)

        # KDS Encomendas — Picking: separação de pedidos de balcão e agendados
        KDSInstance.objects.update_or_create(
            ref="encomendas",
            defaults={
                "name": "Encomendas",
                "type": "picking",
                "target_time_minutes": 5,
                "sound_enabled": True,
                "is_active": True,
            },
        )

        # KDS Expedição — pedidos prontos para balcão/despacho
        KDSInstance.objects.update_or_create(
            ref="expedicao",
            defaults={
                "name": "Expedição",
                "type": "expedition",
                "target_time_minutes": 2,
                "sound_enabled": True,
                "is_active": True,
            },
        )

        KDSInstance.objects.filter(ref__in=["padaria"]).delete()

        self.stdout.write("  ✅ 4 estações KDS (Cafés, Lanches, Encomendas, Expedição)")

    # ────────────────────────────────────────────────────────────────
    # Etiquetas de cliente
    # ────────────────────────────────────────────────────────────────

    def _seed_customer_tags(self, customers):
        """Etiquetas de exemplo — o único público que o operador monta sozinho.

        Existem no seed porque o seletor de público do Marketing nasce VAZIO sem elas, e
        tela vazia não ensina para que serve o recurso. São exemplos plausíveis de padaria,
        não dado real: quem etiqueta de verdade é quem atende.
        """
        self.stdout.write("  🏷️  Etiquetas de cliente...")

        etiquetas = {
            "CLI-001": ["corredores", "vizinho"],
            "CLI-003": ["corredores"],
            "CLI-005": ["sem glúten"],
            "CLI-002": ["entrega na segunda"],
            "CLI-004": ["entrega na segunda"],
        }
        for ref, tags in etiquetas.items():
            customer = customers.get(ref)
            if customer is None:
                continue
            # `resolve` em vez de `set(nomes)`: casar por slug é o que impede "sem glúten"
            # e "sem gluten" de virarem duas etiquetas (ver `guestman/models/tag.py`).
            customer.tags.set(CustomerTag.resolve(tags))

        self.stdout.write(f"  ✅ {len(etiquetas)} clientes etiquetados")

    # ────────────────────────────────────────────────────────────────
    # Insights de cliente
    # ────────────────────────────────────────────────────────────────

    def _seed_customer_insights(self):
        """Derivar RFM, churn e favoritos do histórico que acabamos de criar."""
        self.stdout.write("  📈 Insights de cliente (RFM, churn, favoritos)...")

        from shopman.guestman.contrib.insights import InsightService

        count = InsightService.recalculate_all()
        self.stdout.write(f"  ✅ {count} insights calculados")

    # ────────────────────────────────────────────────────────────────
    # Campanhas e templates de notificação
    # ────────────────────────────────────────────────────────────────

    def _seed_campaigns(self):
        """Campanhas de marketing — o engine que vira evento em anúncio.

        Sem isto o app de Marketing nasce VAZIO: a tela existe, o disparo existe, e não
        há sobre o que agir. Feature que não se pode experimentar é feature que não
        existe para quem usa.

        Duas campanhas, porque são os dois caminhos do domínio:

        · **por evento** — a fornada termina e o anúncio nasce sozinho, para revisão;
        · **manual** — o gestor decide agora, e escolhe o público na hora.
        """
        self.stdout.write("  📣 Campanhas de marketing...")

        from shopman.shop.models import AnnouncementTemplate, Campaign, Trigger

        fornada, _ = AnnouncementTemplate.objects.update_or_create(
            name="Saiu do forno",
            defaults={
                "body": "{{product_name}} acabou de sair do forno! {{price}} 🥖\n{{link}}",
                "variables": ["produto", "preco", "link"],
                "image_source": AnnouncementTemplate.ImageSource.PRODUCT,
                "is_active": True,
            },
        )
        # ⚠️ Sem `{{product_name}}`: disparo manual não tem evento, logo não tem SKU, e a
        # variável resolveria vazia — o gestor veria "Novidade na Padaria: ." e teria de
        # consertar a copy toda vez. Modelo de recado se sustenta sozinho, e o gestor
        # completa no card de revisão.
        novidade, _ = AnnouncementTemplate.objects.update_or_create(
            name="Recado da casa",
            defaults={
                # `{{link}}` também sai: sem SKU não há produto para linkar, e a
                # variável vazia deixaria pontuação órfã. O gestor escreve o recado no
                # card de revisão, que é onde ele já revisa tudo.
                "body": "Um recado da {{store_name}}.",
                "variables": ["store_name"],
                "image_source": AnnouncementTemplate.ImageSource.NONE,
                "is_active": True,
            },
        )

        Campaign.objects.update_or_create(
            name="Fornada pronta",
            defaults={
                "trigger": Trigger.PRODUCTION_FINISHED,
                # Piso de 90%: fornada boa COM até 10% de unidades fora ainda
                # dispara — perda pesa no denominador (previsto). ADR-017 §6.
                "trigger_filter": {"quality_min": "standard", "quality_min_share": 90},
                "template": fornada,
                "platforms": ["instagram", "whatsapp"],
                # Quem favoritou e quem pediu para ser avisado: a audiência mais quente
                # que existe, e as duas já têm consentimento explícito do produto.
                "audience_rules": {"favorites": True, "alerts": True, "vip_first_minutes": 15},
                "requires_approval": True,
                # Frescor é efêmero: anúncio de fornada não aprovado em 90 min caduca,
                # porque publicar "acabou de sair" três horas depois é mentira.
                "expires_after_minutes": 90,
                "is_active": True,
            },
        )

        Campaign.objects.update_or_create(
            name="Recado para os clientes",
            defaults={
                "trigger": Trigger.MANUAL,
                "template": novidade,
                "platforms": ["whatsapp"],
                # Público vazio DE PROPÓSITO: esta campanha existe para o gestor escolher
                # na hora do disparo ("Disparar" → "Escolher agora").
                "audience_rules": {},
                "requires_approval": True,
                "expires_after_minutes": 0,
                "is_active": True,
            },
        )

        # Agendada: o RELÓGIO é o evento. Existe no seed porque feature sem exemplo é
        # feature invisível — staging nasceria sem nenhuma campanha que dispara sozinha,
        # e ninguém descobre o recurso lendo o model. Sexta e sábado às 17h30, quando
        # sobra fornada e o movimento cai.
        Campaign.objects.update_or_create(
            name="Relâmpago de fim de tarde",
            defaults={
                "trigger": Trigger.SCHEDULE,
                "template": novidade,
                "platforms": ["whatsapp"],
                # Público vazio: quem dispara é o relógio, mas para QUEM continua sendo
                # escolha do gestor no card de revisão.
                "audience_rules": {},
                # Anuncia uma oferta de verdade: `semana-do-pao` nomeia a coleção
                # `rusticos`, então o clique no link monta a sacola com preço resolvido
                # na hora. Sem isto, o recurso existiria e nada em staging o exercitaria.
                "promotion_ref": "semana-do-pao",
                "schedule": {
                    "type": "recurring",
                    "windows": [["17:30", "18:30"]],
                    "weekdays": [4, 5],  # 0 = segunda
                },
                "requires_approval": True,
                # Relâmpago que ninguém revisou até as 19h não é mais relâmpago.
                "expires_after_minutes": 90,
                "is_active": True,
            },
        )

        self.stdout.write("  ✅ 2 modelos e 3 campanhas")

    def _seed_notification_templates(self):
        self.stdout.write("  📨 Templates de notificação...")

        from shopman.shop.models import NotificationTemplate

        FALLBACK_TEMPLATES = {
            # Campanha de marketing. A linha existe no seed porque é AQUI que o
            # operador cola o `ns` do flow aprovado — o check W010 manda configurar, e
            # mandar configurar numa linha que não existe é mandar para o vazio.
            "announcement_published": {"subject": "Novidade na padaria", "body": "{body}\n\n{cta} {action_url}"},
            # Alertas por SKU. Sem linha aqui, o adapter caía no texto genérico e o
            # operador não tinha onde mapear o flow — logo o alerta nunca alcançava quem
            # está fora da janela de 24h, que é justamente o caso de "me avise".
            "stock_arrived": {"subject": "{product_name} disponível", "body": "Olá{customer_name_greeting}! O {product_name} que você pediu para acompanhar está disponível: {action_url}"},
            "production_ready": {"subject": "{product_name} saiu do forno", "body": "Olá{customer_name_greeting}! O {product_name} acabou de sair do forno: {action_url}"},
            "order_received": {"subject": "Pedido {order_ref} recebido", "body": "Olá{customer_name_greeting}! Recebemos seu pedido *{order_ref}*. O estabelecimento vai conferir a disponibilidade. Acompanhe por aqui: {tracking_url}"},
            "order_received_outside_hours": {"subject": "Pedido {order_ref} recebido", "body": "Olá{customer_name_greeting}! Recebemos seu pedido *{order_ref}* fora do nosso horário de atendimento. Vamos processar assim que abrirmos. Total: *{total}*."},
            "order_accepted": {"subject": "Pedido {order_ref} confirmado", "body": "Olá{customer_name_greeting}! Seu pedido *{order_ref}* foi confirmado. Total: *{total}*.\n\nObrigado pela preferência!"},
            "order_preparing": {"subject": "Pedido {order_ref} em preparo", "body": "Olá{customer_name_greeting}! Seu pedido *{order_ref}* está sendo preparado.\n\nAvisaremos quando estiver pronto!"},
            "order_ready_pickup": {"subject": "Pedido {order_ref} pronto para retirada", "body": "Olá{customer_name_greeting}! Seu pedido *{order_ref}* está pronto para retirada! \U0001f389\n\nVenha buscar. Obrigado!"},
            "order_ready_delivery": {"subject": "Pedido {order_ref} pronto para entrega", "body": "Olá{customer_name_greeting}! Seu pedido *{order_ref}* está pronto e aguardando entregador. Assim que sair para entrega avisamos. \U0001f4e6"},
            "order_dispatched": {"subject": "Pedido {order_ref} saiu para entrega", "body": "Olá{customer_name_greeting}! Seu pedido *{order_ref}* saiu para entrega!\n\nEm breve estará com você!"},
            "order_delivered": {"subject": "Pedido {order_ref} entregue", "body": "Olá{customer_name_greeting}! Seu pedido *{order_ref}* foi entregue.\n\nEsperamos que tenha gostado! Obrigado pela preferência."},
            "order_cancelled": {"subject": "Pedido {order_ref} cancelado", "body": "Olá{customer_name_greeting}! Seu pedido *{order_ref}* foi cancelado.{reason_note}\n\nEm caso de dúvidas, entre em contato."},
            "order_rejected": {"subject": "Pedido {order_ref} não confirmado", "body": "Olá{customer_name_greeting}! O estabelecimento não conseguiu confirmar o pedido *{order_ref}*.\n\nMotivo: {reason}\n\nEm caso de dúvidas, estamos aqui."},
            "payment_requested": {"subject": "Pedido {order_ref}: pagamento liberado", "body": "Olá{customer_name_greeting}! Confirmamos a disponibilidade do pedido *{order_ref}*.\n\nPara continuar, conclua o pagamento dentro do prazo: {payment_url}"},
            "payment_confirmed": {"subject": "Pagamento do pedido {order_ref} confirmado", "body": "Olá{customer_name_greeting}! O pagamento do pedido *{order_ref}* foi recebido.\n\nValor: *{total}*\n\nSeu pedido seguirá para preparo. Obrigado!"},
            "payment_expired": {"subject": "Pagamento do pedido {order_ref} expirado", "body": "Olá{customer_name_greeting}! O prazo de pagamento do pedido *{order_ref}* expirou.\n\nO pedido foi cancelado automaticamente."},
            "payment_failed": {"subject": "Falha ao preparar pagamento do pedido {order_ref}", "body": "Olá{customer_name_greeting}! Não conseguimos preparar o pagamento do pedido *{order_ref}*.\n\nAcesse {payment_url} para tentar novamente."},
            "payment_refunded": {"subject": "Reembolso do pedido {order_ref} processado", "body": "Olá{customer_name_greeting}! O reembolso do pedido *{order_ref}* foi processado.\n\nValor: *{total}*"},
            "loyalty_earned": {"subject": "Você ganhou pontos de fidelidade!", "body": "Olá{customer_name_greeting}! Você ganhou pontos de fidelidade com o pedido *{order_ref}*!"},
            # Produção → operador (notification.send de sistema, WP-PE2).
            # Opt-in via Shop.defaults["production"]["notifications"].
            "production_late": {"subject": "Produção {work_order_ref} atrasada", "body": "A produção *{work_order_ref}* ({output_sku}) está há {elapsed_minutes} min em andamento (janela: {target_minutes} min).\n\nConfira o chão de produção."},
            "production_low_yield": {"subject": "Yield baixo na produção {work_order_ref}", "body": "A produção *{work_order_ref}* ({output_sku}) fechou com yield de {yield_percent}%.\n\nVale conferir a perda no relatório de produção."},
            "production_forgotten": {"subject": "Produção {work_order_ref} não foi iniciada", "body": "A produção *{work_order_ref}* ({output_sku}) planejada para {target_date} nunca foi iniciada.\n\nConclua, reagende ou estorne no planejamento."},
            "production_stock_short": {"subject": "Produção {work_order_ref} sem insumos", "body": "A produção *{work_order_ref}* ({output_sku}) falhou por estoque insuficiente.\n\nDetalhe: {error}"},
        }

        count = 0
        for event, tpl in FALLBACK_TEMPLATES.items():
            _, created = NotificationTemplate.objects.update_or_create(
                event=event,
                defaults={
                    "subject": tpl["subject"],
                    "body": tpl["body"],
                    "is_active": True,
                },
            )
            if created:
                count += 1

        self.stdout.write(f"  ✅ {len(FALLBACK_TEMPLATES)} templates de notificação ({count} novos)")

    def _seed_rule_configs(self):
        self.stdout.write("  ⚙️  Rule configs...")

        RULE_CONFIGS = [
            {
                "ref": "employee_discount",
                "rule_path": "shopman.shop.rules.pricing.EmployeeRule",
                "label": "Desconto Funcionário",
                "params": {"discount_percent": 20, "price_tier": "staff"},
                "priority": 60,
            },
            {
                "ref": "happy_hour",
                "rule_path": "shopman.shop.rules.pricing.HappyHourRule",
                "label": "Hora da Xepa",
                "params": {"discount_percent": 25, "start": "17:30", "end": "18:00"},
                "priority": 65,
            },
            {
                "ref": "business_hours",
                "rule_path": "shopman.shop.rules.validation.BusinessHoursRule",
                "label": "Horário de Funcionamento",
                "params": {},
                "priority": 10,
            },
            # Mínimo de entrega, mínimo geral e frete grátis são políticas da loja
            # em Shop.defaults["rules"] (ver _seed_shop), fonte única consumida
            # pelo aviso ao vivo e pelos validators de commit.
        ]

        count = 0
        rules_by_ref = {}
        for rc in RULE_CONFIGS:
            obj, created = RuleConfig.objects.update_or_create(
                ref=rc["ref"],
                defaults={
                    "rule_path": rc["rule_path"],
                    "label": rc["label"],
                    "params": rc["params"],
                    "priority": rc["priority"],
                    "enabled": True,
                },
            )
            rules_by_ref[rc["ref"]] = obj
            if created:
                count += 1

        # Happy Hour ("Hora da Xepa") is an in-store, end-of-day clearance —
        # it must NOT touch the online storefront (where listed prices would
        # diverge from the cart). Scope the rule to every non-web channel; an
        # empty channel set would mean "all channels", including web.
        happy_hour = rules_by_ref.get("happy_hour")
        if happy_hour is not None:
            happy_hour.channels.set(Channel.objects.exclude(ref="web"))

        self.stdout.write(f"  ✅ {len(RULE_CONFIGS)} rule configs ({count} novos)")

    def _seed_omotenashi_copy(self):
        """Brand overrides for generic interface copy.

        The pricing modifiers carry generic discount labels; Nelson overrides
        them with its own wording (e.g. "Hora da Xepa") via OmotenashiCopy rows.
        """
        self.stdout.write("  💬 Omotenashi copy (overrides de marca)...")

        COPY_OVERRIDES = [
            {"key": "CART_DISCOUNT_LABEL_TIME_WINDOW", "title": "Hora da Xepa"},
        ]

        count = 0
        for entry in COPY_OVERRIDES:
            _, created = OmotenashiCopy.objects.update_or_create(
                key=entry["key"],
                moment="*",
                audience="*",
                defaults={
                    "title": entry.get("title", ""),
                    "message": entry.get("message", ""),
                    "active": True,
                },
            )
            if created:
                count += 1

        self.stdout.write(f"  ✅ {len(COPY_OVERRIDES)} cópias omotenashi ({count} novas)")

    # ────────────────────────────────────────────────────────────────
    # DayClosing (fechamento do dia)
    # ────────────────────────────────────────────────────────────────

    def _seed_day_closing(self):
        self.stdout.write("  📊 Fechamento do dia...")

        yesterday = timezone.localdate() - timedelta(days=1)
        admin = User.objects.filter(is_superuser=True).first()
        if not admin:
            self.stdout.write("  ⏭️  Sem superuser, pulando DayClosing")
            return

        closing_items = [
            {"sku": "BF", "qty_reported": 6, "qty_applied": 6, "qty_discrepancy": 0, "qty_remaining": 6, "qty_kept": 4, "qty_expired": 2, "qty_nonconforming": 0},
            {"sku": "CI", "qty_reported": 3, "qty_applied": 3, "qty_discrepancy": 0, "qty_remaining": 3, "qty_kept": 2, "qty_expired": 1, "qty_nonconforming": 0},
            {"sku": "FE", "qty_reported": 7, "qty_applied": 7, "qty_discrepancy": 0, "qty_remaining": 7, "qty_kept": 5, "qty_expired": 2, "qty_nonconforming": 0},
            {"sku": "TB", "qty_reported": 5, "qty_applied": 5, "qty_discrepancy": 0, "qty_remaining": 5, "qty_kept": 4, "qty_expired": 1, "qty_nonconforming": 0},
            {"sku": "CI", "qty_reported": 4, "qty_applied": 4, "qty_discrepancy": 0, "qty_remaining": 4, "qty_kept": 3, "qty_expired": 1, "qty_nonconforming": 0},
            {"sku": "PH", "qty_reported": 8, "qty_applied": 8, "qty_discrepancy": 0, "qty_remaining": 8, "qty_kept": 6, "qty_expired": 2, "qty_nonconforming": 0},
        ]
        production_summary = {}
        for work_order in WorkOrder.objects.filter(target_date=yesterday).select_related("recipe"):
            row = production_summary.setdefault(
                work_order.recipe.ref,
                {
                    "recipe_ref": work_order.recipe.ref,
                    "output_sku": work_order.output_sku,
                    "planned": 0,
                    "finished": 0,
                    "loss": 0,
                },
            )
            row["planned"] += int(work_order.quantity or 0)
            if work_order.finished is not None:
                row["finished"] += int(work_order.finished or 0)
                row["loss"] += max(0, int((work_order.started_qty or work_order.quantity) - work_order.finished))

        _, created = DayClosing.objects.update_or_create(
            date=yesterday,
            defaults={
                "closed_by": admin,
                "notes": "Fechamento automatico (seed)",
                "data": {
                    "items": closing_items,
                    "production_summary": production_summary,
                    "reconciliation_errors": [],
                },
            },
        )
        self.stdout.write("  ✅ DayClosing criado" if created else "  ✅ DayClosing atualizado")

    # ────────────────────────────────────────────────────────────────
    # Caixa (cashman: terminal, turno, livro)
    # ────────────────────────────────────────────────────────────────

    def _seed_cash_register(self):
        """Um turno fechado ontem (com o livro populado) e um aberto hoje.

        Tudo pelos services do ``cashman``: o seed não escreve ``Entry`` na mão,
        porque o livro tem regras (sinal por tipo, segunda assinatura, contagem
        só no fechamento) e o único jeito de o dado de demonstração respeitá-las
        é passar por quem as guarda.
        """
        from shopman.cashman import services as cash
        from shopman.cashman.models import Entry as CashEntry
        from shopman.cashman.models import Shift as CashShiftLedger
        from shopman.cashman.models import Terminal as CashTerminal

        self.stdout.write("  💵 Turnos de caixa...")

        admin = User.objects.filter(is_superuser=True).first()
        if not admin:
            self.stdout.write("  ⏭️  Sem superuser, pulando o caixa")
            return

        yesterday = timezone.localdate() - timedelta(days=1)
        yesterday_open = timezone.make_aware(datetime.combine(yesterday, time(8, 30)))
        yesterday_close = timezone.make_aware(datetime.combine(yesterday, time(18, 15)))

        terminal = CashTerminal.default()

        # O aparelho do balcão da Nelson: Epson TM-T20, USB, rolo de 80mm
        # (confirmado com o Pablo em 2026-08-12). Declarar a largura aqui é o que
        # faz o `@page` do recibo parar de depender do driver — a superfície
        # escreve `--pos-roll-width` a partir disto. 80mm é também o default do
        # print CSS, então a declaração não muda o desenho: ela torna explícito
        # o que hoje é sorte, e é o gancho para um balcão com rolo diferente.
        hardware = dict(terminal.metadata.get("hardware") or {})
        hardware["printer"] = {"adapter": "driver", "model": "epson-tm-t20", "roll_width_mm": 80}

        # A gaveta do balcão pendura no RJ11 dessa mesma TM-T20 e abre pelo
        # agente local. Declarar aqui, SEM token, é deliberado: o token nasce no
        # Admin e forma par com a máquina do balcão — inventar um no seed criaria
        # um par que não existe do outro lado.
        #
        # ⚠️ Isto existe porque o reseed apagava a gaveta em silêncio (o terminal
        # é recriado, e antes só a impressora era declarada). O PDV escondia o
        # card e ninguém entendia por quê. Declarado sem token, o estado passa a
        # ser "tem gaveta, falta instalar" — que aponta para a próxima ação em
        # vez de fingir que o balcão não tem gaveta.
        hardware.setdefault(
            "cash_drawer",
            {"enabled": True, "adapter": "agent", "agent_url": "http://127.0.0.1:47811", "token": ""},
        )
        terminal.metadata = {**terminal.metadata, "hardware": hardware}
        terminal.save(update_fields=["metadata"])

        # Ontem: turno fechado com o livro inteiro — fundo de troco, as vendas do
        # PDV de ontem (uma linha `sale` por pedido, efeito em dinheiro só para o
        # que foi pago em espécie), uma sangria autorizada e a contagem cega com
        # R$ 3 a menos. Idempotente: se o turno de ontem já existe, não repete.
        already = CashShiftLedger.objects.filter(operator=admin, opened_at=yesterday_open).exists()
        if not already and not cash.open_shift_for(admin) and not cash.open_shift_for_terminal(terminal):
            shift_yesterday = cash.open_shift(operator=admin, terminal=terminal, float_q=20000, at=yesterday_open)
            for order in (
                Order.objects.filter(
                    channel_ref=terminal.channel_ref,
                    created_at__gte=yesterday_open,
                    created_at__lte=yesterday_close,
                )
                .exclude(status__in=["cancelled", "returned"])
                .order_by("created_at")
            ):
                payment = dict((order.data or {}).get("payment") or {})
                method = str(payment.get("method") or "external")
                if payment.get("collection", "terminal") == "on_delivery":
                    continue
                cash_q = 0
                if method == "cash":
                    cash_q = int(payment.get("cash_received_q") or order.total_q or 0)
                cash.record(
                    CashEntry.Kind.SALE,
                    shift=shift_yesterday,
                    operator=admin,
                    amount_q=max(0, cash_q),
                    order_ref=order.ref,
                    payment_ref=str(payment.get("intent_ref") or ""),
                    payload={"method": method, "collection": "terminal"},
                    at=order.created_at,
                )
            # A sangria sai do que a gaveta TEM: R$ 300 num dia com vendas em
            # dinheiro, R$ 100 quando o histórico do perfil não trouxe venda de
            # ontem no PDV (o livro nunca pode ficar negativo por dado de demo).
            in_drawer_q = cash.balance(shift_yesterday)
            withdrawal_q = 30000 if in_drawer_q >= 30300 else 10000
            cash.record(
                CashEntry.Kind.CASH_OUT,
                shift=shift_yesterday,
                operator=admin,
                approved_by=admin,
                amount_q=-withdrawal_q,
                reason="Retirada para depósito",
                at=timezone.make_aware(datetime.combine(yesterday, time(14, 0))),
            )
            expected_q = cash.expected_before_count(shift_yesterday)
            cash.close_shift(
                shift_yesterday,
                counted_q=expected_q - 300,  # faltou R$ 3,00 na gaveta
                actor=admin,
                notes="Dia tranquilo, faltou R$3 no caixa.",
                at=yesterday_close,
            )

        # Hoje: turno aberto com fundo de troco.
        if not cash.open_shift_for(admin) and not cash.open_shift_for_terminal(terminal):
            today_open = timezone.make_aware(datetime.combine(timezone.localdate(), time(8, 45)))
            cash.open_shift(operator=admin, terminal=terminal, float_q=20000, at=today_open)

        self.stdout.write("  ✅ 2 turnos de caixa (ontem fechado + hoje aberto)")

    # ────────────────────────────────────────────────────────────────
    # Operation checklists (abertura, rotina, fechamento)
    # ────────────────────────────────────────────────────────────────

    def _seed_operation_checklists(self):
        self.stdout.write("  ✅ Checklists operacionais...")

        admin = User.objects.filter(is_superuser=True).first()
        if not admin:
            self.stdout.write("  ⏭️  Sem superuser, pulando checklists operacionais")
            return

        task_specs = [
            {
                "ref": "nelson-opening-cash-count",
                "title": "Caixa aberto e conferido",
                "description": "Registrar fundo de troco antes de iniciar atendimento.",
                "moment": OperationMoment.OPENING,
                "area": OperationArea.CASH,
                "evidence_required": OperationEvidence.NUMBER,
                "expected_role": "caixa",
                "sort_order": 10,
            },
            {
                "ref": "nelson-opening-showcase-ready",
                "title": "Vitrine preparada",
                "description": "Conferir exposição, etiquetas e itens críticos antes da abertura.",
                "moment": OperationMoment.OPENING,
                "area": OperationArea.ROOM,
                "evidence_required": OperationEvidence.TEXT,
                "expected_role": "atendimento",
                "sort_order": 20,
            },
            {
                "ref": "nelson-opening-equipment-safe",
                "title": "Equipamentos ligados e seguros",
                "description": "Forno, geladeiras, iluminação e PDV em condição segura.",
                "moment": OperationMoment.OPENING,
                "area": OperationArea.PRODUCTION,
                "evidence_required": OperationEvidence.DOUBLE_CHECK,
                "expected_role": "produção",
                "sort_order": 30,
            },
            {
                "ref": "nelson-routine-tables-clean",
                "title": "Mesas limpas",
                "description": "Conferência periódica do salão.",
                "moment": OperationMoment.ROUTINE,
                "area": OperationArea.CLEANING,
                "evidence_required": OperationEvidence.TEXT,
                "expected_role": "salão",
                "sort_order": 10,
            },
            {
                "ref": "nelson-routine-bathroom-clean",
                "title": "Banheiro limpo",
                "description": "Checagem de limpeza, papel, sabonete e lixeira.",
                "moment": OperationMoment.ROUTINE,
                "area": OperationArea.CLEANING,
                "evidence_required": OperationEvidence.TEXT,
                "expected_role": "salão",
                "sort_order": 20,
            },
            {
                "ref": "nelson-routine-showcase-restock",
                "title": "Reposição de vitrine",
                "description": "Registrar rupturas, reposições e itens de atenção.",
                "moment": OperationMoment.ROUTINE,
                "area": OperationArea.ROOM,
                "evidence_required": OperationEvidence.TEXT,
                "expected_role": "atendimento",
                "sort_order": 30,
            },
            {
                "ref": "nelson-routine-critical-stock",
                "title": "Ruptura ou item crítico conferido",
                "description": "Checar itens com alerta ou alta demanda no dia.",
                "moment": OperationMoment.ROUTINE,
                "area": OperationArea.STOCK,
                "evidence_required": OperationEvidence.TEXT,
                "expected_role": "gestão",
                "sort_order": 40,
            },
            {
                "ref": "nelson-closing-cash-closed",
                "title": "Caixa fechado",
                "description": "Conferir valor informado, esperado e diferença.",
                "moment": OperationMoment.CLOSING,
                "area": OperationArea.CASH,
                "evidence_required": OperationEvidence.DOUBLE_CHECK,
                "expected_role": "caixa",
                "sort_order": 10,
            },
            {
                "ref": "nelson-closing-unsold-blind",
                "title": "Não vendidos informados às cegas",
                "description": "Registrar quantidade apurada sem revelar saldo esperado.",
                "moment": OperationMoment.CLOSING,
                "area": OperationArea.STOCK,
                "evidence_required": OperationEvidence.NUMBER,
                "expected_role": "fechamento",
                "sort_order": 20,
            },
            {
                "ref": "nelson-closing-showcase-clean",
                "title": "Vitrine limpa",
                "description": "Limpeza final e retirada de itens sem condição de venda.",
                "moment": OperationMoment.CLOSING,
                "area": OperationArea.CLEANING,
                "evidence_required": OperationEvidence.TEXT,
                "expected_role": "salão",
                "sort_order": 30,
            },
            {
                "ref": "nelson-closing-equipment-safe",
                "title": "Equipamentos desligados ou seguros",
                "description": "Conferir equipamentos, refrigeração e segurança para a noite.",
                "moment": OperationMoment.CLOSING,
                "area": OperationArea.PRODUCTION,
                "evidence_required": OperationEvidence.DOUBLE_CHECK,
                "expected_role": "produção",
                "sort_order": 40,
            },
        ]

        tasks: dict[str, OperationTaskTemplate] = {}
        for spec in task_specs:
            ref = spec.pop("ref")
            task, _ = OperationTaskTemplate.objects.update_or_create(
                ref=ref,
                defaults={**spec, "is_required": True, "is_active": True, "is_system": True, "config": {"seed": "nelson"}},
            )
            tasks[ref] = task

        checklist_specs = [
            (
                "nelson-opening",
                "Abertura da casa",
                OperationMoment.OPENING,
                [
                    "nelson-opening-cash-count",
                    "nelson-opening-showcase-ready",
                    "nelson-opening-equipment-safe",
                ],
            ),
            (
                "nelson-routine",
                "Rotina do dia",
                OperationMoment.ROUTINE,
                [
                    "nelson-routine-tables-clean",
                    "nelson-routine-bathroom-clean",
                    "nelson-routine-showcase-restock",
                    "nelson-routine-critical-stock",
                ],
            ),
            (
                "nelson-closing",
                "Fechamento da casa",
                OperationMoment.CLOSING,
                [
                    "nelson-closing-cash-closed",
                    "nelson-closing-unsold-blind",
                    "nelson-closing-showcase-clean",
                    "nelson-closing-equipment-safe",
                ],
            ),
        ]
        checklists: dict[str, OperationChecklistTemplate] = {}
        for index, (ref, title, moment, task_refs) in enumerate(checklist_specs, start=1):
            checklist, _ = OperationChecklistTemplate.objects.update_or_create(
                ref=ref,
                defaults={
                    "title": title,
                    "description": "Checklist canônico Nelson para operação diária.",
                    "moment": moment,
                    "is_active": True,
                    "sort_order": index * 10,
                },
            )
            checklists[ref] = checklist
            for sort_order, task_ref in enumerate(task_refs, start=1):
                OperationChecklistTemplateTask.objects.update_or_create(
                    checklist_template=checklist,
                    task_template=tasks[task_ref],
                    defaults={"sort_order": sort_order * 10, "is_required_override": None},
                )

        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        OperationChecklistRun.objects.filter(context__seed="nelson").delete()

        opening_run = start_checklist_run(
            template=checklists["nelson-opening"],
            business_date=today,
            shift_ref="manha",
            user=admin,
            context={"seed": "nelson", "state": "completed_opening"},
        )
        for task in opening_run.task_runs.select_related("template"):
            if task.evidence_required == OperationEvidence.NUMBER:
                complete_task_run(task, user=admin, evidence_number=200, notes="Fundo de troco conferido.")
            elif task.evidence_required == OperationEvidence.DOUBLE_CHECK:
                complete_task_run(task, user=admin, notes="Equipamentos verificados.")
                supervise_task_run(task, user=admin, notes="Dupla conferência seed.")
            else:
                complete_task_run(task, user=admin, evidence_text="Conferido no seed operacional.")
        complete_checklist_run(opening_run, user=admin)

        routine_run = start_checklist_run(
            template=checklists["nelson-routine"],
            business_date=today,
            shift_ref="tarde",
            user=admin,
            context={"seed": "nelson", "state": "routine_in_progress"},
        )
        for task in routine_run.task_runs.filter(template__ref__in=["nelson-routine-tables-clean", "nelson-routine-showcase-restock"]):
            complete_task_run(task, user=admin, evidence_text="Conferido durante a rotina.")

        closing_run = start_checklist_run(
            template=checklists["nelson-closing"],
            business_date=yesterday,
            shift_ref="noite",
            user=admin,
            context={"seed": "nelson", "state": "completed_closing"},
        )
        for task in closing_run.task_runs.select_related("template"):
            if task.evidence_required == OperationEvidence.NUMBER:
                complete_task_run(task, user=admin, evidence_number=33, notes="Total agregado de não vendidos.")
            elif task.evidence_required == OperationEvidence.DOUBLE_CHECK:
                complete_task_run(task, user=admin, notes="Fechamento conferido.")
                supervise_task_run(task, user=admin, notes="Dupla conferência seed.")
            else:
                complete_task_run(task, user=admin, evidence_text="Conferido no fechamento.")
        complete_checklist_run(closing_run, user=admin)

        self.stdout.write("  ✅ 3 templates e 3 execuções de checklist operacional")

    # ── B.I.: a série que dá o que ver ──────────────────────────────────────
    #
    # O resto do seed grava pedidos e fornadas DIRETO no banco, sem passar pelo
    # lifecycle — rápido e determinístico, mas deixa o B.I. cego: sem movimento
    # de estoque não há prateleira, sem prateleira não há sobra nem falta, e as
    # métricas de abastecimento nascem vazias por construção.
    #
    # Esta seção fecha esse buraco escrevendo o que a operação real escreveria,
    # com PERFIS distintos e reconhecíveis: um produto que acaba cedo todo dia,
    # um que sobra sempre, um que só falha no fim de semana, um pausado. Sem
    # perfis, o gráfico vira ruído e ninguém consegue dizer se a tela está certa.

    BI_SHELF_PROFILES = {
        # sku: (produção/dia, hora que acaba ou None, dias de folga)
        "CT": (42, 11, ()),          # some cedo: subprodução crônica
        "PC": (36, 13, ()),      # some no meio da tarde
        "BF": (22, 16, ()),            # aguenta quase o dia
        "CGO": (16, None, ()),         # sempre sobra
        "MD": (68, 12, (5, 6)),      # só falta no fim de semana
    }

    # Dois anos: é o alcance do histórico real da casa, e sem ele nenhuma
    # pergunta de "o que esperar" tem o que comparar — um mês de dados não tem
    # duas quartas de dezembro nem um único dia das mães.
    BI_LONG_DAYS = 730

    def _seed_bi_history(self, products, positions, days: int = 42) -> None:
        """Prateleira, faltas, forno e contexto do dia — o que o B.I. lê.

        Duas escalas, e é assim na vida real: o **abastecimento** (prateleira,
        faltas, forno) só existe no presente curto, porque depende do ledger da
        casa; a **venda** vem de dois anos de histórico, que é o que sustenta
        sazonalidade e previsibilidade.
        """
        vitrine = positions.get("vitrine")
        if vitrine is None:
            return
        self._seed_episode_kinds()
        self._seed_consumption_roles()
        self._seed_consumption_tags()
        self._seed_seating()
        self._seed_bi_aliases()
        self._seed_bi_alert_rules()
        self._seed_business_days(days=days)
        self._seed_shelf_movements(products, vitrine, days=days)
        self._seed_shelf_outages(products, days=days)
        self._seed_oven_runs(days=days)
        self._seed_day_weather(days=self.BI_LONG_DAYS)
        self._seed_day_calendar(days=self.BI_LONG_DAYS)
        sales = self._seed_long_sales_history(products, days=self.BI_LONG_DAYS)
        native = self._seed_recent_native_volume(products, days=days)
        # A série diária materializada é derivada do que acabou de ser semeado:
        # recomputada do zero, senão a projeção leria a tabela de um seed antigo.
        from shopman.backstage.bi.daily_series import refresh_all

        materialized = refresh_all()
        self.stdout.write(
            f"  ✅ B.I.: {days} dias de prateleira/faltas/forno, "
            f"{self.BI_LONG_DAYS} dias de contexto, {sales} vendas históricas, "
            f"{native} pedidos nativos de volume e {materialized} dias materializados"
        )

    def _seed_episode_kinds(self) -> None:
        """As opções que o operador escolhe no fechamento.

        Vocabulário da casa, editável no Admin. ``affects_demand`` marca o que
        atrapalhou a venda — esses dias saem da amostra que ensina quanto
        produzir, porque vender pouco sem energia não é procura baixa.
        """
        from shopman.backstage.models import OperationEpisodeKind

        catalogo = [
            ("falta-de-energia", "Faltou energia", "A loja ficou sem luz", True, 10),
            ("falta-de-agua", "Faltou água", "Sem água na cozinha", True, 20),
            ("equipamento-parado", "Equipamento parado", "Forno, geladeira ou PDV fora", True, 30),
            # Duas causas diferentes, com ações diferentes: sem conexão se liga
            # para a operadora; sistema fora do ar se chama o suporte.
            ("falta-de-conexao", "Faltou internet", "A loja ficou sem conexão", True, 40),
            ("sistema-fora", "Sistema fora do ar", "Sistema indisponível, com internet ok", True, 45),
            ("rua-interditada", "Rua interditada", "Obra ou bloqueio na porta", True, 50),
            ("chuva-forte", "Chuva forte", "Temporal esvaziou a rua", True, 60),
            ("evento-na-regiao", "Evento na região", "Movimento fora do normal", False, 70),
            ("equipe-reduzida", "Equipe reduzida", "Faltou gente no turno", True, 80),
        ]
        for ref, label, hint, afeta, ordem in catalogo:
            OperationEpisodeKind.objects.update_or_create(
                ref=ref,
                defaults={
                    "label": label, "hint": hint,
                    "affects_demand": afeta, "position": ordem, "is_active": True,
                },
            )

    def _seed_consumption_roles(self) -> None:
        """O vocabulário que faz a cesta dizer quem sentou e quem levou.

        As LEITURAS são três, porque são três as coisas que a regra sabe usar.
        Os papéis são cinco porque bebida é um fato à parte da leitura: três
        perguntas do B.I. (strike rate, bebidas por pedido, receita de bebida
        pronta industrializada) precisam saber "esta linha é bebida? preparada
        ou pronta?" — e isso é dado do papel, não nome de categoria hardcoded.
        Bebida preparada e bebida pronta leem IGUAL a "consome aqui" (ancoram):
        trocar um SKU entre eles não muda perfil nenhum, só a conta de bebida.

        A âncora é a bebida: nesta casa, quem pede bebida pra levar é quantidade
        desprezível, então bebida na cesta significa alguém que sentou.

        ⚠️ Aqui nasce só o VOCABULÁRIO. Etiquetar produto a produto é curadoria
        do gestor, no Admin — e tem de ser, porque o nome engana: "Hambúrguer
        100g" é o pão, não o sanduíche.
        """
        from shopman.backstage.models import Beverage, ConsumptionRole, Reading

        # O peso (%) é a vocação em graus — P(consumido aqui | está na cesta).
        # Parte da leitura e é editável no Admin, por papel e por SKU: é o que
        # transforma a faixa piso–teto numa estimativa (passo 1 do
        # BI-CONSUMPTION-PROFILES §8; o passo 2 mede pela comanda).
        catalog = [
            ("bebida-preparada", "Bebida preparada",
             "Café, chá, frappé, soda da casa — feita aqui, bebida aqui",
             Reading.ANCHOR, Beverage.PREPARED, 95, 5),
            ("bebida-pronta", "Bebida pronta",
             "Água, refrigerante, suco de garrafa — abre e bebe aqui",
             Reading.ANCHOR, Beverage.READY, 95, 6),
            ("consome-aqui", "Consome aqui",
             "Prato quente, lanche montado, sobremesa servida", Reading.ANCHOR,
             Beverage.NONE, 95, 10),
            ("leva", "Leva",
             "Pão, geleia, café em grão — o que sai pela porta", Reading.TAKEAWAY,
             Beverage.NONE, 5, 20),
            ("hibrido", "Híbrido",
             "Croissant, doce, pão japonês: serve aos dois usos", Reading.HYBRID,
             Beverage.NONE, 50, 30),
        ]
        for ref, label, hint, reading, beverage, weight, position in catalog:
            ConsumptionRole.objects.update_or_create(
                ref=ref,
                defaults={
                    "label": label, "hint": hint, "reading": reading,
                    "beverage": beverage, "eat_in_weight": weight,
                    "ordering": position, "is_active": True,
                },
            )

    def _seed_consumption_tags(self) -> None:
        """A curadoria do dono, produto a produto (revisada em 17/08/2026).

        Etiqueta é decisão de negócio, não dedução: o `propose_consumption_tags`
        propõe a partir da coleção, mas quem confirma é quem conhece o cardápio.
        Estas 59 linhas entram como `reviewed=True` porque foram
        conferidas uma a uma — diferente de proposta, que nasce falsa.

        Duas correções que só a revisão pegaria: os **salgados** da casa são
        prato quente (croque, queijo-quente, jambon-beurre), então ancoram; e a
        **viennoiserie** é híbrida, não "de levar" — croissant, pain au
        chocolat, madeleine e os pães japoneses servem aos dois usos.
        """
        from shopman.backstage.models import ConsumptionRole, ProductConsumptionTag

        curated = {
            # Bebida é papel próprio (mesma leitura de "consome aqui"), porque
            # o B.I. conta bebida por pedido. Preparada = feita na casa; pronta
            # = industrializada. Água é pronta.
            "bebida-preparada": [
                "PS", "THB", "THC", "THR", "THS", "CD", "CE",
                "CV", "SS", "FP", "MC",
                "SO",
            ],
            "bebida-pronta": [
                "AG",
            ],
            "consome-aqui": [
                "COMBO-PETIT-DEJ", "CCOM",
                "CMA", "CMO",
                "JB", "MS",
                "PG", "PPU",
                "PU", "QQ", "TI", "TJ",
            ],
            "leva": [
                "BK", "BF", "BE",
                "BRIOCHE-BURGER", "GR", "CGO",
                "CPX", "THL", "CX",
                "KP", "LN",
                "MT", "PH", "PAO-HOTDOG",
                "QC", "QP", "SK",
            ],
            "hibrido": [
                "ANC", "CI", "CO",
                "CT", "FE", "GL", "MD", "ME",
                "MIB", "PC", "PT",
                "TB", "TP",
            ],
        }
        roles = {role.ref: role for role in ConsumptionRole.objects.all()}
        for role_ref, skus in curated.items():
            role = roles.get(role_ref)
            if role is None:
                continue
            for sku in skus:
                ProductConsumptionTag.objects.update_or_create(
                    sku=sku,
                    defaults={"role": role, "reviewed": True,
                              "note": "curadoria do cardápio 2027"},
                )

        self._seed_historical_consumption_tags(roles)

    def _seed_historical_consumption_tags(self, roles) -> None:
        """A curadoria dos SKUs do YOOGA — o histórico também tem dono.

        Os dois anos importados usam SKUs do sistema antigo (CT, PC, FA…), que
        não estão no cardápio 2027. Sem etiqueta própria, cada um cairia na
        reserva por categoria — e "Pães Finos" (55% da receita, de croissant a
        pão de forma) é grossa demais para decidir sozinha. O dono revisou os
        61 SKUs dessa categoria em 18/08/2026, linha a linha, e a decisão vale
        para qualquer ambiente que carregue o histórico — por isso mora aqui, e
        não só no banco do staging.

        A regra que ele fixou na revisão: **a bebida no pedido é que define**.
        Salgado montado (Hot Dog Vienna, Deli, Croissant Presunto, Folhado) NÃO
        ancora sozinho — é híbrido, como a viennoiserie. O que vira "leva" é o
        pão de abastecimento: forma, burger bun, pão de hot dog, pita, challah,
        nanterre, kuro pan (o dado concorda: 63–99% dessas vendas são de 4+
        unidades, e a bebida acompanha só 17–23% delas).

        Os combos do Yooga (jul/24–jul/25: 9 mil linhas sem SKU e sem
        categoria, em 5,5 mil vendas) entram pelo NOME (`nome:`) como "consome
        aqui" — confirmado pelo dono no Admin em 18/08. NÃO como bebida: a
        linha é o combo inteiro, e contá-la como refrigerante jogaria R$ 140
        mil de hotdog na receita de bebida pronta.
        """
        from shopman.backstage.models import ProductConsumptionTag

        note_a = "pão de levar — revisão do dono 18/08/2026 (Pães Finos do Yooga)"
        note_h = "híbrido confirmado pelo dono 18/08/2026: a bebida no pedido é que define"
        historical = {
            "leva": (note_a, [
                "FA", "MFA",              # Forma Artesanal - 6 Fatias
                "BBB", "MBBB", "MBBBG",   # Brioche Burger Bun
                "PHO", "MPHO", "MIPHO",   # Pão Para Hot Dog
                "PI", "MPI",              # Pita
                "CH", "MCH",              # Challah
                "BN", "MBN",              # Brioche Nanterre
                "KP", "MKP",              # Kuro Pan
                "KBB", "MKPB",            # Kuro Pan Burger
            ]),
            "hibrido": (note_h, [
                # viennoiserie e doces
                "PC", "MPC", "CT", "MCT", "CN", "MD", "MMD", "BH", "MBH",
                "BCH", "MBCH", "CM", "MCM", "PR", "MPR", "CO", "MCO",
                "COC", "MCOC", "MA", "MMA", "ME", "MME",
                # os pães-bicho (melonpan): Coelhinho, Caranguejo, Ursinho, Porquinho
                "ANC", "JO", "MJO", "ANU", "MANU", "ANP", "MANP",
                # salgados montados: a bebida define, não o salgado
                "HO", "MHO", "MIHO", "DL", "MDL", "CPQ", "MCPQ", "FF", "MFF",
                # os mesmos produtos com SKU do iFood (só entrega; a etiqueta é
                # coerência, a entrega precede a cesta)
                "IFOOD_7b8ad920c82b11eea8170d006",
                "IFOOD_7a2d5980c82b11eead2087b32",
                "IFOOD_7ee4ad50c82b11eea051db114",
                "IFOOD_a8feac8b-0c72-43b6-a067-b9e451585762",
            ]),
            "consome-aqui": ("combo do Yooga sem SKU: lanche + refrigerante, come aqui — confirmado pelo dono 18/08/2026", [
                "nome:Combo Cola + Hotdog", "nome:Combo Citrus + Hotdog",
                "nome:Combo Cola + Donut", "nome:Combo Citrus + Donut",
            ]),
        }
        # Segunda rodada (19/08/2026): as 70 propostas que restavam — cafés,
        # pratos e pães rústicos do Yooga — revisadas pelo dono. Duas decisões
        # que o dado sozinho não daria: ciabatta, tabatière, fendu e mini
        # baguete ficam HÍBRIDOS (como seus gêmeos no cardápio 2027, para o
        # histórico não discordar do cardápio), embora só 14–18% das vendas
        # levem bebida; e as mini focaccias são lanchinho, híbridas também.
        # O café do Yooga vira "bebida preparada" por curadoria, não por
        # reserva de categoria.
        round_two = (
            ("bebida-preparada", "café/chá da casa — revisão do dono 19/08/2026 (SKUs do Yooga)", [
                "PS", "SS", "SL", "CL", "CQ", "FP", "MH", "CTV", "MC", "SE", "HI", "CHAI_A",
            ]),
            ("consome-aqui", "prato servido à mesa — revisão do dono 19/08/2026 (SKUs do Yooga)", [
                "CMO", "QQ", "CMA", "CCOM", "JB", "PPU",   # croques, queijo quente, jambon, pain perdu
            ]),
            ("leva", "pão rústico / mercearia — revisão do dono 19/08/2026 (SKUs do Yooga)", [
                "BAX", "BF", "CF", "CGO", "CPX", "BE", "BAP", "CBT", "PH", "FOA", "BA", "CGR",
                "MBAX", "MBF", "MCF", "MCGO", "MCPX", "MBAP", "MCBT", "MFOA", "MBA", "MCGR",
                "BEP", "FOC", "MPH",
                # chás Kãnfa em pouch/lata (mercearia, como CHA-LATA)
                "INTU_P50", "CHEGO_P50", "INTIMI_P50", "CHEGO_L50", "NAMAS_P50", "INTU_L70",
                "NAMAS_L60", "INTIMI_L50", "SOFIA_P50", "VITAL_P50", "MAMA_L60", "MAMA_P50",
                # pães com SKU do iFood (só entrega)
                "IFOOD_76da4710c82b11ee8012e9ac1", "IFOOD_7554d170c82b11ee9bb70dcd9",
            ]),
            ("hibrido", "serve aos dois usos (como no cardápio 2027; mini focaccia é lanchinho) — revisão do dono 19/08/2026", [
                "CI", "CIQ", "MCI", "TB", "MTB", "FE", "MFE", "MIB",
                "MICBT", "MIF", "MIFOC", "MMICBT", "MMIF",
            ]),
        )
        entries = [(ref, note, skus) for ref, (note, skus) in historical.items()] + list(round_two)
        for role_ref, note, skus in entries:
            role = roles.get(role_ref)
            if role is None:
                continue
            for sku in skus:
                ProductConsumptionTag.objects.update_or_create(
                    sku=sku, defaults={"role": role, "reviewed": True, "note": note},
                )

    def _seed_bi_aliases(self) -> None:
        """Os vocabulários do B.I. — de-para de categoria e de forma de pagamento.

        Eram tuplas em código (a tabela de categoria do consumo, o vocabulário do
        histórico em ``bi_payments``); agora são linhas de ``CategoryAlias`` e
        ``PaymentMethodAlias``, editáveis no Admin. Nascem CONFIRMADAS porque
        são a curadoria já feita com o dono (17–18/08) — a máquina não decidiu
        nada aqui. A ordem manda: a primeira que casa vence, então o específico
        tem posição menor que o genérico ("pães finos" antes de "pão", senão
        38.369 linhas de viennoiserie cairiam em "leva").

        Só o de-para de PRODUTO fica de fora: ele é por SKU real do Yooga e é
        sugerido pelo ``suggest_aliases`` a partir do histórico carregado.
        """
        from shopman.backstage.models import AliasStatus, CategoryAlias, PaymentMethodAlias

        # As categorias do export real do Yooga (medidas em 18/08, linhas
        # afetadas entre parênteses); leituras decididas pelo dono.
        categories = (
            ("pães finos", "hybrid"),          # 38.369 — viennoiserie serve aos dois usos
            ("paes finos", "hybrid"),
            ("sanduíche", "anchor"),           # 907 — tartine é prato montado, come aqui
            ("sanduiche", "anchor"),
            ("tartine", "anchor"),
            ("sobremesa", "anchor"),           # 108 — decisão do dono: consumo local
            ("pães rústicos", "takeaway"),     # 15.299
            ("paes rusticos", "takeaway"),
            ("café", "anchor"),                # 5.211
            ("cafe", "anchor"),
            ("bebida", "anchor"),
            ("suco", "anchor"),
            ("refri", "anchor"),
            ("mercearia", "takeaway"),
            ("chai", "anchor"),                # 290 — "Festival Chai" é bebida (dono, 18/08).
                                               # Vem DEPOIS de mercearia: a lata de chai
                                               # da prateleira é compra, não consumo.
            ("doce", "hybrid"),
            ("salgado", "hybrid"),
            ("confeitaria", "hybrid"),
            ("lanche", "anchor"),              # lanche montado come aqui, como a tartine
            # Genéricos por último: só pegam o que os específicos não pegaram.
            ("pão", "takeaway"),
            ("pao", "takeaway"),
            ("padaria", "takeaway"),
        )
        for position, (pattern, reading) in enumerate(categories, start=1):
            CategoryAlias.objects.update_or_create(
                pattern=pattern,
                defaults={
                    "position": position * 10,
                    "reading": reading,
                    "status": AliasStatus.CONFIRMED,
                    "note": "curadoria do dono (17–18/08/2026)",
                },
            )

        # Forma de pagamento crua do histórico → forma canônica da casa. O
        # específico antes do genérico: "vale refeição" antes de "vale",
        # "cartão de crédito" antes de "cartão".
        payments = (
            ("pix", "pix"),
            ("dinheiro", "cash"),
            ("especie", "cash"),
            ("espécie", "cash"),
            ("credito", "credit"),
            ("crédito", "credit"),
            ("debito", "debit"),
            ("débito", "debit"),
            ("vale", "voucher"),
            ("ticket", "voucher"),
            ("alelo", "voucher"),
            ("sodexo", "voucher"),
            ("ifood", "ifood"),
            ("cartao", "card"),
            ("cartão", "card"),
        )
        for position, (pattern, method_key) in enumerate(payments, start=1):
            PaymentMethodAlias.objects.update_or_create(
                pattern=pattern,
                defaults={
                    "position": position * 10,
                    "method_key": method_key,
                    "status": AliasStatus.CONFIRMED,
                    "note": "vocabulário do histórico Yooga",
                },
            )

    def _seed_bi_alert_rules(self) -> None:
        """Os primeiros alarmes do B.I. — regras como dado, editáveis no Admin.

        Cinco regras, quatro ativas: o faturamento de ontem abaixo de 70% da média
        do mesmo dia da semana (4 semanas) avisa o operador uma vez por dia. A
        de importação silenciosa nasce DESLIGADA: o export do Yooga é único até
        hoje; quando um export passar a ser recorrente, ativa-se e ajusta-se a
        cadência — a regra existe para o gestor achar, não para disparar à toa.
        """
        from shopman.backstage.models import BIAlertRule

        rules = (
            {
                "ref": "faturamento-abaixo-do-esperado",
                "label": "Faturamento do dia abaixo do esperado",
                "metric": BIAlertRule.Metric.DAILY_REVENUE_VS_BASELINE,
                "is_active": True,
                "severity": "warning",
                "cooldown_minutes": 24 * 60,
                "threshold_percent": 70,
                "baseline_weeks": 4,
            },
            {
                "ref": "importacao-yooga-silenciosa",
                "label": "Importação do Yooga não chegou",
                "metric": BIAlertRule.Metric.IMPORT_SILENCE,
                "is_active": False,
                "severity": "warning",
                "cooldown_minutes": 24 * 60,
                "source": "yooga",
                "expected_every_days": 7,
            },
            # O guard da fusão como alarme: um pedido de teste num dia antigo apaga
            # ~110 vendas do Yooga daquele dia — certo por regra, mudo não.
            {
                "ref": "pedido-nativo-apagou-historico",
                "label": "Pedido nativo apagou histórico",
                "metric": BIAlertRule.Metric.NATIVE_OVERRIDES_HISTORY,
                "is_active": True,
                "severity": "warning",
                "cooldown_minutes": 7 * 24 * 60,
                "lookback_days": 7,
                "max_native_orders": 5,
                "min_historical_dropped": 20,
            },
            # Apuração: o aviso ao operador não carrega nome nem valor; o detalhe
            # é para quem audita. Régua inicial R$ 50,00 em 7 dias — ajuste do dono.
            {
                "ref": "quebra-de-caixa-acumulada",
                "label": "Quebra de caixa acumulada por operador",
                "metric": BIAlertRule.Metric.CASH_VARIANCE_BY_OPERATOR,
                "is_active": True,
                "severity": "warning",
                "cooldown_minutes": 24 * 60,
                "lookback_days": 7,
                "threshold_q": 5000,
            },
            # Fecha o ciclo humano da camada canônica: lote novo com linhas sem
            # de-para confirmado é número ainda não confiável.
            {
                "ref": "de-para-de-produto-pendente",
                "label": "De-para de produto pendente",
                "metric": BIAlertRule.Metric.CURATION_PENDING,
                "is_active": True,
                "severity": "warning",
                "cooldown_minutes": 7 * 24 * 60,
                "source": "yooga",
                "threshold_percent": 20,
            },
        )
        for rule in rules:
            BIAlertRule.objects.update_or_create(ref=rule["ref"], defaults={k: v for k, v in rule.items() if k != "ref"})

    def _seed_seating(self) -> None:
        """O salão real da Nelson (informado pelo dono, 17/08).

        Capacidade oficial: 4 mesas internas + 4 externas + 6 lugares de balcão.
        Ficam FORA da conta as duas mesinhas altas de bistrô (em pé) e o bancão
        externo — eles existem e comportam gente em dia cheio, mas contá-los
        esconderia o momento em que a casa bateu no teto, que é exatamente o que
        a leitura precisa enxergar. Pelo mesmo motivo o sofá das mesas internas,
        que permite apertar mais gente com menos conforto, não vira lugar novo.
        """
        from shopman.backstage.models import SeatingSpot, SpotKind

        spots = []
        for index in range(1, 5):
            spots.append((f"mesa-interna-{index}", f"Mesa interna {index}",
                            SpotKind.TABLE, "Salão interno", 2, True))
        for index in range(1, 5):
            spots.append((f"mesa-externa-{index}", f"Mesa externa {index}",
                            SpotKind.TABLE, "Calçada", 2, True))
        for index in range(1, 7):
            spots.append((f"balcao-{index}", f"Balcão {index}",
                            SpotKind.COUNTER, "Balcão", 1, True))
        for index in range(1, 3):
            spots.append((f"bistro-{index}", f"Mesinha alta {index}",
                            SpotKind.TABLE, "Salão interno", 2, False))
        spots.append(("bancao-externo", "Bancão externo",
                        SpotKind.COUNTER, "Calçada", 4, False))

        for ref, label, kind, area, seats, counts in spots:
            SeatingSpot.objects.update_or_create(
                ref=ref,
                defaults={
                    "label": label, "kind": kind, "area": area,
                    "seats": seats, "counts_in_capacity": counts,
                },
            )

    def _seed_business_days(self, *, days: int) -> None:
        """Expediente congelado por dia — o denominador das métricas de tempo."""
        from shopman.backstage.services.business_day import stamp_day

        today = timezone.localdate()
        for offset in range(1, days + 1):
            stamp_day(today - timedelta(days=offset))

    def _seed_shelf_movements(self, products, vitrine, *, days: int) -> None:
        """Fornada de manhã, venda ao longo do dia, sobra descartada no fim.

        Escreve o ledger como a operação escreveria: MAKE na chegada, SELL na
        saída, WASTE no fechamento. É isso que faz `shelf_history` enxergar
        quando o produto chegou e quando acabou.
        """
        from shopman.stockman.models import Move, Quant

        today = timezone.localdate()
        rng = random.Random(20260815)
        for sku, (base, soldout_hour, weekend_only) in self.BI_SHELF_PROFILES.items():
            if sku not in products:
                continue
            quant, _ = Quant.objects.get_or_create(
                sku=sku, position=vitrine, target_date=None, batch=""
            )
            for offset in range(1, days + 1):
                day = today - timedelta(days=offset)
                if not self._shop_operates_on(day):
                    continue
                produced = max(1, base + rng.randint(-4, 4))
                acaba = soldout_hour if not weekend_only or day.weekday() in weekend_only else None
                sold = produced if acaba else int(produced * 0.75)
                Move.objects.create(
                    quant=quant, delta=Decimal(produced), kind=Move.Kind.MAKE,
                    reason=f"Recebido de produção: seed {day}",
                    timestamp=self._at(day, 9),
                )
                Move.objects.create(
                    quant=quant, delta=Decimal(-sold), kind=Move.Kind.SELL,
                    reason=f"Entrega hold:seed-{day}",
                    timestamp=self._at(day, acaba or 16),
                )
                leftover = produced - sold
                if leftover:
                    Move.objects.create(
                        quant=quant, delta=Decimal(-leftover), kind=Move.Kind.WASTE,
                        reason=f"perda_vencido:{day}",
                        timestamp=self._at(day, 18),
                    )

    def _seed_shelf_outages(self, products, *, days: int) -> None:
        """Períodos sem poder vender: os que acabaram e um que ficou pausado.

        O registro nasce da observação em tempo real, que o seed não roda — então
        aqui ele é escrito direto, espelhando o que teria sido observado.
        """
        from shopman.backstage.models import OutageReason, ShelfOutage

        today = timezone.localdate()
        for sku, (_, soldout_hour, weekend_only) in self.BI_SHELF_PROFILES.items():
            if sku not in products or soldout_hour is None:
                continue
            for offset in range(1, days + 1):
                day = today - timedelta(days=offset)
                if not self._shop_operates_on(day):
                    continue
                if weekend_only and day.weekday() not in weekend_only:
                    continue
                ShelfOutage.objects.get_or_create(
                    sku=sku, channel_ref="web",
                    started_at=self._at(day, soldout_hour),
                    defaults={
                        "reason": OutageReason.SOLD_OUT,
                        "ended_at": self._at(day + timedelta(days=1), 9),
                    },
                )
        # Um produto parado por decisão: é o que a métrica de tempo pausado lê.
        pausado = "KP"
        if pausado in products:
            ShelfOutage.objects.get_or_create(
                sku=pausado, channel_ref="web",
                started_at=self._at(today - timedelta(days=9), 9),
                defaults={
                    "reason": OutageReason.PAUSED,
                    "ended_at": self._at(today - timedelta(days=4), 18),
                },
            )

    def _seed_oven_runs(self, *, days: int) -> None:
        """Tempo de forno com cobertura PARCIAL — o KPI de adoção precisa disso.

        Cobertura 100% esconderia o indicador que mostra se a equipe está mesmo
        usando o timer; aqui ~70% das fornadas têm medição.
        """
        from shopman.craftsman.models import WorkOrder

        from shopman.backstage.models import OvenRun

        rng = random.Random(20260816)
        finished = WorkOrder.objects.filter(
            status=WorkOrder.Status.FINISHED, finished_at__isnull=False
        ).order_by("-target_date")[: days * 4]
        for index, wo in enumerate(finished):
            if index % 10 < 3:  # 30% sem medição: fornada em que ninguém armou
                continue
            planned = rng.choice((18, 22, 25, 30)) * 60
            real = planned + rng.randint(-180, 420)  # às vezes passa do ponto
            armed = wo.finished_at - timedelta(seconds=real)
            OvenRun.objects.get_or_create(
                work_order_ref=wo.ref,
                defaults={
                    "oven_ref": wo.position_ref or "",
                    "operator_ref": wo.operator_ref or "",
                    "planned_seconds": planned,
                    "armed_at": armed,
                    "concluded_at": wo.finished_at,
                    "status": "concluded",
                },
            )

    def _seed_day_weather(self, *, days: int) -> None:
        """Clima de exemplo, CARIMBADO como exemplo.

        Dado de demonstração não pode se passar por medição: `sources.weather`
        diz "seed", e quem injetar o arquivo real sobrescreve.
        """
        from shopman.backstage.models import DayContext

        today = timezone.localdate()
        rng = random.Random(20260817)
        for offset in range(1, days + 1):
            day = today - timedelta(days=offset)
            estacao = 1 if day.month in (12, 1, 2, 3) else 0
            tmax = Decimal(str(round(22 + estacao * 7 + rng.uniform(-4, 5), 1)))
            context, _ = DayContext.objects.get_or_create(date=day)
            context.temp_max_c = tmax
            context.temp_min_c = tmax - Decimal("9.0")
            context.temp_avg_c = tmax - Decimal("4.5")
            context.rain_mm = Decimal(str(round(max(0.0, rng.uniform(-8, 14)), 1)))
            context.sources = {**(context.sources or {}), "weather": "seed"}
            context.save()

    def _at(self, day, hour: int):
        """Instante local do dia — o B.I. lê tudo em hora da loja."""
        return timezone.make_aware(datetime.combine(day, time(hour=hour)))

    # ── Calendário e histórico longo: a base de "o que esperar" ──────────────

    # Fixos nacionais + o aniversário de Londrina. Móveis saem da Páscoa.
    BI_FIXED_HOLIDAYS = {
        (1, 1): ("Confraternização Universal", "national"),
        (4, 21): ("Tiradentes", "national"),
        (5, 1): ("Dia do Trabalho", "national"),
        (9, 7): ("Independência", "national"),
        (10, 10): ("Aniversário de Londrina", "city"),
        (10, 12): ("Nossa Senhora Aparecida", "national"),
        (11, 2): ("Finados", "national"),
        (11, 15): ("Proclamação da República", "national"),
        (11, 20): ("Consciência Negra", "national"),
        (12, 25): ("Natal", "national"),
    }

    def _seed_day_calendar(self, *, days: int) -> None:
        """Feriados do período, com véspera e volta derivadas.

        Sem isso o recorte "tipo de dia" não existe num banco semeado: a regra
        da casa é que a dimensão só aparece quando há calendário carregado, e um
        banco de teste sem feriado nenhum esconderia a funcionalidade em vez de
        demonstrá-la.
        """
        from shopman.backstage.models import DayContext

        today = timezone.localdate()
        first = today - timedelta(days=days)
        holidays: dict[date, tuple[str, str]] = {}
        commercial: dict[date, str] = {}
        for year in range(first.year, today.year + 2):
            for (month, day_of), value in self.BI_FIXED_HOLIDAYS.items():
                holidays[date(year, month, day_of)] = value
            easter = self._easter(year)
            holidays[easter - timedelta(days=47)] = ("Carnaval", "national")
            holidays[easter - timedelta(days=2)] = ("Sexta-feira Santa", "national")
            holidays[easter + timedelta(days=60)] = ("Corpus Christi", "national")
            commercial.update(self._commercial_dates(year))

        # Véspera e volta saem da UNIÃO: o sábado antes do dia das mães enche
        # tanto quanto a véspera de um feriado. A véspera guarda DE QUAL data
        # ela é véspera — numa padaria fechada no domingo, é no sábado que o
        # dia das mães acontece.
        special = {
            **{day: name for day, (name, _scope) in holidays.items()},
            **commercial,  # data comercial nomeia o dia quando é os dois
        }

        # O calendário cobre até um ano à frente: perguntar "o que esperar no
        # dia das mães que vem" exige saber que ele vem.
        for offset in range(-365, days + 1):
            day = today - timedelta(days=offset)
            name, scope = holidays.get(day, ("", ""))
            context, _ = DayContext.objects.get_or_create(date=day)
            context.holiday_name = name
            context.holiday_scope = scope
            context.commercial_name = commercial.get(day, "")
            context.eve_of = special.get(day + timedelta(days=1), "")
            context.is_special_eve = bool(context.eve_of)
            context.is_post_special = (day - timedelta(days=1)) in special
            context.has_calendar = True
            context.sources = {**(context.sources or {}), "holiday": "seed"}
            context.save()

    def _commercial_dates(self, year: int) -> dict:
        """As datas que movem a Nelson sem serem feriado (lista do dono).

        O Natal e a Páscoa são feriado E data comercial: os dois campos convivem
        porque respondem perguntas diferentes (a loja abre? / o movimento sobe?).
        """
        easter = self._easter(year)
        return {
            self._nth_sunday(year, 5, 2): "Dia das Mães",
            self._nth_sunday(year, 8, 2): "Dia dos Pais",
            easter: "Páscoa",
            date(year, 6, 12): "Dia dos Namorados",
            date(year, 12, 25): "Natal",
        }

    @staticmethod
    def _nth_sunday(year: int, month: int, nth: int) -> date:
        first = date(year, month, 1)
        first_sunday = first + timedelta(days=(6 - first.weekday()) % 7)
        return first_sunday + timedelta(days=7 * (nth - 1))

    @staticmethod
    def _easter(year: int) -> date:
        """Domingo de Páscoa (algoritmo gregoriano anônimo)."""
        a, b, c = year % 19, year // 100, year % 100
        d, e = b // 4, b % 4
        g = (b - (b + 8) // 25 + 1) // 3
        h = (19 * a + b - d - g + 15) % 30
        i, k = c // 4, c % 4
        el = (32 + 2 * e + 2 * i - h - k) % 7
        m = (a + 11 * h + 22 * el) // 451
        month = (h + el - 7 * m + 114) // 31
        return date(year, month, (h + el - 7 * m + 114) % 31 + 1)

    # ── Calibração: os pesos abaixo vêm da OPERAÇÃO REAL, não de chute ──────
    #
    # Primeira versão destes números era palpite meu, e errava o volume em ~8×
    # (16 vendas/dia contra ~111 reais). Um seed que erra de ordem de grandeza
    # não demonstra a tela: ensina o dono a desconfiar dela.
    #
    # Fonte: painel do próprio Yooga da Nelson (81.255 pedidos, jul/2024 a
    # 20/jul/2026). Só a FORMA vem de lá; nenhuma venda real é copiada.

    # Pedidos/dia por dia da semana ÷ média dos dias abertos. O domingo real tem
    # 224 pedidos em dois anos (a casa não abre), e fica aqui só por completude.
    BI_WEEKDAY_WEIGHT = (0.87, 0.90, 0.90, 0.92, 1.11, 1.30, 0.02)

    # Pedidos/mês ÷ média. Duas surpresas contra a intuição: **julho é o pico**
    # (não dezembro), e **janeiro despenca** para um terço — é quando a casa
    # para. Dezembro é um mês comum.
    BI_MONTH_WEIGHT = (0.31, 0.86, 1.03, 0.96, 1.11, 1.03, 1.48, 1.24, 1.02, 1.08, 0.94, 0.94)

    # Pedidos por dia de expediente, na média (81.255 ÷ ~626 dias abertos).
    BI_DAILY_ORDERS = 128

    def _seed_long_sales_history(self, products, *, days: int) -> int:
        """Dois anos de venda com estrutura reconhecível.

        Vai para ``HistoricalSale`` e não para ``Order`` de propósito, e o
        motivo é o mesmo da vida real: o passado longo da casa não tem ledger,
        estoque nem fornada — é só venda. Gravar dois anos de pedidos nativos
        inventaria um passado operacional que nunca existiu, além de custar
        caro.

        A origem fica carimbada como ``seed``: dado de demonstração não pode se
        passar por um export real que ninguém carregou.
        """
        from shopman.backstage.models import (
            DayContext,
            HistoricalSale,
            HistoricalSaleItem,
            ImportBatch,
        )

        # Limpa o que ESTE seed criou antes — nunca o que veio de um export.
        # Vem antes de qualquer saída antecipada de propósito: faxina não pode
        # depender de haver catálogo, senão um ambiente sem produtos guarda
        # linhas sintéticas órfãs para sempre. As vendas saem antes do lote
        # (a FK protege o lote enquanto houver venda pendurada).
        HistoricalSale.objects.filter(source="seed").delete()
        ImportBatch.objects.filter(source="seed").delete()

        # ⚠️ Onde já existe histórico de verdade, não se inventa histórico.
        # Sem esta guarda, rodar o seed num ambiente com o export carregado
        # somava dois anos sintéticos aos dois anos reais, e TODA leitura do
        # B.I. passava a ser metade ficção — o `source` rotula a série, mas os
        # totais são a soma. Com o delete acima, um ambiente semeado no passado
        # se limpa sozinho ao atualizar.
        real = HistoricalSale.objects.exclude(source="seed")
        if real.exists():
            self.stdout.write(
                f"  ↷ histórico sintético pulado: já há {real.count()} vendas reais carregadas"
            )
            return 0

        catalogo = [p for sku, p in products.items() if sku in self.BI_SHELF_PROFILES]
        if not catalogo:
            catalogo = list(products.values())[:8]
        if not catalogo:
            return 0

        today = timezone.localdate()
        rng = random.Random(20260819)
        contexts = {
            row.date: row
            for row in DayContext.objects.filter(date__gte=today - timedelta(days=days))
        }

        sales, items_by_key = [], {}
        external_id = 1
        for offset in range(days, 0, -1):
            day = today - timedelta(days=offset)
            if not self._shop_operates_on(day):
                continue
            context = contexts.get(day)
            if context is not None and context.holiday_name:
                continue  # feriado de portas fechadas não vende
            count = self._bi_sales_count(day, context, offset=offset, days=days, rng=rng)
            price_factor = self._bi_price_factor(offset=offset, days=days)
            for _ in range(count):
                lines = [
                    (product, rng.randint(1, 3), int(product.base_price_q * price_factor))
                    for product in rng.sample(catalogo, k=min(len(catalogo), rng.randint(1, 3)))
                ]
                total_q = sum(unit * qty for _p, qty, unit in lines)
                sales.append(
                    HistoricalSale(
                        source="seed",
                        external_id=external_id,
                        occurred_at=self._at(day, rng.choice((8, 9, 10, 10, 11, 12, 15, 16, 17))),
                        total_q=total_q,
                        # Forma de pagamento crua, como o export externo entrega.
                        # Sem ela a previsão de troco não teria de onde tirar
                        # "quantas vendas em dinheiro num sábado", que é o único
                        # fator dela com dois anos de base.
                        payment=self._bi_historical_payment(day, rng),
                        is_delivery=rng.random() < 0.12,
                    )
                )
                items_by_key[external_id] = lines
                external_id += 1

        # Dado sintético também tem lote: a proveniência de TODA venda histórica
        # é declarada, e aqui ela diz "seed", sem arquivo nem hash.
        batch = ImportBatch.objects.create(
            source="seed",
            status=ImportBatch.Status.DONE,
            rows_read=len(sales),
            sales_created=len(sales),
            items_created=sum(len(lines) for lines in items_by_key.values()),
            notes="histórico sintético gerado pelo seed",
        )
        for sale in sales:
            sale.batch = batch
        HistoricalSale.objects.bulk_create(sales, batch_size=1000)
        ids = dict(
            HistoricalSale.objects.filter(source="seed").values_list("external_id", "id")
        )
        HistoricalSaleItem.objects.bulk_create(
            [
                HistoricalSaleItem(
                    sale_id=ids[key], seq=seq, product_name=product.name,
                    sku=product.sku, category=self._bi_category(product),
                    qty=Decimal(qty), unit_price_q=unit, line_total_q=unit * qty,
                )
                for key, lines in items_by_key.items()
                for seq, (product, qty, unit) in enumerate(lines, start=1)
            ],
            batch_size=1000,
        )
        return len(sales)

    def _bi_sales_count(self, day, context, *, offset: int, days: int, rng) -> int:
        """Quantas vendas naquele dia, com as estruturas que o B.I. deve achar.

        Cada fator existe para uma pergunta virar visível na tela: dia da
        semana, sazonalidade do ano, véspera e volta de feriado, data
        comercial, clima e crescimento da casa.
        """
        base = float(self.BI_DAILY_ORDERS)
        weight = self.BI_WEEKDAY_WEIGHT[day.weekday()] * self.BI_MONTH_WEIGHT[day.month - 1]
        if context is not None:
            if context.is_special_eve:
                # A véspera de uma data comercial carrega quase todo o peso
                # dela: a casa fecha no domingo do dia das mães, então é no
                # sábado que a compra acontece. Véspera de feriado comum tem o
                # empurrão modesto de sempre.
                commercial = self.BI_COMMERCIAL_WEIGHT.get(context.eve_of)
                weight *= 1 + (commercial - 1) * 0.9 if commercial else 1.35
            if context.is_post_special:
                weight *= 0.85
            if context.temp_max_c is not None and context.temp_max_c > 30:
                weight *= 0.9
            if context.rain_mm is not None and context.rain_mm > 6:
                weight *= 0.78
            # A data comercial vem do contexto já carregado, não de uma segunda
            # conta de calendário: duas contas divergiriam no primeiro ano em
            # que alguém editasse uma delas.
            weight *= self.BI_COMMERCIAL_WEIGHT.get(context.commercial_name, 1.0)
        return max(1, int(base * weight * rng.uniform(0.85, 1.15)))

    # A rampa do ticket, relativa ao preço do catálogo de hoje: o histórico real
    # começa em R$ 42,65 (jul/2024) e termina em R$ 66,30 (jul/2026).
    BI_TICKET_RAMP = (0.75, 1.19)

    def _bi_price_factor(self, *, offset: int, days: int) -> float:
        """O crescimento da casa mora no TICKET, não no volume.

        Nos dois anos reais o número de pedidos por mês ficou **estável** (até
        caiu um pouco) e o ticket médio subiu 55%. Inventar crescimento de
        volume, como a primeira versão fazia, contradiria o próprio dado — e o
        método de "nível do presente" ganha demonstração igual pelo preço.
        """
        start, end = self.BI_TICKET_RAMP
        return start + (end - start) * (days - offset) / max(days, 1)

    # Quanto cada data move o movimento, para a estrutura existir no dado.
    BI_COMMERCIAL_WEIGHT = {
        "Dia das Mães": 1.9,
        "Natal": 2.2,
        "Páscoa": 1.6,
        "Dia dos Pais": 1.4,
        "Dia dos Namorados": 1.2,
    }

    def _seed_recent_native_volume(self, products, *, days: int) -> int:
        """Volume de verdade nos dias recentes, do lado do Shopman.

        Sem isto o seed descreve uma casa que **não existe**: dois anos de
        histórico com ~128 vendas/dia e um presente com quatro pedidos de QA por
        dia. Como o dia nativo vence o histórico no mesmo dia (regra certa,
        evita contar a venda duas vezes), o presente medido virava 12% do
        passado — e a projeção inteira saía oito vezes baixa, com toda a
        aparência de estar certa.

        Os pedidos de QA continuam onde estão; estes só somam o movimento que
        uma casa em operação teria. Vão em lote, sem passar pelo lifecycle:
        aqui interessa a série de vendas, não o ciclo do pedido.
        """
        from shopman.orderman.models import OrderItem

        catalogo = [p for sku, p in products.items() if sku in self.BI_SHELF_PROFILES]
        if not catalogo:
            return 0

        Order.objects.filter(ref__startswith="BIV-").delete()
        today = timezone.localdate()
        rng = random.Random(20260821)
        contexts = {
            row.date: row
            for row in DayContext.objects.filter(date__gte=today - timedelta(days=days))
        }

        created = 0
        for offset in range(1, days + 1):
            day = today - timedelta(days=offset)
            if not self._shop_operates_on(day):
                continue
            context = contexts.get(day)
            if context is not None and context.holiday_name:
                continue
            count = self._bi_sales_count(
                day, context, offset=offset, days=self.BI_LONG_DAYS, rng=rng
            )
            price_factor = self._bi_price_factor(offset=offset, days=self.BI_LONG_DAYS)
            orders, lines_by_ref = [], {}
            for index in range(count):
                # Convenção de ref da casa: PREFIXO-aammdd-sufixo (há teste cobrando).
                ref = f"BIV-{day:%y%m%d}-{index}"
                lines = [
                    (product, rng.randint(1, 3), int(product.base_price_q * price_factor))
                    for product in rng.sample(
                        catalogo, k=min(len(catalogo), rng.randint(1, 3))
                    )
                ]
                total_q = sum(unit * qty for _p, qty, unit in lines)
                orders.append(
                    Order(
                        ref=ref, channel_ref="pdv", session_key=f"seed-{ref}",
                        status=Order.Status.COMPLETED,
                        total_q=total_q,
                        data=self._bi_native_payment(day, total_q, rng),
                        snapshot={"seed": "nelson", "source": "bi_native_volume"},
                    )
                )
                lines_by_ref[ref] = lines
            Order.objects.bulk_create(orders, batch_size=500)
            ids = dict(
                Order.objects.filter(ref__startswith=f"BIV-{day:%y%m%d}-")
                .values_list("ref", "id")
            )
            OrderItem.objects.bulk_create(
                [
                    OrderItem(
                        order_id=ids[ref], line_id=f"{ref}-{seq}", sku=product.sku,
                        name=product.name, qty=Decimal(qty), unit_price_q=unit,
                        line_total_q=unit * qty,
                    )
                    for ref, lines in lines_by_ref.items()
                    for seq, (product, qty, unit) in enumerate(lines, start=1)
                ],
                batch_size=500,
            )
            # created_at é auto_now_add: só depois do insert dá para datar.
            Order.objects.filter(ref__startswith=f"BIV-{day:%y%m%d}-").update(
                created_at=self._at(day, 11)
            )
            created += len(orders)
        return created

    # Fatia das vendas pagas em espécie no balcão. Fim de semana puxa dinheiro
    # para cima (movimento de bairro, compra pequena); dia útil puxa para baixo.
    BI_CASH_SHARE = (0.30, 0.30, 0.30, 0.32, 0.36, 0.44, 0.44)

    def _bi_historical_payment(self, day, rng) -> str:
        """Texto cru de forma de pagamento, no dialeto do export externo."""
        roll = rng.random()
        if roll < self.BI_CASH_SHARE[day.weekday()]:
            return "DINHEIRO"
        return "PIX" if roll < 0.72 else rng.choice(("CARTAO DE CREDITO", "CARTAO DE DEBITO"))

    def _bi_native_payment(self, day, total_q: int, rng) -> dict:
        """O bloco ``payment`` de uma venda de balcão, como o PDV grava.

        O troco entra **medido**, e não estimado: é o que separa a previsão de
        troco de um chute. Uma parte das vendas em dinheiro sai sem
        ``tendered_q`` de propósito — o operador nem sempre digita o valor
        recebido, e a tela precisa enxergar esse buraco de medição em vez de
        encontrar um mundo perfeito que a casa não tem.
        """
        payment = {"method": "pix", "collection": "terminal", "amount_q": total_q}
        roll = rng.random()
        if roll >= self.BI_CASH_SHARE[day.weekday()]:
            payment["method"] = "pix" if roll < 0.72 else "card"
            return {"payment": payment}

        payment.update({"method": "cash", "cash_received_q": total_q})
        if rng.random() < 0.12:
            return {"payment": payment}  # ninguém registrou o valor recebido
        # A nota que o cliente entrega quase sempre é a mais próxima do total;
        # a de R$ 50 aparece, mas é minoria. Uniformizar os degraus inflaria o
        # troco médio e a tela pediria muito mais dinheiro do que a casa precisa.
        step = rng.choice((500, 500, 500, 1000, 1000, 2000))
        tendered_q = total_q if rng.random() < 0.10 else -(-total_q // step) * step
        payment["tendered_q"] = tendered_q
        payment["change_q"] = max(0, tendered_q - total_q)
        return {"payment": payment}

    def _bi_category(self, product) -> str:
        """Categoria da linha histórica — o recorte barato de 2 anos."""
        return {
            "CT": "Viennoiserie", "PC": "Viennoiserie",
            "BF": "Pães", "CGO": "Pães", "MD": "Confeitaria",
        }.get(product.sku, "Pães")
