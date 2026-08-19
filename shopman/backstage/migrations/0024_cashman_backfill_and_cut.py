"""O caixa legado vira livro do cashman e some (WP-5 do CASHMAN-PLAN, ADR-022).

Uma migração só, porque é um corte só: o que ``POSTerminal``/``CashShift``/
``CashMovement`` sabiam entra no ``cashman`` como terminal, turno e lançamentos,
o algoritmo de atribuição do ``CashShift.close()`` roda UMA última vez (aqui,
copiado, sobre o estado congelado), e as três tabelas são apagadas na mesma
transação. Depois disto o caixa tem um livro só.

O que o backfill produz por turno legado (nesta ordem, por ``at``):

- ``float_in``           ← ``opening_amount_q`` (só quando > 0)
- ``sale``/``cod_settled`` ← uma linha por pedido em dinheiro, atribuída pelo
                            MESMO algoritmo que o ``close()`` usava (cópia fiel)
- ``cash_out``/``cash_in`` ← ``CashMovement`` sangria/suprimento, com o
                            ``receipt_result`` filho quando o papel teve resultado
- ``drawer_open``        ← ``metadata.drawer_openings``
- ``change_requested`` (+ ``change_served``/``change_cancelled`` filhos)
                         ← ``metadata.change_requests``
- ``count``              ← ``blind_closing_amount_q − Σ reproduzido``; o
                            ``expected``/``difference`` legados ficam no payload
                            para auditoria (divergem quando um pedido foi
                            cancelado DEPOIS do fechamento: o livro é a verdade
                            de hoje, não a foto de ontem)
- ``note``               ← turno legado ainda ABERTO no corte: fecha sem
                            contagem e diz isso (a janela de deploy é caixa
                            fechado; se não foi, o registro grita)

Permissões: quem tinha ``backstage.operate_pos`` / ``audit_cashshift`` /
``adjust_cashshift`` / ``manage_operators`` (usuário ou grupo) ganha a mesma
no ``cashman.shift`` (``audit_shift``/``adjust_shift``), e as linhas legadas de
``auth_permission`` + o content type somem, para o Admin não oferecer
permissão de model morto.

Irreversível de propósito no dado: o reverso recria as tabelas vazias (o
livro fica), mas o legado não volta. A janela de deploy faz snapshot antes.
"""

from __future__ import annotations

import logging
from datetime import datetime

from django.conf import settings
from django.db import migrations
from django.utils import timezone

log = logging.getLogger("shopman.backstage.migrations.cashman_backfill")

_POS_CHANNEL_REF = "pdv"

# backstage.cashshift codename → cashman.shift codename
PERMISSION_MAP = {
    "operate_pos": "operate_pos",
    "audit_cashshift": "audit_shift",
    "adjust_cashshift": "adjust_shift",
    "manage_operators": "manage_operators",
}
PERMISSION_NAMES = {
    "operate_pos": "Pode operar o PDV (abrir/fechar caixa, sangria, balcão)",
    "audit_shift": "Pode auditar turnos de caixa",
    "adjust_shift": "Pode ajustar turnos de caixa",
    "manage_operators": "Pode gerir operadores (resetar PIN, provisionar)",
}

MOVEMENT_KIND = {"sangria": "cash_out", "suprimento": "cash_in"}


def _int_or_none(value):
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_dt(value, fallback):
    if not value:
        return fallback
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return fallback
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


