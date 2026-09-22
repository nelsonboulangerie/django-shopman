"""O módulo Merchant do iFood à mão: leitura para diagnóstico e para a homologação.

    python manage.py ifood_merchant merchants      # GET /merchants
    python manage.py ifood_merchant merchant       # GET /merchants/{id}
    python manage.py ifood_merchant status         # GET /merchants/{id}/status
    python manage.py ifood_merchant interruptions  # GET /merchants/{id}/interruptions
    python manage.py ifood_merchant hours          # GET /merchants/{id}/opening-hours
    python manage.py ifood_merchant plan           # o que a casa gravaria (sem chamar o iFood)
    python manage.py ifood_merchant sync           # grava horário + calendário AGORA (exige a chave ligada)

Só ``sync`` escreve, e só com ``IFOOD_MERCHANT_SYNC`` ligado. A pausa do gestor não
tem atalho aqui de propósito: ela é gesto com dono, e o dono fica registrado pela tela.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Lê (e, com 'sync', grava) o horário/status da loja no módulo Merchant do iFood."

    def add_arguments(self, parser):
        parser.add_argument(
            "action",
            choices=["merchants", "merchant", "status", "interruptions", "hours", "plan", "sync"],
        )

    def handle(self, *args, **options):
        from shopman.shop.services import ifood_merchant as m

        action = options["action"]
        if action == "plan":
            closures = [
                {"key": c.key, "start": c.starts_at.isoformat(), "end": c.ends_at.isoformat(), "description": c.description}
                for c in m.desired_calendar_closures()
            ]
            self._dump({"governs": m.governs(), "enabled": m.enabled(), "shifts": m.desired_shifts(), "calendar_interruptions": closures})
            return
        if not m.merchant_id():
            raise CommandError("IFOOD_MERCHANT_ID não configurado.")
        try:
            if action == "sync":
                if not m.enabled():
                    raise CommandError("IFOOD_MERCHANT_SYNC está desligado: nada é gravado no iFood.")
                self._dump(m.sync_store().__dict__)
                return
            reader = {
                "merchants": m.list_merchants,
                "merchant": m.get_merchant,
                "status": m.get_status,
                "interruptions": m.list_interruptions,
                "hours": m.get_opening_hours,
            }[action]
            self._dump(reader())
        except m.MerchantAPIError as exc:
            raise CommandError(str(exc)) from exc

    def _dump(self, value) -> None:
        self.stdout.write(json.dumps(value, ensure_ascii=False, indent=2, default=str))
