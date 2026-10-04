"""V6-MKT: o selo com a digital do dispositivo e a segunda pessoa por push.

Decisão do dono (SUITE-UX §15): confirma com a digital do dispositivo, a frase
digitada fica como alternativa, e acima do limiar outra pessoa confirma no celular
dela. A criptografia do WebAuthn é da biblioteca (``webauthn``); aqui se trava o que
é nosso: a digital vale só para a confirmação para a qual foi pedida, dispensa a
frase e a senha, e a segunda pessoa pela ``ref`` continua precisando ser outra, com a
capacidade e com a digital ou o autenticador.
"""

from __future__ import annotations

import io
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from shopman.shop.models import Announcement, AnnouncementStatus, UserNotification
from shopman.shop.services.marketing_security import (
    MarketingAuthorizationError,
    MarketingAuthorizationRequired,
    StepUpEvidence,
    approve_second_actor,
    authorization_context,
    authorize_command,
    issue_confirmation,
    permission_fingerprint,
    request_second_control,
    safety_state,
    second_control_summary,
)
from shopman.shop.services.user_notifications import MARKETING_SECOND_CONTROL, reconcile_marketing_second_control

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture(autouse=True)
def customer_base(monkeypatch):
    from shopman.shop.services import marketing_ceremony

    monkeypatch.setattr(marketing_ceremony, "customer_base_size", lambda **_: 2_500)


def _actor(username: str, *codenames: str):
    actor = User.objects.create_user(username=username, password="senha-segura", is_staff=True)
    actor.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    return actor


def _evidence(actor, level: str, *, ref: str = "", at=None) -> StepUpEvidence:
    state = safety_state()
    return StepUpEvidence(
        actor_id=actor.pk,
        level=level,
        verified_at=at or timezone.now(),
        auth_hash=actor.get_session_auth_hash(),
        permission_fingerprint=permission_fingerprint(actor, state=state),
        safety_generation=state.generation,
        confirmation_ref=ref,
    )


def _context(count: int, *, resource: str = "announcement:900"):
    return authorization_context(
        action="approve",
        resource_ref=resource,
        base_version=1,
        artifact_hash="a" * 64,
        audience_hash="b" * 64,
        audience_count=count,
        platforms=("whatsapp",),
        scheduled_for=timezone.now() + timedelta(hours=1),
        consequence="schedules_publish_to_eligible_audience",
    )


def _open(actor, context):
    with pytest.raises(MarketingAuthorizationRequired) as caught:
        authorize_command(actor=actor, capability="shop.publish_marketing_announcements", context=context, token="")
    return issue_confirmation(caught.value, actor=actor)["confirmation"]


def test_the_challenge_says_whether_the_device_is_registered_and_the_dual_threshold(customer_base):
    from shopman.shop.models import OperatorPasskey

    publisher = _actor("seal-device", "publish_marketing_announcements")
    challenge = _open(publisher, _context(86))
    assert challenge["device_available"] is False
    assert challenge["dual_control_threshold"] == 500

    OperatorPasskey.objects.create(user=publisher, credential_id="cred-1", public_key="pk")
    assert _open(publisher, _context(86, resource="announcement:901"))["device_available"] is True


def test_the_device_seal_replaces_the_typed_phrase_and_the_password_for_its_confirmation(customer_base):
    publisher = _actor("seal-phrase", "publish_marketing_announcements")
    context = _context(86)  # 86 ≥ 50: frase + senha
    challenge = _open(publisher, context)
    assert challenge["typed_phrase"] == "ENVIAR 86"
    assert challenge["step_up"] == "password"

    confirmed = authorize_command(
        actor=publisher,
        capability="shop.publish_marketing_announcements",
        context=context,
        token=challenge["token"],
        typed_confirmation="",
        step_up=_evidence(publisher, "device", ref=challenge["ref"]),
    )
    assert confirmed.consumed_at is not None


def test_a_device_seal_for_another_confirmation_does_not_waive_the_phrase(customer_base):
    publisher = _actor("seal-other", "publish_marketing_announcements")
    context = _context(86)
    challenge = _open(publisher, context)
    with pytest.raises(MarketingAuthorizationError) as caught:
        authorize_command(
            actor=publisher,
            capability="shop.publish_marketing_announcements",
            context=context,
            token=challenge["token"],
            typed_confirmation="",
            step_up=_evidence(publisher, "device", ref="00000000-0000-0000-0000-000000000000"),
        )
    assert caught.value.code == "typed_confirmation_mismatch"


