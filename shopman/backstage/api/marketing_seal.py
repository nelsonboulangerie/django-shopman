"""O selo do Marketing com a digital do dispositivo e a segunda pessoa por push.

Decisão do dono (SUITE-UX §15, 03/10/2026): o envio se confirma com a digital do
dispositivo (a frase digitada fica como alternativa), e acima do limiar outra pessoa
confirma no celular dela, chamada por push. Prévia: ``v4/marketing-decisoes.jpg`` (b),
pinos 6 a 8.

Também aqui: a foto do lote tirada na revisão ("Tirar outra", MKT-17).

Nada disto afrouxa o selo: a digital vale só para a confirmação para a qual foi
pedida, a segunda pessoa continua precisando ser outra, com a capacidade de aprovar
e publicar, e a confirmação do comando continua sendo consumida dentro da transação
do comando (``marketing_security.authorize_command``).
"""

from __future__ import annotations

import io
import uuid

from rest_framework.response import Response

from shopman.backstage.api.marketing import (
    _DANGEROUS_THROTTLES,
    _authorization_error_response,
    _CampaignBase,
    _unknown_command_fields,
)

#: A foto do lote: o que a câmera do celular entrega, com folga, e nada além disso.
PHOTO_MAX_BYTES = 12 * 1024 * 1024
PHOTO_MAX_SIDE = 2048
PHOTO_DIR = "marketing/announcements"


def _payload(request) -> dict:
    return request.data if isinstance(request.data, dict) else {}


def _passkey_error(exc) -> Response:
    return Response({"code": "device_unavailable", "detail": str(exc)}, status=422)


class OperatorPasskeyRegistrationOptionsView(_CampaignBase):
    """Cadastrar a digital deste dispositivo: o desafio."""

    permission_map = {"POST": "shop.view_marketing"}
    throttle_classes = list(_DANGEROUS_THROTTLES)

    def post(self, request):
        from shopman.shop.services.operator_passkey import OperatorPasskeyError, registration_options

        try:
            return Response({"options": registration_options(request, user=request.user)})
        except OperatorPasskeyError as exc:
            return _passkey_error(exc)


class OperatorPasskeyRegistrationView(_CampaignBase):
    """Cadastrar a digital deste dispositivo: conferir o que o navegador criou."""

    permission_map = {"POST": "shop.view_marketing"}
    throttle_classes = list(_DANGEROUS_THROTTLES)

    def post(self, request):
        from shopman.shop.services.operator_passkey import OperatorPasskeyError, verify_registration

        payload = _payload(request)
        unexpected = sorted(set(payload) - {"credential", "label"})
        if unexpected:
            return _unknown_command_fields(unexpected)
        credential = payload.get("credential")
        if not isinstance(credential, dict):
            return Response({"code": "invalid_credential", "detail": "A credencial veio vazia."}, status=422)
        try:
            passkey = verify_registration(
                request, user=request.user, credential=credential, label=str(payload.get("label") or "")
            )
        except OperatorPasskeyError as exc:
            return _passkey_error(exc)
        return Response({"ok": True, "label": passkey.label})


def _confirmation_for_device(request, payload):
    """A confirmação que a digital vai assinar: pelo token (quem pediu) ou pela ref
    (a segunda pessoa, que só tem o pedido do push)."""
    from shopman.shop.models import MarketingConfirmation
    from shopman.shop.services.marketing_security import _token_hash, second_control_summary

    token = str(payload.get("confirmation_token") or "").strip()
    if token:
        confirmation = MarketingConfirmation.objects.filter(token_hash=_token_hash(token)).first()
        if confirmation is None or confirmation.actor_id != request.user.pk:
            return None
        return confirmation
    ref = str(payload.get("confirmation_ref") or "").strip()
    if not ref:
        return None
    # A leitura do resumo já confere quem pode ser a segunda pessoa.
    summary = second_control_summary(ref, actor=request.user)
    if summary["is_requester"]:
        return None
    try:
        return MarketingConfirmation.objects.filter(ref=uuid.UUID(ref)).first()
    except ValueError:
        return None


class MarketingDeviceStepUpOptionsView(_CampaignBase):
    """O desafio da digital, preso a UMA confirmação."""

    permission_map = {"POST": "shop.view_marketing"}
    throttle_classes = list(_DANGEROUS_THROTTLES)

    def post(self, request):
        from shopman.shop.services.marketing_security import (
            MarketingAuthorizationError,
            MarketingAuthorizationRequired,
        )
        from shopman.shop.services.operator_passkey import OperatorPasskeyError, assertion_options

        payload = _payload(request)
        unexpected = sorted(set(payload) - {"confirmation_token", "confirmation_ref"})
        if unexpected:
            return _unknown_command_fields(unexpected)
        try:
            confirmation = _confirmation_for_device(request, payload)
        except (MarketingAuthorizationRequired, MarketingAuthorizationError) as exc:
            return _authorization_error_response(exc, request)
        if confirmation is None:
            return Response(
                {"code": "confirmation_invalid", "detail": "Este resumo não existe mais. Revise de novo."},
                status=422,
            )
        try:
            options = assertion_options(request, user=request.user, confirmation_ref=str(confirmation.ref))
        except OperatorPasskeyError as exc:
            return Response({"code": "no_device_passkey", "detail": str(exc)}, status=409)
        return Response({"options": options})


