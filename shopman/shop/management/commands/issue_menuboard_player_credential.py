"""Emite credenciais escopadas e uma configuração pronta para o player do Pi."""

from __future__ import annotations

import json
from datetime import timedelta
from urllib.parse import urlsplit

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from shopman.doorman.models import TrustedDevice

from shopman.shop.menuboard_access import DISPLAY_SUBJECT, PLAYER_USER_AGENT_PREFIX
from shopman.shop.projections.menuboard import MenuboardError, resolve_menuboard


class Command(BaseCommand):
    help = "Emite credenciais do player de menuboard e imprime o JSON do Raspberry Pi uma única vez."

    def add_arguments(self, parser):
        parser.add_argument("refs", nargs="+", help="Refs dos menuboards, na ordem HDMI 0, HDMI 1…")
        parser.add_argument("--server-url", required=True, help="Origem HTTPS do Shopman")
        parser.add_argument("--label", default="Raspberry Pi 4", help="Nome auditável do controlador")
        parser.add_argument("--standby-delay-minutes", type=int, default=30)
        parser.add_argument("--ttl-days", type=int, default=365)
        parser.add_argument("--width", type=int, default=1920)
        parser.add_argument("--height", type=int, default=1080)

    def handle(self, *args, **options):
        refs = list(dict.fromkeys(str(ref).strip() for ref in options["refs"] if str(ref).strip()))
        if len(refs) != len(options["refs"]):
            raise CommandError("Informe refs únicas e não vazias.")
        server_url = str(options["server_url"]).strip().rstrip("/")
        parsed = urlsplit(server_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise CommandError("--server-url precisa ser uma origem HTTP(S) válida.")
        if options["standby_delay_minutes"] < 0:
            raise CommandError("--standby-delay-minutes não pode ser negativo.")
        if options["ttl_days"] < 1:
            raise CommandError("--ttl-days precisa ser maior que zero.")
        if options["width"] < 1 or options["height"] < 1:
            raise CommandError("--width e --height precisam ser maiores que zero.")

        try:
            for ref in refs:
                resolve_menuboard(ref)
        except MenuboardError as exc:
            raise CommandError(str(exc)) from exc

        screens = []
        expires_at = timezone.now() + timedelta(days=options["ttl_days"])
        with transaction.atomic():
            for index, ref in enumerate(refs):
                device, raw_token = TrustedDevice.create_for(
                    subject_type=DISPLAY_SUBJECT,
                    subject_id=ref,
                    user_agent=f"{PLAYER_USER_AGENT_PREFIX}1.0",
                    label=f"{options['label']} · controlador · {ref}",
                )
                TrustedDevice.objects.filter(pk=device.pk).update(expires_at=expires_at)
                screens.append(
                    {
                        "ref": ref,
                        "cec_adapter": f"/dev/cec{index}",
                        "token": raw_token,
                        "window_position": f"{index * options['width']},0",
                        "window_size": f"{options['width']},{options['height']}",
                    }
                )

        config = {
            "server_url": server_url,
            "poll_seconds": 30,
            "standby_delay_minutes": options["standby_delay_minutes"],
            "chromium": "chromium",
            "screens": screens,
        }
        self.stdout.write(json.dumps(config, ensure_ascii=False, indent=2))
        self.stderr.write(
            f"Guarde este JSON agora: os Bearers aparecem uma única vez. Eles expiram em {options['ttl_days']} dias."
        )