def test_the_typed_phrase_still_works_as_the_alternative(customer_base):
    publisher = _actor("seal-code", "publish_marketing_announcements")
    context = _context(86)
    challenge = _open(publisher, context)
    confirmed = authorize_command(
        actor=publisher,
        capability="shop.publish_marketing_announcements",
        context=context,
        token=challenge["token"],
        typed_confirmation="ENVIAR 86",
        step_up=_evidence(publisher, "password"),
    )
    assert confirmed.consumed_at is not None


def test_second_person_by_push_confirms_by_ref_with_the_device(customer_base):
    publisher = _actor("seal-first", "publish_marketing_announcements")
    second = _actor("seal-second", "approve_marketing_announcements")
    bystander = _actor("seal-bystander")  # sem capacidade: não é chamado
    context = _context(600)
    challenge = _open(publisher, context)
    assert challenge["dual_control"] is True

    called = request_second_control(challenge["token"], actor=publisher)
    assert called == 1
    notification = UserNotification.objects.get(source_condition=MARKETING_SECOND_CONTROL)
    assert notification.user == second
    assert notification.action_url == f"/second-control/{challenge['ref']}"
    assert not UserNotification.objects.filter(user=bystander).exists()

    summary = second_control_summary(challenge["ref"], actor=second)
    assert summary["state"] == "open"
    assert summary["is_requester"] is False
    assert summary["audience_count"] == 600

    # Quem pediu não confirma o próprio pedido.
    with pytest.raises(MarketingAuthorizationError):
        approve_second_actor(
            actor=publisher, step_up=_evidence(publisher, "device", ref=challenge["ref"]), confirmation_ref=challenge["ref"]
        )
    # Sem digital nem autenticador, a segunda pessoa não confirma.
    with pytest.raises(MarketingAuthorizationError):
        approve_second_actor(actor=second, step_up=None, confirmation_ref=challenge["ref"])

    approve_second_actor(
        actor=second, step_up=_evidence(second, "device", ref=challenge["ref"]), confirmation_ref=challenge["ref"]
    )
    assert second_control_summary(challenge["ref"], actor=publisher)["state"] == "approved"
    assert reconcile_marketing_second_control(f"marketing_confirmation:{challenge['ref']}") == 1

    confirmed = authorize_command(
        actor=publisher,
        capability="shop.publish_marketing_announcements",
        context=context,
        token=challenge["token"],
        typed_confirmation="",
        step_up=_evidence(publisher, "device", ref=challenge["ref"]),
    )
    assert confirmed.second_actor_id == second.pk


def test_bystander_cannot_read_the_second_control_summary(customer_base):
    publisher = _actor("seal-req", "publish_marketing_announcements")
    bystander = _actor("seal-nosy")
    challenge = _open(publisher, _context(600))
    with pytest.raises(MarketingAuthorizationError):
        second_control_summary(challenge["ref"], actor=bystander)


def test_device_step_up_options_need_a_registered_device(client, customer_base):
    publisher = _actor("seal-api", "publish_marketing_announcements", "view_marketing")
    client.force_login(publisher)
    challenge = _open(publisher, _context(86))
    response = client.post(
        "/api/v1/backstage/marketing/security/device/options/",
        {"confirmation_token": challenge["token"]},
        content_type="application/json",
        HTTP_ORIGIN="http://testserver",
    )
    assert response.status_code == 409
    assert response.json()["code"] == "no_device_passkey"

    from shopman.shop.models import OperatorPasskey

    OperatorPasskey.objects.create(user=publisher, credential_id="AAAA", public_key="pk")
    response = client.post(
        "/api/v1/backstage/marketing/security/device/options/",
        {"confirmation_token": challenge["token"]},
        content_type="application/json",
        HTTP_ORIGIN="http://testserver",
    )
    assert response.status_code == 200
    options = response.json()["options"]
    assert options["userVerification"] == "required"
    assert options["allowCredentials"][0]["id"] == "AAAA"
    assert client.session["operator_passkey_assertion"]["confirmation_ref"] == challenge["ref"]


# ── A foto do lote ───────────────────────────────────────────────────────────


def _jpeg() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 150, 90)).save(buffer, format="JPEG")
    return buffer.getvalue()


