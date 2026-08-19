"""
Guestman Admin with Unfold theme.

This module provides Unfold-styled admin classes for Guestman models.
To use, add 'shopman.guestman.contrib.admin_unfold' to INSTALLED_APPS after 'customers'.

The admins will automatically unregister the basic admins and register
the Unfold versions.
"""
from __future__ import annotations

import csv

from django import forms
from django.apps import apps
from django.contrib import admin, messages
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from shopman.guestman.models import (
    ContactPoint,
    Customer,
    CustomerAddress,
    ExternalIdentity,
    PriceTier,
)
from shopman.utils import unfold_link
from shopman.utils.contrib.admin_unfold.badges import unfold_badge, unfold_badge_numeric
from shopman.utils.contrib.admin_unfold.base import BaseModelAdmin, BaseTabularInline
from taggit.managers import TaggableManager
from unfold.contrib.filters.admin.dropdown_filters import ChoicesDropdownFilter
from unfold.decorators import display
from unfold.widgets import UnfoldAdminRadioSelectWidget, UnfoldAdminTextInputWidget

# Unregister basic admins
for model in [Customer, PriceTier, CustomerAddress, ContactPoint, ExternalIdentity]:
    try:
        admin.site.unregister(model)
    except admin.sites.NotRegistered:
        pass


# =============================================================================
# ETIQUETAS EM MASSA
# =============================================================================


def _existing_tag_names() -> list[str]:
    """As etiquetas que já existem, para o operador reusar em vez de reinventar.

    ⚠️ Sem esta lista nascem "corredores", "Corredores" e "corredor" como três etiquetas
    diferentes — e aí o público por etiqueta alcança um terço de quem devia. O taggit
    deduplica por slug, o que resolve maiúscula e acento, mas não resolve sinônimo.
    """
    from shopman.guestman.models import CustomerTag

    return list(CustomerTag.objects.order_by("name").values_list("name", flat=True))


class TagCustomersForm(forms.Form):
    """Etiquetas a pôr ou tirar. Texto livre, separado por vírgula."""

    tags = forms.CharField(
        label=_("Etiquetas"),
        widget=UnfoldAdminTextInputWidget(
            attrs={"placeholder": _("corredores, sem glúten, vizinho")}
        ),
        help_text=_("Separe por vírgula. Etiqueta nova é criada na hora."),
    )
    mode = forms.ChoiceField(
        label=_("O que fazer"),
        choices=[("add", _("Pôr estas etiquetas")), ("remove", _("Tirar estas etiquetas"))],
        initial="add",
        widget=UnfoldAdminRadioSelectWidget,
    )

    def clean_tags(self) -> list[str]:
        """"a, b" → ["a", "b"], sem vazios e sem repetição.

        Não uso o `parse_tags` do taggit aqui de propósito: ele quebra em ESPAÇO quando não
        há vírgula, e "sem glúten" viraria duas etiquetas ("sem" e "glúten"). O separador
        desta tela é a vírgula, e é isso que o placeholder mostra.
        """
        raw = self.cleaned_data["tags"]
        names: list[str] = []
        for piece in raw.split(","):
            name = piece.strip()
            if name and name not in names:
                names.append(name)
        if not names:
            raise forms.ValidationError(_("Escreva ao menos uma etiqueta."))
        return names


# =============================================================================
# CUSTOM FILTERS
# =============================================================================


def _rfm_segment_labels() -> dict[str, str]:
    """Rótulos PT-BR dos segmentos (o valor cru vem em inglês da insight).

    O dono é ``RFM_SEGMENTS``: filtro e coluna leem dele, para o operador nunca ver
    "At Risk"/"Lost" nem um rótulo diferente do que a campanha mostra. Import tardio
    porque ``contrib.insights`` é opcional — sem ele, não há segmento para rotular.
    """
    try:
        from shopman.guestman.contrib.insights.models import RFM_SEGMENTS
    except (ImportError, RuntimeError):
        return {}
    return dict(RFM_SEGMENTS)


class RFMSegmentFilter(admin.SimpleListFilter):
    """Filter customers by RFM segment (via CustomerInsight)."""
    title = _("Segmento")
    parameter_name = "rfm_segment"

    def lookups(self, request, model_admin):
        return list(_rfm_segment_labels().items())

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        try:
            from shopman.guestman.contrib.insights.models import CustomerInsight
            customer_ids = CustomerInsight.objects.filter(
                rfm_segment=value
            ).values_list("customer_id", flat=True)
            return queryset.filter(pk__in=customer_ids)
        except ImportError:
            return queryset


