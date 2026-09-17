"""MKT-020 — exact confirmation, step-up, quotas and emergency revoke."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from shopman.shop.models import (
    Announcement,
    AnnouncementStatus,
    MarketingCommandReceipt,
    MarketingConfirmation,
    MarketingOutbox,
    MarketingQuotaUsage,
    MarketingSafetyState,
    MarketingSecurityEvent,
)
from shopman.shop.services.marketing_security import (
    AuthorizationRequirement,
    MarketingAuthorizationError,
    MarketingAuthorizationRequired,
    StepUpEvidence,
    activate_freeze,
    approve_second_actor,
    authorization_context,
    authorize_command,
    deactivate_freeze,
    direct_message_recipient_count,
    external_destination_count,
    issue_confirmation,
    permission_fingerprint,
    public_post_count,
    requirement_for,
    safety_state,
)

pytestmark = pytest.mark.django_db

User = get_user_model()
APPROVE = "/api/v1/backstage/marketing/announcements/{pk}/approve/"
STEP_UP = "/api/v1/backstage/marketing/security/step-up/"


def _actor(username: str, *codenames: str):
    actor = User.objects.create_user(
        username=username,
        password="senha-segura",
        is_staff=True,
    )
    actor.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    return actor


def _announcement():
    return Announcement.objects.create(
        status=AnnouncementStatus.PENDING_REVIEW,
        content={"body": "Fornada pronta", "image_url": "/media/fornada.jpg"},
        platforms=["instagram"],
    )


def _step_up(actor, level: str, *, at=None) -> StepUpEvidence:
    state = safety_state()
    return StepUpEvidence(
        actor_id=actor.pk,
        level=level,
        verified_at=at or timezone.now(),
        auth_hash=actor.get_session_auth_hash(),
        permission_fingerprint=permission_fingerprint(actor, state=state),
        safety_generation=state.generation,
    )


@pytest.fixture(autouse=True)
def customer_base(monkeypatch):
    """Fixa o tamanho da base de clientes que o limiar de cerimônia usa.

    O limiar é ``max(piso, min(2% da base, teto de gasto ÷ custo por mensagem))``. Uma
    base de 2.500 dá 50 pessoas para frase+senha e 500 para duplo controle — de
    propósito: são os números que a política anterior cravava no código, e amarrá-los
    aqui deixa cada faixa deste arquivo continuar exercitando o que exercitava.

    Sem chamar, a base é ZERO: o limiar cai no piso (10), que é o lado fechado da conta.
    """
    from shopman.shop.services import marketing_ceremony

    state = {"size": 0}

    def _set(size: int) -> None:
        state["size"] = int(size)

    monkeypatch.setattr(
        marketing_ceremony, "customer_base_size", lambda **_: state["size"]
    )
    return _set


def _open_confirmation(actor, context, *, capability, now=None):
    with pytest.raises(MarketingAuthorizationRequired) as caught:
        authorize_command(
            actor=actor,
            capability=capability,
            context=context,
            token="",
            now=now,
        )
    return issue_confirmation(caught.value, actor=actor, now=now)["confirmation"]


def test_immediate_api_command_returns_exact_server_challenge_before_any_write(client):
    """Um destino imediato pede leitura e um toque — não frase digitada e senha.

    A cerimônia mede a consequência. Publicar num mural é um destino; cobrar aqui o
    mesmo ritual de um disparo para quinhentas pessoas era o que fazia o caminho do
    teste parecer protocolo. O desafio continua existindo, e continua acontecendo
    ANTES de qualquer escrita — é isso que este teste protege.
    """
    actor = _actor(
        "publisher-challenge",
        "view_marketing",
        "approve_marketing_announcements",
        "publish_marketing_announcements",
    )
    announcement = _announcement()
    client.force_login(actor)

    response = client.post(
        APPROVE.format(pk=announcement.pk),
        data={"base_version": 1, "publish_mode": "now"},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="security-challenge-key-0001",
    )

    assert response.status_code == 428
    challenge = response.json()["confirmation"]
    assert challenge["mode"] == "summary"
    assert challenge["step_up"] == "none"
    assert challenge["audience_count"] == 0
    assert challenge["typed_phrase"] == ""
    assert challenge["resource_ref"] == f"announcement:{announcement.pk}"
    assert challenge["platforms"] == ["instagram"]
    assert MarketingCommandReceipt.objects.count() == 0
    assert MarketingOutbox.objects.count() == 0
    stored = MarketingConfirmation.objects.get(ref=challenge["ref"])
    assert stored.token_hash != challenge["token"]
    assert challenge["token"] not in str(stored.__dict__)


def test_password_step_up_and_exact_phrase_consume_with_effect_in_one_transaction(client):
    actor = _actor(
        "publisher-confirm",
        "view_marketing",
        "approve_marketing_announcements",
        "publish_marketing_announcements",
    )
    announcement = _announcement()
    client.force_login(actor)
    payload = {"base_version": 1, "publish_mode": "now"}
    key = "security-confirm-key-000001"
    challenge = client.post(
        APPROVE.format(pk=announcement.pk),
        data=payload,
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=key,
    ).json()["confirmation"]

    stepped = client.post(
        STEP_UP,
        data={"method": "password", "credential": "senha-segura"},
        content_type="application/json",
    )
    assert stepped.status_code == 200
    confirmed_payload = {
        **payload,
        "confirmation_token": challenge["token"],
        "typed_confirmation": challenge["typed_phrase"],
    }
    completed = client.post(
        APPROVE.format(pk=announcement.pk),
        data=confirmed_payload,
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    replay = client.post(
        APPROVE.format(pk=announcement.pk),
        data=confirmed_payload,
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=key,
    )

    assert completed.status_code == replay.status_code == 200
    assert replay.json()["replayed"] is True
    receipt = MarketingCommandReceipt.objects.get(ref=completed.json()["receipt"]["ref"])
    confirmation = MarketingConfirmation.objects.get(ref=challenge["ref"])
    assert confirmation.command_id == receipt.pk
    assert confirmation.consumed_at is not None
    assert MarketingOutbox.objects.filter(command=receipt).count() == 1


def test_permission_revoked_after_challenge_blocks_loaded_action_without_effect(client):
    actor = _actor(
        "publisher-revoked",
        "view_marketing",
        "approve_marketing_announcements",
        "publish_marketing_announcements",
    )
    announcement = _announcement()
    client.force_login(actor)
    payload = {"base_version": 1, "publish_mode": "now"}
    challenge = client.post(
        APPROVE.format(pk=announcement.pk),
        data=payload,
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="security-revoke-key-000001",
    ).json()["confirmation"]
    actor.user_permissions.remove(
        Permission.objects.get(codename="publish_marketing_announcements")
    )

    response = client.post(
        APPROVE.format(pk=announcement.pk),
        data={
            **payload,
            "confirmation_token": challenge["token"],
            "typed_confirmation": challenge["typed_phrase"],
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="security-revoke-key-000001",
    )

    assert response.status_code == 403
    announcement.refresh_from_db()
    assert announcement.status == AnnouncementStatus.PENDING_REVIEW
    assert MarketingCommandReceipt.objects.count() == 0
    assert MarketingOutbox.objects.count() == 0


def test_dangerous_api_rate_limit_returns_retry_after_before_effect(
    client, monkeypatch
):
    from shopman.backstage.api.throttles import (
        MarketingDangerousShopThrottle,
        MarketingDangerousUserThrottle,
    )

    monkeypatch.setattr(
        MarketingDangerousUserThrottle, "rate", "2/minute", raising=False
    )
    monkeypatch.setattr(
        MarketingDangerousShopThrottle, "rate", "100/minute", raising=False
    )
    cache.clear()
    actor = _actor(
        "publisher-throttled",
        "view_marketing",
        "approve_marketing_announcements",
        "publish_marketing_announcements",
    )
    announcement = _announcement()
    client.force_login(actor)
    url = APPROVE.format(pk=announcement.pk)
    payload = {"base_version": 1, "publish_mode": "now"}

    for index in range(2):
        response = client.post(
            url,
            data=payload,
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=f"security-throttle-{index:04d}",
        )
        assert response.status_code == 428

    limited = client.post(
        url,
        data=payload,
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="security-throttle-blocked",
    )

    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) > 0
    assert MarketingCommandReceipt.objects.count() == 0
    assert MarketingOutbox.objects.count() == 0


def test_confirmation_is_one_use_short_lived_and_bound_to_exact_context(customer_base):
    customer_base(2_500)
    actor = _actor("direct-publisher", "publish_marketing_announcements")
    now = timezone.now()
    context = authorization_context(
        action="approve",
        resource_ref="announcement:42",
        base_version=7,
        artifact_hash="a" * 64,
        audience_hash="b" * 64,
        audience_count=50,
        platforms=("whatsapp",),
        consequence="publishes_now_to_eligible_audience",
    )
    challenge = _open_confirmation(
        actor,
        context,
        capability="shop.publish_marketing_announcements",
        now=now,
    )
    evidence = _step_up(actor, "password", at=now)

    authorize_command(
        actor=actor,
        capability="shop.publish_marketing_announcements",
        context=context,
        token=challenge["token"],
        typed_confirmation="ENVIAR 50",
        step_up=evidence,
        now=now + timedelta(seconds=1),
    )
    with pytest.raises(MarketingAuthorizationError, match="já foi usada"):
        authorize_command(
            actor=actor,
            capability="shop.publish_marketing_announcements",
            context=context,
            token=challenge["token"],
            typed_confirmation="ENVIAR 50",
            step_up=evidence,
            now=now + timedelta(seconds=2),
        )

    changed = authorization_context(
        **{**context.payload(), "audience_count": 49, "scheduled_for": None}
    )
    other = _open_confirmation(
        actor,
        context,
        capability="shop.publish_marketing_announcements",
        now=now,
    )
    with pytest.raises(MarketingAuthorizationError) as caught:
        authorize_command(
            actor=actor,
            capability="shop.publish_marketing_announcements",
            context=changed,
            token=other["token"],
            typed_confirmation="ENVIAR 49",
            step_up=evidence,
            now=now + timedelta(seconds=1),
        )
    assert caught.value.code == "confirmation_context_changed"

    expired = _open_confirmation(
        actor,
        context,
        capability="shop.publish_marketing_announcements",
        now=now,
    )
    with pytest.raises(MarketingAuthorizationError) as stale:
        authorize_command(
            actor=actor,
            capability="shop.publish_marketing_announcements",
            context=context,
            token=expired["token"],
            typed_confirmation="ENVIAR 50",
            step_up=_step_up(actor, "password", at=now + timedelta(minutes=6)),
            now=now + timedelta(minutes=6),
        )
    assert stale.value.code == "confirmation_expired"


def test_500_targets_requires_totp_and_distinct_second_authorized_actor(customer_base):
    customer_base(2_500)
    publisher = _actor("publisher-large", "publish_marketing_announcements")
    approver = _actor("approver-large", "approve_marketing_announcements")
    context = authorization_context(
        action="approve",
        resource_ref="announcement:500",
        base_version=3,
        artifact_hash="c" * 64,
        audience_hash="d" * 64,
        audience_count=500,
        platforms=("whatsapp",),
        scheduled_for=timezone.now() + timedelta(hours=1),
        consequence="schedules_publish_to_eligible_audience",
    )
    challenge = _open_confirmation(
        publisher,
        context,
        capability="shop.publish_marketing_announcements",
    )
    assert challenge["step_up"] == "totp"
    assert challenge["dual_control"] is True

    approve_second_actor(
        challenge["token"],
        actor=approver,
        step_up=_step_up(approver, "totp"),
    )
    confirmed = authorize_command(
        actor=publisher,
        capability="shop.publish_marketing_announcements",
        context=context,
        token=challenge["token"],
        typed_confirmation="ENVIAR 500",
        step_up=_step_up(publisher, "totp"),
    )

    assert confirmed.second_actor_id == approver.pk
    assert MarketingQuotaUsage.objects.get().target_count == 500


def test_mixed_dispatch_is_decided_by_the_message_half_not_by_the_sum(customer_base):
    """Postagem não empurra o disparo para a faixa de cima, e nem segura embaixo.

    Somar 498 pessoas com 2 murais dava 500 e mudava a cerimônia de faixa por causa de
    duas postagens — que se apagam com um toque e não custam por pessoa. Quem manda num
    disparo misto é a metade irreversível: as 498 mensagens.
    """
    customer_base(2_500)
    context = authorization_context(
        action="approve",
        resource_ref="announcement:mixed-500",
        base_version=1,
        audience_count=498,
        platforms=("whatsapp", "instagram", "facebook"),
        scheduled_for=timezone.now() + timedelta(hours=1),
        consequence="schedules_publish_to_eligible_audience",
    )

    requirement = requirement_for(context)

    assert requirement.typed_phrase == "ENVIAR 498"
    assert requirement.step_up_level == "password"
    assert requirement.dual_control is False
    # E a quota continua somando as duas grandezas: 498 mensagens + 2 postagens saem
    # da casa hoje, e é isso que o teto diário conta.
    assert external_destination_count(context) == 500
    assert direct_message_recipient_count(context) == 498
    assert public_post_count(context) == 2


def test_the_same_dispatch_changes_ceremony_when_the_house_changes_size(customer_base):
    """O mesmo disparo, duas casas: 300 pessoas é muito numa, rotina na outra.

    Era isto que um número no código não conseguia dizer. Com 2.500 clientes, 300
    mensagens são 12% da casa e pedem frase digitada e senha; com 100.000, são 0,3% e
    pedem o resumo — o mesmo resumo que 2.000 pediriam lá, porque lá o limiar é 714,
    onde o teto de gasto chega antes da fatia.
    """
    payload = {
        "action": "approve",
        "resource_ref": "announcement:same-300",
        "base_version": 1,
        "audience_count": 300,
        "platforms": ("whatsapp",),
        "consequence": "publishes_now_to_eligible_audience",
    }
    context = authorization_context(**payload)

    customer_base(2_500)
    assert requirement_for(context) == AuthorizationRequirement(
        "typed", "password", False, "ENVIAR 300"
    )

    customer_base(100_000)
    assert requirement_for(context) == AuthorizationRequirement("summary", "none", False, "")


def test_public_post_asks_for_the_summary_however_many_platforms(customer_base):
    """Plataforma não é pessoa. Nenhum número de murais vira senha.

    Postagem é apagável, não tem custo por pessoa e não chega em ninguém que não tenha
    ido olhar. Contar plataformas contra um limiar de gente era medir peso com metro —
    e com a base pequena deste teste (piso em 10) três postagens pediriam senha.
    """
    customer_base(0)
    context = authorization_context(
        action="approve",
        resource_ref="announcement:public-only",
        base_version=1,
        audience_count=498,
        platforms=("instagram", "facebook", "google_business"),
        consequence="publishes_now_to_eligible_audience",
    )

    requirement = requirement_for(context)

    assert requirement == AuthorizationRequirement("summary", "none", False, "")
    assert direct_message_recipient_count(context) == 0
    assert public_post_count(context) == 3


def test_firing_asks_for_nothing_because_it_publishes_nothing(customer_base):
    """Disparar cria um rascunho em revisão; a revisão é o portão, não o disparo.

    O módulo já tratava o disparo como consequência zero — `_reserve_external_quota`
    o isenta da quota de destinos externos. Enquanto ele pedia frase digitada e senha,
    o gestor pagava duas vezes o preço da mesma entrega: uma para preparar, outra para
    aprovar. O token continua sendo emitido, porque é ele que ancora versão, permissão
    e congelamento.
    """
    customer_base(2_500)
    fire = authorization_context(
        action="fire",
        resource_ref="campaign:7",
        base_version=1,
        audience_count=480,
        platforms=("instagram", "whatsapp"),
        consequence="creates_review_announcement",
    )
    approve = authorization_context(
        action="approve",
        resource_ref="announcement:7",
        base_version=1,
        audience_count=480,
        platforms=("instagram", "whatsapp"),
        consequence="publishes_now_to_eligible_audience",
    )

    assert requirement_for(fire) == AuthorizationRequirement("none", "none", False, "")
    assert requirement_for(approve).typed_phrase == "ENVIAR 480"
    assert requirement_for(approve).step_up_level == "password"


def test_a_large_retry_still_escalates_because_it_still_sends(customer_base):
    """Reentregar é entregar. O que mudou foi o preço do pequeno, não o do grande."""
    customer_base(2_500)
    small = authorization_context(
        action="retry_delivery",
        resource_ref="announcement:88",
        base_version=2,
        audience_count=3,
        platforms=("whatsapp",),
        consequence="publishes_now_to_eligible_audience",
    )
    large = authorization_context(
        action="retry_delivery",
        resource_ref="announcement:89",
        base_version=2,
        audience_count=800,
        platforms=("whatsapp",),
        scheduled_for=timezone.now() + timedelta(hours=1),
        consequence="schedules_publish_to_eligible_audience",
    )

    assert requirement_for(small) == AuthorizationRequirement("summary", "none", False, "")
    assert requirement_for(large) == AuthorizationRequirement(
        "typed", "totp", True, "ENVIAR 800"
    )


def test_a_big_audience_is_not_cheaper_to_send_just_because_it_was_scheduled(customer_base):
    """Agendar adia o efeito; não o diminui. Antes, o agora escalava e o agendado não."""
    customer_base(2_500)
    payload = {
        "action": "approve",
        "resource_ref": "announcement:77",
        "base_version": 1,
        "audience_count": 120,
        "platforms": ("whatsapp",),
        "consequence": "publishes_now_to_eligible_audience",
    }
    now = authorization_context(**payload)
    later = authorization_context(
        **{**payload, "scheduled_for": timezone.now() + timedelta(hours=2)}
    )

    assert requirement_for(now) == requirement_for(later)
    assert requirement_for(later).typed_phrase == "ENVIAR 120"
    assert requirement_for(later).step_up_level == "password"


def test_second_actor_password_change_invalidates_open_dual_control(customer_base):
    customer_base(2_500)
    publisher = _actor("publisher-dual-revoked", "publish_marketing_announcements")
    approver = _actor("approver-dual-revoked", "approve_marketing_announcements")
    context = authorization_context(
        action="approve",
        resource_ref="announcement:501",
        base_version=1,
        audience_count=500,
        scheduled_for=timezone.now() + timedelta(hours=1),
        consequence="schedules_publish_to_eligible_audience",
    )
    challenge = _open_confirmation(
        publisher,
        context,
        capability="shop.publish_marketing_announcements",
    )
    approve_second_actor(
        challenge["token"],
        actor=approver,
        step_up=_step_up(approver, "totp"),
    )
    approver.set_password("credencial-rotacionada")
    approver.save(update_fields=["password"])

    with pytest.raises(MarketingAuthorizationError) as changed:
        authorize_command(
            actor=publisher,
            capability="shop.publish_marketing_announcements",
            context=context,
            token=challenge["token"],
            typed_confirmation="ENVIAR 500",
            step_up=_step_up(publisher, "totp"),
        )

    assert changed.value.code == "dual_control_authorization_changed"
    assert MarketingQuotaUsage.objects.count() == 0


def test_threshold_policy_blocks_oversize_and_immediate_large_blast():
    too_large = authorization_context(
        action="approve",
        resource_ref="announcement:1",
        base_version=1,
        audience_count=5_001,
        consequence="schedules_publish_to_eligible_audience",
        scheduled_for=timezone.now() + timedelta(hours=1),
    )
    with pytest.raises(MarketingAuthorizationError) as oversized:
        requirement_for(too_large)
    assert oversized.value.code == "marketing_blast_limit_exceeded"

    immediate = authorization_context(
        action="approve",
        resource_ref="announcement:1",
        base_version=1,
        audience_count=2_000,
        consequence="publishes_now_to_eligible_audience",
    )
    with pytest.raises(MarketingAuthorizationError) as must_schedule:
        requirement_for(immediate)
    assert must_schedule.value.code == "large_blast_must_be_scheduled"


def test_daily_external_target_quota_returns_retry_after_and_is_append_only():
    actor = _actor("publisher-quota", "publish_marketing_announcements")
    now = timezone.now()
    reservation = MarketingQuotaUsage.objects.create(
        actor=actor,
        action="approve",
        resource_ref="announcement:previous",
        target_count=5_000,
        occurred_at=now,
        retention_until=now + timedelta(days=365),
    )
    context = authorization_context(
        action="approve",
        resource_ref="announcement:next",
        base_version=1,
        audience_count=1,
        consequence="publishes_now_to_eligible_audience",
    )
    challenge = _open_confirmation(
        actor,
        context,
        capability="shop.publish_marketing_announcements",
        now=now,
    )

    with pytest.raises(MarketingAuthorizationError) as limited:
        authorize_command(
            actor=actor,
            capability="shop.publish_marketing_announcements",
            context=context,
            token=challenge["token"],
            typed_confirmation="",
            step_up=_step_up(actor, "password", at=now),
            now=now,
        )

    assert limited.value.code == "marketing_daily_target_quota_exceeded"
    assert limited.value.retry_after == 86_400
    assert MarketingQuotaUsage.objects.count() == 1
    reservation.target_count = 1
    with pytest.raises(ValidationError, match="imutáveis"):
        reservation.save(update_fields=["target_count"])
    with pytest.raises(ValidationError, match="não podem ser apagadas"):
        reservation.delete()


def test_emergency_freeze_is_persisted_and_invalidates_open_confirmation():
    publisher = _actor("publisher-freeze", "publish_marketing_announcements")
    security = _actor("security-freeze", "freeze_marketing")
    context = authorization_context(
        action="approve",
        resource_ref="announcement:7",
        base_version=1,
        audience_count=10,
        scheduled_for=timezone.now() + timedelta(hours=1),
        consequence="schedules_publish_to_eligible_audience",
    )
    challenge = _open_confirmation(
        publisher,
        context,
        capability="shop.publish_marketing_announcements",
    )

    frozen = activate_freeze(actor=security, reason="Suspeita de credencial comprometida")

    assert frozen.frozen is True
    assert MarketingSafetyState.objects.get().generation > 1
    with pytest.raises(MarketingAuthorizationError) as blocked:
        authorize_command(
            actor=publisher,
            capability="shop.publish_marketing_announcements",
            context=context,
            token=challenge["token"],
        )
    assert blocked.value.code == "marketing_frozen"


def test_emergency_freeze_suppresses_only_reversible_work():
    from shopman.orderman.models import Directive

    from shopman.shop.directives import ANNOUNCEMENT_PUBLISH
    from shopman.shop.models import DeliveryTarget
    from shopman.shop.services.marketing_delivery_worker import fanout_in_chunks
    from shopman.shop.tests.test_marketing_delivery_ledger import _graph

    pending_outbox, _ = _graph(suffix="freeze-pending", target_keys=())
    MarketingOutbox.objects.filter(pk=pending_outbox.pk).update(
        state=MarketingOutbox.State.PENDING,
        dispatch_ref="",
        dispatched_at=None,
    )
    delivery_outbox, members = _graph(
        suffix="freeze-targets",
        target_keys=("accepted", "unknown", "reversible"),
    )
    fanout_in_chunks(
        delivery_outbox.ref,
        member_ids=[member.pk for member in members],
    )
    targets = list(DeliveryTarget.objects.filter(outbox=delivery_outbox).order_by("pk"))
    DeliveryTarget.objects.filter(pk=targets[0].pk).update(
        state=DeliveryTarget.State.ACCEPTED
    )
    DeliveryTarget.objects.filter(pk=targets[1].pk).update(
        state=DeliveryTarget.State.UNKNOWN
    )
    directive = Directive.objects.create(topic=ANNOUNCEMENT_PUBLISH)
    security = _actor("security-suppress", "freeze_marketing")

    activate_freeze(actor=security, reason="Bloqueio preventivo do canal")

    pending_outbox.refresh_from_db()
    directive.refresh_from_db()
    current_states = list(
        DeliveryTarget.objects.filter(outbox=delivery_outbox)
        .order_by("pk")
        .values_list("state", flat=True)
    )
    event = MarketingSecurityEvent.objects.get(event_type="freeze_activated")
    assert pending_outbox.state == MarketingOutbox.State.CANCELLED
    assert directive.status == Directive.Status.FAILED
    assert current_states == [
        DeliveryTarget.State.ACCEPTED,
        DeliveryTarget.State.UNKNOWN,
        DeliveryTarget.State.CANCELLED,
    ]
    assert event.facts["suppressed_outbox_count"] == 1
    assert event.facts["suppressed_target_count"] == 1
    assert event.facts["suppressed_directive_count"] == 1


def test_unfreeze_requires_totp_and_distinct_security_actor_after_reconciliation():
    primary = _actor("security-primary", "freeze_marketing")
    second = _actor("security-second", "freeze_marketing")
    frozen = activate_freeze(actor=primary, reason="Exercício local de contenção")

    with pytest.raises(MarketingAuthorizationRequired) as required:
        deactivate_freeze(
            actor=primary,
            base_version=frozen.version,
            token="",
            step_up=None,
        )
    challenge = issue_confirmation(required.value, actor=primary)["confirmation"]
    assert challenge["step_up"] == "totp"
    assert challenge["dual_control"] is True
    approve_second_actor(
        challenge["token"],
        actor=second,
        step_up=_step_up(second, "totp"),
    )

    active = deactivate_freeze(
        actor=primary,
        base_version=frozen.version,
        token=challenge["token"],
        step_up=_step_up(primary, "totp"),
    )

    assert active.frozen is False
    assert active.version == frozen.version + 1


@pytest.mark.django_db(transaction=True)
def test_security_authorization_migration_reverses_and_reapplies_cleanly():
    before = [("shop", "0034_marketing_delivery_recovery")]
    after = [("shop", "0035_marketing_security_authorization")]
    security_tables = {
        "shop_marketingconfirmation",
        "shop_marketingquotausage",
        "shop_marketingsafetystate",
        "shop_marketingsecurityevent",
    }

    executor = MigrationExecutor(connection)
    executor.migrate(before)
    assert security_tables.isdisjoint(connection.introspection.table_names())

    executor = MigrationExecutor(connection)
    executor.migrate(after)
    assert security_tables.issubset(connection.introspection.table_names())
    with connection.cursor() as cursor:
        audit_columns = {
            column.name
            for column in connection.introspection.get_table_description(
                cursor, "shop_marketingauditevent"
            )
        }
    assert "decision_reason" in audit_columns

    executor = MigrationExecutor(connection)
    executor.migrate(before)
    assert security_tables.isdisjoint(connection.introspection.table_names())

    MigrationExecutor(connection).migrate(after)
