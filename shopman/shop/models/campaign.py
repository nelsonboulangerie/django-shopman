"""Campanha — a intenção, o modelo e o anúncio.

A operação real da padaria É o marketing: cada fornada, cada estoque baixo é
uma oportunidade de conversão. Estes três models são o engine que transforma
evento operacional em conteúdo.

- ``Campaign``  — que evento vira o quê, para quem, em quais plataformas
- ``AnnouncementTemplate``   — o conteúdo, com variáveis resolvidas em runtime
- ``Announcement``  — o registro de um announcement gerado (pendente → publicado)

O operador de produção não publica: ele marca a qualidade da fornada
(derivada das linhas de OUTPUT — ADR-017) e o gestor decide. Separação de papéis
deliberada (FOMO-MARKETING-SPECS §8).
"""

from __future__ import annotations

import hashlib
import json
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class _AppendOnlyMarketingQuerySet(models.QuerySet):
    """Prevent generic bulk APIs from rewriting sealed Marketing evidence."""

    def update(self, **kwargs):
        raise ValidationError("Registros selados de Marketing são imutáveis.")

    def delete(self):
        raise ValidationError("Registros selados de Marketing não podem ser apagados.")


class Trigger(models.TextChoices):
    """Eventos operacionais que podem gerar campanha."""

    PRODUCTION_FINISHED = "production_finished", "Fornada concluída"
    LOW_STOCK = "low_stock", "Estoque baixo"
    STOCK_BACK = "stock_back", "Voltou ao estoque"
    PRODUCT_CREATED = "product_created", "Produto novo"
    #: O gestor decide agora, para quem ele escolher. Substitui o `scheduled`, que era
    #: escolha morta — `evaluate()` só era chamado por handler de evento, então nada
    #: nunca produziu uma campanha `scheduled`. Este tem produtor real: uma Action na
    #: superfície de Marketing.
    MANUAL = "manual", "Disparo manual"
    #: O RELÓGIO é o evento: não há fornada por trás. Produtor real é a vassoura, que
    #: **arma** uma Directive no instante exato — quem dispara é a fila
    #: (`process_directives --watch`), com latência de segundos em vez dos até 5 minutos
    #: do ciclo de manutenção. Só este gatilho aceita `schedule` do tipo
    #: `once`/`recurring`.
    SCHEDULE = "schedule", "Agendado"


class AnnouncementStatus(models.TextChoices):
    """Ciclo de vida de um announcement."""

    DRAFT = "draft", "rascunho"
    PENDING_REVIEW = "pending_review", "aguardando aprovação"
    APPROVED = "approved", "aprovado"
    PUBLISHING = "publishing", "publicando"
    SETTLED = "settled", "execução encerrada"
    PUBLISHED = "published", "publicado"
    FAILED = "failed", "falhou"
    #: ⚠️ Recusa e vencimento são fatos DIFERENTES, e antes os dois colapsavam em
    #: `expired`. Quem recusou tomou uma decisão; quem venceu só perdeu a hora. Sem a
    #: distinção, ninguém consegue responder "quantos anúncios o gestor recusou, e por
    #: quê" — e é essa a pergunta que revela modelo de campanha errado.
    REJECTED = "rejected", "recusado"
    EXPIRED = "expired", "expirado"
    CANCELLED = "cancelled", "cancelado"
    #: Um fato operacional posterior invalidou a mensagem antes de ela sair.
    #: Não é recusa humana nem vencimento: a origem foi substituída por uma
    #: versão mais nova (por exemplo, a correção do QC de uma fornada).
    SUPERSEDED = "superseded", "Substituído"


class AnnouncementDeliveryState(models.TextChoices):
    """Ledger-derived execution truth, separate from the operator decision."""

    NOT_STARTED = "not_started", "não iniciada"
    FANOUT_PENDING = "fanout_pending", "preparando entregas"
    DELIVERING = "delivering", "em andamento"
    SUCCEEDED = "succeeded", "concluída"
    COMPLETED_WITH_FAILURES = "completed_with_failures", "concluída com falhas"
    UNKNOWN = "unknown", "resultado desconhecido"
    CANCELLED = "cancelled", "cancelada"
    EXPIRED = "expired", "expirada"
    LEGACY_UNTRACKED = "legacy_untracked", "legado sem ledger"