# =============================================================================
# CUSTOMER GROUP ADMIN
# =============================================================================


@admin.register(PriceTier)
class PriceTierAdmin(BaseModelAdmin):
    list_display = [
        "ref",
        "name",
        "listing_ref",
        "priority",
        "is_default_badge",
        "customer_count",
    ]
    list_filter = ["is_default"]
    search_fields = ["ref", "name"]
    ordering = ["-priority", "name"]

    def get_queryset(self, request):
        # Anota a contagem num único JOIN em vez de uma query por linha (N+1).
        from django.db.models import Count

        return super().get_queryset(request).annotate(_customer_count=Count("customers"))

    @display(description="Padrão", boolean=True)
    def is_default_badge(self, obj):
        return obj.is_default

    @display(description="Clientes", ordering="_customer_count")
    def customer_count(self, obj):
        return getattr(obj, "_customer_count", obj.customers.count())


# =============================================================================
# CUSTOMER ADMIN
# =============================================================================


class CustomerAddressInline(BaseTabularInline):
    model = CustomerAddress
    extra = 0
    fields = ["label", "formatted_address", "is_default", "is_verified"]
    readonly_fields = ["is_verified"]


class ContactPointInline(BaseTabularInline):
    """Telefones e e-mails do cliente, no cliente.

    Contato só faz sentido junto de quem ele contata: uma lista global de
    telefones não responde nenhuma pergunta que alguém realmente faça. O estado
    de verificação é lavrado pelo fluxo de verificação (OTP, link), nunca
    digitado aqui.
    """

    model = ContactPoint
    extra = 0
    fields = ["type", "value_display", "is_primary", "is_verified", "verified_at"]
    readonly_fields = ["is_verified", "verified_at"]
    verbose_name = _("contato")
    verbose_name_plural = _("contatos")


class CommunicationConsentInline(BaseTabularInline):
    """Consentimento de comunicação por canal — registro de LGPD, somente leitura.

    Quem concede e quem revoga é o cliente, pelas superfícies dele. O Admin
    mostra para que a loja consiga responder "posso mandar mensagem para esta
    pessoa?" sem sair da ficha dela.
    """

    extra = 0
    can_delete = False
    verbose_name = _("consentimento")
    verbose_name_plural = _("consentimentos de comunicação")
    fields = ["channel", "status", "legal_basis", "source", "consented_at", "revoked_at"]
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


class CustomerForm(forms.ModelForm):
    """O form do cliente com a conta na casa como checkbox, não como JSON.

    A elegibilidade mora em ``Customer.metadata.house_account`` (dado contextual,
    schema em docs/reference/data-schemas.md), desligada por padrão; só o Admin
    liga. Pedir ao dono que edite JSON para isso seria fazê-lo trabalhar para a
    tela; o campo lê e escreve a chave preservando o resto do ``metadata``.
    """

    house_account = forms.BooleanField(
        label=_("Conta na casa"),
        required=False,
        help_text=_("O cliente pode comprar \"em conta\" no PDV e acertar por período. Não se divulga; é por cliente."),
    )

    class Meta:
        model = Customer
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = kwargs.get("instance")
        if instance is not None:
            self.fields["house_account"].initial = bool((instance.metadata or {}).get("house_account"))

    def save(self, commit=True):
        customer = super().save(commit=False)
        metadata = dict(customer.metadata or {})
        if self.cleaned_data.get("house_account"):
            metadata["house_account"] = True
        else:
            metadata.pop("house_account", None)
        customer.metadata = metadata
        if commit:
            customer.save()
            self.save_m2m()
        return customer