class _Backfill:
    def __init__(self, apps):
        self.apps = apps
        self.POSTerminal = apps.get_model("backstage", "POSTerminal")
        self.CashShift = apps.get_model("backstage", "CashShift")
        self.CashMovement = apps.get_model("backstage", "CashMovement")
        self.Terminal = apps.get_model("cashman", "Terminal")
        self.Shift = apps.get_model("cashman", "Shift")
        self.Entry = apps.get_model("cashman", "Entry")
        self.Order = apps.get_model("orderman", "Order")
        self.User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
        self.now = timezone.now()
        self._users: dict[str, object] = {}
        # Pedidos que JÁ estão no livro novo (venda gravada pelo shop depois do
        # WP-3): nunca entram de novo, mesmo que o algoritmo legado os alcance.
        self.already_booked = set(
            self.Entry.objects.filter(kind__in=["sale", "cod_settled"])
            .exclude(order_ref="")
            .values_list("order_ref", flat=True)
        )
        # Adoção em memória: o ``close()`` carimbava o pedido sem turno com o
        # turno que o contou. Aqui não se escreve no pedido (etiqueta morta);
        # a memória faz o mesmo papel para quem vem depois.
        self.adopted: dict[int, int] = {}
        self.report = {"terminals": 0, "shifts": 0, "entries": 0, "open_shifts_closed": 0, "divergent": 0}

    # ── utilitários ─────────────────────────────────────────────────────

    def user(self, username, default=None):
        username = str(username or "").strip()
        if not username:
            return default
        if username not in self._users:
            self._users[username] = self.User.objects.filter(username=username).first()
        return self._users[username] or default

    # ── terminais ───────────────────────────────────────────────────────

    def terminals(self) -> dict[int, object]:
        mapping = {}
        for legacy in self.POSTerminal.objects.all().order_by("pk"):
            target = self.Terminal.objects.filter(ref=legacy.ref).first()
            if target is None:
                target = self.Terminal.objects.create(
                    ref=legacy.ref,
                    label=legacy.label,
                    channel_ref=legacy.channel_ref or _POS_CHANNEL_REF,
                    location_ref=legacy.location_ref,
                    is_active=legacy.is_active,
                    metadata=dict(legacy.metadata or {}),
                )
                self.report["terminals"] += 1
            elif legacy.metadata and not target.metadata:
                # O pacote nasceu sem a configuração do aparelho; o legado tinha.
                target.metadata = dict(legacy.metadata)
                target.save(update_fields=["metadata"])
            mapping[legacy.pk] = target
        return mapping

    # ── turnos ──────────────────────────────────────────────────────────

    def run(self):
        terminal_by_legacy = self.terminals()
        shifts = list(self.CashShift.objects.select_related("terminal", "operator").order_by("opened_at", "pk"))
        for legacy in shifts:
            self.shift(legacy, terminal_by_legacy[legacy.terminal_id])
        return self.report

    def shift(self, legacy, terminal):
        is_open = legacy.status == "open"
        closed_at = legacy.closed_at or self.now
        shift = self.Shift.objects.create(
            terminal=terminal,
            operator_id=legacy.operator_id,
            opened_at=legacy.opened_at,
            closed_at=closed_at,
            status="closed",
        )
        self.report["shifts"] += 1
        operator = legacy.operator
        pending: list[tuple] = []  # (at, seq, kind, kwargs, parent_key)

        seq = 0

        def push(kind, at, parent_key=None, key=None, **kwargs):
            nonlocal seq
            seq += 1
            pending.append((at, seq, kind, kwargs, parent_key, key))

        if int(legacy.opening_amount_q or 0) > 0:
            push("float_in", legacy.opened_at, amount_q=int(legacy.opening_amount_q), operator=operator)

        cash_sales_q = 0
        for order, amount_q, source in self.cash_orders(legacy, bound=closed_at):
            cash_sales_q += amount_q
            if amount_q <= 0 or order.ref in self.already_booked:
                continue
            payment = (order.data or {}).get("payment") or {}
            if source == "cod":
                push(
                    "cod_settled",
                    _parse_dt(payment.get("cod_settled_at"), closed_at),
                    amount_q=amount_q,
                    operator=self.user(payment.get("cod_settled_by"), operator),
                    order_ref=order.ref,
                    payload={"legacy": True, "source": source, "settled_by": str(payment.get("cod_settled_by") or "")},
                )
            else:
                push(
                    "sale",
                    order.created_at,
                    amount_q=amount_q,
                    operator=operator,
                    order_ref=order.ref,
                    payload={
                        "legacy": True,
                        "source": source,
                        "method": str(payment.get("method") or "cash"),
                        "collection": str(payment.get("collection") or "terminal"),
                        "intents": {},
                    },
                )

        suprimentos_q = 0
        sangrias_q = 0
        for movement in self.CashMovement.objects.filter(shift=legacy).order_by("created_at", "pk"):
            amount_q = int(movement.amount_q or 0)
            if movement.movement_type == "sangria":
                sangrias_q += amount_q
            else:
                suprimentos_q += amount_q
            kind = MOVEMENT_KIND.get(movement.movement_type, "cash_out")
            if amount_q <= 0:
                # Sem efeito: o legado aceitava zero; o livro não (sinal por tipo).
                push(
                    "note",
                    movement.created_at,
                    operator=self.user(movement.created_by, operator),
                    reason=f"Movimento legado sem valor ({movement.movement_type}) #{movement.pk}",
                    payload={"legacy_movement_id": movement.pk},
                )
                continue
            key = ("movement", movement.pk)
            push(
                kind,
                movement.created_at,
                key=key,
                amount_q=-amount_q if kind == "cash_out" else amount_q,
                operator=self.user(movement.created_by, operator),
                approved_by=self.user(movement.approved_by),
                reason=str(movement.reason or "")[:200],
                payload={
                    "legacy_movement_id": movement.pk,
                    "created_by": str(movement.created_by or ""),
                    "approved_by": str(movement.approved_by or ""),
                },
            )
            if movement.receipt_status and movement.receipt_status != "pending":
                push(
                    "receipt_result",
                    movement.receipt_at or movement.created_at,
                    parent_key=key,
                    operator=self.user(movement.created_by, operator),
                    payload={"status": movement.receipt_status, "detail": str(movement.receipt_detail or "")[:200]},
                )

        metadata = dict(legacy.metadata or {})
        for opening in metadata.get("drawer_openings") or []:
            if not isinstance(opening, dict):
                continue
            push(
                "drawer_open",
                _parse_dt(opening.get("at"), legacy.opened_at),
                operator=self.user(opening.get("by"), operator),
                reason=str(opening.get("reason") or "")[:200],
                payload={"legacy": True},
            )
        for request in metadata.get("change_requests") or []:
            if not isinstance(request, dict):
                continue
            key = ("change", request.get("ref") or seq)
            requested_at = _parse_dt(request.get("requested_at"), legacy.opened_at)
            push(
                "change_requested",
                requested_at,
                key=key,
                operator=self.user(request.get("requested_by"), operator),
                payload={
                    "amount_q": int(_int_or_none(request.get("amount_q")) or 0),
                    "denominations": [],
                    "note": str(request.get("note") or "")[:120],
                    "legacy_ref": str(request.get("ref") or ""),
                    "legacy_kind": str(request.get("kind") or ""),
                },
            )
            status = request.get("status")
            if status == "served":
                push(
                    "change_served",
                    _parse_dt(request.get("served_at"), requested_at),
                    parent_key=key,
                    operator=operator,
                    approved_by=self.user(request.get("served_by")),
                    payload={"served_by": str(request.get("served_by") or "")},
                )
            elif status == "cancelled":
                push(
                    "change_cancelled",
                    _parse_dt(request.get("cancelled_at"), requested_at),
                    parent_key=key,
                    operator=operator,
                )

        reproduced_q = int(legacy.opening_amount_q or 0) + cash_sales_q + suprimentos_q - sangrias_q
        booked_q = sum(
            int(kw.get("amount_q") or 0)
            for _, _, kind, kw, _, _ in pending
            if kind in {"float_in", "sale", "cod_settled", "cash_in", "cash_out"}
        )
        if is_open:
            self.report["open_shifts_closed"] += 1
            push(
                "note",
                closed_at,
                operator=operator,
                reason="Turno legado ainda aberto no corte para o cashman: fechado sem contagem",
                payload={"legacy_shift_id": legacy.pk, "legacy_status": "open", "balance_q": booked_q},
            )
        else:
            counted_q = int(legacy.blind_closing_amount_q or 0)
            legacy_expected = legacy.expected_amount_q
            divergent = legacy_expected is not None and int(legacy_expected) != reproduced_q
            if divergent:
                self.report["divergent"] += 1
            push(
                "count",
                closed_at,
                operator=operator,
                amount_q=counted_q - booked_q,
                payload={
                    "counted_q": counted_q,
                    "notes": str(legacy.notes or "").strip(),
                    "supervisory": False,
                    "legacy": {
                        "shift_id": legacy.pk,
                        "expected_q": legacy_expected,
                        "difference_q": legacy.difference_q,
                        "reproduced_expected_q": reproduced_q,
                        "booked_q": booked_q,
                        "divergent": divergent,
                    },
                },
            )

        # Cronológico e com o pai antes do filho: ``at`` do filho nunca é
        # anterior ao do pai, e o empate resolve pela ordem de inserção.
        pending.sort(key=lambda item: (item[0], item[1]))
        created_by_key = {}
        for at, _, kind, kwargs, parent_key, key in pending:
            parent = created_by_key.get(parent_key) if parent_key else None
            entry = self.Entry.objects.create(shift=shift, at=at, kind=kind, parent=parent, **kwargs)
            if key is not None:
                created_by_key[key] = entry
            self.report["entries"] += 1

    # ── atribuição de vendas: cópia fiel de CashShift.close() ───────────

    def cash_orders(self, legacy, *, bound):
        """Gera ``(order, cash_q, source)`` exatamente como o ``close()`` somava."""
        from django.db.models import Q

        channel_ref = legacy.terminal.channel_ref or _POS_CHANNEL_REF
        orders_qs = (
            self.Order.objects.filter(channel_ref=channel_ref)
            .filter(
                Q(data__pos__cash_shift_id=legacy.pk)
                | Q(data__payment__cod_cash_shift_id=legacy.pk)
                | Q(created_at__gte=legacy.opened_at, created_at__lte=bound)
            )
            .exclude(status="cancelled")
            .order_by("created_at", "pk")
        )
        for order in orders_qs:
            data = order.data or {}
            payment = data.get("payment") or {}
            pos_shift_id = self.adopted.get(order.pk) or _int_or_none((data.get("pos") or {}).get("cash_shift_id"))
            created_by_other_shift = bool(pos_shift_id and pos_shift_id != legacy.pk)

            cash_received_q = payment.get("cash_received_q")
            if cash_received_q is not None:
                cod_shift_id = _int_or_none(payment.get("cod_cash_shift_id"))
                if cod_shift_id:
                    if cod_shift_id == legacy.pk:
                        yield order, int(cash_received_q or 0), "cod"
                    continue
                if created_by_other_shift:
                    continue
                self._adopt(order, pos_shift_id, legacy.pk)
                yield order, int(cash_received_q or 0), "cash_received"
                continue
            tenders = payment.get("tenders") or []
            if tenders:
                total_q = 0
                adopted = False
                for tender in tenders:
                    if tender.get("method") != "cash" or tender.get("collection", "terminal") != "terminal":
                        continue
                    tender_shift_id = _int_or_none(tender.get("cash_shift_id"))
                    if tender_shift_id:
                        if tender_shift_id != legacy.pk:
                            continue
                    else:
                        if created_by_other_shift or order.created_at < legacy.opened_at:
                            continue
                    total_q += int(tender.get("amount_q") or 0)
                    adopted = adopted or not tender_shift_id
                if adopted:
                    self._adopt(order, pos_shift_id, legacy.pk)
                if total_q:
                    yield order, total_q, "tenders"
                continue
            if payment.get("method") == "cash" and payment.get("collection", "terminal") != "on_delivery":
                if created_by_other_shift:
                    continue
                self._adopt(order, pos_shift_id, legacy.pk)
                yield order, int(order.total_q or 0), "method"

    def _adopt(self, order, pos_shift_id, shift_pk):
        if pos_shift_id == shift_pk:
            return
        self.adopted[order.pk] = shift_pk


