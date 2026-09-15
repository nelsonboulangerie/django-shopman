"""Leituras não destrutivas das superfícies vizinhas para retenção.

O domínio ``shop`` não conhece os modelos internos de Storefront, Doorman,
Guestman ou Orderman. Este adapter reduz cada consulta a contagens agregadas e
nunca devolve identificadores pessoais ao comando operacional.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.apps import apps
from django.db.models import Q


def _years_ago(now: datetime, years: int) -> datetime:
    """Volte anos de calendário sem antecipar o corte em anos bissextos."""

    try:
        return now.replace(year=now.year - years)
    except ValueError:
        # 29/02 não existe em anos comuns; 28/02 é o último dia equivalente.
        return now.replace(year=now.year - years, day=28)


def external_retention_counts(*, now: datetime) -> dict[str, dict[str, int]]:
    """Conte inventários agregados; não carregue conteúdo nem altere registros."""

    order = apps.get_model("orderman", "Order")
    customer = apps.get_model("guestman", "Customer")
    consent = apps.get_model("customer_consent", "CommunicationConsent")
    consent_event = apps.get_model("customer_consent", "CommunicationConsentEvent")
    insight = apps.get_model("customer_insights", "CustomerInsight")
    access_link = apps.get_model("doorman", "AccessLink")
    verification_code = apps.get_model("doorman", "VerificationCode")
    trusted_device = apps.get_model("doorman", "TrustedDevice")
    stock_alert = apps.get_model("storefront", "StockAlertSubscription")
    stock_alert_delivery = apps.get_model("storefront", "StockAlertDelivery")

    five_years_ago = _years_ago(now, 5)
    ninety_days_ago = now - timedelta(days=90)
    one_hundred_eighty_days_ago = now - timedelta(days=180)
    seven_days_ago = now - timedelta(days=7)

    return {
        "R01": {
            "pedidos_terminais_apos_prazo": order.objects.filter(
                Q(status="completed", completed_at__lte=five_years_ago)
                | Q(status="cancelled", cancelled_at__lte=five_years_ago)
                | Q(status="returned", returned_at__lte=five_years_ago)
            ).count(),
        },
        "R03": {
            "eventos_com_mais_de_cinco_anos": consent_event.objects.filter(
                occurred_at__lte=five_years_ago,
            ).count(),
        },
        "R04": {
            "bloqueios_opt_out_com_mais_de_cinco_anos": consent.objects.filter(
                status="opted_out",
                revoked_at__lte=five_years_ago,
            ).count(),
        },
        "R06": {
            "recibos_de_avise_me": stock_alert_delivery.objects.filter(
                status__in=("accepted", "suppressed"),
                updated_at__lte=one_hundred_eighty_days_ago,
            )
            .exclude(provider_receipt_ref="")
            .count(),
        },
        "R07": {
            "inscricoes_inativas_apos_prazo": stock_alert.objects.filter(
                Q(revoked_at__lte=ninety_days_ago) | Q(paused_at__lte=ninety_days_ago)
            )
            .exclude(
                deliveries__status__in=(
                    "queued",
                    "claimed",
                    "retryable",
                    "indeterminate",
                ),
            )
            .filter(Q(customer_ref__gt="") | Q(contact_phone__gt=""))
            .distinct()
            .count(),
        },
        "R09": {
            "contas_inativas": customer.objects.filter(is_active=False).count(),
        },
        "R10": {
            "links_vencidos": access_link.objects.filter(
                expires_at__lte=seven_days_ago,
            ).count(),
            "codigos_vencidos": verification_code.objects.filter(
                expires_at__lte=seven_days_ago,
            ).count(),
            "dispositivos_vencidos": trusted_device.objects.filter(
                expires_at__lte=seven_days_ago,
            ).count(),
        },
        "R11": {
            "projecoes_com_ip_vencido": consent.objects.filter(
                ip_address__isnull=False,
                updated_at__lt=ninety_days_ago,
            ).count(),
            "eventos_com_ip_vencido": consent_event.objects.filter(
                ip_address__isnull=False,
                occurred_at__lt=ninety_days_ago,
            ).count(),
        },
        "R13": {
            "perfis_de_contas_inativas": insight.objects.filter(
                customer__is_active=False,
            ).count(),
        },
    }
