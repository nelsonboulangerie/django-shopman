"""Webhook URL routing — payment provider + courier callbacks."""

from django.urls import path, re_path

from shopman.shop.webhooks.efi import EfiPixWebhookView
from shopman.shop.webhooks.ifood_events import IFoodEventsWebhookView
from shopman.shop.webhooks.machine import MachineWebhookView
from shopman.shop.webhooks.stripe import StripeWebhookView

app_name = "webhooks"

urlpatterns = [
    path("efi/pix/", EfiPixWebhookView.as_view(), name="efi-pix-webhook"),
    path("stripe/", StripeWebhookView.as_view(), name="stripe-webhook"),
    # Push assinado da integração direta do iFood (eventos). A barra final é
    # opcional porque o iFood a corta da URL cadastrada no portal, e o
    # APPEND_SLASH responderia 301 a um POST, que o iFood trata como falha.
    re_path(r"^ifood/events/?$", IFoodEventsWebhookView.as_view(), name="ifood-events-webhook"),
    # Courier (Machine): status/posição das corridas de entrega.
    path("machine/", MachineWebhookView.as_view(), name="machine-webhook"),
    # do ManyChat). Não colide com o include do guestman em
    # `api/webhooks/manychat/webhook/` (sync de assinante): caminho distinto.
]
