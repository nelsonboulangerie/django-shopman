"""Apagar o sintético do alpha e deixar só o dado do Dia 1 (decisão B1, D-029).

A loja vira produção no próprio app vivo, no mesmo banco. Antes de virar as
chaves, o banco perde tudo que o ensaio produziu (pedidos, pagamentos, clientes,
turnos de caixa, produção, estoque, conversas, marketing de ensaio) e guarda o
que é cadastro da casa (catálogo, preços, fichas, insumos, fornecedores, canais,
regras, Shop, operadores, terminais e estações pareadas, histórico real do
Yooga).

A peça central é :data:`POLICY`: **todo** modelo instalado tem uma linha, com o
destino e o motivo. Modelo novo sem linha faz o comando recusar antes de tocar
em qualquer coisa: classificar é decisão, e decisão não se infere.

Destinos:

``keep``
    Cadastro do Dia 1. A contagem depois tem de ser igual à de antes, salvo as
    linhas que a exclusão das contas de cliente leva junto pelo próprio Django
    (relatadas uma a uma).
``purge``
    Dado do ensaio. ``DELETE`` cru da tabela inteira, de propósito: livro-caixa,
    ledger de estoque e auditoria são imutáveis pelo app (``delete()`` levanta),
    e este é o único momento em que apagá-los é o certo.
``purge_rows``
    Tabela mista: só as linhas do filtro saem, pelo ORM (com cascata e sinais).
    Contas de cliente saem; operadores ficam. Dispositivo de cliente sai;
    estação e tela pareadas ficam.

``detach`` (em ``keep``) esvazia a FK que apontaria para linha apagada, como a
leitora de entrega que guarda o pedido em curso.

Tudo corre numa transação só. O ensaio (padrão) executa, mede e desfaz; o
``--apply`` grava. Antes de terminar, as constraints são conferidas na hora
(``check_constraints``): FK quebrada desfaz tudo, inclusive no ``--apply``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from django.apps import apps
from django.db import connections, transaction
from django.db.models import Model, Q, QuerySet

KEEP = "keep"
PURGE = "purge"
PURGE_ROWS = "purge_rows"


@dataclass(frozen=True)
class Rule:
    action: str
    reason: str
    rows: Callable[[], QuerySet] | None = None
    detach: tuple[str, ...] = ()


def _keep(reason: str, *, detach: tuple[str, ...] = ()) -> Rule:
    return Rule(KEEP, reason, detach=detach)


def _purge(reason: str) -> Rule:
    return Rule(PURGE, reason)


def _purge_rows(reason: str, rows: Callable[[], QuerySet]) -> Rule:
    return Rule(PURGE_ROWS, reason, rows=rows)


def _customer_accounts() -> QuerySet:
    """Contas de cliente: ligadas a um Customer pelo doorman e sem papel de operador."""
    User = apps.get_model("auth", "User")
    CustomerUser = apps.get_model("doorman", "CustomerUser")
    linked = CustomerUser.objects.values("user_id")
    return User.objects.filter(pk__in=linked, is_staff=False, is_superuser=False, groups__isnull=True)


def _customer_devices() -> QuerySet:
    TrustedDevice = apps.get_model("doorman", "TrustedDevice")
    return TrustedDevice.objects.filter(subject_type="customer")


def _order_refs() -> QuerySet:
    Ref = apps.get_model("refs", "Ref")
    return Ref.objects.filter(Q(target_type__startswith="orderman."))


_LEDGER = "ledger do ensaio; o inventário de abertura entra depois, contado"
_ORDERS = "pedido, carrinho e efeitos do ensaio"
_CUSTOMER = "cliente do ensaio (sintético)"
_MARKETING = "marketing de ensaio (fora do v1, D-017)"
_DERIVED = "derivado do ensaio; recalculável"
_AUDIT = "trilha do ensaio"
_CONFIG = "configuração da casa"
_CATALOG = "catálogo da casa"
_RECIPES = "fichas técnicas da casa"
_PURCHASE = "cadastro de compra da casa"
_USER_CASCADE = "do operador; some só junto da conta de cliente, se houver"
_YOOGA = "histórico real (Yooga) e sua curadoria"
_FRAMEWORK = "infraestrutura do Django"

POLICY: dict[str, Rule] = {
    # Django e bibliotecas
    "contenttypes.ContentType": _keep(_FRAMEWORK),
    "auth.Permission": _keep(_FRAMEWORK),
    "auth.Group": _keep("papéis dos operadores"),
    "auth.Group_permissions": _keep("papéis dos operadores"),
    "auth.User": _purge_rows("contas de cliente saem; operadores ficam", _customer_accounts),
    "auth.User_groups": _keep(_USER_CASCADE),
    "auth.User_user_permissions": _keep(_USER_CASCADE),
    "admin.LogEntry": _keep("trilha do Admin (curadoria feita por gente)"),
    "sessions.Session": _keep("estações pareadas continuam logadas; sessão de cliente apagado vira anônima"),
    "taggit.Tag": _keep(_CATALOG),
    "taggit.TaggedItem": _keep(_CATALOG),
    "django_eventstream.EventCounter": _keep("contador do SSE; zerar confundiria quem está conectado"),
    "django_eventstream.Event": _keep("fila curta do SSE"),
    "otp_totp.TOTPDevice": _keep("2FA do Admin"),
    "otp_static.StaticDevice": _keep("2FA do Admin"),
    "otp_static.StaticToken": _keep("2FA do Admin"),
    # refs
    "refs.Ref": _purge_rows("refs de sessão e pedido do ensaio", _order_refs),
    "refs.RefSequence": _purge("sequência de refs de pedido; recomeça"),
    # offerman
    "offerman.Product": _keep(_CATALOG),
    "offerman.HistoricalProduct": _keep(_CATALOG),
    "offerman.ProductComponent": _keep(_CATALOG),
    "offerman.Collection": _keep(_CATALOG),
    "offerman.CollectionItem": _keep(_CATALOG),
    "offerman.Listing": _keep(_CATALOG),
    "offerman.ListingItem": _keep(_CATALOG),
    "offerman.HistoricalListingItem": _keep(_CATALOG),
    # stockman
    "stockman.Position": _keep("posições de estoque da casa"),
    "stockman.StockAlert": _keep("mínimos de estoque configurados"),
    "stockman.Quant": _purge(_LEDGER),
    "stockman.Move": _purge(_LEDGER),
    "stockman.Hold": _purge(_LEDGER),
    "stockman.Batch": _purge(_LEDGER),
    # craftsman
    "craftsman.Recipe": _keep(_RECIPES),
    "craftsman.RecipeItem": _keep(_RECIPES),
    "craftsman.RecipeEntry": _keep(_RECIPES),
    "craftsman.RecipeVersion": _keep(_RECIPES),
    "craftsman.RefSequence": _purge("numeração de ordem de produção; recomeça"),
    "craftsman.WorkOrder": _purge("produção do ensaio"),
    "craftsman.WorkOrderItem": _purge("produção do ensaio"),
    "craftsman.WorkOrderEvent": _purge("produção do ensaio"),
    # orderman
    "orderman.Session": _purge(_ORDERS),
    "orderman.SessionItem": _purge(_ORDERS),
    "orderman.SessionEvent": _purge(_ORDERS),
    "orderman.Order": _purge(_ORDERS),
    "orderman.OrderItem": _purge(_ORDERS),
    "orderman.OrderEvent": _purge(_ORDERS),
    "orderman.Fulfillment": _purge(_ORDERS),
    "orderman.FulfillmentItem": _purge(_ORDERS),
    "orderman.Directive": _purge(_ORDERS),
    "orderman.IdempotencyKey": _purge(_ORDERS),
    # payman
    "payman.PaymentIntent": _purge(_ORDERS),
    "payman.PaymentTransaction": _purge(_ORDERS),
    # guestman
    "guestman.Customer": _purge(_CUSTOMER),
    # Tabela do M2M Customer.price_tiers (N:N): elo do cliente, some com ele.
    "guestman.Customer_price_tiers": _purge(_CUSTOMER),
    "guestman.CustomerAddress": _purge(_CUSTOMER),
    "guestman.ContactPoint": _purge(_CUSTOMER),
    "guestman.ExternalIdentity": _purge(_CUSTOMER),
    "guestman.ProviderErasureTombstone": _purge(_CUSTOMER),
    "guestman.ProcessedEvent": _purge(_CUSTOMER),
    "guestman.TaggedCustomer": _purge(_CUSTOMER),
    "guestman.PriceTier": _keep(_CONFIG),
    "guestman.PriceTierAdvantage": _keep(_CONFIG),
    "guestman.CustomerTag": _keep(_CONFIG),
    "customer_consent.CommunicationConsent": _purge(_CUSTOMER),
    "customer_consent.CommunicationConsentEvent": _purge(_CUSTOMER),
    "customer_identifiers.CustomerIdentifier": _purge(_CUSTOMER),
    "customer_insights.CustomerInsight": _purge(_CUSTOMER),
    "customer_loyalty.LoyaltyAccount": _purge(_CUSTOMER),
    "customer_loyalty.LoyaltyTransaction": _purge(_CUSTOMER),
    "customer_preferences.CustomerPreference": _purge(_CUSTOMER),
    "customer_timeline.TimelineEvent": _purge(_CUSTOMER),
    "customer_merge.MergeAudit": _purge(_CUSTOMER),
    # doorman
    "doorman.CustomerUser": _purge(_CUSTOMER),
    "doorman.AccessLink": _purge(_CUSTOMER),
    "doorman.VerificationCode": _purge(_CUSTOMER),
    "doorman.Passkey": _purge(_CUSTOMER),
    "doorman.TrustedDevice": _purge_rows(
        "dispositivo de cliente sai; estação e tela pareadas ficam", _customer_devices
    ),
    "doorman.PinCredential": _keep("PIN dos operadores"),
    # buyman
    "buyman.Supplier": _keep(_PURCHASE),
    "buyman.SupplierContact": _keep(_PURCHASE),
    "buyman.Material": _keep(_PURCHASE),
    "buyman.MaterialConversion": _keep(_PURCHASE),
    "buyman.SupplierMaterialCost": _keep(_PURCHASE),
    # cashman
    "cashman.Terminal": _keep("terminal e hardware do balcão"),
    "cashman.Shift": _purge("turno de caixa do ensaio"),
    "cashman.Entry": _purge("livro-caixa do ensaio"),
    # shop: configuração
    "shop.Shop": _keep(_CONFIG),
    "shop.Channel": _keep(_CONFIG),
    "shop.RuleConfig": _keep(_CONFIG),
    "shop.RuleConfig_channels": _keep(_CONFIG),
    "shop.HistoricalRuleConfig": _keep(_CONFIG),
    "shop.NotificationTemplate": _keep(_CONFIG),
    "shop.OmotenashiCopy": _keep(_CONFIG),
    "shop.HistoricalOmotenashiCopy": _keep(_CONFIG),
    "shop.FAQEntry": _keep(_CONFIG),
    "shop.HistoricalFAQEntry": _keep(_CONFIG),
    "shop.DeliveryZone": _keep(_CONFIG),
    "shop.DeliveryDistanceBand": _keep(_CONFIG),
    "shop.Promotion": _keep("promoções e cupons: entram ou não no Dia 1 é decisão do dono"),
    "shop.Promotion_channels": _keep("promoções e cupons: entram ou não no Dia 1 é decisão do dono"),
    "shop.Coupon": _keep("promoções e cupons: entram ou não no Dia 1 é decisão do dono"),
    "shop.AttributeDefinition": _keep(_CATALOG),
    "shop.RetiredProduct": _keep("lápides do catálogo (URL antiga responde 410)"),
    "shop.QualityGrade": _keep(_CONFIG),
    "shop.QualityDefect": _keep(_CONFIG),
    "shop.CatalogSnapshot": _keep("vínculo do catálogo com o iFood"),
    "shop.CatalogBinding": _keep("vínculo do catálogo com o iFood"),
    "shop.CatalogSyncState": _keep("vínculo do catálogo com o iFood"),
    "shop.IFoodStoreStatus": _keep("estado da loja no iFood"),
    "shop.OperatorPasskey": _keep("passkey dos operadores"),
    "shop.PushSubscription": _keep("aviso no dispositivo do operador"),
    "shop.AnnouncementTemplate": _keep(_CONFIG),
    "shop.Campaign": _keep(_CONFIG),
    "shop.MarketingSafetyState": _keep(_CONFIG),
    # shop: ensaio
    "shop.ProductAffinity": _purge(_DERIVED),
    "shop.UserNotification": _purge("avisos do ensaio na caixa do operador"),
    "shop.UserNotificationEvent": _purge("avisos do ensaio na caixa do operador"),
    "shop.Conversation": _purge("conversas do ensaio (WhatsApp)"),
    "shop.ConversationBinding": _purge("conversas do ensaio (WhatsApp)"),
    "shop.ConversationMessage": _purge("conversas do ensaio (WhatsApp)"),
    "shop.OutboundAttempt": _purge("conversas do ensaio (WhatsApp)"),
    "shop.ContactRelease": _purge("conversas do ensaio (WhatsApp)"),
    "shop.PrivacyRequestReceipt": _purge(_CUSTOMER),
    "shop.IFoodInterruption": _purge(_AUDIT),
    "shop.Announcement": _purge(_MARKETING),
    "shop.AudienceSnapshot": _purge(_MARKETING),
    "shop.AudienceSnapshotMember": _purge(_MARKETING),
    "shop.MarketingTestReceipt": _purge(_MARKETING),
    "shop.MarketingCommandReceipt": _purge(_MARKETING),
    "shop.MarketingContentArtifact": _purge(_MARKETING),
    "shop.MarketingAuditEvent": _purge(_MARKETING),
    "shop.MarketingAISuggestion": _purge(_MARKETING),
    "shop.MarketingAISuggestionEvent": _purge(_MARKETING),
    "shop.MarketingPlatformAuditEvent": _purge(_MARKETING),
    "shop.MarketingConfirmation": _purge(_MARKETING),
    "shop.MarketingQuotaUsage": _purge(_MARKETING),
    "shop.MarketingSecurityEvent": _purge(_MARKETING),
    "shop.MarketingOutbox": _purge(_MARKETING),
    "shop.DeliveryTarget": _purge(_MARKETING),
    "shop.DeliveryAttempt": _purge(_MARKETING),
    "shop.DeliveryReconciliation": _purge(_MARKETING),
    # storefront
    "storefront.CatalogStructureHead": _keep(_CATALOG),
    "storefront.IntentCategory": _keep(_CONFIG),
    "storefront.CustomerFavorite": _purge(_CUSTOMER),
    "storefront.StockAlertSubscription": _purge(_CUSTOMER),
    "storefront.StockAlertOccurrence": _purge(_CUSTOMER),
    "storefront.StockAlertDelivery": _purge(_CUSTOMER),
    "storefront.MessageIntentSample": _purge("amostras automáticas das conversas do ensaio"),
    "storefront.MessageIntentSample_intents": _purge("amostras automáticas das conversas do ensaio"),
    "storefront.IntentPilotReport": _purge(_DERIVED),
    # backstage: configuração da operação
    "backstage.AdminTwoFactorEnrollment": _keep("2FA do Admin"),
    "backstage.Workstation": _keep("estações da casa"),
    "backstage.DeliveryDevice": _keep("leitora de entrega", detach=("current_order",)),
    "backstage.KDSInstance": _keep(_CONFIG),
    "backstage.KDSInstance_collections": _keep(_CONFIG),
    "backstage.POSTab": _keep("comandas físicas"),
    "backstage.PrintAgentCredential": _keep("credencial da impressora do balcão"),
    "backstage.OperationTaskTemplate": _keep(_CONFIG),
    "backstage.OperationChecklistTemplate": _keep(_CONFIG),
    "backstage.OperationChecklistTemplateTask": _keep(_CONFIG),
    "backstage.OperationEpisodeKind": _keep(_CONFIG),
    "backstage.TimerTag": _keep(_CONFIG),
    "backstage.SeatingSpot": _keep(_CONFIG),
    "backstage.SeatingFixture": _keep(_CONFIG),
    "backstage.RecipeRatingCriterion": _keep(_RECIPES),
    "backstage.RecipeVersionRating": _keep(_RECIPES),
    "backstage.RecipeVersionRatingScore": _keep(_RECIPES),
    "backstage.OperatorRecipeFavorite": _keep(_RECIPES),
    "backstage.SavedView": _keep("visões salvas dos operadores"),
    "backstage.ConsumptionRole": _keep(_CATALOG),
    "backstage.ProductConsumptionTag": _keep(_CATALOG),
    "backstage.BIAlertRule": _keep(_CONFIG),
    # backstage: histórico real do Yooga
    "backstage.ImportBatch": _keep(_YOOGA),
    "backstage.HistoricalSale": _keep(_YOOGA),
    "backstage.HistoricalSaleItem": _keep(_YOOGA),
    "backstage.ProductAlias": _keep(_YOOGA),
    "backstage.CategoryAlias": _keep(_YOOGA),
    "backstage.PaymentMethodAlias": _keep(_YOOGA),
    "backstage.AliasBenchmarkReport": _keep(_YOOGA),
    "backstage.BIScenarioReport": _keep(_YOOGA),
    "backstage.DayContext": _keep("calendário e clima (fonte externa)"),
    # backstage: ensaio
    "backstage.DailySalesFact": _purge(_DERIVED + " (refresh_bi_daily_series --all)"),
    "backstage.KDSTicket": _purge("cozinha do ensaio"),
    "backstage.OvenRun": _purge("produção do ensaio"),
    "backstage.BlindPrepCode": _purge("produção do ensaio"),
    "backstage.PlanCarryNote": _purge("produção do ensaio"),
    "backstage.DayClosing": _purge("fechamento do ensaio"),
    "backstage.OperationChecklistRun": _purge("rotina do ensaio"),
    "backstage.OperationTaskRun": _purge("rotina do ensaio"),
    "backstage.OperationEpisode": _purge(_AUDIT),
    "backstage.ShelfOutage": _purge(_AUDIT),
    "backstage.OperatorAlert": _purge(_AUDIT),
    "backstage.BIAlertEvent": _purge(_AUDIT),
    "backstage.SignInEvent": _purge(_AUDIT),
    "backstage.PrintJob": _purge("impressões do ensaio"),
    "backstage.PrintAttempt": _purge("impressões do ensaio"),
}


class PolicyError(RuntimeError):
    """A classificação não cobre o banco ou se contradiz; nada foi tocado."""


class PurgeAborted(RuntimeError):
    """O ensaio mediu algo fora do esperado; a transação foi desfeita."""


def _models() -> dict[str, type[Model]]:
    return {
        m._meta.label: m
        for m in apps.get_models(include_auto_created=True)
        if m._meta.managed and not m._meta.proxy
    }


def check_policy() -> dict[str, type[Model]]:
    """Recusa modelo sem classificação, linha órfã e FK de cadastro para dado apagado."""
    models = _models()
    unclassified = sorted(set(models) - set(POLICY))
    stale = sorted(set(POLICY) - set(models))
    problems = []
    if unclassified:
        problems.append("modelo sem classificação: " + ", ".join(unclassified))
    if stale:
        problems.append("classificação de modelo que não existe: " + ", ".join(stale))
    for label, model in models.items():
        rule = POLICY.get(label)
        if rule is None or rule.action != KEEP:
            continue
        for f in model._meta.concrete_fields:
            if not f.is_relation or f.related_model is None:
                continue
            target = POLICY.get(f.related_model._meta.label)
            if target is not None and target.action == PURGE and f.name not in rule.detach:
                problems.append(
                    f"{label}.{f.name} aponta para {f.related_model._meta.label}, que será apagado "
                    "inteiro; classifique um dos dois de novo ou declare o detach"
                )
    if problems:
        raise PolicyError("\n".join(problems))
    return models


def _delete_order(labels: list[str], models: dict[str, type[Model]]) -> list[str]:
    """Filhos antes dos pais (as FKs são adiadas, mas a ordem lê melhor no log)."""
    pending = set(labels)
    ordered: list[str] = []
    while pending:
        progress = False
        for label in sorted(pending):
            has_child = any(
                other != label
                and any(
                    f.is_relation and f.related_model is not None and f.related_model._meta.label == label
                    for f in models[other]._meta.concrete_fields
                )
                for other in pending
            )
            if not has_child:
                ordered.append(label)
                pending.discard(label)
                progress = True
        if not progress:  # ciclo: a ordem deixa de importar
            ordered.extend(sorted(pending))
            break
    return ordered


@dataclass
class Report:
    applied: bool
    database: str
    before: dict[str, int] = field(default_factory=dict)
    after: dict[str, int] = field(default_factory=dict)
    cascade: dict[str, int] = field(default_factory=dict)
    detached: dict[str, int] = field(default_factory=dict)
    portrait: dict[str, object] = field(default_factory=dict)

    def rows(self):
        for label in sorted(POLICY):
            if label in self.before:
                yield label, POLICY[label], self.before[label], self.after.get(label, self.before[label])

    def removed(self, action: str) -> int:
        return sum(b - a for _l, r, b, a in self.rows() if r.action == action)

    def as_dict(self) -> dict:
        return {
            "applied": self.applied,
            "database": self.database,
            "tables": {
                label: {"action": rule.action, "before": b, "after": a, "reason": rule.reason}
                for label, rule, b, a in self.rows()
            },
            "cascade": dict(sorted(self.cascade.items())),
            "detached": dict(sorted(self.detached.items())),
            "portrait": self.portrait,
        }


def day_one_portrait() -> dict[str, object]:
    """O que o Dia 1 encontra no banco: só contagens e refs de cadastro, nunca dado pessoal."""
    get = apps.get_model
    Product = get("offerman", "Product")
    ListingItem = get("offerman", "ListingItem")
    User = get("auth", "User")
    PinCredential = get("doorman", "PinCredential")
    listings: dict[str, dict[str, int]] = {}
    for ref, published, sellable in ListingItem.objects.values_list(
        "listing__ref", "is_published", "is_sellable"
    ):
        entry = listings.setdefault(ref, {"items": 0, "on_sale": 0})
        entry["items"] += 1
        entry["on_sale"] += int(bool(published and sellable))
    pinned = set(PinCredential.objects.values_list("user_id", flat=True))
    operators = {}
    for user in User.objects.order_by("username").prefetch_related("groups"):
        groups = sorted(g.name for g in user.groups.all())
        operators[user.username] = {
            "groups": groups,
            "staff": user.is_staff,
            "superuser": user.is_superuser,
            "pin": user.pk in pinned,
        }
    return {
        "products": Product.objects.count(),
        "products_on_sale": Product.objects.filter(is_published=True, is_sellable=True).count(),
        "products_sellable_unpublished": Product.objects.filter(is_published=False, is_sellable=True).count(),
        "listings": dict(sorted(listings.items())),
        "recipes_active": get("craftsman", "Recipe").objects.filter(is_active=True).count(),
        "materials": get("buyman", "Material").objects.count(),
        "suppliers": get("buyman", "Supplier").objects.count(),
        "channels_active": sorted(get("shop", "Channel").objects.filter(is_active=True).values_list("ref", flat=True)),
        "rules_active": get("shop", "RuleConfig").objects.filter(enabled=True).count(),
        "promotions_active": sorted(get("shop", "Promotion").objects.filter(is_active=True).values_list("name", flat=True)),
        "coupons_active": sorted(get("shop", "Coupon").objects.filter(is_active=True).values_list("code", flat=True)),
        "stock_quants": get("stockman", "Quant").objects.count(),
        "customers": get("guestman", "Customer").objects.count(),
        "orders": get("orderman", "Order").objects.count(),
        "accounts": operators,
    }


def _count_all(models: dict[str, type[Model]]) -> dict[str, int]:
    return {label: model._base_manager.count() for label, model in sorted(models.items())}


def run(*, apply: bool, using: str = "default") -> Report:
    """Executa a limpeza numa transação; sem ``apply``, desfaz no fim."""
    models = check_policy()
    connection = connections[using]
    report = Report(applied=apply, database=str(connection.settings_dict.get("NAME")))

    with transaction.atomic(using=using):
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = '15s'")
        report.before = _count_all(models)

        # 1. Linhas mistas: decide quem sai ANTES de apagar a tabela que as liga
        #    (a conta de cliente é reconhecida pelo vínculo do doorman).
        partial = {
            label: list(POLICY[label].rows().values_list("pk", flat=True))
            for label in sorted(models)
            if POLICY[label].action == PURGE_ROWS
        }

        # 2. Cadastro que guarda ponteiro para dado do ensaio.
        for label in sorted(models):
            rule = POLICY[label]
            for field_name in rule.detach:
                n = models[label]._base_manager.exclude(**{f"{field_name}__isnull": True}).update(
                    **{field_name: None}
                )
                if n:
                    report.detached[f"{label}.{field_name}"] = n

        # 3. Tabelas inteiras do ensaio: DELETE cru, sem passar pelo delete() que as tranca.
        purge = [label for label in models if POLICY[label].action == PURGE]
        with connection.cursor() as cursor:
            for label in _delete_order(purge, models):
                cursor.execute(f"DELETE FROM {connection.ops.quote_name(models[label]._meta.db_table)}")

        # 4. Linhas mistas, pelo ORM (cascata do próprio Django, sinais incluídos).
        for label, pks in partial.items():
            if not pks:
                continue
            _total, per_model = models[label]._base_manager.filter(pk__in=pks).delete()
            for other, n in per_model.items():
                if other != label and POLICY.get(other, Rule(KEEP, "")).action == KEEP and n:
                    report.cascade[other] = report.cascade.get(other, 0) + n

        connection.check_constraints()
        report.after = _count_all(models)

        broken = []
        for label, rule, before, after in report.rows():
            if rule.action == KEEP and after != before - report.cascade.get(label, 0):
                broken.append(f"{label}: {before} → {after}")
            if rule.action == PURGE and after:
                broken.append(f"{label}: sobraram {after}")
        if broken:
            raise PurgeAborted("cadastro mudou fora do previsto; nada foi gravado:\n" + "\n".join(broken))

        report.portrait = day_one_portrait()
        if not apply:
            transaction.set_rollback(True, using=using)
    return report