# A hierarquia de qualidade não vive mais aqui: era o literal QUALITY_LEVELS,
# triplicado entre este módulo, production.QUALITY_CHOICES e a superfície. A
# fonte única é QualityGrade.rank (catálogo editável — ADR-017).


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
        "variações por plataforma",
        default=dict,
        blank=True,
        help_text='Override por plataforma, ex: {"google_business": {"body": "…"}}',
    )
    variables = models.JSONField(
        "variáveis",
        default=list,
        blank=True,
        help_text="Variáveis que este template espera (documentação para o gestor)",
    )
    use_ai_generation = models.BooleanField(
        "oferecer sugestão de IA",
        default=False,
        help_text=(
            "Quando ligado, oferece uma sugestão separada durante a revisão. "
            "Nunca altera nem publica o anúncio automaticamente."
        ),
    )
    ai_prompt = models.TextField("instrução para a IA", blank=True)
    image_source = models.CharField(
        "origem da imagem",
        max_length=16,
        choices=ImageSource.choices,
        default=ImageSource.PRODUCT,
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

    def clean(self) -> None:
        from shopman.shop.services.marketing_ai import (
            MarketingAIError,
            validate_instruction,
        )

        try:
            self.ai_prompt = validate_instruction(self.ai_prompt)
        except MarketingAIError as exc:
            raise ValidationError({"ai_prompt": exc.detail}) from exc

    def body_for(self, platform: str) -> str:
        """Corpo específico da plataforma, com fallback para o corpo padrão."""
        variant = (self.platform_variants or {}).get(platform) or {}
        return variant.get("body") or self.body


class Campaign(models.Model):
    """Liga um evento operacional a uma ação de campanha."""

    name = models.CharField("nome", max_length=100)
    trigger = models.CharField("gatilho", max_length=64, choices=Trigger.choices)
    trigger_filter = models.JSONField(
        "filtro do gatilho",
        default=dict,
        blank=True,
        help_text='Condições extras, ex: {"collections": ["paes"], "quality_min": "standard"}',
    )
    template = models.ForeignKey(
        AnnouncementTemplate,
        on_delete=models.PROTECT,
        related_name="rules",
        verbose_name="modelo",
    )
    platforms = models.JSONField(
        "plataformas",
        default=list,
        #: ⚠️ `tv` NÃO entra aqui, e a razão é de modelo: a TV mostra a promoção porque a
        #: promoção **vale naquele canal** (`Promotion.channels` incluindo o menuboard),
        #: não porque um anúncio a escolheu como destino. Enquanto ela era plataforma, o
        #: anúncio gravava `published` e empurrava num canal SSE com ZERO consumidores —
        #: o painel dizia "publicado" e nenhuma TV mostrava nada. Ver ADR-020 §10.
        help_text='["instagram", "google_business", "facebook", "whatsapp"]',
    )
    #: Vocabulário FECHADO e PLANO. Sem AND/OR aninhado, sem construtor de segmento
    #: arbitrário: no dia em que alguém precisar de árvore booleana, o que está sendo
    #: construído é um CDP, e a resposta é não. As chaves são lidas em
    #: `services/audience.py::resolve`.
    #:
    #: `match` é o único combinador, e é um interruptor: `any` soma (união, padrão) e
    #: `all` cruza (interseção). Sem ele só existia a união, e a união não sabe dizer
    #: "leais QUE são atacado" — pedir as duas coisas devolvia a SOMA das duas.
    audience_rules = models.JSONField(
        "regras de audiência",
        default=dict,
        blank=True,
        help_text=(
            'Por evento (exigem SKU): {"favorites": true, "alerts": true, '
            '"bought_within_days": 90}. '
            'Escolhidos pelo gestor: {"customer_refs": [], "price_tiers": [], '
            '"tags": ["corredores"], "rfm_segments": ["champion"], "churn_risk_min": 0.7, '
            '"bought_skus": [], "bought_collections": [], "birthday_today": true}. '
            'Combinação: {"match": "any"} soma as regras, {"match": "all"} cruza. '
            'Entrega: {"vip_first_minutes": 15, "preferred_hour_window_hours": 4}.'
        ),
    )
    #: Dois papéis diferentes no mesmo campo, e a diferença importa: `immediate` e
    #: `preferred_hours` **adiam** um anúncio que um evento já criou; `once` e
    #: `recurring` **criam** a ocasião sozinhos, e só valem com `trigger=schedule`.
    #: Ver `services/campaign_schedule.py`.
    schedule = models.JSONField(
        "agendamento",
        default=dict,
        blank=True,
        help_text=(
            'Adiar o que o evento criou: {"type": "immediate"} ou '
            '{"type": "preferred_hours", "windows": [["07:00", "11:00"]]}. '
            'Disparar sozinho (exige gatilho "agendado"): '
            '{"type": "once", "at": "2026-08-15T17:30:00-03:00"} ou '
            '{"type": "recurring", "windows": [["17:30", "18:30"]], '
            '"weekdays": [4, 5], "starts_on": "2026-08-15", "ends_on": "2026-12-31"}.'
        ),
    )
    #: A oferta que esta campanha anuncia (`Promotion.ref`, ADR-020 §9). Vazio = a
    #: campanha só conta uma novidade, sem desconto atrás.
    #:
    #: ⚠️ Aponta para `Promotion.ref`, **nunca** para `Coupon.code`: cupom é o ATIVADOR
    #: de uma promoção, não a promoção. Relâmpago automática não tem código nenhum, e
    #: amarrar a campanha ao cupom obrigaria a inventar um só para poder anunciar.
    #:
    #: É `SlugField` solto, e não FK, de propósito: apagar uma promoção antiga não pode
    #: derrubar o histórico de anúncios que a mencionaram, e a resolução acontece no
    #: CLIQUE — quem clica amanhã precisa da promoção de amanhã, não do que ela era
    #: quando a mensagem saiu.
    promotion_ref = models.SlugField(
        "oferta",
        max_length=64,
        blank=True,
        help_text="`ref` da promoção anunciada. Vazio = anúncio sem desconto atrás.",
    )
    requires_approval = models.BooleanField(
        "exige aprovação",
        default=True,
        help_text="Desligado = publica sozinho, sem o gestor revisar",
    )
    expires_after_minutes = models.PositiveIntegerField(
        "expira em (min)",
        default=0,
        help_text="Anúncio não aprovado caduca depois disso. 0 = não expira. "
        "Frescor é efêmero: fornada merece prazo curto.",
    )
    notify_users = models.JSONField(
        "avisar usuários",
        default=list,
        blank=True,
        help_text="IDs de usuário a notificar. Vazio = todos com a permissão de aprovar anúncios de Marketing.",
    )
    is_active = models.BooleanField("ativa", default=True)
    # CAS monotônico para comandos operacionais. ``updated_at`` continua sendo a
    # versão editorial dos rascunhos, mas não é um token seguro para idempotência.
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "campanha"
        verbose_name_plural = "campanhas"
        indexes = [models.Index(fields=["trigger", "is_active"])]
        permissions = [
            ("manage_campaigns", "Pode revisar e publicar campanhas"),
            ("view_marketing", "Pode ver Marketing agregado"),
            ("edit_marketing_campaigns", "Pode criar e editar campanhas de Marketing"),
            ("edit_marketing_templates", "Pode criar e editar textos de Marketing"),
            ("preview_marketing_audience", "Pode pré-visualizar audiência de Marketing"),
            ("approve_marketing_announcements", "Pode aprovar e rejeitar anúncios de Marketing"),
            ("publish_marketing_announcements", "Pode publicar, agendar e cancelar anúncios de Marketing"),
            ("fire_marketing_campaigns", "Pode disparar campanhas de Marketing manualmente"),
            ("retry_failed_marketing", "Pode repetir entregas de Marketing com falha segura"),
            ("reconcile_unknown_marketing", "Pode reconciliar entregas de Marketing desconhecidas"),
            ("send_marketing_test", "Pode enviar teste unitário de Marketing em sandbox"),
            ("configure_marketing_platforms", "Pode configurar plataformas de Marketing"),
            ("audit_marketing", "Pode consultar auditoria de Marketing"),
            ("access_marketing_delivery_pii", "Pode acessar PII protegida de entrega de Marketing"),
            ("freeze_marketing", "Pode congelar efeitos externos de Marketing"),
        ]

    def clean(self) -> None:
        """Recusa o par impossível entre gatilho e agendamento.

        Sem isto, os dois erros abaixo salvam limpos e a campanha aparece **ativa** na
        lista sem nunca produzir anúncio. Silêncio é o pior resultado possível aqui: o
        gestor não tem como distinguir "não disparou ainda" de "não vai disparar nunca".
        """
        from shopman.shop.services import audience as aud
        from shopman.shop.services import campaign_schedule as sched
        from shopman.shop.services import marketing_time

        match = (self.audience_rules or {}).get("match")
        if match is not None and str(match).strip().lower() not in aud.MATCH_MODES:
            raise ValidationError(
                {
                    "audience_rules": (
                        f'A combinação "{match}" não existe. Use "any" para somar as regras '
                        f'(quem se encaixa em qualquer uma) ou "all" para cruzá-las (quem se '
                        f"encaixa em todas)."
                    ),
                }
            )

        schedule = self.schedule if isinstance(self.schedule, dict) else {}
        if schedule.get("timezone"):
            try:
                marketing_time.require_configured_timezone(str(schedule["timezone"]))
            except ValueError:
                raise ValidationError(
                    {
                        "schedule": (
                            "O timezone do agendamento não corresponde ao configurado "
                            "para a loja. Reabra o horário antes de salvar."
                        ),
                    }
                ) from None

        fires = sched.fires_on_its_own(self.schedule)
        if self.trigger == Trigger.SCHEDULE and not fires:
            raise ValidationError(
                {
                    "schedule": (
                        "O gatilho é 'agendado', então o agendamento precisa ser do tipo "
                        "'once' ou 'recurring' — os outros só adiam um anúncio que um "
                        "evento já criou, e aqui não há evento."
                    ),
                }
            )
        if fires and self.trigger != Trigger.SCHEDULE:
            raise ValidationError(
                {
                    "trigger": (
                        "Este agendamento dispara sozinho, então o gatilho tem de ser "
                        "'agendado'. Com um gatilho de evento, o agendamento seria "
                        "ignorado e o anúncio sairia na hora do evento."
                    ),
                }
            )
        if fires and sched.next_occurrence(self.schedule) is None:
            raise ValidationError(
                {
                    "schedule": (
                        "Este agendamento não tem nenhuma próxima ocasião — a data já "
                        "passou, o período terminou, ou a configuração está incompleta."
                    ),
                }
            )

    def __str__(self) -> str:  # pragma: no cover - admin/debug only
        status = "✓" if self.is_active else "✗"
        return f"[{status}] {self.name}"


class Announcement(models.Model):
    """Um announcement gerado: pendente, aprovado, publicado ou caduco."""

    # Compare-and-set token for every operator command.  It starts at one so a
    # missing/zero value can never be mistaken for a valid version at the API
    # boundary.  Mutations advance it while holding a row lock.
    version = models.PositiveIntegerField(default=1, editable=False)

    rule = models.ForeignKey(
        Campaign,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="announcements",
        verbose_name="regra",
    )
    template = models.ForeignKey(
        AnnouncementTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="announcements",
        verbose_name="modelo",
    )
    #: A ocasião que gerou este anúncio, quando ele nasceu do relógio. Existe para o
    #: unique parcial abaixo: sem ela, a vassoura rodando duas vezes (ou dois workers)
    #: criaria dois anúncios para a mesma janela, e o cliente receberia em dobro.
    #:
    #: Vazio para anúncio de evento — fornada não tem "ocasião agendada", e é por isso
    #: que o unique é PARCIAL.
    occurrence_key = models.CharField(
        "ocasião",
        max_length=120,
        blank=True,
        default="",
        db_index=True,
        help_text="Identidade da ocasião agendada (campanha + instante). Vazio = nasceu de evento.",
    )
    status = models.CharField(
        "situação",
        max_length=16,
        choices=AnnouncementStatus.choices,
        default=AnnouncementStatus.DRAFT,
    )
    content = models.JSONField(
        "conteúdo",
        default=dict,
        help_text='{"body": "…", "image_url": "…", "hashtags": [...], "link": "…"}',
    )
    platform_content = models.JSONField("conteúdo por plataforma", default=dict, blank=True)
    platforms = models.JSONField("plataformas", default=list, blank=True)
    audience = models.JSONField(
        "audiência",
        default=dict,
        blank=True,
        help_text="Só contagens — a lista de destinatários nunca é persistida aqui",
    )
    platform_results = models.JSONField("resultado por plataforma", default=dict, blank=True)
    delivery_state = models.CharField(
        max_length=32,
        choices=AnnouncementDeliveryState.choices,
        default=AnnouncementDeliveryState.NOT_STARTED,
    )
    delivery_state_updated_at = models.DateTimeField(null=True, blank=True)
    delivery_settled_at = models.DateTimeField(null=True, blank=True)
    trigger_context = models.JSONField("contexto do evento", default=dict, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_announcements",
        verbose_name="aprovado por",
    )
    approved_at = models.DateTimeField("aprovado em", null=True, blank=True)
    #: Quem recusou e por quê. Guardar o autor é o que separa "a casa decidiu" de
    #: "alguém decidiu": num balcão com quatro pessoas no mesmo turno, recusa anônima
    #: não é auditável.
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rejected_announcements",
        verbose_name="recusado por",
    )
    rejected_at = models.DateTimeField("recusado em", null=True, blank=True)
    rejected_reason = models.CharField(
        "motivo da recusa",
        max_length=200,
        blank=True,
        help_text="O que estava errado. Vazio é permitido: exigir justificativa "
        "empurra o gestor a digitar qualquer coisa para se livrar do campo.",
    )
    publish_at = models.DateTimeField(
        "publicar em",
        null=True,
        blank=True,
        help_text="Aprovado com hora marcada. Preenchido = ainda não saiu; volta a vazio no despacho.",
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
            models.CheckConstraint(
                condition=(
                    models.Q(
                        delivery_state__in=(
                            "not_started",
                            "fanout_pending",
                            "delivering",
                        ),
                        delivery_settled_at__isnull=True,
                    )
                    | models.Q(
                        delivery_state__in=(
                            "succeeded",
                            "completed_with_failures",
                            "unknown",
                            "cancelled",
                            "expired",
                            "legacy_untracked",
                        ),
                        delivery_settled_at__isnull=False,
                    )
                ),
                name="shop_announcement_delivery_settlement_ck",
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


class AudienceSnapshot(models.Model):
    """Sealed, backend-only audience cohort created for an approved version."""

    ref = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    announcement = models.ForeignKey(
        Announcement,
        on_delete=models.PROTECT,
        related_name="audience_snapshots",
        null=True,
        blank=True,
    )
    version = models.PositiveIntegerField(default=1)
    summary = models.JSONField(default=dict)
    rule_summary = models.JSONField(default=dict)
    rule_hash = models.CharField(max_length=64)
    cohort_hash = models.CharField(max_length=64)
    policy_version = models.CharField(max_length=64)
    calculated_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    sealed_at = models.DateTimeField(auto_now_add=True)
    retention_until = models.DateTimeField()

    class Meta:
        ordering = ["-sealed_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["announcement", "version"],
                condition=models.Q(announcement__isnull=False),
                name="shop_audience_snapshot_announcement_version_uq",
            ),
        ]


class AudienceSnapshotMember(models.Model):
    """Protected member identity; never projected or registered in ordinary Admin."""

    snapshot = models.ForeignKey(
        AudienceSnapshot,
        on_delete=models.CASCADE,
        related_name="members",
    )
    customer = models.ForeignKey(
        "guestman.Customer",
        on_delete=models.SET_NULL,
        related_name="marketing_audience_memberships",
        null=True,
        blank=True,
    )
    subscription_ref = models.UUIDField(null=True, blank=True)
    target_key = models.CharField(max_length=64)
    reasons = models.JSONField(default=list)
    is_vip = models.BooleanField(default=False)
    preferred_hour = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "target_key"],
                name="shop_audience_snapshot_member_target_uq",
            ),
            models.CheckConstraint(
                condition=(models.Q(customer__isnull=False) | models.Q(subscription_ref__isnull=False)),
                name="shop_audience_snapshot_member_has_identity",
            ),
        ]
        indexes = [models.Index(fields=["snapshot", "customer"])]


