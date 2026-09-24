"""Confere a loja no iFood contra a casa — o vigia do ``ifood_poll`` e das pausas.

Roda no maintenance-worker (a cada ciclo, ~5 min; o iFood pede no mínimo 30 s
entre leituras). Lê ``GET /merchants/{id}/status`` e cria ``OperatorAlert``
quando o iFood diverge da casa por mais de uma conferência:

* iFood fechado com a casa aberta — polling caído (``is-connected``), pausa
  esquecida no Portal do Parceiro, horário diferente;
* iFood aberto com a casa fechada — horário ou pausa que não chegou ao iFood.

Também pede uma regravação de horário/calendário a cada 6 h ou na divergência.
Desligado (``IFOOD_MERCHANT_SYNC`` fora), volta calado. A regra mora em
``shopman.shop.services.ifood_merchant.check_store``; aqui só se chama.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Confere o status da loja no iFood contra o horário/pausas da casa (alerta na divergência)."

    def handle(self, *args, **options):
        from shopman.shop.services import ifood_merchant

        if not ifood_merchant.enabled():
            return
        result = ifood_merchant.check_store()
        if result is None:
            self.stdout.write("check_ifood_store: sem conferência (sem grade semanal ou status ilegível)")
            return
        self.stdout.write(
            "check_ifood_store: "
            f"ifood={'aberto' if result.available else 'fechado'} ({result.state or '—'}) "
            f"casa={'aberta' if result.expected_available else 'fechada'}"
            + (f" alerta={result.alerted}" if result.alerted else "")
        )