def test_retake_photo_is_reencoded_and_travels_with_the_approval(client, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    reviewer = _actor("seal-photo", "approve_marketing_announcements", "publish_marketing_announcements", "view_marketing")
    client.force_login(reviewer)
    announcement = Announcement.objects.create(
        status=AnnouncementStatus.PENDING_REVIEW,
        content={"body": "Croissant saindo do forno."},
        platforms=["instagram"],
        platform_content={"instagram": {"image_url": "/media/produto.jpg", "format": "feed"}},
    )
    response = client.post(
        f"/api/v1/backstage/marketing/announcements/{announcement.pk}/photo/",
        {"photo": SimpleUploadedFile("lote.jpg", _jpeg(), content_type="image/jpeg")},
    )
    assert response.status_code == 200
    image_url = response.json()["image_url"]
    assert f"marketing/announcements/{announcement.pk}/" in image_url

    junk = client.post(
        f"/api/v1/backstage/marketing/announcements/{announcement.pk}/photo/",
        {"photo": SimpleUploadedFile("x.jpg", b"isto nao e imagem", content_type="image/jpeg")},
    )
    assert junk.status_code == 422


def test_the_retaken_photo_goes_to_every_platform_that_carries_an_image(client, settings, tmp_path, monkeypatch):
    """A foto do lote vale para todo mural que já levava foto; a mensagem sem foto segue sem.

    O endereço passa pela mesma validação de mídia de sempre (host privado continua
    recusado em ``content.image_url``, trava em ``test_api_marketing_surface``).
    """
    settings.MEDIA_ROOT = str(tmp_path)
    reviewer = _actor("seal-carry", "approve_marketing_announcements", "publish_marketing_announcements", "view_marketing")
    client.force_login(reviewer)
    announcement = Announcement.objects.create(
        status=AnnouncementStatus.PENDING_REVIEW,
        content={"body": "Croissant."},
        platforms=["instagram"],
        platform_content={"instagram": {"image_url": "/media/produto.jpg", "format": "feed"}, "whatsapp": {"format": "text"}},
    )
    upload = client.post(
        f"/api/v1/backstage/marketing/announcements/{announcement.pk}/photo/",
        {"photo": SimpleUploadedFile("lote.jpg", _jpeg(), content_type="image/jpeg")},
    )
    image_url = upload.json()["image_url"]

    from shopman.shop.services import marketing_approval

    captured = {}

    def fake_approve(*_args, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("parou aqui")

    monkeypatch.setattr(marketing_approval, "approve_command", fake_approve)
    with pytest.raises(RuntimeError):
        client.post(
            f"/api/v1/backstage/marketing/announcements/{announcement.pk}/approve/",
            {
                "base_version": announcement.version,
                "publish_mode": "now",
                "publish_timezone": "America/Sao_Paulo",
                "image_url": image_url,
                "platforms": ["instagram", "whatsapp"],
            },
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="k-carry-photo",
        )
    platform_content = captured["platform_content"]
    assert platform_content["instagram"]["image_url"] == image_url
    assert "image_url" not in platform_content.get("whatsapp", {})


# ── O nome da campanha do lote ───────────────────────────────────────────────


def test_campaign_rename_migration_only_touches_the_seed_name():
    from importlib import import_module

    from django.apps import apps

    from shopman.shop.models import AnnouncementTemplate, Campaign, Trigger

    migration = import_module("shopman.shop.migrations.0089_campanha_lote_pronto")
    template = AnnouncementTemplate.objects.create(name="Saída do forno", body="{{product_name}} saiu")
    Campaign.objects.create(name="Fornada pronta", trigger=Trigger.PRODUCTION_FINISHED, template=template)
    Campaign.objects.create(name="Fornada da tarde", trigger=Trigger.PRODUCTION_FINISHED, template=template)
    migration.forward(apps, None)
    assert set(Campaign.objects.values_list("name", flat=True)) == {"Lote pronto", "Fornada da tarde"}
    migration.backward(apps, None)
    assert Campaign.objects.filter(name="Fornada pronta").exists()


def test_seed_names_operator_facing_campaigns_with_lote_not_fornada():
    """O nome da campanha aparece ao gestor (fila, histórico, cartão): é "lote" (SPEC4).

    "fornada" segue certa no texto que o CLIENTE lê (corpo, hashtag); a trava olha só
    os literais de nome de campanha do seed.
    """
    import ast
    from pathlib import Path

    import config.management.commands.seed as seed

    tree = ast.parse(Path(seed.__file__).read_text(encoding="utf-8"))
    names = [
        keyword.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg == "name" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str)
    ]
    assert "Lote pronto" in names
    assert not [name for name in names if name.lower().startswith("fornada")]
