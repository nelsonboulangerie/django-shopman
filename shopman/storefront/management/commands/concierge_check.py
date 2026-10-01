"""Conferir se o Concierge, ligado, consegue atender.

    python manage.py concierge_check           # só configuração, sem rede
    python manage.py concierge_check --live    # e o campo de atendimento humano no ManyChat

Sem ``--live`` repete o system check ``SHOPMAN_W022``/``SHOPMAN_W023``
(``shopman/storefront/checks.py``). Com ``--live``, pergunta ao ManyChat
(``getCustomFields``) se o campo que a triagem usa para calar o bot existe na
conta. O que nenhum dos dois enxerga é o grafo do flow (se o External Request
roda em TODA mensagem): a API do ManyChat não o expõe, e a conferência continua
sendo o ensaio do checklist em ``docs/plans/WHATSAPP-CONCIERGE-PLAN.md``.

Sai com código 1 quando há pendência, para servir de portão num roteiro.
"""

from __future__ import annotations

import json
import urllib.request
from urllib.error import HTTPError, URLError

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

_CUSTOM_FIELDS_URL = "https://api.manychat.com/fb/page/getCustomFields"


class Command(BaseCommand):
    help = "Confere se o Concierge ligado consegue atender (configuração e, com --live, o ManyChat)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--live",
            action="store_true",
            help="Confere no ManyChat se o campo de atendimento humano existe.",
        )

    def handle(self, *args, **options):
        from shopman.storefront.checks import concierge_findings
        from shopman.storefront.concierge.transport import configured_connections

        config = getattr(settings, "SHOPMAN_CONCIERGE", {}) or {}
        if not config.get("enabled"):
            self.stdout.write(
                "Concierge desligado (SHOPMAN_CONCIERGE_ENABLED=false). Nada a conferir; "
                f"modo atual: {config.get('operation_mode') or 'assist'}."
            )
            return

        problems = 0
        self.stdout.write(self.style.MIGRATE_HEADING("Configuração"))
        findings = concierge_findings(config)
        for check_id, message, hint in findings:
            problems += 1
            self.stdout.write(self.style.ERROR(f"  {check_id} {message}"))
            self.stdout.write(f"      {hint}")
        if not findings:
            self.stdout.write("  OK: modo assist, contrato 3, chave da Anthropic, conexão, coorte e ManyChat.")

        if options["live"]:
            self.stdout.write(self.style.MIGRATE_HEADING("ManyChat"))
            fields = {str(item.get("name") or "") for item in self._fetch_custom_fields()}
            for connection in configured_connections(config):
                if connection.provider != "manychat":
                    continue
                name = str((connection.options or {}).get("handoff_field") or "").strip()
                if name and name in fields:
                    self.stdout.write(f"  OK: campo {name} existe ({connection.key}).")
                else:
                    problems += 1
                    self.stdout.write(self.style.ERROR(
                        f"  Campo de atendimento humano {name or '(vazio)'} não existe no ManyChat "
                        f"({connection.key}): a triagem não consegue calar o bot."
                    ))

        self.stdout.write(
            "Não conferido por comando: se o flow chama o Concierge em toda mensagem "
            "(ensaio manual do checklist)."
        )
        if problems:
            raise CommandError(f"{problems} pendência(s) no Concierge.")

    def _fetch_custom_fields(self) -> list[dict]:
        token = (getattr(settings, "MANYCHAT_API_TOKEN", "") or "").strip()
        if not token:
            raise CommandError("MANYCHAT_API_TOKEN não está configurado neste ambiente.")
        request = urllib.request.Request(_CUSTOM_FIELDS_URL, headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise CommandError(f"ManyChat devolveu HTTP {exc.code}.") from exc
        except URLError as exc:
            raise CommandError(f"Não foi possível falar com o ManyChat: {exc.reason}") from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        return [item for item in (data or []) if isinstance(item, dict)]
