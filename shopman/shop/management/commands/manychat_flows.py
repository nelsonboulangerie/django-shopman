"""Listar os flows da conta do ManyChat, com o ``ns`` de cada um.

Existe porque o `flow_ns` é o único jeito de alcançar quem está **fora da janela de 24
horas** — texto livre (`sendContent`) só passa para quem conversou hoje, e é a Meta que
manda nisso, não nós. Para configurar um flow no Admin é preciso o `ns`, que na interface
do ManyChat fica escondido; este comando o traz.

**Read-only, e isso é decisão.** A API do ManyChat não cria flow nem submete template
para aprovação da Meta — só lê (`getFlows`) e envia (`sendFlow`). Fingir que o app
"propõe template" seria inventar capacidade que o provedor não tem. O que dá para
automatizar é a VERIFICAÇÃO, e é o que este comando e o system check
``check_whatsapp_flow_coverage`` fazem.

    python manage.py manychat_flows
    python manage.py manychat_flows --check    # confronta o configurado com o real
"""

from __future__ import annotations

import json
import urllib.request
from urllib.error import HTTPError, URLError

from django.core.management.base import BaseCommand, CommandError

_FLOWS_URL = "https://api.manychat.com/fb/page/getFlows"


class Command(BaseCommand):
    help = "Lista os flows do ManyChat (ns + nome). Com --check, confronta com o configurado."

    def add_arguments(self, parser):
        parser.add_argument(
            "--check",
            action="store_true",
            help="Confere se cada `whatsapp_flow_ns` configurado ainda existe no ManyChat.",
        )

    def handle(self, *args, **options):
        flows = self._fetch_flows()
        by_ns = {str(f.get("ns") or ""): str(f.get("name") or "") for f in flows if f.get("ns")}

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(f"Flows no ManyChat ({len(by_ns)})"))
        for ns, name in sorted(by_ns.items(), key=lambda kv: kv[1].lower()):
            self.stdout.write(f"  {ns}  {name}")

        if not options["check"]:
            self.stdout.write("")
            self.stdout.write(
                "Copie o `ns` do flow para o campo 'flow do WhatsApp' do "
                "NotificationTemplate no Admin."
            )
            return

        self._check_configured(by_ns)

    def _fetch_flows(self) -> list[dict]:
        from django.conf import settings

        token = getattr(settings, "MANYCHAT_API_TOKEN", "") or ""
        if not token:
            raise CommandError(
                "MANYCHAT_API_TOKEN não está configurado neste ambiente. "
                "O token vive no staging; rode lá."
            )

        request = urllib.request.Request(
            _FLOWS_URL, headers={"Authorization": f"Bearer {token}"}
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", "replace") if exc.fp else ""
            raise CommandError(f"ManyChat devolveu HTTP {exc.code}: {body[:300]}") from exc
        except URLError as exc:
            raise CommandError(f"Não foi possível falar com o ManyChat: {exc.reason}") from exc

        data = payload.get("data") or {}
        flows = data.get("flows") if isinstance(data, dict) else data
        return list(flows or [])

    def _check_configured(self, by_ns: dict[str, str]) -> None:
        """Todo `ns` configurado ainda existe? Flow apagado é campanha que falha calada."""
        from shopman.shop.models import NotificationTemplate

        configured = [
            (template.event, template.whatsapp_flow_ns)
            for template in NotificationTemplate.objects.exclude(whatsapp_flow_ns="")
        ]

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Conferência do configurado"))

        if not configured:
            self.stdout.write(self.style.WARNING(
                "  Nenhum evento tem flow configurado. Consequência concreta: notificação "
                "e campanha só alcançam quem conversou nas últimas 24h."
            ))
            return

        problems = 0
        for event, ns in sorted(configured):
            if ns in by_ns:
                self.stdout.write(f"  ✅ {event} → {ns}  ({by_ns[ns]})")
            else:
                problems += 1
                self.stdout.write(self.style.ERROR(
                    f"  ❌ {event} → {ns}  NÃO EXISTE mais no ManyChat"
                ))

        if problems:
            self.stdout.write("")
            self.stdout.write(self.style.ERROR(
                f"  {problems} flow(s) configurado(s) apontam para o vazio. "
                "O envio falha destinatário por destinatário, sem aviso."
            ))
