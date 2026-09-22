"""Carimba no canal o que os períodos do toggle "Ativo" já decidiram.

Roda no maintenance-worker, no começo do ciclo. O período escolhido no Gestor
("por 30 minutos", "por hoje", um período no calendário) vale na hora para quem
decide — o commit, a TV, o feed e o iFood leem o relógio, não este carimbo. O que
depende daqui é quem lê ``Channel.is_active`` direto (colunas do Catálogo, envio
de catálogo) e os efeitos do fim do período: reenviar o catálogo ao religar e
avisar a TV. A regra mora em ``shopman.shop.services.channel_switch.apply_due``.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Aplica o início e o fim dos períodos de ligar/desligar canal (toggle do Gestor)."

    def handle(self, *args, **options):
        from shopman.shop.services.channel_switch import apply_due

        changed = apply_due()
        if changed:
            self.stdout.write(f"apply_channel_switches: {changed} canal(is) mudaram de estado")
