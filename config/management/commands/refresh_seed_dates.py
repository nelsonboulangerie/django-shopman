"""Rejuvenesce as DATAS de um banco semeado, relativo a HOJE.

Usage::

    python manage.py refresh_seed_dates            # só mostra o que faria
    python manage.py refresh_seed_dates --apply    # executa

**Por que este comando existe.** Um ambiente de QA semeado envelhece: em 26/08
o alpha estava com acumuladores criados no seed de 19/08, insumo consumido até
zero (todo finish de produção respondia 409 ``material_shortage``) e nenhuma
fornada do dia — inutilizável para QA. Reseedar (`seed --flush`) é destrutivo e
tem ritual próprio; este comando faz o recorte oposto: **re-ancora o presente
sem tocar na história**.

O que ele faz, tudo relativo a UMA âncora de relógio (``timezone.localdate()``,
lida uma única vez — duas fontes de "hoje" no mesmo dado foi armadilha real):

- **feriados de fechamento**: datas que ficaram no passado avançam para a
  próxima ocorrência;
- **despensa de insumos**: repõe cada insumo ATÉ o alvo de abertura
  (``material_opening_targets()`` — a mesma fonte do seed). Só o delta: saldo
  acima do alvo não é mexido;
- **mise en place**: repõe os pré-preparos até o alvo do plano (idem);
- **vitrine**: repõe o estoque vendável até o alvo do seed e recria os lotes
  datados de "sobra de ontem" quando o de ontem não existe;
- **produção**: cancela fornadas PLANEJADAS que ficaram no passado (apenas as
  de origem seed/refresh — as de operador ficam) e cria as fornadas PLANEJADAS
  de hoje até +7 dias que estiverem faltando, no MESMO plano calibrado do seed
  (``PRODUCTION_PLAN``), com o sinal ``production_changed`` para os dias
  futuros virarem estoque planejado (gate de encomenda).

O que ele NÃO faz, de propósito:

- não apaga nem "conserta" história (pedidos velhos, lotes vencidos, WOs
  concluídas) — dado envelhecido que revela defeito é FEATURE deste ambiente
  (o #332 nasceu de um), e o comando só REPORTA o que encontrou de vencido;
- não recria a narrativa demo do dia (fornadas started/finished com alerta):
  QA opera o dia planejado; a narrativa é papel do seed;
- não roda em produção. Nunca. A trava é dura e não tem flag de override —
  mesmo desenho do ``seed --flush`` e do autopilot de staging.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_CEILING, Decimal

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from config.management.commands.seed import (
    LEFTOVER_ITEMS,
    PREP_DAYS_OF_COVER,
    PRODUCTION_PLAN,
    STOCK_VITRINE,
    material_opening_targets,
    prep_daily_needs,
)
from shopman.shop.environment import environment_name, is_production


class Command(BaseCommand):
    help = "Re-ancora um banco SEMEADO em hoje: despensa, mise, vitrine e fornadas planejadas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Executa. Sem esta flag o comando só mostra o que faria.",
        )

    def handle(self, *args, apply: bool = False, **options):
        # `is_production()` e não `== "production"`: valor desconhecido é tratado
        # como produção. Ver `shopman/shop/environment.py`.
        if is_production():
            raise CommandError(
                f"Recusando refresh_seed_dates em produção "
                f"(SHOPMAN_ENVIRONMENT={environment_name()!r}): "
                "este comando reescreve estoque e fornadas de um banco de QA semeado. "
                "Não há flag de override, de propósito."
            )

        from shopman.craftsman.models import Recipe, WorkOrder
        from shopman.craftsman.signals import production_changed
        from shopman.stockman import stock
        from shopman.stockman.models import Batch, Position, Quant

        from shopman.shop.models import Shop

        hoje = timezone.localdate()  # a ÚNICA âncora de relógio deste comando
        acoes: list[str] = []
        modo = "APPLY" if apply else "DRY-RUN (use --apply para executar)"
        self.stdout.write(f"🕰️  Rejuvenescimento relativo a {hoje.isoformat()} — {modo}")

        # ── 1. Feriados de fechamento: sempre à frente de hoje ──────────────
        shop = Shop.objects.filter(pk=1).first()
        if shop is None:
            raise CommandError("Shop pk=1 não existe — este banco não foi semeado.")
        defaults = dict(shop.defaults or {})
        closed = list(defaults.get("closed_dates") or [])
        mudou_feriado = False
        for entry in closed:
            try:
                d = date.fromisoformat(entry.get("date", ""))
            except ValueError:
                continue
            if d < hoje:
                candidato = date(hoje.year, d.month, d.day)
                if candidato < hoje:
                    candidato = date(hoje.year + 1, d.month, d.day)
                acoes.append(f"feriado '{entry.get('label', '?')}': {d} → {candidato}")
                entry["date"] = candidato.isoformat()
                mudou_feriado = True
        if mudou_feriado and apply:
            defaults["closed_dates"] = closed
            shop.defaults = defaults
            shop.save(update_fields=["defaults"])

        # ── 2. Despensa de insumos: repõe até o alvo (só o delta) ───────────
        deposito = Position.objects.filter(ref="deposito").first()
        if deposito is None:
            raise CommandError("Posição 'deposito' não existe — este banco não foi semeado.")
        for sku, alvo in sorted(material_opening_targets().items()):
            atual = stock.available(sku, position=deposito)
            delta = alvo - atual
            if delta <= 0:
                continue
            acoes.append(f"insumo {sku}: {atual} → {alvo} (+{delta})")
            if apply:
                stock.receive(
                    quantity=delta,
                    sku=sku,
                    position=deposito,
                    reason="Rejuvenescimento: reposição ao alvo de abertura",
                )

        # ── 3. Mise en place: pré-preparo até o alvo do plano ───────────────
        for prep_sku, per_day in sorted(prep_daily_needs().items()):
            alvo = (per_day * PREP_DAYS_OF_COVER).quantize(Decimal("0.001"), rounding=ROUND_CEILING)
            atual = stock.available(prep_sku, position=deposito)
            delta = alvo - atual
            if delta <= 0:
                continue
            acoes.append(f"mise {prep_sku}: {atual} → {alvo} (+{delta})")
            if apply:
                stock.receive(
                    quantity=delta,
                    sku=prep_sku,
                    position=deposito,
                    reason="Rejuvenescimento: mise en place ao alvo do plano",
                    kind="make",
                )

        # ── 4. Vitrine: estoque vendável ao alvo + sobras de ontem ──────────
        vitrine = Position.objects.filter(ref="vitrine").first()
        if vitrine is None:
            raise CommandError("Posição 'vitrine' não existe — este banco não foi semeado.")
        from shopman.offerman.models import Product

        produtos = {
            p.sku: p for p in Product.objects.filter(sku__in=set(STOCK_VITRINE) | {s for s, _ in LEFTOVER_ITEMS})
        }
        for sku, alvo_int in sorted(STOCK_VITRINE.items()):
            if sku not in produtos:
                continue
            alvo = Decimal(str(alvo_int))
            atual = stock.available(sku, position=vitrine)
            delta = alvo - atual
            if delta <= 0:
                continue
            acoes.append(f"vitrine {sku}: {atual} → {alvo} (+{delta})")
            if apply:
                stock.receive(
                    quantity=delta,
                    sku=sku,
                    position=vitrine,
                    reason="Rejuvenescimento: vitrine ao alvo do dia",
                )
        ontem = hoje - timedelta(days=1)
        for sku, qty in LEFTOVER_ITEMS:
            product = produtos.get(sku)
            if product is None:
                continue
            lot_ref = f"{sku}-{ontem:%Y%m%d}-SOBRA"
            if Quant.objects.filter(batch=lot_ref).exists():
                continue
            acoes.append(f"sobra de ontem {sku}: lote {lot_ref} ({qty} un)")
            if apply:
                shelf = product.shelf_life_days or 0
                Batch.objects.update_or_create(
                    ref=lot_ref,
                    defaults={
                        "sku": sku,
                        "production_date": ontem,
                        "expiry_date": ontem + timedelta(days=shelf),
                    },
                )
                stock.receive(
                    quantity=Decimal(str(qty)),
                    sku=sku,
                    position=vitrine,
                    batch=lot_ref,
                    reason=f"Rejuvenescimento: sobra de ontem (lote datado): {sku}",
                )

        # ── 5. Produção: cancela o planejado que apodreceu, planta o de hoje+7 ─
        # Só WOs de origem sintética (seed/refresh) são canceladas: uma WO
        # planejada por um OPERADOR no passado é achado de QA, não lixo.
        stale = WorkOrder.objects.filter(
            status=WorkOrder.Status.PLANNED,
            target_date__lt=hoje,
        ).filter(source_ref__regex=r"^(seed|refresh):")
        if stale.exists():
            acoes.append(f"fornadas planejadas no passado (seed/refresh): {stale.count()} → void")
            if apply:
                for wo in stale:
                    wo.status = WorkOrder.Status.VOID
                    wo.meta = {**(wo.meta or {}), "cancelled_by": "refresh_seed_dates"}
                    wo.save(update_fields=["status", "meta"])

        recipes = {r.ref: r for r in Recipe.objects.filter(ref__in=[row[0] for row in PRODUCTION_PLAN])}
        criadas = 0
        for offset in range(0, 8):
            target = hoje + timedelta(days=offset)
            for ref, qty, _start, _finish in PRODUCTION_PLAN:
                recipe = recipes.get(ref)
                if recipe is None:
                    continue
                ja_tem = WorkOrder.objects.filter(
                    recipe=recipe, target_date=target
                ).exclude(status=WorkOrder.Status.VOID).exists()
                if ja_tem:
                    continue
                multiplicador = Decimal("1.25") if target.weekday() in (4, 5) else Decimal("1")
                planned = (qty * multiplicador).quantize(Decimal("1"))
                acoes.append(f"fornada planejada {ref} em {target.isoformat()} ({planned})")
                criadas += 1
                if not apply:
                    continue
                work_order = WorkOrder.objects.create(
                    source_ref=f"refresh:{target.isoformat()}:{ref}",
                    recipe=recipe,
                    output_sku=recipe.output_sku,
                    quantity=planned,
                    status=WorkOrder.Status.PLANNED,
                    target_date=target,
                    position_ref="producao",
                    operator_ref="chef:planejamento",
                    meta={"refresh": True},
                )
                if offset >= 1:
                    # Futuro vira estoque planejado (gate de encomenda) — hoje
                    # não: a vitrine física de hoje já foi reposta acima.
                    production_changed.send(
                        sender=WorkOrder,
                        product_ref=work_order.output_sku,
                        date=target,
                        action="planned",
                        work_order=work_order,
                    )

        # ── Relato do que envelheceu e NÃO foi tocado (de propósito) ────────
        vencidos = Batch.objects.filter(expiry_date__lt=hoje).count()
        if vencidos:
            self.stdout.write(
                f"  ℹ️  {vencidos} lote(s) vencido(s) seguem no banco — o fechamento "
                "os baixa como perda_vencido; envelhecimento visível é dado de QA."
            )

        if not acoes:
            self.stdout.write(self.style.SUCCESS("  ✅ Nada a fazer: o banco já está ancorado em hoje."))
            return
        for linha in acoes:
            self.stdout.write(f"  · {linha}")
        if apply:
            self.stdout.write(self.style.SUCCESS(f"  ✅ Rejuvenescido: {len(acoes)} ações aplicadas."))
        else:
            self.stdout.write(f"  {len(acoes)} ações a aplicar — repita com --apply.")
