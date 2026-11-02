"""A resposta do WhatsApp traz o botão de volta (escada sem fricção, decisão de 23/10).

No celular, o botão "Voltar à loja" entra no navegador que ele abrir; no computador, o
botão nomeia o que libera ("Liberar o Chrome no Windows"). A mensagem do login começado
no site e os passos da tela de entrada deixam de prometer que a aba "entra sozinha" e
passam a dizer qual botão tocar. Só textos ainda iguais ao padrão anterior mudam; o que a
casa editou no Admin fica como está.
"""

from django.db import migrations
from django.db.models import F

SITE_EVENT = "access_link_site"
SITE_OLD_SUBJECT = "Você entrou na loja"
SITE_OLD_BODY = (
    "Pronto{customer_name_greeting}! Seu acesso foi liberado.\n"
    "{cart_note}Volte à loja para continuar."
)
SITE_SUBJECT = "Liberar a loja no computador"
SITE_BODY = (
    "Pronto{customer_name_greeting}! Toque abaixo para entrar na loja com {release_target}.\n"
    "{cart_note}Depois, é só voltar ao computador."
)

# Mesmo formato das outras migrações de texto (0082…), lido pelo teste que confere que a
# cadeia de migrações chega ao texto do seed.
TEXTS = [
    (SITE_EVENT, SITE_OLD_SUBJECT, SITE_SUBJECT, SITE_OLD_BODY, SITE_BODY),
]

COPY_UPDATES = (
    (
        "LOGIN_WA_STEPS",
        "",
        "Toque em “Abrir o WhatsApp”\nEnvie a mensagem que já está pronta\nVolte para esta tela. A entrada será automática",
        "",
        "Toque em “Abrir o WhatsApp”\nEnvie a mensagem que já está pronta\nNa resposta, toque em “{button}”",
    ),
    (
        "LOGIN_WA_WAITING",
        "Mensagem enviada?",
        "Volte para esta tela. Estamos conferindo e vamos entrar automaticamente.",
        "Mensagem enviada?",
        "Na resposta do WhatsApp, toque em “{button}”. Esta tela entra logo depois.",
    ),
)


def forwards(apps, schema_editor):
    NotificationTemplate = apps.get_model("shop", "NotificationTemplate")
    OmotenashiCopy = apps.get_model("shop", "OmotenashiCopy")

    NotificationTemplate.objects.filter(event=SITE_EVENT, body=SITE_OLD_BODY).update(
        body=SITE_BODY, version=F("version") + 1,
    )
    NotificationTemplate.objects.filter(event=SITE_EVENT, subject=SITE_OLD_SUBJECT).update(
        subject=SITE_SUBJECT,
    )
    for key, old_title, old_message, new_title, new_message in COPY_UPDATES:
        OmotenashiCopy.objects.filter(
            key=key, moment="*", audience="*", title=old_title, message=old_message, active=True,
        ).update(title=new_title, message=new_message)


def backwards(apps, schema_editor):
    NotificationTemplate = apps.get_model("shop", "NotificationTemplate")
    OmotenashiCopy = apps.get_model("shop", "OmotenashiCopy")

    NotificationTemplate.objects.filter(event=SITE_EVENT, body=SITE_BODY).update(
        body=SITE_OLD_BODY, version=F("version") + 1,
    )
    NotificationTemplate.objects.filter(event=SITE_EVENT, subject=SITE_SUBJECT).update(
        subject=SITE_OLD_SUBJECT,
    )
    for key, old_title, old_message, new_title, new_message in COPY_UPDATES:
        OmotenashiCopy.objects.filter(
            key=key, moment="*", audience="*", title=new_title, message=new_message, active=True,
        ).update(title=old_title, message=old_message)


class Migration(migrations.Migration):
    dependencies = [("shop", "0106_storefront_host")]

    operations = [migrations.RunPython(forwards, backwards)]