@admin.register(Customer)
class CustomerAdmin(BaseModelAdmin):
    form = CustomerForm
    # O campo de etiquetas vem do taggit, cujo widget é um campo de texto cru:
    # dentro de um form Unfold ele aparecia com a borda do Django antigo. O taggit
    # continua dono do PARSE (vírgula, aspas, etiqueta nova na hora); troca só o
    # desenho.
    formfield_overrides = {
        TaggableManager: {"widget": UnfoldAdminTextInputWidget},
    }

    list_display = [
        "customer_header",
        "customer_type_badge",
        "price_tier",
        "tag_list",
        "orders_count",
        "rfm_segment_badge",
        "churn_risk_badge",
        "is_active_badge",
    ]
    list_display_links = ["customer_header"]
    list_filter = [
        "customer_type",
        ("price_tier", ChoicesDropdownFilter),
        "tags",
        "is_active",
        RFMSegmentFilter,
    ]
    list_filter_submit = True
    date_hierarchy = "created_at"
    search_fields = ["ref", "first_name", "last_name", "document", "phone", "email"]
    readonly_fields = ["uuid", "created_at", "updated_at"]

    def get_inlines(self, request, obj=None):
        """Endereços, contatos e — se o contrib de consentimento estiver instalado
        neste deployment — o registro de LGPD.

        O consentimento é opcional (``guestman.contrib.consent``), então o inline
        se monta em tempo de request: um pacote genérico não pode assumir que
        quem o instalou também instalou o contrib.
        """
        inlines = [CustomerAddressInline, ContactPointInline]

        try:
            consent_model = apps.get_model("customer_consent", "CommunicationConsent")
        except LookupError:
            return inlines

        inlines.append(
            type(
                "BoundCommunicationConsentInline",
                (CommunicationConsentInline,),
                {"model": consent_model, "__module__": __name__},
            )
        )
        return inlines

    fieldsets = [
        (
            "Identificação",
            {
                "fields": [
                    "ref",
                    "uuid",
                    "first_name",
                    "last_name",
                    "customer_type",
                    "document",
                ]
            },
        ),
        ("Contato", {"fields": ["email", "phone"]}),
        ("Segmentação", {"fields": ["price_tier", "tags", "house_account", "notes"]}),
        (
            "Sistema",
            {
                "fields": [
                    "is_active",
                    "metadata",
                    "created_at",
                    "updated_at",
                    "created_by",
                    "source_system",
                ],
                "classes": ["collapse"],
            },
        ),
    ]

    actions = ["tag_selected", "export_selected_csv", "recalculate_insights"]

    @display(description="Cliente", header=True)
    def customer_header(self, obj):
        # Célula de duas linhas do Unfold: nome em destaque, telefone abaixo, com
        # as iniciais no avatar. Substitui as colunas soltas ref/nome/telefone.
        initials = "".join(p[0] for p in obj.name.split()[:2]).upper() or "?"
        return [obj.name, obj.phone or obj.ref, initials]

    @display(description="Tipo")
    def customer_type_badge(self, obj):
        colors = {
            "individual": "blue",
            "business": "green",
        }
        color = colors.get(obj.customer_type, "base")
        return unfold_badge(obj.get_customer_type_display(), color)

    @display(description="Ativo", boolean=True)
    def is_active_badge(self, obj):
        return obj.is_active

    @display(description=_("Etiquetas"))
    def tag_list(self, obj):
        """As etiquetas do cliente, em texto. Sem etiqueta é "—", não vazio."""
        names = [tag.name for tag in obj.tags.all()]
        return ", ".join(names) if names else "—"

    @display(description="Pedidos")
    def orders_count(self, obj):
        """Show order count using Orderman's public customer-history contract."""
        try:
            from shopman.orderman.services import CustomerOrderHistoryService

            count = CustomerOrderHistoryService.get_customer_stats(obj.ref).total_orders
            if count == 0:
                return "—"
            return unfold_badge_numeric(str(count), "base")
        except ImportError:
            return "—"

    def get_queryset(self, request):
        # ⚠️ `prefetch_related("tags")` não é enfeite: a coluna de etiquetas faria uma
        # query POR LINHA da lista (N+1) — 50 clientes, 50 idas ao banco.
        qs = super().get_queryset(request).prefetch_related("tags")
        try:
            from django.db.models import OuterRef, Subquery
            from shopman.guestman.contrib.insights.models import CustomerInsight
            insight_qs = CustomerInsight.objects.filter(customer=OuterRef("pk"))
            qs = qs.annotate(
                _rfm_segment=Subquery(insight_qs.values("rfm_segment")[:1]),
                _churn_risk=Subquery(insight_qs.values("churn_risk")[:1]),
            )
        except ImportError:
            pass
        return qs

    @display(description=_("Segmento"))
    def rfm_segment_badge(self, obj):
        """Display RFM segment badge from CustomerInsight."""
        segment = getattr(obj, "_rfm_segment", None)
        if not segment:
            return "—"
        segment_colors = {
            "champion": "green",
            "loyal_customer": "blue",
            "recent_customer": "blue",
            "at_risk": "yellow",
            "lost": "red",
            "regular": "base",
        }
        color = segment_colors.get(segment, "base")
        # Rótulo PT-BR (nunca "At Risk"/"Lost" na cara do operador).
        label = _rfm_segment_labels().get(segment, segment.replace("_", " ").capitalize())
        return unfold_badge(label, color)

    @display(description=_("Risco de perda"))
    def churn_risk_badge(self, obj):
        """Display churn risk badge from CustomerInsight."""
        churn_risk = getattr(obj, "_churn_risk", None)
        if churn_risk is None:
            return "-"
        risk = float(churn_risk)
        pct = f"{risk * 100:.0f}%"
        if risk >= 0.7:
            return unfold_badge(pct, "red")
        elif risk >= 0.4:
            return unfold_badge(pct, "yellow")
        else:
            return unfold_badge(pct, "green")

    @admin.action(description=_("Etiquetar selecionados…"))
    def tag_selected(self, request, queryset):
        """Página intermediária para pôr ou tirar etiquetas de vários clientes.

        ⚠️ Existe porque etiquetar um por um não escala: o público por etiqueta só vale a
        pena quando dá para marcar trinta corredores de uma vez. Sem isto, o recurso nasce
        com um custo de uso que ninguém paga, e a etiqueta fica vazia — que é justamente o
        estado que a contagem no seletor do Marketing denuncia.

        Segue o padrão da casa (`refs`: `rename_value_action`): ação → `TemplateResponse`
        com form Unfold → confirmação. Sem overlay novo, que o gate proíbe.
        """
        # ⚠️ Vincular ao POST da SELEÇÃO faria o form abrir já em vermelho ("este campo é
        # obrigatório"), porque o POST que traz os checkboxes não traz as etiquetas. Ralhar
        # com quem ainda não digitou nada ensina a ignorar o vermelho.
        confirming = bool(request.POST.get("_tag_confirm"))
        form = TagCustomersForm(request.POST if confirming else None)
        if confirming:
            if form.is_valid():
                from shopman.guestman.models import CustomerTag

                # `resolve` casa por SLUG: "sem glúten" reusa a etiqueta "sem gluten" em vez
                # de criar uma segunda com o mesmo sentido (ver `models/tag.py`).
                tags = CustomerTag.resolve(form.cleaned_data["tags"])
                removing = form.cleaned_data["mode"] == "remove"
                for customer in queryset:
                    if removing:
                        customer.tags.remove(*tags)
                    else:
                        customer.tags.add(*tags)

                names = ", ".join(tag.name for tag in tags)
                self.message_user(
                    request,
                    (
                        _("Etiquetas retiradas de {count} cliente(s): {tags}.")
                        if removing
                        else _("{count} cliente(s) etiquetado(s) com: {tags}.")
                    ).format(count=queryset.count(), tags=names),
                )
                return None
            self.message_user(
                request, _("Escreva ao menos uma etiqueta."), messages.ERROR
            )

        return TemplateResponse(
            request,
            "admin/guestman/customer/tag_confirm.html",
            {
                "form": form,
                "queryset": queryset,
                "existing_tags": _existing_tag_names(),
                "action_checkbox_name": admin.helpers.ACTION_CHECKBOX_NAME,
                "opts": self.model._meta,
                "app_label": self.model._meta.app_label,
                "title": _("Etiquetar clientes"),
            },
        )

    @admin.action(description=_("Exportar selecionados (CSV)"))
    def export_selected_csv(self, request, queryset):
        """Export selected customers as CSV."""
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="guestman.csv"'
        writer = csv.writer(response)
        writer.writerow([
            "ref", "first_name", "last_name", "customer_type",
            "email", "phone", "price_tier", "is_active",
        ])
        for customer in queryset.select_related("price_tier"):
            writer.writerow([
                customer.ref,
                customer.first_name,
                customer.last_name,
                customer.customer_type,
                customer.email or "",
                customer.phone or "",
                customer.price_tier.ref if customer.price_tier else "",
                customer.is_active,
            ])
        return response

    @admin.action(description=_("Recalcular insights"))
    def recalculate_insights(self, request, queryset):
        """Recalculate CustomerInsight for selected customers."""
        try:
            from shopman.guestman.contrib.insights.service import InsightService
        except ImportError:
            messages.error(request, _("guestman.contrib.insights não está instalado."))
            return

        recalculated = 0
        errors = 0
        for customer in queryset:
            try:
                InsightService.recalculate(customer.ref)
                recalculated += 1
            except Exception:
                errors += 1

        if recalculated:
            messages.success(
                request,
                _("%(count)d insight(s) recalculado(s).") % {"count": recalculated},
            )
        if errors:
            messages.warning(
                request,
                _("%(count)d erro(s) ao recalcular.") % {"count": errors},
            )