class MarketingTestReceipt(models.Model):
    """Receipt isolado de teste sandbox; nunca entra no ledger/KPI de campanha."""

    class State(models.TextChoices):
        PROCESSING = "processing", "processando"
        ACCEPTED_UNCONFIRMED = "accepted_unconfirmed", "aceito, não confirmado"
        FAILED_FINAL = "failed_final", "recusado"
        UNKNOWN = "unknown", "resultado desconhecido"
        DENIED = "denied", "negado"

    ref = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="marketing_test_receipts",
    )
    idempotency_key_hash = models.CharField(max_length=64)
    payload_hash = models.CharField(max_length=64)
    artifact_hash = models.CharField(max_length=64)
    target_ref = models.SlugField(max_length=80)
    backend = models.CharField(max_length=32)
    state = models.CharField(
        max_length=24,
        choices=State.choices,
        default=State.PROCESSING,
    )
    failure_code = models.CharField(max_length=48, blank=True)
    sandbox = models.BooleanField(default=True)
    max_targets = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    retention_until = models.DateTimeField()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["actor", "idempotency_key_hash"],
                name="shop_marketing_test_actor_idempotency_uq",
            ),
            models.CheckConstraint(
                condition=models.Q(sandbox=True),
                name="shop_marketing_test_must_be_sandbox",
            ),
            models.CheckConstraint(
                condition=models.Q(max_targets=1),
                name="shop_marketing_test_max_one_target",
            ),
        ]
        indexes = [models.Index(fields=["actor", "created_at"])]


