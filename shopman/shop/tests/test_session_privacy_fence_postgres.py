"""Real row-lock proofs for the post-deletion Session privacy fence."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic

import pytest
from django.db import close_old_connections, connection, connections, transaction
from shopman.guestman.models import Customer
from shopman.orderman.models import Session, SessionEvent
from shopman.orderman.services.modify import ModifyService

from shopman.shop.services.account import _anonymize_order_trail

requires_postgres = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Requires independent PostgreSQL connections and row locks",
)

pytestmark = [pytest.mark.django_db(transaction=True), requires_postgres]


class Worker:
    def __init__(self, command):
        self.command = command
        self.started = Event()
        self.pid = None

    def __call__(self):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                self.pid = cursor.fetchone()[0]
                cursor.execute("SET lock_timeout = '15s'")
            self.started.set()
            try:
                return self.command()
            except Exception as exc:
                return {"exception": type(exc).__name__, "code": getattr(exc, "code", "")}
        finally:
            connections.close_all()


def _blocking_pids(worker: Worker) -> list[int]:
    assert worker.started.wait(10)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_blocking_pids(%s)", [worker.pid])
        return list(cursor.fetchone()[0])


def _assert_blocked_by(worker: Worker, blocker_pid: int) -> None:
    deadline = monotonic() + 10
    while monotonic() < deadline:
        if blocker_pid in _blocking_pids(worker):
            return
        Event().wait(0.01)
    pytest.fail(f"backend {worker.pid} did not wait for backend {blocker_pid}")


def _customer(suffix: str) -> Customer:
    return Customer.objects.create(
        ref=f"CUS-SESSION-PG-{suffix}",
        first_name="Ana",
        phone=f"+5543999930{suffix}",
    )


def _personal_session(customer: Customer, suffix: str) -> Session:
    return Session.objects.create(
        session_key=f"session-privacy-pg-{suffix}",
        channel_ref="web",
        handle_type="phone",
        handle_ref=customer.phone,
        data={"customer": {"ref": customer.ref, "phone": customer.phone}},
    )


def test_delete_first_makes_stale_direct_save_wait_then_fail_closed():
    customer = _customer("01")
    session = _personal_session(customer, "delete-first")
    stale = Session.objects.get(pk=session.pk)
    deletion_locked = Event()
    release_deletion = Event()

    def delete_subject():
        with transaction.atomic():
            locked_customer = Customer.objects.select_for_update().get(pk=customer.pk)
            locked_session = Session.objects.select_for_update().get(pk=session.pk)
            locked_customer.is_active = False
            locked_customer.phone = ""
            locked_customer.save(update_fields=["is_active", "phone"])
            Session.objects.filter(pk=locked_session.pk).update(
                handle_type="anonymized",
                handle_ref="ANON-delete-first",
                data={},
            )
            deletion_locked.set()
            assert release_deletion.wait(10)

    def stale_write():
        stale.data = {"customer": {"ref": customer.ref, "phone": customer.phone}}
        stale.handle_ref = customer.phone
        stale.save(update_fields=["data", "handle_ref"])

    deletion = Worker(delete_subject)
    writer = Worker(stale_write)
    with ThreadPoolExecutor(max_workers=2) as pool:
        deleted = pool.submit(deletion)
        assert deletion_locked.wait(10)
        written = pool.submit(writer)
        try:
            _assert_blocked_by(writer, deletion.pid)
        finally:
            release_deletion.set()
        assert deleted.result(20) is None
        write_result = written.result(20)

    assert write_result == {"exception": "SessionError", "code": "session_anonymized"}
    session.refresh_from_db()
    assert session.handle_type == "anonymized"
    assert session.handle_ref == "ANON-delete-first"
    assert session.data == {}


def test_modify_identity_takes_customer_before_session_and_deletion_finishes_without_deadlock():
    customer = _customer("02")
    session = Session.objects.create(
        session_key="session-privacy-pg-resolver-first",
        channel_ref="web",
        data={},
    )

    def resolve_identity():
        return ModifyService.modify_session(
            session_key=session.session_key,
            channel_ref=session.channel_ref,
            ops=[
                {
                    "op": "set_data",
                    "path": "customer",
                    "value": {"ref": customer.ref, "phone": customer.phone},
                }
            ],
        )

    def delete_subject():
        with transaction.atomic():
            locked_customer = Customer.objects.select_for_update().get(pk=customer.pk)
            locked_customer.is_active = False
            locked_customer.phone = ""
            locked_customer.save(update_fields=["is_active", "phone"])
            locked_session = Session.objects.select_for_update().get(pk=session.pk)
            Session.objects.filter(pk=locked_session.pk).update(
                handle_type="anonymized",
                handle_ref="ANON-resolver-first",
                data={},
            )

    resolver = Worker(resolve_identity)
    deletion = Worker(delete_subject)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_backend_pid()")
        test_pid = cursor.fetchone()[0]

    with ThreadPoolExecutor(max_workers=2) as pool:
        with transaction.atomic():
            Session.objects.select_for_update().get(pk=session.pk)
            resolved = pool.submit(resolver)
            _assert_blocked_by(resolver, test_pid)
            deleted = pool.submit(deletion)
            # The resolver already owns Customer while waiting for Session, so
            # deletion must queue behind it.  This is the no-deadlock lock order.
            _assert_blocked_by(deletion, resolver.pid)

        resolve_result = resolved.result(20)
        delete_result = deleted.result(20)

    assert not isinstance(resolve_result, dict), resolve_result
    assert delete_result is None
    session.refresh_from_db()
    assert session.handle_type == "anonymized"
    assert session.handle_ref == "ANON-resolver-first"
    assert session.data == {}


def test_delete_first_makes_identity_modify_revalidate_inactive_customer():
    customer = _customer("03")
    session = Session.objects.create(
        session_key="session-privacy-pg-modify-delete-first",
        channel_ref="web",
        data={},
    )
    deletion_locked = Event()
    release_deletion = Event()

    def delete_subject():
        with transaction.atomic():
            locked_customer = Customer.objects.select_for_update().get(pk=customer.pk)
            locked_customer.is_active = False
            locked_customer.phone = ""
            locked_customer.save(update_fields=["is_active", "phone"])
            locked_session = Session.objects.select_for_update().get(pk=session.pk)
            Session.objects.filter(pk=locked_session.pk).update(
                handle_type="anonymized",
                handle_ref="ANON-modify-delete-first",
                data={},
            )
            deletion_locked.set()
            assert release_deletion.wait(10)

    def resolve_identity():
        return ModifyService.modify_session(
            session_key=session.session_key,
            channel_ref=session.channel_ref,
            ops=[{"op": "set_data", "path": "customer_ref", "value": customer.ref}],
        )

    deletion = Worker(delete_subject)
    resolver = Worker(resolve_identity)
    with ThreadPoolExecutor(max_workers=2) as pool:
        deleted = pool.submit(deletion)
        assert deletion_locked.wait(10)
        resolved = pool.submit(resolver)
        try:
            _assert_blocked_by(resolver, deletion.pid)
        finally:
            release_deletion.set()
        assert deleted.result(20) is None
        resolve_result = resolved.result(20)

    assert resolve_result == {"exception": "SessionError", "code": "customer_inactive"}
    session.refresh_from_db()
    assert session.handle_type == "anonymized"
    assert session.data == {}


def test_delete_first_makes_stale_personal_event_wait_then_fail_closed():
    customer = _customer("04")
    session = _personal_session(customer, "event-delete-first")
    stale = Session.objects.get(pk=session.pk)
    deletion_locked = Event()
    release_deletion = Event()

    def delete_subject():
        with transaction.atomic():
            locked_customer = Customer.objects.select_for_update().get(pk=customer.pk)
            locked_session = Session.objects.select_for_update().get(pk=session.pk)
            locked_customer.is_active = False
            locked_customer.phone = ""
            locked_customer.save(update_fields=["is_active", "phone"])
            Session.objects.filter(pk=locked_session.pk).update(
                handle_type="anonymized",
                handle_ref="ANON-event-delete-first",
                data={},
            )
            deletion_locked.set()
            assert release_deletion.wait(10)

    deletion = Worker(delete_subject)
    writer = Worker(
        lambda: stale.emit_event(
            "manual_context",
            payload={"note": "texto pessoal tardio", "sku": "SKU-1"},
        )
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        deleted = pool.submit(deletion)
        assert deletion_locked.wait(10)
        written = pool.submit(writer)
        try:
            _assert_blocked_by(writer, deletion.pid)
        finally:
            release_deletion.set()
        assert deleted.result(20) is None
        write_result = written.result(20)

    assert write_result == {"exception": "SessionError", "code": "session_anonymized"}
    assert not SessionEvent.objects.filter(session_key=session.session_key).exists()


def test_delete_first_blocks_personal_session_item_meta_writer():
    customer = _customer("05")
    original_phone = customer.phone
    session = _personal_session(customer, "meta-delete-first")
    deletion_locked = Event()
    release_deletion = Event()

    def delete_subject():
        with transaction.atomic():
            locked_customer = Customer.objects.select_for_update().get(pk=customer.pk)
            locked_customer.is_active = False
            locked_customer.phone = ""
            locked_customer.save(update_fields=["is_active", "phone"])
            _anonymize_order_trail(
                customer_ref=customer.ref,
                phone=original_phone,
                pseudonym="ANON-meta-delete-first",
            )
            deletion_locked.set()
            assert release_deletion.wait(10)

    def add_personal_line():
        return ModifyService.modify_session(
            session_key=session.session_key,
            channel_ref=session.channel_ref,
            ops=[
                {
                    "op": "add_line",
                    "sku": "SKU-META",
                    "qty": 1,
                    "unit_price_q": 1000,
                    "meta": {
                        "batch_ref": "LOT-KEEP",
                        "customer_note": "texto pessoal tardio",
                    },
                }
            ],
        )

    deletion = Worker(delete_subject)
    writer = Worker(add_personal_line)
    with ThreadPoolExecutor(max_workers=2) as pool:
        deleted = pool.submit(deletion)
        assert deletion_locked.wait(10)
        written = pool.submit(writer)
        try:
            _assert_blocked_by(writer, deletion.pid)
        finally:
            release_deletion.set()
        delete_result = deleted.result(20)
        write_result = written.result(20)

    assert delete_result is None
    assert write_result == {"exception": "SessionError", "code": "session_anonymized"}
    session.refresh_from_db()
    assert session.handle_type == "anonymized"
    assert session.items == []


def test_session_item_meta_writer_first_is_scrubbed_after_deletion_waits():
    customer = _customer("06")
    original_phone = customer.phone
    session = _personal_session(customer, "meta-writer-first")

    def delete_subject():
        with transaction.atomic():
            locked_customer = Customer.objects.select_for_update().get(pk=customer.pk)
            locked_customer.is_active = False
            locked_customer.phone = ""
            locked_customer.save(update_fields=["is_active", "phone"])
            return _anonymize_order_trail(
                customer_ref=customer.ref,
                phone=original_phone,
                pseudonym="ANON-meta-writer-first",
            )

    deletion = Worker(delete_subject)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_backend_pid()")
        writer_pid = cursor.fetchone()[0]

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            Session.objects.select_for_update().get(pk=session.pk)
            ModifyService.modify_session(
                session_key=session.session_key,
                channel_ref=session.channel_ref,
                ops=[
                    {
                        "op": "add_line",
                        "sku": "SKU-META",
                        "qty": 1,
                        "unit_price_q": 1000,
                        "meta": {
                            "batch_ref": "LOT-KEEP",
                            "customer_note": "texto pessoal anterior",
                        },
                    }
                ],
            )
            deleted = pool.submit(deletion)
            _assert_blocked_by(deletion, writer_pid)

        delete_result = deleted.result(20)

    assert "exception" not in delete_result, delete_result
    session.refresh_from_db()
    assert session.handle_type == "anonymized"
    assert len(session.items) == 1
    assert session.items[0]["meta"]["batch_ref"] == "LOT-KEEP"
    assert "customer_note" not in session.items[0]["meta"]
