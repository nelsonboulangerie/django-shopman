"""O comando operacional delega à recuperação canônica, sem versão paralela."""

from io import StringIO

from django.core.management import call_command


def test_recover_concierge_reports_canonical_recovery(monkeypatch):
    monkeypatch.setattr(
        "shopman.storefront.management.commands.recover_concierge.recover_pending",
        lambda: {"queued": 2, "unknown": 1},
    )
    output = StringIO()

    call_command("recover_concierge", stdout=output)

    assert output.getvalue().strip() == '{"queued": 2, "unknown": 1}'