class MarketingCommandReceipt(models.Model):
    """Durable, PII-free outcome for one mutating Marketing command.

    The raw idempotency key is deliberately not retained.  Its keyed digest is
    enough to recognize a replay without turning an operator-supplied bearer
    value into audit data.  ``outcome`` may contain only stable refs, versions
    and machine codes; content and audience membership belong to their sealed
    artifacts instead.
    """

    class Kind(models.TextChoices):
        APPROVE = "approve", "aprovar"
        REJECT = "reject", "recusar"
        RESCHEDULE = "reschedule", "reagendar"
        PUBLISH_NOW = "publish_now", "publicar agora"
        CANCEL = "cancel", "cancelar"
        FIRE = "fire", "disparar campanha"
        EXPIRE = "expire", "expirar"
        RETRY_DELIVERY = "retry_delivery", "repetir falhas de entrega"
        RECONCILE_DELIVERY = "reconcile_delivery", "reconciliar entrega desconhecida"
        CONFIGURE_PLATFORM = "configure_platform", "configurar plataforma"

    class State(models.TextChoices):
        ACCEPTED = "accepted", "aceito"
        COMPLETED = "completed", "concluído"
        REJECTED = "rejected", "recusado"
        CONFLICT = "conflict", "conflito"
        UNKNOWN = "unknown", "resultado desconhecido"

    ref = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    kind = models.CharField(max_length=24, choices=Kind.choices)
    state = models.CharField(
        max_length=16,
        choices=State.choices,
        default=State.ACCEPTED,
    )
    announcement = models.ForeignKey(
        Announcement,
        on_delete=models.PROTECT,
        related_name="command_receipts",
        null=True,
        blank=True,
    )
    resource_ref = models.CharField(max_length=120)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="marketing_command_receipts",
        null=True,
        blank=True,
    )
    actor_ref = models.CharField(max_length=128, blank=True, db_index=True)
    idempotency_key_hash = models.CharField(max_length=64)
    payload_hash = models.CharField(max_length=64)
    base_version = models.PositiveIntegerField()
    resulting_version = models.PositiveIntegerField(null=True, blank=True)
    outcome = models.JSONField(default=dict, blank=True)
    request_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    retention_until = models.DateTimeField()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["actor", "idempotency_key_hash"],
                name="shop_marketing_command_actor_idem_uq",
            ),
            models.UniqueConstraint(
                fields=["actor_ref", "idempotency_key_hash"],
                condition=models.Q(actor__isnull=True) & models.Q(actor_ref__gt=""),
                name="shop_marketing_command_system_idem_uq",
            ),
        ]
        indexes = [
            models.Index(fields=["announcement", "created_at"]),
            models.Index(fields=["state", "created_at"]),
        ]