# =============================================================================
# CUSTOMER ADDRESS ADMIN
# =============================================================================


@admin.register(CustomerAddress)
class CustomerAddressAdmin(BaseModelAdmin):
    list_display = [
        "customer",
        "label_badge",
        "formatted_address",
        "is_default_badge",
        "is_verified_badge",
    ]
    list_filter = ["label", "is_default", "is_verified"]
    search_fields = ["customer__ref", "customer__first_name", "formatted_address"]
    raw_id_fields = ["customer"]

    @display(description="Rótulo")
    def label_badge(self, obj):
        colors = {
            "home": "green",
            "work": "blue",
            "other": "base",
        }
        color = colors.get(obj.label, "base")
        return unfold_badge(obj.get_label_display(), color)

    @display(description="Padrão", boolean=True)
    def is_default_badge(self, obj):
        return obj.is_default

    @display(description="Verificado", boolean=True)
    def is_verified_badge(self, obj):
        return obj.is_verified


# =============================================================================
# CONTACT POINT ADMIN
# =============================================================================


@admin.register(ContactPoint)
class ContactPointAdmin(BaseModelAdmin):
    list_display = [
        "value_masked",
        "type",
        "customer_link",
        "is_primary",
        "is_verified_badge",
        "created_at",
    ]
    list_filter = ["type", "is_primary", "is_verified", "verification_method"]
    search_fields = ["value_normalized", "customer__ref", "customer__first_name"]
    raw_id_fields = ["customer"]
    readonly_fields = ["id", "verified_at", "created_at", "updated_at"]

    fieldsets = [
        (None, {"fields": ["id", "customer", "type", "value_normalized", "value_display"]}),
        ("Situação", {"fields": ["is_primary", "is_verified"]}),
        (
            "Verificação",
            {"fields": ["verification_method", "verified_at", "verification_ref"]},
        ),
        ("Datas", {"fields": ["created_at", "updated_at"], "classes": ["collapse"]}),
    ]

    @display(description="Valor")
    def value_masked(self, obj):
        return obj.value_masked

    @display(description="Cliente")
    def customer_link(self, obj):
        from django.urls import reverse

        url = reverse("admin:guestman_customer_change", args=[obj.customer.pk])
        return format_html('<a href="{}">{}</a>', url, obj.customer.ref)

    @display(description="Verificado", boolean=True)
    def is_verified_badge(self, obj):
        return obj.is_verified


