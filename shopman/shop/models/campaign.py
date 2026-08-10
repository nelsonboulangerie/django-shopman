"""Campanha — a intenção, o modelo e o anúncio.

A operação real da padaria É o marketing: cada fornada, cada estoque baixo é
uma oportunidade de conversão. Estes três models são o engine que transforma
evento operacional em conteúdo.

- ``Campaign``  — que evento vira o quê, para quem, em quais plataformas
- ``AnnouncementTemplate``   — o conteúdo, com variáveis resolvidas em runtime
- ``Announcement``  — o registro de um announcement gerado (pendente → publicado)

O operador de produção não publica: ele marca a qualidade da fornada
(``WorkOrder.meta["quality"]``) e o gestor decide. Separação de papéis
deliberada (FOMO-MARKETING-SPECS §8).
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Trigger(models.TextChoices):
    """Eventos operacionais que podem gerar campanha."""

    PRODUCTION_FINISHED = "production_finished", "fornada concluída"
    LOW_STOCK = "low_stock", "estoque baixo"
    STOCK_BACK = "stock_back", "voltou ao estoque"
    PRODUCT_CREATED = "product_created", "produto novo"
    #: O gestor decide agora, para quem ele escolher. Substitui o `scheduled`, que era
    #: escolha morta — `evaluate()` só era chamado por handler de evento, então nada
    #: nunca produziu uma campanha `scheduled`. Este tem produtor real: uma Action na
    #: superfície de Marketing.
    MANUAL = "manual", "disparo manual"
    #: O RELÓGIO é o evento: não há fornada por trás. Produtor real é a vassoura, que
    #: **arma** uma Directive no instante exato — quem dispara é a fila
    #: (`process_directives --watch`), com latência de segundos em vez dos até 5 minutos
    #: do ciclo de manutenção. Só este gatilho aceita `schedule` do tipo
    #: `once`/`recurring`.
    SCHEDULE = "schedule", "agendado"


class AnnouncementStatus(models.TextChoices):
    """Ciclo de vida de um announcement."""

    DRAFT = "draft", "rascunho"
    PENDING_REVIEW = "pending_review", "aguardando aprovação"
    APPROVED = "approved", "aprovado"
    PUBLISHING = "publishing", "publicando"
    PUBLISHED = "published", "publicado"
    FAILED = "failed", "falhou"
    EXPIRED = "expired", "expirado"


#: Hierarquia da flag de qualidade da fornada. Índice maior = melhor.
QUALITY_LEVELS = ("regular", "bom", "excelente")


class AnnouncementTemplate(models.Model):
    """Template de conteúdo, com variáveis resolvidas em runtime.

    O corpo usa ``{{variavel}}``. As disponíveis dependem do trigger; ver
    ``shopman.shop.services.campaign.available_variables``.
    """

    class ImageSource(models.TextChoices):
        PRODUCT = "product", "foto do produto"
        GALLERY = "gallery", "galeria do produto"
        CUSTOM = "custom", "imagem fixa"
        NONE = "none", "sem imagem"

    name = models.CharField("nome", max_length=100)
    body = models.TextField(
        "corpo",
        help_text="Use {{product_name}}, {{price}}, {{hashtags}}, {{link}}, {{store_name}}…",
    )
    platform_variants = models.JSONField(
        "variações por plataforma", default=dict, blank=True,
        help_text='Override por plataforma, ex: {"google_business": {"body": "…"}}',
    )
    variables = models.JSONField(
        "variáveis", default=list, blank=True,
        help_text="Variáveis que este template espera (documentação para o gestor)",
    )
    use_ai_generation = models.BooleanField(
        "gerar texto com IA", default=False,
        help_text="Quando ligado, a IA escreve a partir do contexto do evento",
    )
    ai_prompt = models.TextField("instrução para a IA", blank=True)
    image_source = models.CharField(
        "origem da imagem", max_length=16,
        choices=ImageSource.choices, default=ImageSource.PRODUCT,
    )
    is_active = models.BooleanField("ativo", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "modelo de anúncio"
        verbose_name_plural = "modelos de anúncio"

    def __str__(self) -> str:  # pragma: no cover - admin/debug only
        return self.name

    def body_for(self, platform: str) -> str:
        """Corpo específico da plataforma, com fallback para o corpo padrão."""
        variant = (self.platform_variants or {}).get(platform) or {}
        return variant.get("body") or self.body


class Campaign(models.Model):
    """Liga um evento operacional a uma ação de campanha."""

    name = models.CharField("nome", max_length=100)
    trigger = models.CharField("gatilho", max_length=64, choices=Trigger.choices)
    trigger_filter = models.JSONField(
        "filtro do gatilho", default=dict, blank=True,
        help_text='Condições extras, ex: {"collections": ["paes"], "quality_min": "bom"}',
    )
    template = models.ForeignKey(
        AnnouncementTemplate, on_delete=models.PROTECT,
        related_name="rules", verbose_name="modelo",
    )
    platforms = models.JSONField(
        "plataformas", default=list,
        help_text='["instagram", "google_business", "facebook", "whatsapp", "tv"]',
    )
    #: Vocabulário FECHADO e PLANO. Sem AND/OR aninhado, sem construtor de segmento
    #: arbitrário: no dia em que alguém precisar de árvore booleana, o que está sendo
    #: construído é um CDP, e a resposta é não. As chaves são lidas em
    #: `services/audience.py::resolve`.
    audience_rules = models.JSONField(
        "regras de audiência", default=dict, blank=True,
        help_text=(
            'Por evento (exigem SKU): {"favorites": true, "alerts": true, '
            '"bought_within_days": 90}. '
            'Escolhidos pelo gestor: {"customer_refs": [], "groups": [], '
            '"rfm_segments": ["champion"], "churn_risk_min": 0.7, '
            '"bought_skus": [], "bought_collections": [], "birthday_today": true}. '
            'Entrega: {"vip_first_minutes": 15, "preferred_hour_window_hours": 4}.'
        ),
    )
    #: Dois papéis diferentes no mesmo campo, e a diferença importa: `immediate` e
    #: `preferred_hours` **adiam** um anúncio que um evento já criou; `once` e
    #: `recurring` **criam** a ocasião sozinhos, e só valem com `trigger=schedule`.
    #: Ver `services/campaign_schedule.py`.
    schedule = models.JSONField(
        "agendamento", default=dict, blank=True,
        help_text=(
            'Adiar o que o evento criou: {"type": "immediate"} ou '
            '{"type": "preferred_hours", "windows": [["07:00", "11:00"]]}. '
            'Disparar sozinho (exige gatilho "agendado"): '
            '{"type": "once", "at": "2026-08-15T17:30:00-03:00"} ou '
            '{"type": "recurring", "windows": [["17:30", "18:30"]], '
            '"weekdays": [4, 5], "starts_on": "2026-08-15", "ends_on": "2026-12-31"}.'
        ),
    )
    requires_approval = models.BooleanField(
        "exige aprovação", default=True,
        help_text="Desligado = publica sozinho, sem o gestor revisar",
    )
    expires_after_minutes = models.PositiveIntegerField(
        "expira em (min)", default=0,
        help_text="Anúncio não aprovado caduca depois disso. 0 = não expira. "
                  "Frescor é efêmero: fornada merece prazo curto.",
    )
    notify_users = models.JSONField(
        "avisar usuários", default=list, blank=True,
        help_text="IDs de usuário a notificar. Vazio = todos com a permissão "
                  "de gerenciar campanhas.",
    )
    is_active = models.BooleanField("ativa", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "campanha"
        verbose_name_plural = "campanhas"
        indexes = [models.Index(fields=["trigger", "is_active"])]
        permissions = [
            ("manage_campaigns", "Pode revisar e publicar campanhas"),
        ]

    def clean(self) -> None:
        """Recusa o par impossível entre gatilho e agendamento.

        Sem isto, os dois erros abaixo salvam limpos e a campanha aparece **ativa** na
        lista sem nunca produzir anúncio. Silêncio é o pior resultado possível aqui: o
        gestor não tem como distinguir "não disparou ainda" de "não vai disparar nunca".
        """
        from shopman.shop.services import campaign_schedule as sched

        fires = sched.fires_on_its_own(self.schedule)
        if self.trigger == Trigger.SCHEDULE and not fires:
            raise ValidationError({
                "schedule": (
                    "O gatilho é 'agendado', então o agendamento precisa ser do tipo "
                    "'once' ou 'recurring' — os outros só adiam um anúncio que um "
                    "evento já criou, e aqui não há evento."
                ),
            })
        if fires and self.trigger != Trigger.SCHEDULE:
            raise ValidationError({
                "trigger": (
                    "Este agendamento dispara sozinho, então o gatilho tem de ser "
                    "'agendado'. Com um gatilho de evento, o agendamento seria "
                    "ignorado e o anúncio sairia na hora do evento."
                ),
            })
        if fires and sched.next_occurrence(self.schedule) is None:
            raise ValidationError({
                "schedule": (
                    "Este agendamento não tem nenhuma próxima ocasião — a data já "
                    "passou, o período terminou, ou a configuração está incompleta."
                ),
            })

    def __str__(self) -> str:  # pragma: no cover - admin/debug only
        status = "✓" if self.is_active else "✗"
        return f"[{status}] {self.name}"


class Announcement(models.Model):
    """Um announcement gerado: pendente, aprovado, publicado ou caduco."""

    rule = models.ForeignKey(
        Campaign, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="announcements", verbose_name="regra",
    )
    template = models.ForeignKey(
        AnnouncementTemplate, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="announcements", verbose_name="modelo",
    )
    #: A ocasião que gerou este anúncio, quando ele nasceu do relógio. Existe para o
    #: unique parcial abaixo: sem ela, a vassoura rodando duas vezes (ou dois workers)
    #: criaria dois anúncios para a mesma janela, e o cliente receberia em dobro.
    #:
    #: Vazio para anúncio de evento — fornada não tem "ocasião agendada", e é por isso
    #: que o unique é PARCIAL.
    occurrence_key = models.CharField(
        "ocasião", max_length=120, blank=True, default="", db_index=True,
        help_text="Identidade da ocasião agendada (campanha + instante). Vazio = nasceu de evento.",
    )
    status = models.CharField(
        "situação", max_length=16,
        choices=AnnouncementStatus.choices, default=AnnouncementStatus.DRAFT,
    )
    content = models.JSONField(
        "conteúdo", default=dict,
        help_text='{"body": "…", "image_url": "…", "hashtags": [...], "link": "…"}',
    )
    platform_content = models.JSONField("conteúdo por plataforma", default=dict, blank=True)
    platforms = models.JSONField("plataformas", default=list, blank=True)
    audience = models.JSONField(
        "audiência", default=dict, blank=True,
        help_text="Só contagens — a lista de destinatários nunca é persistida aqui",
    )
    platform_results = models.JSONField("resultado por plataforma", default=dict, blank=True)
    trigger_context = models.JSONField("contexto do evento", default=dict, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="approved_announcements",
        verbose_name="aprovado por",
    )
    approved_at = models.DateTimeField("aprovado em", null=True, blank=True)
    publish_at = models.DateTimeField(
        "publicar em", null=True, blank=True,
        help_text="Aprovado com hora marcada. Preenchido = ainda não saiu; "
                  "volta a vazio no despacho.",
    )
    published_at = models.DateTimeField("publicado em", null=True, blank=True)
    expires_at = models.DateTimeField("expira em", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "anúncio"
        verbose_name_plural = "anúncios"
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["expires_at"]),
            models.Index(fields=["publish_at"]),
        ]
        constraints = [
            # Parcial: vale só onde há ocasião. Anúncio de evento (fornada) tem
            # `occurrence_key` vazio e pode repetir à vontade — duas fornadas do mesmo
            # pão no mesmo dia são dois anúncios legítimos. Já a mesma OCASIÃO agendada
            # não pode gerar dois, senão a vassoura rodando duas vezes (ou dois workers
            # concorrendo) manda a mensagem em dobro. O banco decide, não o código.
            models.UniqueConstraint(
                fields=["occurrence_key"],
                condition=models.Q(occurrence_key__gt=""),
                name="shop_announcement_occurrence_uq",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin/debug only
        return f"[{self.get_status_display()}] {self.body[:40] or self.pk}"

    @property
    def body(self) -> str:
        return (self.content or {}).get("body", "")

    @property
    def is_awaiting_review(self) -> bool:
        return self.status == AnnouncementStatus.PENDING_REVIEW

    def is_expired(self, *, now=None) -> bool:
        """Caducou sem ninguém aprovar. Anúncio vencido não vira propaganda velha."""
        if self.expires_at is None or self.status != AnnouncementStatus.PENDING_REVIEW:
            return False
        from django.utils import timezone

        return self.expires_at <= (now or timezone.now())
