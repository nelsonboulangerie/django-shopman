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
- ``planned`` — sem pronto hoje, fornada planejada amanhã: indisponível no
  cardápio de hoje, mas orderável ao escolher data futura (encomenda).
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

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from config.management.commands.seed import (
    STOCK_VITRINE,
    STOREFRONT_STATES,
    apply_storefront_state,
)

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
                "Desarma: religa a venda e repõe a vitrine até o alvo do seed. "
                "Sem argumento cobre os SKUs padrão + todo SKU que este comando "
                "já mexeu; nomeie o SKU quando ele foi PAUSADO à mão (pausa não "
                "deixa rastro no estoque)."
            ),
        )

    def handle(self, *args, **options):
        environment = str(getattr(settings, "SHOPMAN_ENVIRONMENT", "") or "").lower()
        if environment == "production":
            raise CommandError(
                "Recusando qa_scenarios em produção (SHOPMAN_ENVIRONMENT=production): "
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

    def _arm(self, raw: list[str]) -> None:
        from shopman.offerman.models import Product

        targets = self._parse_targets(raw)
        known = set(
            Product.objects.filter(sku__in=set(targets.values())).values_list("sku", flat=True)
        )
        for state, sku in targets.items():
            if sku not in known:
                raise CommandError(f"SKU '{sku}' não existe no catálogo (estado '{state}').")

        self.stdout.write(self.style.MIGRATE_HEADING("🎬 Armando cenários de vitrine..."))
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

    def _reset(self, extra: list[str] | None = None) -> None:
        from shopman.offerman.models import ListingItem, Product
        from shopman.stockman import stock

        skus = sorted(set(DEFAULT_SKUS.values()) | self._previously_touched() | {
            s.strip().upper() for s in (extra or []) if s.strip()
        })
        self.stdout.write(self.style.MIGRATE_HEADING("🧹 Desarmando cenários..."))

        religados = Product.objects.filter(sku__in=skus, is_sellable=False).update(is_sellable=True)
        religados_canal = ListingItem.objects.filter(
            listing__ref=STOREFRONT_LISTING_REF, product__sku__in=skus, is_sellable=False
        ).update(is_sellable=True)
        if religados or religados_canal:
            self.stdout.write(
                f"  ✅ venda religada: {religados} produto(s), {religados_canal} item(ns) de vitrine"
            )

        for sku in skus:
            alvo = Decimal(str(STOCK_VITRINE.get(sku, FALLBACK_RESTOCK_QTY)))
            atual = stock.available(sku, position=self.vitrine)
            delta = alvo - atual
            if delta <= 0:
                continue
            stock.receive(
                quantity=delta,
                sku=sku,
                position=self.vitrine,
                reason=f"{MOVE_REASON_TAG}: vitrine de volta ao alvo do seed",
            )
            self.stdout.write(f"  ✅ vitrine {sku}: {atual} → {alvo}")

        self.touched.update(skus)
        # O estoque PLANEJADO de amanhã (cenário `planned`) fica: é indistinguível
        # de uma fornada real já planejada, e sobra de plano não atrapalha nenhum
        # outro teste — só deixa o produto orderável para amanhã, como qualquer
        # produto normal da casa.
        self.stdout.write("  ℹ️  plano de amanhã preservado (não dá para distinguir do plano real)")

    def _previously_touched(self) -> set[str]:
        """SKUs que ESTE comando já mexeu, lidos do ledger.

        O rastro sobrevive à sessão: quem armou `sold_out=BF` ontem consegue
        desarmar hoje sem lembrar do SKU. Só alcança o que passou pelo estoque —
        pausa não gera movimento, e por isso `--reset` aceita SKU nomeado.
        """
        from shopman.stockman.models import Move

        return set(
            Move.objects.filter(reason__contains=MOVE_REASON_TAG)
            .values_list("quant__sku", flat=True)
            .distinct()
        )

    # ── relatório ────────────────────────────────────────────────────────

    def _pending(self, sku: str) -> int:
        from shopman.storefront.models import StockAlertSubscription

        return StockAlertSubscription.objects.filter(sku=sku, notified_at__isnull=True).count()

    def _report(self) -> None:
        from datetime import timedelta

        from django.utils import timezone
        from shopman.stockman import stock

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
        # O que dá para ENCOMENDAR para amanhã (pronto que sobrevive à validade
        # + fornada planejada) sai em coluna própria: sem ela, "esgotado" e
        # "previsto" imprimem a MESMA linha — os dois são `unavailable` com zero
        # pronto —, e é justamente essa diferença que separa o teste do sino do
        # teste da encomenda.
        amanha = timezone.localdate() + timedelta(days=1)

        self.stdout.write(self.style.MIGRATE_HEADING("\n🛍️  Vitrine web, como o cliente vê:"))
        self.stdout.write(
            f"  {'SKU':<6} {'cenário':<15} {'estado':<14} {'hoje':>6} {'amanhã':>7}  sino"
        )
        for sku in skus:
            item = items.get(sku)
            if item is None:
                self.stdout.write(
                f"  {sku:<6} {('/'.join(por_sku[sku]) or '—'):<15} (fora do cardápio web)"
            )
                continue
            qty = "—" if item.available_qty is None else str(item.available_qty)
            planejado = stock.available(sku, target_date=amanha, position=self.vitrine)
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
                f"{qty:>6} {planejado:>7}  {sino}"
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
