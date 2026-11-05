"""Fornada diária da TRADI no alpha, para o Google ler a baguete como disponível.

Decisão do dono, 29/10/2026 (``docs/coordination/GO-LIVE-HANDOFF-2026-10-29.md``):
antes do go-live só a TRADI fica visível no Google, e o alpha faz uma fornada
por dia para que a página do produto mostre estoque de verdade. Sem essa
fornada a TRADI aparece "Indisponível" (o lote vence em um dia, a validade é
``shelf_life_days=1``) e o Google recusa as Listagens locais gratuitas.

## O caminho é o do operador, inteiro

A fornada é a "fornada avulsa" da Produção (``apply_quick_finish``): plano e
fechamento da ``WorkOrder`` pelo ``craft``, ``production_changed`` e a ponte
``craftsman/contrib/stockman`` escrevendo o ledger (``kind=MAKE``), com a
saída na vitrine e o lote com validade. Nada de reseed, ajuste direto de quant
ou disponibilidade fingida: o que a loja mostra é o que a fornada produziu.

## Quando falta massa

A massa (``MASSA-TRADICAO``) dá para poucas baguetes, e o alpha não tem quem a
reponha: uma fornada de massa pelo mesmo caminho sairia na vitrine, onde a
ficha não consome. Quando o guardrail de insumo barra, a rotina faz o mesmo
gesto que o operador faz na tela: confirma a falta EXATA que o guardrail
mostrou, com a justificativa escrita abaixo. Fica o evento
``SHORTAGE_OVERRIDDEN`` na fornada e o alerta de falta no Gestor, como em
qualquer falta confirmada. Faltar outra coisa que não a falta medida recusa.

## Portões

* **Só no alpha**: ``SHOPMAN_ENVIRONMENT=staging``. Em qualquer outro ambiente
  volta calada; na loja de verdade quem assa é o forno.
* **Só a TRADI**, fixa no código. Não há parâmetro de SKU.
* **Uma vez por dia**, a partir das 7h (antes de a loja abrir às 9h), de segunda
  a sábado. A chave de idempotência é a data: o ciclo de 5 minutos do
  ``maintenance_worker`` passa por aqui o dia todo e só a primeira passada assa.
  Domingo a casa não abre, e o lote de sábado ainda vale (vence no domingo).

Uso::

    python manage.py bake_alpha_tradi_daily            # o que o worker roda
    python manage.py bake_alpha_tradi_daily --dry-run  # diz o que faria
"""

from __future__ import annotations

import logging
from datetime import time
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from shopman.shop.environment import environment_name

logger = logging.getLogger(__name__)

SKU = "TRADI"
#: 20 baguetes por dia: o mesmo tamanho das fornadas de TRADI já planejadas no
#: alpha. Com o lote de ontem ainda válido, a vitrine passa o expediente (9h às
#: 18h) com folga mesmo com os testes de compra.
DAILY_QUANTITY = Decimal("20")
#: Antes da abertura (9h): o Google lê a página a qualquer hora do expediente.
BAKE_FROM = time(7, 0)
#: Segunda (0) a sábado (5), como o expediente da casa.
BAKE_WEEKDAYS = frozenset(range(6))
ENVIRONMENT = "staging"
ACTOR = "system:fornada-diaria-alpha"
SHORTAGE_REASON = (
    "Fornada diária da TRADI no alpha (decisão do dono, 29/10/2026). "
    "O alpha não repõe a massa: a falta é confirmada pela rotina."
)


def idempotency_key_for(day) -> str:
    return f"alpha-tradi-daily:{day.isoformat()}"


class Command(BaseCommand):
    help = "Assa a fornada diária da TRADI no alpha (só staging, uma vez por dia)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Diz o que faria, sem assar.")

    def handle(self, *args, **options):
        if environment_name() != ENVIRONMENT:
            return

        now = timezone.localtime()
        if now.weekday() not in BAKE_WEEKDAYS or now.time() < BAKE_FROM:
            return

        from shopman.backstage.services import production as production_service

        key = idempotency_key_for(now.date())
        if production_service._quick_finish_receipt_exists(key):
            return

        from shopman.craftsman.models import ProductionMode, Recipe

        recipe = Recipe.objects.filter(
            output_sku=SKU,
            is_active=True,
            production_mode=ProductionMode.BATCH,
        ).first()
        if recipe is None:
            raise CommandError(f"Nenhuma ficha ativa de {SKU} para a fornada diária do alpha.")

        if options["dry_run"]:
            self.stdout.write(f"Assaria {DAILY_QUANTITY} {SKU} pela ficha {recipe.ref} (chave {key}).")
            return

        request = {
            "recipe_id": recipe.pk,
            "quantity": DAILY_QUANTITY,
            "position_id": None,
            "actor": ACTOR,
            "idempotency_key": key,
        }
        forced = False
        try:
            output_sku, wo_ref, total = production_service.apply_quick_finish(**request)
        except production_service.ProductionStockShortError as blocked:
            forced = True
            output_sku, wo_ref, total = production_service.apply_quick_finish(
                **request,
                force=True,
                override_reason=SHORTAGE_REASON,
                approved_shortage=production_service.production_shortage_snapshot(blocked),
            )

        logger.info(
            "alpha_tradi_daily: %s %s assadas na %s (falta confirmada: %s)",
            total,
            output_sku,
            wo_ref,
            "sim" if forced else "não",
        )
        self.stdout.write(f"{total} {output_sku} na {wo_ref}" + (" (falta de insumo confirmada)" if forced else ""))