class MarketingContentArtifact(models.Model):
    """Byte-stable, immutable content approved for one Announcement version."""

    ref = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    announcement = models.ForeignKey(
        Announcement,
        on_delete=models.PROTECT,
        related_name="content_artifacts",
    )
    version = models.PositiveIntegerField()
    schema_version = models.PositiveSmallIntegerField(default=1)
    payload = models.JSONField()
    artifact_hash = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    retention_until = models.DateTimeField()

    objects = models.Manager.from_queryset(_AppendOnlyMarketingQuerySet)()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["announcement", "version"],
                name="shop_marketing_artifact_announcement_version_uq",
            ),
        ]

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Artefatos de Marketing são imutáveis.")
        expected = hashlib.sha256(self.canonical_bytes()).hexdigest()
        if self.artifact_hash != expected:
            raise ValidationError("Hash do artefato de Marketing não confere.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Artefatos de Marketing não podem ser apagados.")


class MarketingAuditEvent(models.Model):
    """Append-only evidence that ties actor, version, snapshot and artifact."""

    class EventType(models.TextChoices):
        CAMPAIGN_FIRED = "campaign_fired", "disparo de campanha criado"
        APPROVED = "approved", "aprovado"
        REJECTED = "rejected", "recusado"
        RESCHEDULED = "rescheduled", "reagendado"
        CANCELLED = "cancelled", "cancelado"
        EXPIRED = "expired", "expirado"
        DELIVERY_RETRIED = "delivery_retried", "entrega repetida"
        RECONCILIATION_REQUESTED = "reconcile_requested", "reconciliação solicitada"

    ref = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    event_type = models.CharField(max_length=24, choices=EventType.choices)
    command = models.OneToOneField(
        MarketingCommandReceipt,
        on_delete=models.PROTECT,
        related_name="audit_event",
    )
    announcement = models.ForeignKey(
        Announcement,
        on_delete=models.PROTECT,
        related_name="marketing_audit_events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="marketing_audit_events",
        null=True,
        blank=True,
    )
    actor_ref = models.CharField(max_length=128, blank=True, db_index=True)
    snapshot = models.ForeignKey(
        AudienceSnapshot,
        on_delete=models.PROTECT,
        related_name="audit_events",
        null=True,
        blank=True,
    )
    artifact = models.ForeignKey(
        MarketingContentArtifact,
        on_delete=models.PROTECT,
        related_name="audit_events",
        null=True,
        blank=True,
    )
    base_version = models.PositiveIntegerField()
    resulting_version = models.PositiveIntegerField()
    reason_code = models.CharField(max_length=64, blank=True)
    decision_reason = models.CharField(max_length=200, blank=True)
    facts = models.JSONField(default=dict, blank=True)
    request_id = models.CharField(max_length=100, blank=True)
    occurred_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    retention_until = models.DateTimeField()

    objects = models.Manager.from_queryset(_AppendOnlyMarketingQuerySet)()

    class Meta:
        ordering = ["-occurred_at", "-pk"]
        indexes = [models.Index(fields=["announcement", "occurred_at"])]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Eventos de auditoria de Marketing são imutáveis.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Eventos de auditoria de Marketing não podem ser apagados.")


class MarketingAISuggestion(models.Model):
    """PII-free, append-only evidence for one Marketing AI attempt.

    The suggested copy and raw prompt deliberately never enter this ledger.  Their
    content-addressed hashes are enough to prove which suggestion was accepted or
    edited without retaining another copy of customer-facing text or untrusted input.
    """

    class State(models.TextChoices):
        GENERATED = "generated", "gerada"
        REJECTED = "rejected", "bloqueada pela política"
        PROVIDER_FAILED = "provider_failed", "provedor indisponível"

    ref = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    announcement = models.ForeignKey(
        Announcement,
        on_delete=models.PROTECT,
        related_name="ai_suggestions",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="marketing_ai_suggestions",
    )
    actor_ref = models.CharField(max_length=128, blank=True, db_index=True)
    request_id = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=24, choices=State.choices)
    outcome_code = models.CharField(max_length=64)
    base_version = models.PositiveIntegerField()
    provider_ref = models.CharField(max_length=32)
    model_ref = models.CharField(max_length=100)
    policy_version = models.CharField(max_length=32)
    facts_hash = models.CharField(max_length=64)
    prompt_hash = models.CharField(max_length=64)
    suggestion_hash = models.CharField(max_length=64, blank=True)
    body_hash = models.CharField(max_length=64, blank=True)
    hashtags_hash = models.CharField(max_length=64, blank=True)
    used_fact_ids = models.JSONField(default=list, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    latency_bucket = models.CharField(max_length=24, blank=True)
    cost_bucket = models.CharField(max_length=24, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    retention_until = models.DateTimeField()

    objects = models.Manager.from_queryset(_AppendOnlyMarketingQuerySet)()

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(fields=["announcement", "created_at"]),
            models.Index(fields=["state", "created_at"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Tentativas de IA de Marketing são imutáveis.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Tentativas de IA de Marketing não podem ser apagadas.")


class MarketingAISuggestionEvent(models.Model):
    """Human disposition of a suggestion, separate from the provider attempt."""

    class EventType(models.TextChoices):
        DRAFT_ACCEPTED = "draft_accepted", "usada no rascunho"
        DISCARDED = "discarded", "descartada"
        APPROVED_UNEDITED = "approved_unedited", "aprovada sem edição"
        APPROVED_EDITED = "approved_edited", "aprovada após edição"

    suggestion = models.ForeignKey(
        MarketingAISuggestion,
        on_delete=models.PROTECT,
        related_name="human_events",
    )
    event_type = models.CharField(max_length=24, choices=EventType.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="marketing_ai_suggestion_events",
    )
    actor_ref = models.CharField(max_length=128, blank=True, db_index=True)
    command = models.ForeignKey(
        MarketingCommandReceipt,
        on_delete=models.PROTECT,
        related_name="ai_suggestion_events",
        null=True,
        blank=True,
    )
    result_hash = models.CharField(max_length=64, blank=True)
    diff_fields = models.JSONField(default=list, blank=True)
    occurred_at = models.DateTimeField()
    retention_until = models.DateTimeField()

    objects = models.Manager.from_queryset(_AppendOnlyMarketingQuerySet)()

    class Meta:
        ordering = ["-occurred_at", "-pk"]
        indexes = [models.Index(fields=["suggestion", "occurred_at"])]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Decisões sobre sugestões de IA são imutáveis.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Decisões sobre sugestões de IA não podem ser apagadas.")


class MarketingPlatformAuditEvent(models.Model):
    """Append-only evidence for a versioned Marketing platform configuration."""

    class EventType(models.TextChoices):
        FLOW_CONFIGURED = "flow_configured", "flow configurado"
        FLOW_CLEARED = "flow_cleared", "flow removido"

    ref = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    event_type = models.CharField(max_length=24, choices=EventType.choices)
    command = models.OneToOneField(
        MarketingCommandReceipt,
        on_delete=models.PROTECT,
        related_name="platform_audit_event",
    )
    platform = models.CharField(max_length=32)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="marketing_platform_audit_events",
    )
    actor_ref = models.CharField(max_length=128, db_index=True)
    base_version = models.PositiveIntegerField()
    resulting_version = models.PositiveIntegerField()
    previous_flow_ref = models.CharField(max_length=120, blank=True)
    resulting_flow_ref = models.CharField(max_length=120, blank=True)
    catalog_hash = models.CharField(max_length=64)
    catalog_as_of = models.DateTimeField()
    request_id = models.CharField(max_length=100, blank=True)
    occurred_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    retention_until = models.DateTimeField()

    objects = models.Manager.from_queryset(_AppendOnlyMarketingQuerySet)()

    class Meta:
        ordering = ["-occurred_at", "-pk"]
        indexes = [models.Index(fields=["platform", "occurred_at"])]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Eventos de configuração de plataforma são imutáveis.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Eventos de configuração de plataforma não podem ser apagados.")


class MarketingSafetyState(models.Model):
    """Singleton kill switch for every reversible Marketing external effect."""

    scope = models.CharField(max_length=32, default="default", unique=True)
    frozen = models.BooleanField(default=False)
    generation = models.PositiveIntegerField(default=1)
    version = models.PositiveIntegerField(default=1)
    reason = models.CharField(max_length=200, blank=True)
    frozen_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="marketing_freezes",
        null=True,
        blank=True,
    )
    frozen_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(generation__gte=1),
                name="shop_marketing_safety_generation_ck",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1),
                name="shop_marketing_safety_version_ck",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        frozen=True,
                        frozen_by__isnull=False,
                        frozen_at__isnull=False,
                        reason__gt="",
                    )
                    | models.Q(
                        frozen=False,
                        frozen_by__isnull=True,
                        frozen_at__isnull=True,
                        reason="",
                    )
                ),
                name="shop_marketing_safety_frozen_evidence_ck",
            ),
        ]


