"""Move access links from message text to native WhatsApp buttons."""

from django.db import migrations
from django.db.models import F

ACCESS_EVENT = "access_link"
ACCESS_SUBJECT = "Seu acesso à loja"
ACCESS_BODY = (
    "Pronto{customer_name_greeting}! Toque abaixo para entrar.\n"
    "{cart_note}O acesso vale por 5 minutos."
)
ACCESS_OLD_BODY = (
    "Oi{customer_name_greeting}! Use o link para entrar na loja: {access_url}\n"
    "{cart_note}Válido por 5 min."
)
ACCESS_OLD_BODIES = {
    ACCESS_OLD_BODY,
    (
        "Olá{customer_name_greeting}! Aqui está seu acesso à loja:\n"
        "{access_url}{cart_note}\n\nO link é só seu e vale por poucos minutos."
    ),
}

SITE_EVENT = "access_link_site"
SITE_SUBJECT = "Você entrou na loja"
SITE_BODY = (
    "Pronto{customer_name_greeting}! Seu acesso foi liberado.\n"
    "{cart_note}Volte à loja para continuar."
)
SITE_OLD_BODY = (
    "Pronto{customer_name_greeting}! Pode voltar ao site: você já entrou{origin_note}. 💛\n"
    "Se o site não abrir sozinho, toque aqui: {access_url}\n"
    "Não foi você? Encerre este acesso: {revoke_url}"
)

TEXTS = [
    (ACCESS_EVENT, ACCESS_SUBJECT, ACCESS_SUBJECT, ACCESS_OLD_BODY, ACCESS_BODY),
    (SITE_EVENT, SITE_SUBJECT, SITE_SUBJECT, SITE_OLD_BODY, SITE_BODY),
]

COPY_UPDATES = (
    ("LOGIN_PHONE_HEADING", "Entre com seu WhatsApp", "", "Entre pelo WhatsApp", ""),
    (
        "LOGIN_WA_WHY",
        "",
        "É por lá que avisamos cada passo do seu pedido e tiramos suas dúvidas. Sem senha.",
        "",
        "Sem senha e sem código. A mensagem pronta confirma que o número é seu.",
    ),
    (
        "LOGIN_WA_STEPS",
        "",
        "Toque no botão abaixo\nEnvie a mensagem que já vai pronta\nVolte para cá: você já estará dentro",
        "",
        "Toque em “Abrir o WhatsApp”\nEnvie a mensagem que já está pronta\nVolte para esta tela. A entrada será automática",
    ),
    (
        "LOGIN_WA_WAITING",
        "Enviou a mensagem?",
        "Assim que ela chegar, você entra por aqui, sem fazer mais nada.",
        "Mensagem enviada?",
        "Volte para esta tela. Estamos conferindo e vamos entrar automaticamente.",
    ),
)


def forwards(apps, schema_editor):
    NotificationTemplate = apps.get_model("shop", "NotificationTemplate")
    OmotenashiCopy = apps.get_model("shop", "OmotenashiCopy")

    NotificationTemplate.objects.filter(
        event=ACCESS_EVENT,
        body__in=ACCESS_OLD_BODIES,
    ).update(body=ACCESS_BODY, version=F("version") + 1)

    site, created = NotificationTemplate.objects.get_or_create(
        event=SITE_EVENT,
        defaults={
            "subject": SITE_SUBJECT,
            "body": SITE_BODY,
            "is_active": True,
        },
    )
    if not created and site.body == SITE_OLD_BODY:
        NotificationTemplate.objects.filter(pk=site.pk).update(
            body=SITE_BODY,
            version=F("version") + 1,
        )

    for key, old_title, old_message, new_title, new_message in COPY_UPDATES:
        OmotenashiCopy.objects.filter(
            key=key,
            moment="*",
            audience="*",
            title=old_title,
            message=old_message,
            active=True,
        ).update(title=new_title, message=new_message)


def backwards(apps, schema_editor):
    NotificationTemplate = apps.get_model("shop", "NotificationTemplate")
    OmotenashiCopy = apps.get_model("shop", "OmotenashiCopy")
    NotificationTemplate.objects.filter(
        event=ACCESS_EVENT,
        body=ACCESS_BODY,
    ).update(body=ACCESS_OLD_BODY, version=F("version") + 1)
    NotificationTemplate.objects.filter(
        event=SITE_EVENT,
        body=SITE_BODY,
    ).update(body=SITE_OLD_BODY, version=F("version") + 1)

    for key, old_title, old_message, new_title, new_message in COPY_UPDATES:
        OmotenashiCopy.objects.filter(
            key=key,
            moment="*",
            audience="*",
            title=new_title,
            message=new_message,
            active=True,
        ).update(title=old_title, message=old_message)


class Migration(migrations.Migration):
    dependencies = [("shop", "0080_order_rescheduled_notification_template")]

    operations = [migrations.RunPython(forwards, backwards)]
