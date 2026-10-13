"""Cadastra o endpoint de webhook deste deployment na Machine (homologação).

Uso:
    manage.py machine_register_webhook https://api.exemplo.com.br
    manage.py machine_register_webhook https://api.exemplo.com.br --list   # só lê (GET)

Cadastra ``{base}/api/webhooks/machine/?token=<MACHINE_WEBHOOK_TOKEN>`` para os
tipos ``status`` e ``posicao`` (responsabilidade ``solicitante``). Depois do
cadastro confirmado, considere reduzir/zerar o polling
(``Shop.defaults.delivery.courier_poll_seconds``).
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse


class Command(BaseCommand):
    help = "Cadastra a URL de webhook (status + posição) na Machine."

    def add_arguments(self, parser):
        parser.add_argument(
            "public_base",
            help="Base pública HTTPS deste deployment (ex.: https://api.exemplo.com.br)",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="Só lista os webhooks cadastrados na TaOn (GET /listarWebhook); não cadastra nada",
        )
        parser.add_argument(
            "--only",
            choices=["status", "posicao"],
            help="Cadastra só um tipo (default: os dois)",
        )

    def handle(self, *args, **options):
        from shopman.shop.adapters.courier_machine import (
            CourierError,
            is_configured,
            list_webhooks,
            register_webhook,
        )

        cfg = getattr(settings, "SHOPMAN_MACHINE", {}) or {}
        token = cfg.get("webhook_token") or ""
        if not token:
            raise CommandError(
                "MACHINE_WEBHOOK_TOKEN não configurado — o endpoint rejeitaria "
                "todo evento. Defina o token antes de cadastrar."
            )
        if not is_configured():
            raise CommandError(
                "Credenciais da Machine ausentes (MACHINE_API_USER/PASSWORD/API_KEY)."
            )

        base = str(options["public_base"]).rstrip("/")
        if not base.startswith("https://"):
            raise CommandError("A base pública deve ser HTTPS.")
        url = f"{base}{reverse('webhooks:machine-webhook')}?token={token}"
        shown = _mask(url, token)

        try:
            existing = list_webhooks()
        except CourierError as exc:
            raise CommandError(f"Machine recusou a listagem dos webhooks: {exc}") from exc
        for item in existing:
            self.stdout.write(
                f"cadastrado: tipo={item.get('tipo') or item.get('type') or '?'} "
                f"id={item.get('id', '?')} url={_mask(str(item.get('url') or ''), token)}"
            )
        if not existing:
            self.stdout.write("Nenhum webhook cadastrado na TaOn.")
        if options.get("list"):
            return

        kinds = [options["only"]] if options.get("only") else ["status", "posicao"]
        for kind in kinds:
            # A TaOn aceita até 5 por tipo: repetir o comando não pode duplicar o aviso.
            if any(str(item.get("url") or "") == url and (item.get("tipo") or item.get("type")) == kind
                   for item in existing):
                self.stdout.write(f"Webhook '{kind}' já cadastrado: {shown}")
                continue
            try:
                register_webhook(url, kind=kind)
            except CourierError as exc:
                raise CommandError(f"Machine recusou o cadastro ({kind}): {exc}") from exc
            self.stdout.write(self.style.SUCCESS(f"Webhook '{kind}' cadastrado: {shown}"))

        self.stdout.write(
            "Cadastro concluído. Após validar o primeiro evento real, ajuste "
            "Shop.defaults.delivery.courier_poll_seconds (0 desliga o polling)."
        )


def _mask(url: str, token: str) -> str:
    """O token do webhook é segredo: nunca sai inteiro no console."""
    return url.replace(token, token[:4] + "…") if token else url