class MarketingConfirmation(models.Model):
    """Hashed, one-use transaction authorization bound to exact consequences."""

    class Mode(models.TextChoices):
        SUMMARY = "summary", "resumo"
        TYPED = "typed", "digitada"

    class StepUp(models.TextChoices):
        NONE = "none", "nenhum"
        PASSWORD = "password", "senha"
        TOTP = "totp", "TOTP"

    ref = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    token_hash = models.CharField(max_length=64, unique=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="marketing_confirmations",
    )
    second_actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="marketing_second_confirmations",
        null=True,
        blank=True,
    )
    command = models.OneToOneField(
        MarketingCommandReceipt,
        on_delete=models.PROTECT,
        related_name="confirmation",
        null=True,
        blank=True,
    )
    action = models.CharField(max_length=32)
    capability = models.CharField(max_length=64)
    resource_ref = models.CharField(max_length=120)
    base_version = models.PositiveIntegerField()
    context_hash = models.CharField(max_length=64)
    artifact_hash = models.CharField(max_length=64, blank=True)
    audience_hash = models.CharField(max_length=64, blank=True)
    audience_count = models.PositiveIntegerField(default=0)
    platforms = models.JSONField(default=list, blank=True)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    consequence = models.CharField(max_length=64)
    confirmation_mode = models.CharField(max_length=16, choices=Mode.choices)
    step_up_level = models.CharField(max_length=16, choices=StepUp.choices)
    dual_control = models.BooleanField(default=False)
    permission_fingerprint = models.CharField(max_length=64)
    second_permission_fingerprint = models.CharField(max_length=64, blank=True)
    freeze_generation = models.PositiveIntegerField()
    second_approved_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    retention_until = models.DateTimeField()

    objects = models.Manager.from_queryset(_AppendOnlyMarketingQuerySet)()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(base_version__gte=1),
                name="shop_marketing_confirmation_version_ck",
            ),
            models.CheckConstraint(
                condition=models.Q(freeze_generation__gte=1),
                name="shop_marketing_confirmation_generation_ck",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        dual_control=False,
                        second_actor__isnull=True,
                        second_approved_at__isnull=True,
                        second_permission_fingerprint="",
                    )
                    | models.Q(
                        dual_control=True,
                        second_actor__isnull=False,
                        second_approved_at__isnull=False,
                        second_permission_fingerprint__gt="",
                    )
                    | models.Q(
                        dual_control=True,
                        second_actor__isnull=True,
                        second_approved_at__isnull=True,
                        second_permission_fingerprint="",
                    )
                ),
                name="shop_marketing_confirmation_dual_ck",
            ),
        ]
        indexes = [
            models.Index(fields=["actor", "created_at"]),
            models.Index(fields=["resource_ref", "created_at"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            update_fields = set(kwargs.get("update_fields") or ())
            mutable_fields = {
                "command",
                "command_id",
                "consumed_at",
                "second_actor",
                "second_actor_id",
                "second_approved_at",
                "second_permission_fingerprint",
            }
            if not update_fields or not update_fields.issubset(mutable_fields):
                raise ValidationError("Confirmações de Marketing só avançam por transições explícitas.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Confirmações de Marketing não podem ser apagadas.")


class MarketingQuotaUsage(models.Model):
    """Low-cardinality durable reservations for command and blast quotas."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="marketing_quota_usage",
    )
    action = models.CharField(max_length=32)
    resource_ref = models.CharField(max_length=120)
    target_count = models.PositiveIntegerField(default=0)
    occurred_at = models.DateTimeField(db_index=True)
    retention_until = models.DateTimeField()

    objects = models.Manager.from_queryset(_AppendOnlyMarketingQuerySet)()

    class Meta:
        indexes = [
            models.Index(fields=["actor", "action", "occurred_at"]),
            models.Index(fields=["action", "occurred_at"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Reservas de quota de Marketing são imutáveis.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Reservas de quota de Marketing não podem ser apagadas.")


class MarketingSecurityEvent(models.Model):
    """Append-only, PII-free evidence for authorization and emergency actions."""

    ref = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="marketing_security_events",
        null=True,
        blank=True,
    )
    second_actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="marketing_second_security_events",
        null=True,
        blank=True,
    )
    confirmation = models.ForeignKey(
        MarketingConfirmation,
        on_delete=models.PROTECT,
        related_name="security_events",
        null=True,
        blank=True,
    )
    event_type = models.CharField(max_length=32)
    action = models.CharField(max_length=32, blank=True)
    resource_ref = models.CharField(max_length=120, blank=True)
    reason_code = models.CharField(max_length=64, blank=True)
    facts = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField()
    retention_until = models.DateTimeField()

    objects = models.Manager.from_queryset(_AppendOnlyMarketingQuerySet)()

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["event_type", "occurred_at"]),
            models.Index(fields=["resource_ref", "occurred_at"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Eventos de segurança de Marketing são imutáveis.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Eventos de segurança de Marketing não podem ser apagados.")


class MarketingOutbox(models.Model):
    """Durable intent; no provider is called while an operator command commits."""

    class State(models.TextChoices):
        PENDING = "pending", "pendente"
        CLAIMED = "claimed", "reservado"
        DISPATCHED = "dispatched", "despachado"
        CANCELLED = "cancelled", "cancelado"
        FAILED = "failed", "falhou"

    ref = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    command = models.ForeignKey(
        MarketingCommandReceipt,
        on_delete=models.PROTECT,
        related_name="outbox_entries",
    )
    announcement = models.ForeignKey(
        Announcement,
        on_delete=models.PROTECT,
        related_name="marketing_outbox_entries",
    )
    snapshot = models.ForeignKey(
        AudienceSnapshot,
        on_delete=models.PROTECT,
        related_name="outbox_entries",
    )
    artifact = models.ForeignKey(
        MarketingContentArtifact,
        on_delete=models.PROTECT,
        related_name="outbox_entries",
    )
    platform = models.CharField(max_length=32)
    wave_key = models.CharField(max_length=64, blank=True)
    state = models.CharField(max_length=16, choices=State.choices, default=State.PENDING)
    available_at = models.DateTimeField(db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    lease_owner = models.CharField(max_length=100, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True)
    dispatch_ref = models.CharField(max_length=128, blank=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    fanout_selection_hash = models.CharField(max_length=64, blank=True)
    fanout_expected = models.PositiveIntegerField(default=0)
    fanout_materialized = models.PositiveIntegerField(default=0)
    fanout_completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_by_command = models.ForeignKey(
        MarketingCommandReceipt,
        on_delete=models.PROTECT,
        related_name="cancelled_outbox_entries",
        null=True,
        blank=True,
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["available_at", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["command", "platform", "wave_key"],
                name="shop_marketing_outbox_command_lane_uq",
            ),
            models.UniqueConstraint(
                fields=["dispatch_ref"],
                condition=models.Q(dispatch_ref__gt=""),
                name="shop_marketing_outbox_dispatch_ref_uq",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        state="claimed",
                        lease_owner__gt="",
                        lease_until__isnull=False,
                    )
                    | (~models.Q(state="claimed") & models.Q(lease_owner="", lease_until__isnull=True))
                ),
                name="shop_marketing_outbox_lease_state_ck",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        state="dispatched",
                        dispatch_ref__gt="",
                        dispatched_at__isnull=False,
                    )
                    | (~models.Q(state="dispatched") & models.Q(dispatch_ref="", dispatched_at__isnull=True))
                ),
                name="shop_marketing_outbox_dispatch_state_ck",
            ),
            models.CheckConstraint(
                condition=models.Q(fanout_materialized__lte=models.F("fanout_expected")),
                name="shop_marketing_outbox_fanout_count_ck",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(fanout_completed_at__isnull=True)
                    | models.Q(
                        fanout_completed_at__isnull=False,
                        fanout_selection_hash__gt="",
                        fanout_materialized=models.F("fanout_expected"),
                    )
                ),
                name="shop_marketing_outbox_fanout_complete_ck",
            ),
            models.CheckConstraint(
                condition=models.Q(state__in=("pending", "claimed", "dispatched", "cancelled", "failed")),
                name="shop_marketing_outbox_state_ck",
            ),
        ]
        indexes = [models.Index(fields=["state", "available_at"])]


class DeliveryTarget(models.Model):
    """One protected logical effect for a snapshot member or public platform."""

    class State(models.TextChoices):
        PLANNED = "planned", "planejado"
        SUPPRESSED = "suppressed", "suprimido"
        QUEUED = "queued", "enfileirado"
        SENDING = "sending", "enviando"
        ACCEPTED = "accepted", "aceito, não confirmado"
        CONFIRMED = "confirmed", "confirmado"
        FAILED_RETRYABLE = "failed_retryable", "falha repetível"
        FAILED_FINAL = "failed_final", "falha final"
        UNKNOWN = "unknown", "resultado desconhecido"
        CANCELLED = "cancelled", "cancelado"
        EXPIRED = "expired", "expirado"

    ref = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    outbox = models.ForeignKey(
        MarketingOutbox,
        on_delete=models.PROTECT,
        related_name="delivery_targets",
    )
    announcement = models.ForeignKey(
        Announcement,
        on_delete=models.PROTECT,
        related_name="delivery_targets",
    )
    snapshot = models.ForeignKey(
        AudienceSnapshot,
        on_delete=models.PROTECT,
        related_name="delivery_targets",
    )
    artifact = models.ForeignKey(
        MarketingContentArtifact,
        on_delete=models.PROTECT,
        related_name="delivery_targets",
    )
    member = models.ForeignKey(
        AudienceSnapshotMember,
        on_delete=models.SET_NULL,
        related_name="delivery_targets",
        null=True,
        blank=True,
    )
    platform = models.CharField(max_length=32)
    wave_key = models.CharField(max_length=64, blank=True)
    target_fingerprint = models.CharField(max_length=64)
    fingerprint_key_version = models.PositiveSmallIntegerField()
    state = models.CharField(
        max_length=24,
        choices=State.choices,
        default=State.PLANNED,
    )
    version = models.PositiveIntegerField(default=1)
    attempt_count = models.PositiveIntegerField(default=0)
    lease_owner = models.CharField(max_length=100, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    next_attempt_at = models.DateTimeField(db_index=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True)
    provider_receipt_ref = models.CharField(max_length=128, blank=True)
    provider_ref_retention_until = models.DateTimeField(null=True, blank=True)
    identity_retention_until = models.DateTimeField()
    record_retention_until = models.DateTimeField()
    settled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["next_attempt_at", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "platform", "target_fingerprint"],
                name="shop_delivery_target_snapshot_platform_fp_uq",
            ),
            models.CheckConstraint(
                condition=models.Q(fingerprint_key_version__gt=0),
                name="shop_delivery_target_key_version_ck",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gt=0),
                name="shop_delivery_target_version_ck",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(lease_owner="", lease_until__isnull=True)
                    | models.Q(
                        state="queued",
                        lease_owner__gt="",
                        lease_until__isnull=False,
                    )
                ),
                name="shop_delivery_target_lease_state_ck",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    state__in=(
                        "planned",
                        "suppressed",
                        "queued",
                        "sending",
                        "accepted",
                        "confirmed",
                        "failed_retryable",
                        "failed_final",
                        "unknown",
                        "cancelled",
                        "expired",
                    )
                ),
                name="shop_delivery_target_state_ck",
            ),
        ]
        indexes = [
            models.Index(fields=["state", "next_attempt_at"]),
            models.Index(fields=["outbox", "state"]),
        ]


class DeliveryAttempt(models.Model):
    """One sanitized provider-call attempt; raw contact/body/error never lives here."""

    class State(models.TextChoices):
        PREPARED = "prepared", "preparada"
        CALLING = "calling", "chamada iniciada"
        COMPLETED = "completed", "concluída"

    class Outcome(models.TextChoices):
        NOT_ATTEMPTED = "not_attempted", "não tentado"
        ACCEPTED_UNCONFIRMED = "accepted_unconfirmed", "aceito, não confirmado"
        CONFIRMED = "confirmed", "confirmado"
        FAILED_RETRYABLE = "failed_retryable", "falha repetível"
        FAILED_FINAL = "failed_final", "falha final"
        UNKNOWN = "unknown", "resultado desconhecido"

    ref = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    target = models.ForeignKey(
        DeliveryTarget,
        on_delete=models.PROTECT,
        related_name="attempts",
    )
    ordinal = models.PositiveIntegerField()
    state = models.CharField(
        max_length=16,
        choices=State.choices,
        default=State.PREPARED,
    )
    outcome_kind = models.CharField(
        max_length=32,
        choices=Outcome.choices,
        blank=True,
    )
    idempotency_token_hash = models.CharField(max_length=64)
    request_hash = models.CharField(max_length=64)
    provider_receipt_ref = models.CharField(max_length=128, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    retry_after_seconds = models.PositiveIntegerField(null=True, blank=True)
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    retention_until = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["target", "ordinal"]
        constraints = [
            models.UniqueConstraint(
                fields=["target", "ordinal"],
                name="shop_delivery_attempt_target_ordinal_uq",
            ),
            models.UniqueConstraint(
                fields=["target", "idempotency_token_hash"],
                name="shop_delivery_attempt_target_idem_uq",
            ),
            models.CheckConstraint(
                condition=models.Q(ordinal__gt=0),
                name="shop_delivery_attempt_ordinal_ck",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        state__in=("prepared", "calling"),
                        outcome_kind="",
                        completed_at__isnull=True,
                    )
                    | models.Q(
                        state="completed",
                        outcome_kind__gt="",
                        completed_at__isnull=False,
                    )
                ),
                name="shop_delivery_attempt_completion_ck",
            ),
        ]
        indexes = [models.Index(fields=["state", "started_at"])]


class DeliveryReconciliation(models.Model):
    """Durable, lookup-only intent for one uncertain provider attempt.

    The row deliberately points at the protected target and attempt instead of
    copying recipient data.  A worker may repeat a provider lookup after a
    lease expires, but this queue never invokes the provider's send boundary.
    """

    class State(models.TextChoices):
        PENDING = "pending", "pendente"
        CLAIMED = "claimed", "reservada"
        COMPLETED = "completed", "concluída"

    ref = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    command = models.ForeignKey(
        MarketingCommandReceipt,
        on_delete=models.PROTECT,
        related_name="delivery_reconciliations",
    )
    target = models.ForeignKey(
        DeliveryTarget,
        on_delete=models.PROTECT,
        related_name="reconciliations",
    )
    attempt = models.ForeignKey(
        DeliveryAttempt,
        on_delete=models.PROTECT,
        related_name="reconciliations",
    )
    state = models.CharField(
        max_length=16,
        choices=State.choices,
        default=State.PENDING,
    )
    available_at = models.DateTimeField(db_index=True)
    lookup_attempts = models.PositiveIntegerField(default=0)
    lease_owner = models.CharField(max_length=100, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    outcome_kind = models.CharField(
        max_length=32,
        choices=DeliveryAttempt.Outcome.choices,
        blank=True,
    )
    provider_receipt_ref = models.CharField(max_length=128, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    retention_until = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["available_at", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["command", "target"],
                name="shop_delivery_reconcile_command_target_uq",
            ),
            models.UniqueConstraint(
                fields=["target"],
                condition=models.Q(state__in=("pending", "claimed")),
                name="shop_delivery_reconcile_active_target_uq",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        state="claimed",
                        lease_owner__gt="",
                        lease_until__isnull=False,
                    )
                    | (~models.Q(state="claimed") & models.Q(lease_owner="", lease_until__isnull=True))
                ),
                name="shop_delivery_reconcile_lease_state_ck",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        state__in=("pending", "claimed"),
                        outcome_kind="",
                        completed_at__isnull=True,
                    )
                    | models.Q(
                        state="completed",
                        outcome_kind__gt="",
                        completed_at__isnull=False,
                    )
                ),
                name="shop_delivery_reconcile_completion_ck",
            ),
        ]
        indexes = [models.Index(fields=["state", "available_at"])]
