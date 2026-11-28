"""Canonical Unfold CRUD for public frequently asked questions."""

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.shop.concierge_verification import date_warning, origin_of
from shopman.shop.models import FAQEntry
from shopman.shop.models.faq import normalized_question

#: O rótulo da lista quando a curada repete uma pergunta que a loja responde pela
#: configuração: ela não aparece no site (OC-31).
REPEATS_CONFIGURATION = "Repete a configuração"


class OriginFilter(admin.SimpleListFilter):
    """De onde veio a pergunta: de uma conversa da Concierge (WP-15) ou do Admin."""

    title = "origem"
    parameter_name = "origem"

    def lookups(self, request, model_admin):
        return (("concierge", "Conversa da Concierge"), ("admin", "Cadastrada no Admin"))

    def queryset(self, request, queryset):
        from shopman.shop.concierge_verification import FAQ_REF_PREFIX

        if self.value() == "concierge":
            return queryset.filter(ref__startswith=FAQ_REF_PREFIX)
        if self.value() == "admin":
            return queryset.exclude(ref__startswith=FAQ_REF_PREFIX)
        return queryset


@admin.register(FAQEntry)
class FAQEntryAdmin(ModelAdmin):
    list_display = ("question", "repeats_label", "position", "is_published", "origin_label", "updated_at")
    list_editable = ("position", "is_published")
    list_filter = ("is_published", OriginFilter)
    search_fields = ("question", "answer", "search_terms")
    ordering = ("position", "id")
    readonly_fields = ("repetition", "origin", "date_warning", "ref", "created_at", "updated_at")
    fieldsets = (
        (
            None,
            {
                "fields": ("question", "repetition", "answer", "search_terms"),
                "description": (
                    "Esta resposta é pública: aparece no site e pode ser consultada pela Concierge. "
                    "Preço, estoque, taxa, cobertura e horários operacionais continuam vindo das projeções da loja."
                ),
            },
        ),
        # WP-15: o rascunho que nasceu de uma pergunta respondida pela equipe diz de onde veio.
        ("De onde veio", {"fields": ("origin", "date_warning")}),
        ("Publicação", {"fields": ("is_published", "position", "ref", "created_at", "updated_at")}),
    )

    @display(description="no site", label={REPEATS_CONFIGURATION: "warning"})
    def repeats_label(self, obj: FAQEntry) -> str:
        return REPEATS_CONFIGURATION if obj.repeated_operational_question else ""

    @display(description="repetição")
    def repetition(self, obj: FAQEntry) -> str:
        """Por que esta pergunta não aparece no site, quando ela repete outra (OC-31)."""
        if obj is None or not obj.question:
            return "Não repete outra pergunta."
        operational = obj.repeated_operational_question
        if operational:
            return (
                f"Repete “{operational}”, que a loja já responde pela configuração. O site mostra "
                "só a resposta da configuração, e esta fica de fora. Se o assunto é outro, "
                "reescreva a pergunta."
            )
        # Entre curadas com a mesma pergunta, o site mostra a primeira pela posição.
        key = normalized_question(obj.question)
        order = (obj.position, obj.pk or float("inf"))
        first = min(
            (
                other
                for other in FAQEntry.objects.filter(is_published=True).exclude(pk=obj.pk).only("question", "position")
                if normalized_question(other.question) == key and (other.position, other.pk) < order
            ),
            key=lambda other: (other.position, other.pk),
            default=None,
        )
        if first is not None:
            return (
                f"Repete “{first.question}”, outra pergunta publicada que vem antes na ordem. "
                "O site mostra só a primeira."
            )
        return "Não repete outra pergunta."

    @display(description="origem")
    def origin_label(self, obj: FAQEntry) -> str:
        return "Conversa da Concierge" if origin_of(obj.ref) else "Cadastrada no Admin"

    @display(description="de onde veio")
    def origin(self, obj: FAQEntry):
        found = origin_of(obj.ref) if obj and obj.pk else None
        if found is None:
            return "Cadastrada no Admin."
        conversation_pk, _record = found
        url = reverse("admin:shop_conversation_change", args=[conversation_pk])
        return format_html(
            'Promovida de uma pergunta que a equipe respondeu na <a href="{}">conversa #{}</a>.',
            url,
            conversation_pk,
        )

    @display(description="aviso")
    def date_warning(self, obj: FAQEntry) -> str:
        return (date_warning(obj.answer) if obj else "") or "Nenhum."