def backfill(apps, schema_editor):
    report = _Backfill(apps).run()
    log.info("cashman backfill: %s", report)


def move_permissions(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))

    legacy_ct = ContentType.objects.filter(app_label="backstage", model="cashshift").first()
    if legacy_ct is None:
        return
    new_ct, _ = ContentType.objects.get_or_create(app_label="cashman", model="shift")
    for legacy_code, new_code in PERMISSION_MAP.items():
        legacy_perm = Permission.objects.filter(content_type=legacy_ct, codename=legacy_code).first()
        if legacy_perm is None:
            continue
        new_perm, _ = Permission.objects.get_or_create(
            content_type=new_ct, codename=new_code, defaults={"name": PERMISSION_NAMES[new_code]}
        )
        for group in Group.objects.filter(permissions=legacy_perm):
            group.permissions.add(new_perm)
        for user in User.objects.filter(user_permissions=legacy_perm):
            user.user_permissions.add(new_perm)

    # Os models morrem nesta migração; o content type e as permissões não podem
    # ficar para trás oferecendo "Pode auditar turnos de caixa" de uma tabela
    # que não existe mais.
    legacy_cts = ContentType.objects.filter(app_label="backstage", model__in=["cashshift", "cashmovement", "posterminal"])
    Permission.objects.filter(content_type__in=legacy_cts).delete()
    legacy_cts.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("backstage", "0023_consumption_eat_in_weight"),
        ("cashman", "0001_initial"),
        ("orderman", "0003_rotulos_em_portugues"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0012_alter_user_first_name_max_length"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
        migrations.RunPython(move_permissions, migrations.RunPython.noop),
        migrations.DeleteModel(name="CashMovement"),
        migrations.DeleteModel(name="CashShift"),
        migrations.DeleteModel(name="POSTerminal"),
    ]