# =============================================================================
# EXTERNAL IDENTITY ADMIN
# =============================================================================


@admin.register(ExternalIdentity)
class ExternalIdentityAdmin(BaseModelAdmin):
    list_display = [
        "provider",
        "provider_uid_short",
        "customer_link",
        "is_active",
        "created_at",
    ]
    list_filter = ["provider", "is_active"]
    search_fields = ["provider_uid", "customer__ref", "customer__first_name"]
    raw_id_fields = ["customer"]
    readonly_fields = ["id", "created_at", "updated_at"]

    fieldsets = [
        (None, {"fields": ["id", "customer", "provider", "provider_uid"]}),
        ("Situação", {"fields": ["is_active"]}),
        ("Metadados", {"fields": ["provider_meta"], "classes": ["collapse"]}),
        ("Datas", {"fields": ["created_at", "updated_at"], "classes": ["collapse"]}),
    ]

    @display(description="UID do provedor")
    def provider_uid_short(self, obj):
        if len(obj.provider_uid) > 20:
            return obj.provider_uid[:20] + "..."
        return obj.provider_uid

    @display(description="Cliente")
    def customer_link(self, obj):
        from django.urls import reverse

        url = reverse("admin:guestman_customer_change", args=[obj.customer.pk])
        return format_html('<a href="{}">{}</a>', url, obj.customer.ref)


