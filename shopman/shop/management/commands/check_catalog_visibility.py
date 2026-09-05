"""Produto invisível-por-categoria vira OperatorAlert — varredura de ESTADO.

O cardápio agrupa por coleção ativa e recolhe no fim quem não tem coleção
nenhuma. Quem tem **só** coleção desativada não cabe em nenhum dos dois e some
da loja inteira — publicado, na vitrine, com preço e com estoque. A regra de
detecção mora em ``shop.services.catalog_visibility`` (a mesma que a linha do
Gestor lê); aqui só se decide **quando** o sino toca.

Por que varredura e não signal: o que incomoda não é o instante em que alguém
desativa a coleção, é o produto que **já está** invisível hoje e ninguém viu. Um
handler de ``post_save`` só pegaria o evento — e nunca o passivo. Estado se
descobre varrendo.

Como o sino não vira ruído: um alerta enquanto o estado durar, não um por ciclo.
O dedupe é a lista de coleções inativas responsáveis, e a janela é de um dia:

* mesma(s) coleção(ões) presa(s) → nada de novo a dizer, silêncio;
* outra coleção desativada → conjunto diferente → alerta novo, porque é fato novo;
* alerta já **reconhecido** também segura a janela (``active_only=False``): o
  operador que deu ciente não merece o mesmo aviso de volta cinco minutos depois.

Uso:
    python manage.py check_catalog_visibility
    python manage.py check_catalog_visibility --hours 12
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)

ALERT_TYPE = "catalog_hidden_by_inactive_collection"

#: Quantos SKUs a mensagem nomeia antes de resumir. Um aviso que não diz QUAL
#: produto consertar não é aviso; uma lista de 40 nomes também não é.
NAMED_SKUS = 8

#: Janela padrão do dedupe, em horas. Estado que dura não vira aviso diário.
DEFAULT_WINDOW_HOURS = 24


class Command(BaseCommand):
    help = "Alerta o operador sobre produtos fora do cardápio por coleção desativada."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=DEFAULT_WINDOW_HOURS,
            help=f"Janela do dedupe do alerta (default {DEFAULT_WINDOW_HOURS}h).",
        )
        parser.add_argument("--dry-run", action="store_true", help="Só reporta, não alerta.")

    def handle(self, *args, **options):
        from shopman.shop.services import catalog_visibility
        from shopman.shop.services.observability import operational_event

        hidden = catalog_visibility.hidden_by_inactive_collection()

        operational_event(
            "catalog_visibility.checked",
            hidden_count=len(hidden),
            hidden_skus=[item.sku for item in hidden][:NAMED_SKUS],
        )
        self.stdout.write(f"catalog_visibility: hidden_by_inactive_collection={len(hidden)}")

        if not hidden or options["dry_run"]:
            return

        self._alert(hidden, max(1, int(options["hours"])))

    def _alert(self, hidden: list, window_hours: int) -> None:
        from shopman.shop.adapters import alert as alert_adapter
        from shopman.shop.services.observability import create_operator_alert

        # A identidade do estado é a COLEÇÃO presa, não a lista de SKUs. Consertar
        # um produto de cinco não é fato novo — trocar a chave a cada correção
        # parcial faria o sino tocar de novo por um estado que já era conhecido.
        refs = sorted({ref for item in hidden for ref in item.collection_refs})
        dedupe_key = f"{ALERT_TYPE}:{','.join(refs)}"

        cutoff = timezone.now() - timedelta(hours=window_hours)
        # ``create_operator_alert`` só olha alerta ATIVO. Aqui o reconhecido conta
        # também: sem isto, dar ciente devolveria o mesmo aviso no ciclo seguinte.
        if alert_adapter.recent_exists(
            ALERT_TYPE, cutoff, message_contains=dedupe_key, active_only=False
        ):
            logger.info(
                "catalog_visibility: estado já avisado nesta janela (%s) — sem novo alerta.",
                dedupe_key,
            )
            return

        create_operator_alert(
            type=ALERT_TYPE,
            severity="warning",
            message=self._message(hidden),
            dedupe_key=dedupe_key,
            debounce_minutes=window_hours * 60,
            hidden_count=len(hidden),
        )

    def _message(self, hidden: list) -> str:
        named = ", ".join(f"{item.sku} ({item.name})" for item in hidden[:NAMED_SKUS])
        if len(hidden) > NAMED_SKUS:
            named = f"{named} e mais {len(hidden) - NAMED_SKUS}"
        names = sorted({name for item in hidden for name in item.collection_names})
        collections = ", ".join(names)
        head = (
            "1 produto sumiu do cardápio porque a categoria dele está desativada"
            if len(hidden) == 1
            else f"{len(hidden)} produtos sumiram do cardápio porque a categoria deles está desativada"
        )
        tail = "Categoria a reativar" if len(names) == 1 else "Categorias a reativar"
        return f"{head}: {named}. {tail} (ou trocar no produto): {collections}."
