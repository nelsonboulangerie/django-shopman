"""Arma cenários de VITRINE num banco já semeado — sem reseed.

Usage::

    python manage.py qa_scenarios                     # relatório (não escreve)
    python manage.py qa_scenarios --arm               # arma todos os cenários
    python manage.py qa_scenarios --arm sold_out      # arma só um
    python manage.py qa_scenarios --arm sold_out=BF   # ... num SKU escolhido
    python manage.py qa_scenarios --restock BF        # repõe → dispara o "Avise-me"
    python manage.py qa_scenarios --reset             # devolve tudo ao alvo do seed
    python manage.py qa_scenarios --reset BF          # ... incluindo um SKU pausado à mão

**Por que este comando existe.** O perfil ``qa`` do ``seed`` já nasce com um SKU
em cada estado da vitrine (esgotado, últimas unidades, previsto, pausado), mas
chegar nele custa ``seed --flush`` — destrutivo, com ritual próprio, e o alpha
roda o perfil ``demo``, em que TUDO tem estoque. Resultado: o "Avise-me" não
tinha como aparecer na tela para ser testado à mão. Este comando faz o recorte
oposto do reseed: **arma o cenário no banco que já está lá**, num SKU de cada
vez, e desarma depois.

Os estados são armados pela MESMA função que o perfil ``qa`` usa
(``seed.apply_storefront_state``) — o cenário testado à mão é o cenário que a
suíte afirma, não uma imitação dele.

Estados disponíveis:

- ``sold_out`` — sem pronto e sem plano. É o esgotado honesto: o card mostra
  "Indisponível" e oferece o sino "Avise quando voltar" (``is_notifiable``).
- ``low_stock`` — 2 prontos (limiar do canal = 5): badge "Últimas unidades".
- ``planned`` — sem pronto, fornada planejada amanhã: com a fermata ativa o
  cardápio mostra a próxima fornada e limita a fila à quantidade planejada.
- ``paused`` — ``Product.is_sellable=False``: o operador pausou o produto em
  TODO canal. Aparece no cardápio, não vende, e NÃO oferece o sino.
- ``paused_channel`` — ``ListingItem.is_sellable=False`` só na vitrine ``web``:
  o produto segue vendável no balcão. É a pausa de superfície, que nasceu com o
  ``listing_sellable_map`` e não tinha como ser vista à mão.

O que ele NÃO faz, de propósito:

- não cria pedido, cliente nem fornada — cenário de pedido é papel do
  ``seed --profile qa``, e escrever pedido num banco vivo é invasivo;
- não roda em produção. Nunca. Mesma trava dura do ``refresh_seed_dates``, sem
  flag de override.

⚠️ ``--restock`` dispara o aviso DE VERDADE (é um ``Move`` de entrada, igual ao
que a fornada faz): quem estiver inscrito recebe a mensagem no telefone que
informou. É esse o teste; só não use com número de terceiro.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from config.management.commands.seed import (
    STOCK_VITRINE,
    STOREFRONT_STATES,
    apply_storefront_state,
)
from shopman.shop.environment import environment_name, is_production

#: Estados que o comando sabe armar, e o SKU padrão de cada um. Os quatro
#: primeiros herdam o contrato do perfil ``qa`` (mesma tabela, mesmo SKU, para o
#: que você vê à mão bater com o que a suíte afirma). O ``paused_channel`` é só
#: deste comando: o perfil ``qa`` não o usa, então tem SKU próprio para não
#: disputar um card com os outros.
DEFAULT_SKUS = {**STOREFRONT_STATES, "paused_channel": "CO"}

#: Reposição de ``--restock`` quando a quantidade não é dita: o alvo de abertura
#: do próprio seed, para o SKU voltar ao que a vitrine considera um dia normal.
FALLBACK_RESTOCK_QTY = 10

STOREFRONT_LISTING_REF = "web"

#: Assinatura deixada no `reason` de todo movimento deste comando. É por ela que
#: o `--reset` reencontra um SKU armado em outra sessão.
MOVE_REASON_TAG = "Cenário QA"
QA_SNAPSHOT_KEY = "_qa_scenarios_snapshot"


def _mask(phone: str) -> str:
    """Telefone no relatório vira os 4 últimos dígitos — o resto não é da conta
    de quem lê um log de QA."""
    digits = "".join(c for c in phone if c.isdigit())
    return f"…{digits[-4:]}" if len(digits) >= 4 else "…"


class Command(BaseCommand):
    help = "Arma/desarma cenários de disponibilidade da vitrine num banco já semeado."

    def add_arguments(self, parser):
        parser.add_argument(
            "--arm",
            nargs="*",
            metavar="ESTADO[=SKU]",
            help=(
                "Arma os cenários. Sem argumento, arma todos. Aceita "
                f"{', '.join(DEFAULT_SKUS)} — e '=SKU' para escolher o produto."
            ),
        )
        parser.add_argument(
            "--restock",
            metavar="SKU[:QTD]",
            help="Repõe o SKU na vitrine. É o gatilho real do aviso 'voltou ao estoque'.",
        )
        parser.add_argument(
            "--reset",
            nargs="*",
            metavar="SKU",
            help=(
                "Desarma: restaura exatamente o estado anterior aos movimentos de QA. "
                "Sem argumento cobre os SKUs padrão + todo SKU que este comando "
                "já mexeu; nomeie SKUs adicionais para incluí-los no relatório."
            ),
        )

    def handle(self, *args, **options):
        # `is_production()` e não `== "production"`: valor desconhecido é tratado
        # como produção. Ver `shopman/shop/environment.py`.
        if is_production():
            raise CommandError(
                f"Recusando qa_scenarios em produção "
                f"(SHOPMAN_ENVIRONMENT={environment_name()!r}): "
                "este comando esgota produto e pausa venda de propósito. "
                "Não há flag de override, de propósito."
            )

        from shopman.stockman.models import Position

        self.vitrine = Position.objects.filter(ref="vitrine").first()
        if self.vitrine is None:
            raise CommandError("Posição 'vitrine' não existe — este banco não foi semeado.")

        arm = options.get("arm")
        restock = options.get("restock")
        reset = options.get("reset")

        # O que ESTA execução mirou. O relatório fecha sobre isto somado aos
        # SKUs padrão: armar um cenário num SKU escolhido e receber de volta um
        # relatório que não o menciona é pior que não relatar nada.
        self.session_states: dict[str, str] = {}
        self.touched: set[str] = set()

        if reset is not None:
            self._reset(reset)
        if arm is not None:
            self._arm(arm)
        if restock:
            self._restock(restock)

        # O relatório fecha SEMPRE — inclusive depois de armar. Ver o efeito na
        # mesma saída que o causou é o que separa "rodei o comando" de "o cenário
        # está de pé": o estado da vitrine depende de estoque, plano e listing ao
        # mesmo tempo, e um deles pode estar cancelando o outro.
        self._report()

    # ── verbos ───────────────────────────────────────────────────────────

    def _parse_targets(self, raw: list[str]) -> dict[str, str]:
        if not raw:
            return dict(DEFAULT_SKUS)
        targets: dict[str, str] = {}
        for entry in raw:
            state, _, sku = entry.partition("=")
            state = state.strip()
            if state not in DEFAULT_SKUS:
                raise CommandError(
                    f"Estado desconhecido: '{state}'. Conhecidos: {', '.join(DEFAULT_SKUS)}."
                )
            targets[state] = (sku.strip() or DEFAULT_SKUS[state]).upper()
        return targets

    @transaction.atomic
    def _arm(self, raw: list[str]) -> None:
        from django.utils import timezone
        from shopman.offerman.models import ListingItem, Product
        from shopman.stockman.models import Batch
        from shopman.stockman.shelflife import shelf_life_days_for

        from config.management.commands.seed import _validate_seed_standard_batch

        targets = self._parse_targets(raw)
        known = set(
            Product.objects.filter(sku__in=set(targets.values())).values_list("sku", flat=True)
        )
        for state, sku in targets.items():
            if sku not in known:
                raise CommandError(f"SKU '{sku}' não existe no catálogo (estado '{state}').")
        if len(set(targets.values())) != len(targets):
            raise CommandError("Cada estado precisa usar um SKU diferente.")
        listed = set(
            ListingItem.objects.filter(
                listing__ref=STOREFRONT_LISTING_REF,
                product__sku__in=set(targets.values()),
            ).values_list("product__sku", flat=True)
        )
        missing = sorted(set(targets.values()) - listed)
        if missing:
            raise CommandError(
                "SKU(s) fora da vitrine web: " + ", ".join(missing)
            )

        # O lote determinístico de "últimas unidades" pode carregar QC real
        # congelado. Recuse antes de capturar estado ou ajustar qualquer quant.
        low_stock_sku = targets.get("low_stock")
        if low_stock_sku and shelf_life_days_for(low_stock_sku) is not None:
            ref = f"{low_stock_sku}-{timezone.localdate():%Y%m%d}-SEED"
            batch = Batch.objects.filter(ref=ref).first()
            if batch is not None:
                _validate_seed_standard_batch(
                    batch=batch,
                    ref=ref,
                    sku=low_stock_sku,
                )

        self.stdout.write(self.style.MIGRATE_HEADING("🎬 Armando cenários de vitrine..."))
        for sku in targets.values():
            self._remember_sku_state(sku)
        for state, sku in targets.items():
            apply_storefront_state(
                state,
                sku,
                vitrine=self.vitrine,
                listing_ref=STOREFRONT_LISTING_REF,
                reason_prefix=MOVE_REASON_TAG,
            )
            self.stdout.write(f"  ✅ {state}: {sku}")
        self.session_states.update(targets)
        self.touched.update(targets.values())

    @transaction.atomic
    def _restock(self, raw: str) -> None:
        from shopman.offerman.models import Product
        from shopman.stockman import stock

        sku, _, qty_raw = raw.partition(":")
        sku = sku.strip().upper()
        if not Product.objects.filter(sku=sku).exists():
            raise CommandError(f"SKU '{sku}' não existe no catálogo.")
        try:
            qty = Decimal(qty_raw.strip()) if qty_raw.strip() else None
        except ArithmeticError as exc:
            raise CommandError(f"Quantidade inválida: '{qty_raw}'.") from exc
        if qty is None:
            qty = Decimal(str(STOCK_VITRINE.get(sku, FALLBACK_RESTOCK_QTY)))
        if qty <= 0:
            raise CommandError("A reposição precisa ser maior que zero.")

        self._remember_sku_state(sku)
        self.touched.add(sku)
        pendentes_antes = self._pending(sku)
        self.stdout.write(
            self.style.MIGRATE_HEADING(f"📦 Repondo {sku} na vitrine: +{qty}")
        )
        stock.receive(
            quantity=qty,
            sku=sku,
            position=self.vitrine,
            reason=f"{MOVE_REASON_TAG}: reposição manual (gatilho do aviso)",
        )
        # O envio é agendado em `transaction.on_commit` dentro do receive, então
        # já aconteceu quando a linha abaixo roda: a diferença de pendentes é o
        # número de avisos que SAÍRAM, não o que se pretendia enviar.
        avisados = pendentes_antes - self._pending(sku)
        if pendentes_antes:
            self.stdout.write(f"  🔔 {avisados} de {pendentes_antes} aviso(s) pendente(s) disparado(s)")
        else:
            self.stdout.write("  🔕 ninguém estava inscrito neste SKU")

    @transaction.atomic
    def _reset(self, extra: list[str] | None = None) -> None:
        from django.db.models import Sum
        from shopman.offerman.models import ListingItem, Product
        from shopman.stockman import stock
        from shopman.stockman.models import Move, Quant

        skus = sorted(set(DEFAULT_SKUS.values()) | self._previously_touched() | {
            s.strip().upper() for s in (extra or []) if s.strip()
        })
        self.stdout.write(self.style.MIGRATE_HEADING("🧹 Desarmando cenários..."))

        products = list(Product.objects.filter(sku__in=skus))
        restoration: list[tuple[Product, dict, list[tuple[object, Decimal]]]] = []
        for product in products:
            snapshot = dict((product.metadata or {}).get(QA_SNAPSHOT_KEY) or {})
            if not snapshot:
                continue
            marker = int(snapshot.get("after_move_pk") or 0)
            qa_moves = (
                Move.objects.filter(
                    quant__sku=product.sku,
                    pk__gt=marker,
                    reason__contains=MOVE_REASON_TAG,
                )
                .values("quant_id")
                .annotate(delta_sum=Sum("delta"))
            )
            quant_targets: list[tuple[object, Decimal]] = []
            for row in qa_moves:
                quant = Quant.objects.select_for_update().get(pk=row["quant_id"])
                target = quant._quantity - Decimal(str(row["delta_sum"] or 0))
                if target < 0:
                    raise CommandError(
                        f"Não é possível desfazer {product.sku} sem saldo negativo; "
                        "houve consumo do estoque temporário de QA. Reconcilie o SKU manualmente."
                    )
                quant_targets.append((quant, target))
            restoration.append((product, snapshot, quant_targets))

        for product, snapshot, quant_targets in restoration:
            for quant, target in quant_targets:
                stock.adjust(
                    quant,
                    target,
                    reason=f"{MOVE_REASON_TAG}: restaura estado anterior {product.sku}",
                )

            Product.objects.filter(pk=product.pk).update(
                is_sellable=bool(snapshot["product_is_sellable"]),
                metadata={
                    key: value
                    for key, value in (product.metadata or {}).items()
                    if key != QA_SNAPSHOT_KEY
                },
            )
            listing_sellable = snapshot.get("listing_is_sellable")
            if listing_sellable is not None:
                ListingItem.objects.filter(
                    listing__ref=STOREFRONT_LISTING_REF,
                    product=product,
                ).update(is_sellable=bool(listing_sellable))
            self.stdout.write(f"  ✅ {product.sku}: estado anterior restaurado")

        restored_skus = {product.sku for product, _snapshot, _quants in restoration}
        self.touched.update(restored_skus)
        self.stdout.write("  ℹ️  apenas movimentos e pausas deste comando foram desfeitos")

    def _remember_sku_state(self, sku: str) -> None:
        """Congela o estado anterior uma vez; rearmar continua reversível."""
        from shopman.offerman.models import ListingItem, Product
        from shopman.stockman.models import Move

        product = Product.objects.select_for_update().get(sku=sku)
        metadata = dict(product.metadata or {})
        if metadata.get(QA_SNAPSHOT_KEY):
            return
        listing_sellable = (
            ListingItem.objects.filter(
                listing__ref=STOREFRONT_LISTING_REF,
                product=product,
            )
            .values_list("is_sellable", flat=True)
            .first()
        )
        last_move_pk = (
            Move.objects.filter(quant__sku=sku)
            .order_by("-pk")
            .values_list("pk", flat=True)
            .first()
            or 0
        )
        metadata[QA_SNAPSHOT_KEY] = {
            "after_move_pk": last_move_pk,
            "product_is_sellable": product.is_sellable,
            "listing_is_sellable": listing_sellable,
        }
        Product.objects.filter(pk=product.pk).update(metadata=metadata)

    def _previously_touched(self) -> set[str]:
        """SKUs com snapshot reversível deste comando, inclusive pausas."""
        from shopman.offerman.models import Product

        return {
            sku
            for sku, metadata in Product.objects.values_list("sku", "metadata")
            if (metadata or {}).get(QA_SNAPSHOT_KEY)
        }

    # ── relatório ────────────────────────────────────────────────────────

    def _pending(self, sku: str) -> int:
        from shopman.storefront.models import StockAlertSubscription

        return StockAlertSubscription.objects.filter(sku=sku, notified_at__isnull=True).count()

    def _report(self) -> None:
        from django.utils import timezone

        from shopman.shop.projections import catalog_context
        from shopman.storefront.models import StockAlertSubscription
        from shopman.storefront.presentation.catalog import build_catalog_items_for_skus

        # Mapa do relatório: o padrão, sobrescrito pelo que ESTA execução mirou.
        # Um SKU padrão que perdeu o posto continua na lista (ele pode ter ficado
        # armado de uma execução anterior), só que sem rótulo de cenário.
        mapa = {**DEFAULT_SKUS, **self.session_states}
        por_sku: dict[str, list[str]] = {}
        for state, sku in mapa.items():
            por_sku.setdefault(sku, []).append(state)
        for sku in set(DEFAULT_SKUS.values()) | self.touched:
            por_sku.setdefault(sku, [])
        skus = sorted(por_sku)

        items = {
            item.sku: item
            for item in build_catalog_items_for_skus(skus, channel_ref=STOREFRONT_LISTING_REF)
        }
        today = timezone.localdate()

        self.stdout.write(self.style.MIGRATE_HEADING("\n🛍️  Vitrine web, como o cliente vê:"))
        self.stdout.write(
            f"  {'SKU':<6} {'cenário':<15} {'estado':<14} {'agora':>6} {'teto':>7}  sino"
        )
        for sku in skus:
            item = items.get(sku)
            if item is None:
                self.stdout.write(
                f"  {sku:<6} {('/'.join(por_sku[sku]) or '—'):<15} (fora do cardápio web)"
            )
                continue
            qty = "—" if item.available_qty is None else str(item.available_qty)
            current = catalog_context.availability_for_sku(
                sku,
                channel_ref=STOREFRONT_LISTING_REF,
                target_date=today,
            )
            current_qty = catalog_context.promisable_int(current)
            now_qty = "—" if current_qty is None else str(current_qty)
            if item.is_paused:
                sino = "não (pausado)"
            elif item.is_notifiable:
                sino = "SIM — 'Avise quando voltar'"
            elif item.can_add_to_cart:
                sino = "não (vende)"
            else:
                sino = "não"
            self.stdout.write(
                f"  {sku:<6} {('/'.join(por_sku[sku]) or '—'):<15} {item.availability.value:<14} "
                f"{now_qty:>6} {qty:>7}  {sino}"
            )

        pendentes = list(
            StockAlertSubscription.objects.filter(notified_at__isnull=True).order_by("sku", "subscribed_at")
        )
        self.stdout.write(self.style.MIGRATE_HEADING("\n🔔 Avisos pendentes:"))
        if not pendentes:
            self.stdout.write("  (nenhum — inscreva-se pela loja para ter o que disparar)")
        for sub in pendentes:
            quem = sub.customer_ref or _mask(sub.contact_phone)
            self.stdout.write(
                f"  {sub.sku:<6} {sub.alert_type:<17} {quem:<20} desde {sub.subscribed_at:%d/%m %H:%M}"
            )
        self.stdout.write("")