# =============================================================================
# LOYALTY ADMIN (optional contrib — only if guestman.contrib.loyalty installed)
# =============================================================================

try:
    from shopman.guestman.contrib.loyalty.models import (
        LoyaltyAccount,
        LoyaltyTransaction,
    )
except ImportError:
    LoyaltyAccount = None  # type: ignore[assignment,misc]
    LoyaltyTransaction = None  # type: ignore[assignment,misc]


if LoyaltyAccount is not None:
    for _model in (LoyaltyAccount, LoyaltyTransaction):
        try:
            admin.site.unregister(_model)
        except admin.sites.NotRegistered:
            pass

    _TIER_COLORS = {
        "bronze": "orange",
        "silver": "base",
        "gold": "yellow",
        "platinum": "blue",
    }

    class LoyaltyTransactionInline(BaseTabularInline):
        """Histórico imutável de pontos sob uma conta (somente leitura)."""

        model = LoyaltyTransaction
        extra = 0
        fields = ["transaction_type", "points", "balance_after", "description", "reference", "created_at"]
        readonly_fields = fields
        ordering = ["-created_at"]

        def has_add_permission(self, request, obj=None):
            return False

        def has_change_permission(self, request, obj=None):
            return False

        def has_delete_permission(self, request, obj=None):
            return False

    @admin.register(LoyaltyAccount)
    class LoyaltyAccountAdmin(BaseModelAdmin):
        list_display = [
            "customer_link",
            "points_balance",
            "lifetime_points",
            "tier_badge",
            "stamps_progress",
            "is_active_badge",
            "enrolled_at",
        ]
        list_filter = ["tier", "is_active"]
        search_fields = ["customer__ref", "customer__first_name"]
        raw_id_fields = ["customer"]
        readonly_fields = ["enrolled_at", "updated_at"]
        inlines = [LoyaltyTransactionInline]

        @display(description=_("Cliente"))
        def customer_link(self, obj):
            from django.urls import reverse

            url = reverse("admin:guestman_customer_change", args=[obj.customer.pk])
            return unfold_link(url, obj.customer.ref)

        @display(description=_("Nível"))
        def tier_badge(self, obj):
            color = _TIER_COLORS.get(obj.tier, "base")
            return unfold_badge(obj.get_tier_display(), color)

        @display(description=_("Carimbos"))
        def stamps_progress(self, obj):
            return f"{obj.stamps_current}/{obj.stamps_target} ({obj.stamps_progress_percent}%) — {obj.stamps_completed} completas"

        @display(description=_("Ativo"), boolean=True)
        def is_active_badge(self, obj):
            return obj.is_active

    @admin.register(LoyaltyTransaction)
    class LoyaltyTransactionAdmin(BaseModelAdmin):
        list_display = [
            "created_at",
            "customer_ref",
            "type_badge",
            "points_badge",
            "balance_after",
            "description",
        ]
        list_filter = ["transaction_type"]
        search_fields = ["account__customer__ref", "description", "reference"]
        readonly_fields = [
            "account",
            "transaction_type",
            "points",
            "balance_after",
            "description",
            "reference",
            "created_at",
            "created_by",
        ]
        date_hierarchy = "created_at"

        def has_add_permission(self, request):
            return False

        def has_delete_permission(self, request, obj=None):
            return False

        @display(description=_("Cliente"))
        def customer_ref(self, obj):
            return obj.account.customer.ref

        _TYPE_COLORS = {"earn": "green", "redeem": "blue", "adjust": "yellow", "expire": "red"}

        @display(description=_("Tipo"))
        def type_badge(self, obj):
            color = self._TYPE_COLORS.get(obj.transaction_type, "base")
            return unfold_badge(obj.get_transaction_type_display(), color)

        @display(description=_("Pontos"))
        def points_badge(self, obj):
            color = "green" if obj.points > 0 else "red"
            text = f"+{obj.points}" if obj.points > 0 else str(obj.points)
            return unfold_badge(text, color)
