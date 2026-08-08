"""Consentimento de marketing passa a ter um dono: CommunicationConsent.

A audiência de campanha lia ``CustomerPreference(category="marketing",
key="broadcast_optin")`` — uma chave que **nenhum caminho de produção escrevia**
(só a fixture do teste). Enquanto isso o toggle que o cliente usa na tela da conta
escrevia ``CommunicationConsent``, que a audiência nunca consultava.

Efeito no ar: só assinante de alerta de estoque recebia campanha, e quem revogava
WhatsApp continuava recebendo. Dois donos para um fato, com o dono errado no
comando (ADR-011, ADR-020 §3).

Esta migração converte o que existir da chave antiga para o registro canônico e
apaga a chave. Converte apenas valores que o leitor antigo considerava ativos
(``True``, ``{"enabled": true}`` ou ``{"channels": [...]}`` não vazio) — valor
falsy era opt-out explícito e continua opt-out, agora como ausência.

Sem escritor em produção, o esperado é converter zero linhas. A migração existe
para o caso de alguém ter criado a preferência à mão no Admin, e para que o
`--flush` de staging não seja a única garantia.
"""

from __future__ import annotations

from django.db import migrations
from django.utils import timezone

OLD_CATEGORY = "marketing"
OLD_KEY = "broadcast_optin"
CONSENT_CHANNEL = "whatsapp"


def _was_active(value) -> bool:
    """A mesma régua do leitor antigo (`audience._optin_is_on`, agora removido)."""
    if value is True:
        return True
    if not isinstance(value, dict):
        return False
    if "enabled" in value:
        return bool(value["enabled"])
    return bool(value.get("channels"))


def forward(apps, schema_editor):
    CustomerPreference = apps.get_model("customer_preferences", "CustomerPreference")
    CommunicationConsent = apps.get_model("customer_consent", "CommunicationConsent")

    rows = CustomerPreference.objects.filter(category=OLD_CATEGORY, key=OLD_KEY).select_related(
        "customer"
    )

    now = timezone.now()
    for pref in rows:
        if not _was_active(pref.value):
            continue
        consent, created = CommunicationConsent.objects.get_or_create(
            customer=pref.customer,
            channel=CONSENT_CHANNEL,
            defaults={
                "status": "opted_in",
                "legal_basis": "consent",
                "source": "migrated_from_broadcast_optin",
                "consented_at": now,
            },
        )
        # Consentimento já existente NUNCA é sobrescrito: se o cliente revogou na
        # tela da conta, a revogação é a verdade mais recente e vence a preferência
        # antiga. Só preenchemos o que não existia.
        if not created:
            continue

    rows.delete()


def backward(apps, schema_editor):
    """Recria a preferência a partir do que esta migração criou.

    Só reverte o que ela mesma marcou (``source``), para não transformar
    consentimento legítimo do cliente em preferência antiga.
    """
    CustomerPreference = apps.get_model("customer_preferences", "CustomerPreference")
    CommunicationConsent = apps.get_model("customer_consent", "CommunicationConsent")

    migrated = CommunicationConsent.objects.filter(
        channel=CONSENT_CHANNEL, source="migrated_from_broadcast_optin"
    ).select_related("customer")

    for consent in migrated:
        CustomerPreference.objects.update_or_create(
            customer=consent.customer,
            category=OLD_CATEGORY,
            key=OLD_KEY,
            defaults={"value": {"enabled": consent.status == "opted_in"}},
        )
    migrated.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0027_alter_shop_tracking_copy"),
        ("customer_consent", "0001_initial"),
        ("customer_preferences", "0001_initial"),
    ]

    operations = [migrations.RunPython(forward, backward)]
