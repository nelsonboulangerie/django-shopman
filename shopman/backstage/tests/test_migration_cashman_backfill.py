"""A migração 0030 leva o caixa legado para o livro do cashman ao centavo (WP-5, ADR-022).

Roda a migração de verdade (``MigrationExecutor``): volta para 0029, monta o
legado como ele existia (terminal, turno fechado com sangria/suprimento/abertura
de gaveta/pedidos de troco, turno ABERTO no corte, pedidos de cada forma que o
``close()`` sabia somar) e aplica a 0030. Prova:

- ``Σ`` do livro de cada turno == contagem cega (o ``count`` absorve a diferença)
- uma linha por pedido em dinheiro, pela mesma atribuição do ``close()`` legado
- pedido que JÁ estava no livro novo não entra de novo
- movimentos viram ``cash_out``/``cash_in`` com o ``receipt_result`` filho
- etiquetas do metadata viram ``drawer_open``/``change_*`` com ``parent``
- turno legado aberto fecha sem contagem e com ``note`` dizendo isso
- permissões de ``backstage.cashshift`` viram ``cashman.shift``; o content type
  legado e as permissões dele somem; as três tabelas somem
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.fixture(autouse=True)
def _leave_the_schema_at_the_head():
    """Este teste anda o banco para TRÁS e, sem isto, o deixava lá.

    O pytest-django roda os testes transacionais por último e no mesmo banco:
    quem vier depois deste no worker herda um schema velho (``cashman`` sem
    ``Shift.opened_by``, ``backstage`` sem as tabelas novas) e quebra com
    ``no such column`` — longe daqui, em teste que nada tem a ver com migração.
    Devolver o banco à folha é responsabilidade de quem o moveu.
    """
    yield
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())


pytestmark = pytest.mark.django_db(transaction=True)

# O estado "antes" precisa enxergar cashman/orderman/auth também: a 0029 não
# depende deles, e o project_state só carrega o que os alvos alcançam. Os alvos
# desses apps são as FOLHAS atuais (não um número fixo): pinar ``cashman/0001``
# desfaria migrações posteriores do pacote e deixaria o banco de teste velho
# para quem roda depois.
#
# ⚠️ O ``cashman`` é a EXCEÇÃO, e é pinado em ``0004``. A ``0005`` renomeia
# ``Shift.operator`` para ``opened_by`` (a custódia virou da gaveta) e declara,
# via ``run_before`` na 0030, que só pode rodar DEPOIS do backfill — porque o
# backfill escreve no campo antigo. Mirar o cashman na folha aqui pediria as
# duas coisas ao mesmo tempo: 0005 aplicada e 0030 desaplicada. O Django recusa
# o plano ("forwards and backwards migrations are not supported"), e ele está
# certo: o mundo desta migração é, por definição, o anterior ao rename.
_CASHMAN_ANTES_DO_RENAME = "0004_account_settled"


def _shared_targets(executor):
    alvos = [("cashman", _CASHMAN_ANTES_DO_RENAME)]
    alvos += [
        (app, name)
        for app in ("orderman", "auth", "contenttypes")
        for name in {node[1] for node in executor.loader.graph.leaf_nodes(app)}
    ]
    return alvos


def _before(executor):
    return [("backstage", "0029_bi_scenario_report"), *_shared_targets(executor)]


def _after(executor):
    return [("backstage", "0030_cashman_backfill_and_cut"), *_shared_targets(executor)]

T0 = datetime(2026, 8, 10, 8, 0, tzinfo=UTC)


def _at(hours: float):
    return T0 + timedelta(hours=hours)


def _migrate(pick_targets):
    executor = MigrationExecutor(connection)
    targets = pick_targets(executor)
    executor.migrate(targets)
    executor.loader.build_graph()
    return executor.loader.project_state(targets).apps


def _order(Order, ref, created_at, *, total_q, payment, status="confirmed", data=None):
    order = Order.objects.create(
        ref=ref,
        channel_ref="pdv",
        status=status,
        total_q=total_q,
        data={"payment": payment, **(data or {})},
    )
    # auto_now_add ignora o valor passado no create; o algoritmo olha created_at.
    Order.objects.filter(pk=order.pk).update(created_at=created_at)
    return Order.objects.get(pk=order.pk)


def _build_legacy(apps, shift_pk_holder):
    User = apps.get_model("auth", "User")
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    POSTerminal = apps.get_model("backstage", "POSTerminal")
    CashShift = apps.get_model("backstage", "CashShift")
    CashMovement = apps.get_model("backstage", "CashMovement")
    Terminal = apps.get_model("cashman", "Terminal")
    Shift = apps.get_model("cashman", "Shift")
    Entry = apps.get_model("cashman", "Entry")
    Order = apps.get_model("orderman", "Order")

    ana = User.objects.create(username="ana", is_staff=True)
    bia = User.objects.create(username="bia", is_staff=True)
    User.objects.create(username="marina", is_staff=True)  # a segunda assinatura, por nome

    # Permissões legadas, como o post_migrate as criava para backstage.CashShift.
    legacy_ct, _ = ContentType.objects.get_or_create(app_label="backstage", model="cashshift")
    legacy_perms = {
        code: Permission.objects.get_or_create(content_type=legacy_ct, codename=code, defaults={"name": code})[0]
        for code in ("operate_pos", "audit_cashshift", "adjust_cashshift", "manage_operators")
    }
    gerente = Group.objects.create(name="Gerente-legado")
    gerente.permissions.add(legacy_perms["audit_cashshift"], legacy_perms["adjust_cashshift"])
    ana.user_permissions.add(legacy_perms["operate_pos"])

    # Terminal legado com a configuração do aparelho; o do pacote já existe sem ela.
    legacy_main = POSTerminal.objects.create(
        ref="pdv-main",
        label="PDV principal",
        channel_ref="pdv",
        metadata={"hardware": {"cash_drawer": {"mode": "agent"}}},
    )
    legacy_two = POSTerminal.objects.create(ref="pdv-2", label="Caixa 2", channel_ref="pdv", location_ref="balcão")
    Terminal.objects.create(ref="pdv-main", label="PDV principal", channel_ref="pdv")

    # ── turno 1: fechado, com tudo ─────────────────────────────────────
    shift1 = CashShift.objects.create(
        terminal=legacy_main,
        operator=ana,
        opened_at=_at(0),
        closed_at=_at(6),
        opening_amount_q=10000,
        blind_closing_amount_q=24000,
        # O close() legado somou 25.700 (incluía o pedido que hoje já está no
        # livro novo): o payload do count guarda isso; a diferença legada era -1.700.
        expected_amount_q=25700,
        difference_q=-1700,
        notes="fechou com falta",
        status="closed",
        metadata={
            "drawer_openings": [{"at": _at(2).isoformat(), "by": "ana", "reason": "trocar nota"}],
            "change_requests": [
                {
                    "ref": "chg-1",
                    "kind": "coins",
                    "amount_q": 0,
                    "note": "moedas",
                    "status": "served",
                    "requested_by": "ana",
                    "requested_at": _at(1).isoformat(),
                    "served_by": "marina",
                    "served_at": _at(1.5).isoformat(),
                    "cancelled_at": "",
                },
                {
                    "ref": "chg-2",
                    "kind": "amount",
                    "amount_q": 5000,
                    "note": "",
                    "status": "cancelled",
                    "requested_by": "ana",
                    "requested_at": _at(3).isoformat(),
                    "served_by": "",
                    "served_at": "",
                    "cancelled_at": _at(3.2).isoformat(),
                },
            ],
        },
    )
    shift_pk_holder["shift1"] = shift1.pk
    CashMovement.objects.create(
        shift=shift1,
        movement_type="sangria",
        amount_q=5000,
        reason="Cofre",
        created_by="ana",
        approved_by="marina",
        created_at=_at(4),
        receipt_status="printed",
        receipt_at=_at(4.01),
    )
    CashMovement.objects.create(
        shift=shift1, movement_type="suprimento", amount_q=2000, created_by="ana", created_at=_at(5)
    )

    # Pedidos de cada forma que o close() sabia somar.
    _order(Order, "O1", _at(1), total_q=3000, payment={"method": "cash", "collection": "terminal"},
           data={"pos": {"cash_shift_id": shift1.pk}})
    _order(Order, "O2", _at(2), total_q=5000, payment={
        "method": "mixed",
        "tenders": [
            {"method": "cash", "amount_q": 4000, "collection": "terminal"},
            {"method": "pix", "amount_q": 1000, "collection": "terminal"},
        ],
    })
    _order(Order, "O3", _at(3), total_q=5000, payment={"method": "mixed", "cash_received_q": 5000},
           data={"pos": {"cash_shift_id": shift1.pk}})
    _order(Order, "O4", _at(3.5), total_q=9999, payment={"method": "cash"}, status="cancelled")
    _order(Order, "O5", _at(7), total_q=8888, payment={"method": "cash"})  # depois do fechamento
    _order(Order, "O6", _at(-2), total_q=6000, payment={
        "method": "cash", "collection": "on_delivery", "cash_received_q": 6000,
        "cod_cash_shift_id": shift1.pk, "cod_settled_at": _at(5.5).isoformat(), "cod_settled_by": "marina",
    })
    _order(Order, "O7", _at(1.5), total_q=1200, payment={"method": "card", "collection": "terminal"})
    _order(Order, "O9", _at(4.5), total_q=700, payment={"method": "cash", "collection": "terminal"})

    # O9 já está no livro novo (venda gravada pelo shop depois do WP-3).
    booked = Shift.objects.create(
        terminal=Terminal.objects.get(ref="pdv-main"), operator=ana,
        opened_at=_at(4.4), closed_at=_at(4.6), status="closed",
    )
    Entry.objects.create(shift=booked, operator=ana, at=_at(4.5), kind="sale", amount_q=700, order_ref="O9")

    # ── turno 2: ABERTO no corte, noutro terminal ──────────────────────
    shift2 = CashShift.objects.create(
        terminal=legacy_two, operator=bia, opened_at=_at(8), opening_amount_q=5000, status="open",
    )
    shift_pk_holder["shift2"] = shift2.pk
    _order(Order, "O8", _at(8.5), total_q=1500, payment={"method": "cash", "collection": "terminal"})


def test_backfill_moves_the_legacy_cash_into_the_ledger_to_the_cent():
    old_apps = _migrate(_before)
    pks = {}
    _build_legacy(old_apps, pks)

    new_apps = _migrate(_after)

    Terminal = new_apps.get_model("cashman", "Terminal")
    Shift = new_apps.get_model("cashman", "Shift")
    Entry = new_apps.get_model("cashman", "Entry")

    # Terminais: o existente ganha a configuração do aparelho; o que faltava nasce.
    main = Terminal.objects.get(ref="pdv-main")
    assert main.metadata == {"hardware": {"cash_drawer": {"mode": "agent"}}}
    two = Terminal.objects.get(ref="pdv-2")
    assert (two.label, two.location_ref, two.channel_ref) == ("Caixa 2", "balcão", "pdv")

    shifts = list(Shift.objects.order_by("opened_at"))
    assert len(shifts) == 3  # turno 1, o que já estava no livro, turno 2
    assert all(s.status == "closed" and s.closed_at is not None for s in shifts)
    shift1 = shifts[0]
    shift2 = shifts[2]
    assert (shift1.operator.username, shift1.terminal.ref, shift1.opened_at, shift1.closed_at) == (
        "ana", "pdv-main", _at(0), _at(6),
    )

    # ── turno 1 ───────────────────────────────────────────────────────
    entries = list(Entry.objects.filter(shift=shift1).order_by("at", "id"))
    by_kind = {}
    for entry in entries:
        by_kind.setdefault(entry.kind, []).append(entry)

    assert sum(e.amount_q for e in entries) == 24000  # == contagem cega

    assert [e.amount_q for e in by_kind["float_in"]] == [10000]
    sales = {e.order_ref: e for e in by_kind["sale"]}
    assert {ref: e.amount_q for ref, e in sales.items()} == {"O1": 3000, "O2": 4000, "O3": 5000}
    assert sales["O2"].payload["source"] == "tenders"
    assert sales["O1"].payload == {
        "legacy": True, "source": "method", "method": "cash", "collection": "terminal", "intents": {},
    }
    cod = by_kind["cod_settled"]
    assert [(e.amount_q, e.order_ref, e.operator.username, e.at) for e in cod] == [(6000, "O6", "marina", _at(5.5))]
    assert not Entry.objects.filter(shift=shift1, order_ref__in=["O4", "O5", "O7", "O9"]).exists()

    (cash_out,) = by_kind["cash_out"]
    assert (cash_out.amount_q, cash_out.reason, cash_out.approved_by.username, cash_out.at) == (-5000, "Cofre", "marina", _at(4))
    (receipt,) = by_kind["receipt_result"]
    assert receipt.parent_id == cash_out.pk
    assert receipt.payload == {"status": "printed", "detail": ""}
    (cash_in,) = by_kind["cash_in"]
    assert (cash_in.amount_q, cash_in.approved_by) == (2000, None)

    (drawer_open,) = by_kind["drawer_open"]
    assert (drawer_open.reason, drawer_open.operator.username, drawer_open.at) == ("trocar nota", "ana", _at(2))
    requested = {e.payload["legacy_ref"]: e for e in by_kind["change_requested"]}
    assert requested["chg-1"].payload["legacy_kind"] == "coins"
    assert requested["chg-2"].payload["amount_q"] == 5000
    (served,) = by_kind["change_served"]
    assert (served.parent_id, served.approved_by.username, served.at) == (requested["chg-1"].pk, "marina", _at(1.5))
    (cancelled,) = by_kind["change_cancelled"]
    assert (cancelled.parent_id, cancelled.at) == (requested["chg-2"].pk, _at(3.2))

    (count,) = by_kind["count"]
    assert count.at == _at(6)
    assert count.amount_q == 24000 - 25000  # contado − Σ do que entrou no livro
    assert count.payload == {
        "counted_q": 24000,
        "notes": "fechou com falta",
        "supervisory": False,
        "legacy": {
            "shift_id": pks["shift1"],
            "expected_q": 25700,
            "difference_q": -1700,
            "reproduced_expected_q": 25700,  # o algoritmo reproduz o legado (incluindo O9)...
            "booked_q": 25000,  # ...mas O9 já estava no livro novo e não entra de novo
            "divergent": False,
        },
    }
    assert "note" not in by_kind
    # O livro continua com todos os pais antes dos filhos (ids crescem com `at`).
    assert all(e.parent_id < e.pk for e in entries if e.parent_id)

    # ── turno 2: aberto no corte ──────────────────────────────────────
    entries2 = list(Entry.objects.filter(shift=shift2).order_by("at", "id"))
    assert sum(e.amount_q for e in entries2) == 6500
    assert [(e.kind, e.amount_q, e.order_ref) for e in entries2 if e.kind != "note"] == [
        ("float_in", 5000, ""),
        ("sale", 1500, "O8"),
    ]
    (note,) = [e for e in entries2 if e.kind == "note"]
    assert note.payload == {"legacy_shift_id": pks["shift2"], "legacy_status": "open", "balance_q": 6500}
    assert "sem contagem" in note.reason
    assert not Entry.objects.filter(shift=shift2, kind="count").exists()

    # ── permissões e tabelas ──────────────────────────────────────────
    Permission = new_apps.get_model("auth", "Permission")
    ContentType = new_apps.get_model("contenttypes", "ContentType")
    Group = new_apps.get_model("auth", "Group")
    User = new_apps.get_model("auth", "User")
    gerente = Group.objects.get(name="Gerente-legado")
    assert set(gerente.permissions.values_list("content_type__app_label", "codename")) == {
        ("cashman", "audit_shift"),
        ("cashman", "adjust_shift"),
    }
    ana = User.objects.get(username="ana")
    assert list(ana.user_permissions.values_list("content_type__app_label", "codename")) == [("cashman", "operate_pos")]
    assert not Permission.objects.filter(content_type__app_label="backstage", codename__endswith="cashshift").exists()
    assert not ContentType.objects.filter(
        app_label="backstage", model__in=["cashshift", "cashmovement", "posterminal"]
    ).exists()
    tables = set(connection.introspection.table_names())
    assert not tables & {"backstage_cashshift", "backstage_cashmovement", "backstage_posterminal"}
