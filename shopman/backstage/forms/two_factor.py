from django import forms
from unfold.widgets import UnfoldAdminPasswordWidget, UnfoldAdminSelectWidget, UnfoldAdminTextInputWidget


class VerificationForm(forms.Form):
    device = forms.ChoiceField(label="Método de verificação", widget=UnfoldAdminSelectWidget)
    token = forms.CharField(label="Código", max_length=32, strip=True,
                           widget=UnfoldAdminPasswordWidget(attrs={"autocomplete": "one-time-code", "autofocus": True}))

    def __init__(self, *args, devices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["device"].choices = [(d.persistent_id, label) for d, label in devices]


class EnrollmentPasswordForm(forms.Form):
    password = forms.CharField(label="Confirme sua senha", strip=False,
                              widget=UnfoldAdminPasswordWidget(attrs={"autocomplete": "current-password"}))


class EnrollmentTokenForm(forms.Form):
    token = forms.RegexField(r"^[0-9]{6}$", label="Código do app autenticador", max_length=6,
                            widget=UnfoldAdminTextInputWidget(attrs={"inputmode": "numeric", "autocomplete": "one-time-code"}))


class RecoveryConfirmationForm(forms.Form):
    token = forms.CharField(label="Um dos códigos de recuperação que você guardou", max_length=16,
                           widget=UnfoldAdminPasswordWidget(attrs={"autocomplete": "off"}))
