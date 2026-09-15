"""Admin-only OTP verification and console-authorized browser enrollment."""
from __future__ import annotations

import base64
import io
import time
from urllib.parse import unquote, urlsplit

import qrcode
from django.contrib import admin
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_http_methods
from django_otp import login as otp_login
from django_otp import verify_token
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice

from shopman.backstage.forms.two_factor import (
    EnrollmentPasswordForm,
    EnrollmentTokenForm,
    RecoveryConfirmationForm,
    VerificationForm,
)
from shopman.backstage.models import AdminTwoFactorEnrollment
from shopman.backstage.services.admin_two_factor import (
    PENDING_NAME,
    RECOVERY_NAME,
    check_enrollment_password,
    confirm_enrollment_token,
    finish_enrollment,
)

GRANT = "admin_2fa_enrollment"


def _safe_next(request):
    nxt = request.POST.get("next") or request.GET.get("next") or ""
    try:
        parsed = urlsplit(nxt)
        path = unquote(parsed.path)
    except ValueError:
        return reverse("admin:index")
    if (nxt.startswith("/admin/") and not parsed.netloc and "\\" not in nxt
            and "%" not in parsed.path and not any(ord(c) < 32 for c in nxt)
            and not any(p in {".", ".."} for p in path.split("/"))):
        return nxt
    return reverse("admin:index")


def _staff(request):
    return request.user.is_authenticated and request.user.is_active and request.user.is_staff


def _login(request):
    return redirect(reverse("admin:login") + "?" + urlencode({"next": request.get_full_path()}))


def _verified(request):
    return bool(getattr(request.user, "is_verified", lambda: False)())


def _page(request, **context):
    site_context = admin.site.each_context(request)
    response = render(request, "two_factor/verify.html", {
        **site_context, "site_title": site_context.get("site_header", admin.site.site_header),
        "title": "Verificação em duas etapas", **context,
    })
    response["Referrer-Policy"] = "no-referrer"
    response["X-Frame-Options"] = "DENY"
    return response


@never_cache
@csrf_protect
@sensitive_post_parameters()
@sensitive_variables()
@require_http_methods(["GET", "POST"])
def admin_2fa_verify(request):
    if not _staff(request):
        return _login(request)
    next_url = _safe_next(request)
    if _verified(request):
        return HttpResponseRedirect(next_url)
    devices = [(d, "App autenticador: " + d.name) for d in TOTPDevice.objects.filter(user=request.user, confirmed=True)]
    devices += [(d, "Código de recuperação") for d in StaticDevice.objects.filter(user=request.user, confirmed=True, name=RECOVERY_NAME)]
    data = request.POST.copy() if request.method == "POST" else None
    if data is not None and not data.get("device") and devices:
        data["device"] = devices[0][0].persistent_id
    form = VerificationForm(data, devices=devices)
    if request.method == "POST" and devices and form.is_valid():
        device = verify_token(request.user, form.cleaned_data["device"], form.cleaned_data["token"])
        if device:
            otp_login(request, device)
            request.session.cycle_key()
            return HttpResponseRedirect(next_url)
        form.add_error("token", "Código inválido ou temporariamente bloqueado. Aguarde e tente novamente.")
    return _page(request, form=form if devices else None, heading="Verificação em duas etapas",
                 note="Use seu app autenticador ou um código de recuperação guardado." if devices else
                      "Inscrição ainda não concluída. A operação deve preparar sua conta com setup_admin_totp.",
                 enroll_url=reverse("admin_2fa_enroll") if not devices else None, button="Entrar")


@never_cache
@csrf_protect
@sensitive_post_parameters()
@sensitive_variables()
@require_http_methods(["GET", "POST"])
def admin_2fa_enroll(request):
    if not _staff(request):
        return _login(request)
    # Password alone must never replace an already working second factor.
    if (TOTPDevice.objects.filter(user=request.user, confirmed=True).exists()
            or AdminTwoFactorEnrollment.objects.filter(user=request.user).exists()) and not _verified(request):
        return redirect(reverse("admin_2fa_verify") + "?" + urlencode({"next": reverse("admin_2fa_enroll")}))
    device = TOTPDevice.objects.filter(user=request.user, confirmed=False, name=PENDING_NAME).first()
    if device is None:
        return _page(request, heading="Inscrição em duas etapas",
                     note="Peça à operação para preparar a inscrição desta conta. Nenhum dispositivo será substituído aqui.")
    grant = request.session.get(GRANT, {})
    authorized = grant.get("device") == device.pk and grant.get("until", 0) > time.time()
    data = request.POST if request.method == "POST" else None
    if not authorized:
        request.session.pop(GRANT, None)
        form = EnrollmentPasswordForm(data)
        if data is not None and form.is_valid():
            if check_enrollment_password(request.user, device.pk, form.cleaned_data["password"]):
                request.session[GRANT] = {"device": device.pk, "until": time.time() + 600}
                return redirect("admin_2fa_enroll")
            form.add_error("password", "Senha inválida ou temporariamente bloqueada. Aguarde e tente novamente.")
        return _page(request, heading="Preparar seu autenticador", form=form, button="Continuar",
                     note="Confirme sua senha. A inscrição não muda a exigência de 2FA dos outros acessos.")
    try:
        if grant.get("recovery"):
            form = RecoveryConfirmationForm(data)
            if data is not None and form.is_valid():
                confirmed = finish_enrollment(request.user, device.pk, grant["recovery"], form.cleaned_data["token"])
                if confirmed:
                    request.session.pop(GRANT, None)
                    otp_login(request, confirmed)
                    request.session.cycle_key()
                    return _page(request, heading="Inscrição confirmada",
                                 note="2FA foi ativado para seu acesso ao Admin. Restam nove códigos de recuperação de uso único. Guarde-os fora deste dispositivo.",
                                 admin_url=reverse("admin:index"))
                form.add_error("token", "Código inválido ou temporariamente bloqueado.")
            return _page(request, heading="Confirmar a recuperação", form=form, button="Concluir inscrição",
                         note="Use um dos códigos que você guardou. Ele será consumido; os outros nove ficam disponíveis. Se perdeu a lista, peça à operação para reiniciar a inscrição.")
        form = EnrollmentTokenForm(data)
        if data is not None and form.is_valid():
            result = confirm_enrollment_token(request.user, device.pk, form.cleaned_data["token"])
            if result:
                recovery_id, codes = result
                request.session[GRANT] = {**grant, "recovery": recovery_id}
                return _page(request, heading="Guarde seus códigos de recuperação", codes=codes,
                             form=RecoveryConfirmationForm(), button="Concluir inscrição",
                             note="Guarde esta lista em local seguro, fora do celular. Ela só aparece agora. Digite um código abaixo para confirmar a recuperação.")
            form.add_error("token", "Código inválido ou temporariamente bloqueado.")
        image = qrcode.make(device.config_url)
        output = io.BytesIO()
        image.save(output, format="PNG")
        return _page(request, heading="Cadastre seu autenticador", form=form, button="Validar código",
                     qr=base64.b64encode(output.getvalue()).decode(),
                     note="Escaneie o QR no seu app autenticador e digite o código de seis dígitos. Não compartilhe o QR.")
    except (TOTPDevice.DoesNotExist, StaticDevice.DoesNotExist):
        request.session.pop(GRANT, None)
        return redirect("admin_2fa_enroll")