class MarketingDeviceStepUpView(_CampaignBase):
    """Conferir a assinatura do dispositivo e registrar a digital para aquela confirmação."""

    permission_map = {"POST": "shop.view_marketing"}
    throttle_classes = list(_DANGEROUS_THROTTLES)

    def post(self, request):
        from shopman.shop.services.marketing_security import record_step_up
        from shopman.shop.services.operator_passkey import OperatorPasskeyError, verify_assertion

        payload = _payload(request)
        unexpected = sorted(set(payload) - {"credential"})
        if unexpected:
            return _unknown_command_fields(unexpected)
        credential = payload.get("credential")
        if not isinstance(credential, dict):
            return Response({"code": "invalid_credential", "detail": "A digital veio vazia."}, status=422)
        try:
            result = verify_assertion(request, user=request.user, credential=credential)
        except OperatorPasskeyError as exc:
            return Response(
                {"code": "step_up_failed", "detail": str(exc), "field_errors": {"credential": [str(exc)]}},
                status=403,
            )
        return Response(
            {
                "ok": True,
                "step_up": record_step_up(request, level="device", confirmation_ref=result.confirmation_ref),
            }
        )


class MarketingSecondControlRequestView(_CampaignBase):
    """Chamar a segunda pessoa por push (MKT-19)."""

    permission_map = {"POST": "shop.view_marketing"}
    throttle_classes = list(_DANGEROUS_THROTTLES)

    def post(self, request):
        from shopman.shop.services.marketing_security import (
            MarketingAuthorizationError,
            MarketingAuthorizationRequired,
            request_second_control,
        )

        payload = _payload(request)
        unexpected = sorted(set(payload) - {"confirmation_token"})
        if unexpected:
            return _unknown_command_fields(unexpected)
        try:
            called = request_second_control(str(payload.get("confirmation_token") or ""), actor=request.user)
        except (MarketingAuthorizationRequired, MarketingAuthorizationError) as exc:
            return _authorization_error_response(exc, request)
        return Response({"ok": True, "called": called})


class MarketingSecondControlView(_CampaignBase):
    """O pedido aberto no celular da segunda pessoa: ler o resumo e confirmar."""

    permission_map = {"GET": "shop.view_marketing", "POST": "shop.view_marketing"}
    throttle_classes = list(_DANGEROUS_THROTTLES)

    def get(self, request, ref: str):
        from shopman.shop.services.marketing_security import (
            MarketingAuthorizationError,
            MarketingAuthorizationRequired,
            second_control_summary,
        )

        try:
            return Response({"second_control": second_control_summary(ref, actor=request.user)})
        except (MarketingAuthorizationRequired, MarketingAuthorizationError) as exc:
            return _authorization_error_response(exc, request)

    def post(self, request, ref: str):
        from shopman.shop.services.marketing_security import (
            MarketingAuthorizationError,
            MarketingAuthorizationRequired,
            approve_second_actor,
            second_control_summary,
            step_up_evidence_from_session,
        )

        if _payload(request):
            return _unknown_command_fields(sorted(_payload(request)))
        try:
            approve_second_actor(
                actor=request.user,
                step_up=step_up_evidence_from_session(request),
                confirmation_ref=ref,
            )
            return Response({"ok": True, "second_control": second_control_summary(ref, actor=request.user)})
        except (MarketingAuthorizationRequired, MarketingAuthorizationError) as exc:
            return _authorization_error_response(exc, request)


class MarketingAnnouncementPhotoView(_CampaignBase):
    """"Tirar outra" (MKT-17): a foto do lote pela câmera do dispositivo, sem sair da revisão.

    A foto não muda o anúncio sozinha: a resposta devolve o endereço, e ele viaja junto
    com a aprovação (``image_url`` das edições), como o texto. Assim o selo continua
    congelando exatamente o que a pessoa conferiu. A imagem é relida e regravada em
    JPEG (sem os metadados da câmera, como a localização), com o lado maior limitado.
    """

    permission_map = {
        "POST": (
            "shop.approve_marketing_announcements",
            "shop.publish_marketing_announcements",
        ),
    }
    throttle_classes = list(_DANGEROUS_THROTTLES)

    def post(self, request, pk: int):
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage
        from PIL import Image, ImageOps, UnidentifiedImageError

        from shopman.shop.models import Announcement, AnnouncementStatus

        announcement = Announcement.objects.filter(pk=pk).first()
        if announcement is None:
            return Response({"code": "announcement_not_found", "detail": "Anúncio não encontrado."}, status=404)
        if announcement.status != AnnouncementStatus.PENDING_REVIEW:
            return Response(
                {"code": "announcement_decided", "detail": "Este anúncio já foi decidido; a foto não muda mais."},
                status=409,
            )
        upload = request.FILES.get("photo")
        if upload is None:
            return Response({"code": "photo_required", "detail": "A foto não chegou.", "field": "photo"}, status=422)
        if upload.size > PHOTO_MAX_BYTES:
            return Response(
                {"code": "photo_too_large", "detail": "A foto passou de 12 MB. Tire de novo.", "field": "photo"},
                status=422,
            )
        try:
            image = Image.open(upload)
            image.load()
        except (UnidentifiedImageError, OSError, ValueError):
            return Response(
                {"code": "photo_invalid", "detail": "Não deu para ler esta foto. Tire de novo.", "field": "photo"},
                status=422,
            )
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((PHOTO_MAX_SIDE, PHOTO_MAX_SIDE))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=86, optimize=True)
        path = default_storage.save(f"{PHOTO_DIR}/{pk}/{uuid.uuid4().hex}.jpg", ContentFile(buffer.getvalue()))
        return Response({"image_url": default_storage.url(path)})
