"""Adapter fiscal de simulação da pilha local (#2585)."""

from __future__ import annotations

import inspect
import json

import pytest
from django.core.checks import Error
from django.core.exceptions import ImproperlyConfigured
from shopman.fiscalman.contracts import FiscalBackend

from shopman.shop import checks
from shopman.shop.adapters.fiscal_simulated import (
    DEFAULT_REJECTION,
    REJECTION_CODE,
    SimulatedFiscalBackend,
    _mod11,
    access_key,
)

pytestmark = pytest.mark.django_db

SIMULATED = "shopman.shop.adapters.fiscal_simulated.SimulatedFiscalBackend"
ITEMS = [{"sku": "PAO", "description": "Pão", "quantity": 1, "unit_price_q": 1000, "total_q": 1000}]
PAYMENT = {"method": "pix", "amount_q": 1000}


@pytest.fixture
def backend(settings, tmp_path):
    settings.TEST_STACK_CONTROL_DIR = str(tmp_path)
    return SimulatedFiscalBackend()


def emit(backend, ref="ORD-SIM-1", **extra):
    return backend.emit(reference=ref, items=ITEMS, payment=PAYMENT, **extra)


def test_it_follows_the_contract_signature():
    contract = set(inspect.signature(FiscalBackend.emit).parameters)
    assert set(inspect.signature(SimulatedFiscalBackend.emit).parameters) == contract
    assert isinstance(SimulatedFiscalBackend.__new__(SimulatedFiscalBackend), FiscalBackend)


def test_it_declares_homologation():
    # É o que deixa a porta fiscal emitir sobre o pagamento simulado da pilha.
    assert SimulatedFiscalBackend.is_homologation is True


def test_it_needs_the_control_dir(settings):
    settings.TEST_STACK_CONTROL_DIR = None
    with pytest.raises(ImproperlyConfigured, match="TEST_STACK_CONTROL_DIR"):
        SimulatedFiscalBackend()


def test_emit_authorizes_with_a_valid_access_key(backend):
    result = emit(backend)

    assert result.success is True
    assert result.status == "authorized"
    assert result.document_number == 1
    assert len(result.access_key) == 44
    assert result.access_key[20:22] == "65"  # modelo NFC-e
    assert int(result.access_key[-1]) == _mod11(result.access_key[:-1])
    assert result.authorization_date
    # Nada que pareça um endereço de provedor de verdade.
    assert result.xml_url is None and result.danfe_url is None


def test_numbers_follow_and_the_same_ref_is_the_same_note(backend):
    first = emit(backend, "ORD-SIM-1")
    second = emit(backend, "ORD-SIM-2")
    again = emit(backend, "ORD-SIM-1")

    assert (first.document_number, second.document_number) == (1, 2)
    assert again.access_key == first.access_key


def test_a_scripted_rejection_refuses_once_and_the_reprocess_authorizes(backend, tmp_path):
    (tmp_path / "fiscal.json").write_text(
        json.dumps({"deny_next": 1, "error_message": "Rejeição 778: Informado NCM inexistente"})
    )

    denied = emit(backend)
    reprocessed = emit(backend)

    assert denied.success is False
    assert denied.status == "denied"
    assert denied.error_code == REJECTION_CODE
    assert denied.error_message == "Rejeição 778: Informado NCM inexistente"
    assert reprocessed.success is True
    assert json.loads((tmp_path / "fiscal.json").read_text())["deny_next"] == 0


def test_a_rejection_without_a_message_uses_one_that_does_not_point_an_item(backend, tmp_path):
    (tmp_path / "fiscal.json").write_text(json.dumps({"deny_next": 1}))

    denied = emit(backend)

    # Sem "nItem": não dispara a reemissão sem GTIN do handler.
    assert denied.error_message == DEFAULT_REJECTION
    assert "nItem" not in DEFAULT_REJECTION


def test_query_reads_what_another_process_emitted(backend, settings):
    emitted = emit(backend)
    other_process = SimulatedFiscalBackend()

    assert other_process.query_status(reference="ORD-SIM-1").access_key == emitted.access_key
    assert other_process.query_status(reference="ORD-NUNCA").status == "not_found"


def test_cancel_marks_the_note(backend):
    emit(backend)

    cancelled = backend.cancel(reference="ORD-SIM-1", reason="Cliente desistiu do pedido")

    assert cancelled.success is True
    assert backend.query_status(reference="ORD-SIM-1").status == "cancelled"
    assert backend.cancel(reference="ORD-NUNCA", reason="x" * 20).success is False


def test_send_email_only_after_authorization(backend):
    assert backend.send_email(reference="ORD-SIM-1", emails=["a@exemplo.com"])[0] is False
    emit(backend)
    assert backend.send_email(reference="ORD-SIM-1", emails=["a@exemplo.com"])[0] is True


def test_access_key_layout():
    key = access_key("2611", "12345678000190", 7)
    assert key.startswith("41" + "2611" + "12345678000190" + "65" + "001" + "000000007")
    assert len(key) == 44


def test_check_refuses_the_simulator_outside_debug(settings):
    settings.DEBUG = False
    settings.SHOPMAN_FISCAL_ADAPTER = SIMULATED

    errors = checks.check_simulated_fiscal_adapter(None)

    assert [e.id for e in errors] == ["SHOPMAN_E029"]
    assert isinstance(errors[0], Error)


def test_check_is_quiet_in_debug(settings):
    settings.DEBUG = True
    settings.SHOPMAN_FISCAL_ADAPTER = SIMULATED
    assert checks.check_simulated_fiscal_adapter(None) == []


def test_the_simulator_and_the_clock_are_open_test_doors(settings, tmp_path):
    settings.DEBUG = False
    settings.SHOPMAN_FISCAL_ADAPTER = SIMULATED
    settings.TEST_STACK_CONTROL_DIR = str(tmp_path)

    doors = " ".join(checks._open_test_doors())

    assert "fiscal_simulated" in doors
    assert "TEST_STACK_CONTROL_DIR" in doors


# ── #3124: a DANFE da nota simulada ─────────────────────────────────────────

REAL_ITEMS = [
    {"sku": "CRO", "name": "Croissant", "qty": "3", "unit": "UN", "unit_price_q": 1300, "total_q": 3900},
]


def test_the_emitted_note_has_an_authorized_xml_that_passes_the_provider_validation(backend):
    from shopman.shop.services.danfe_xml import NS, parse_authorized_xml, value

    result = backend.emit(reference="ORD-XML-1", items=REAL_ITEMS, payment={"method": "pix", "amount_q": 3900})

    content = backend.authorized_xml(result.access_key)
    root = parse_authorized_xml(content, result.access_key)  # a mesma régua da Focus
    info = root.find("n:NFe/n:infNFe", NS)
    assert value(info, "ide/tpAmb") == "2"
    assert value(info, "ide/indPres") == "1"
    assert value(info, "total/ICMSTot/vNF") == "39.00"
    assert value(info, "det/prod/xProd") == "Croissant"
    assert value(info, "pag/detPag/tPag") == "17"


def test_a_delivery_with_a_document_goes_out_remote_with_the_recipient(backend):
    from shopman.shop.services.danfe_xml import NS, parse_authorized_xml, value

    result = backend.emit(
        reference="ORD-XML-2",
        items=REAL_ITEMS,
        payment={"method": "card", "amount_q": 3900},
        customer={"name": "Marta", "tax_id": "52998224725"},
        delivery={"address": {"route": "Rua Santos", "street_number": "450", "city": "Londrina", "state_code": "PR"}},
    )

    root = parse_authorized_xml(backend.authorized_xml(result.access_key), result.access_key)
    info = root.find("n:NFe/n:infNFe", NS)
    assert value(info, "ide/indPres") == "4"
    assert value(info, "dest/CPF") == "52998224725"
    assert value(info, "dest/enderDest/xLgr") == "Rua Santos"


def test_an_unknown_key_has_no_xml(backend):
    assert backend.authorized_xml("4" * 44) is None


def test_the_danfe_reads_the_xml_from_the_simulator_and_never_from_a_made_up_url(settings, tmp_path):
    from shopman.orderman.models import Order

    from shopman.shop.fiscal import fiscal_pool
    from shopman.shop.views.fiscal_danfe import build_danfe

    settings.TEST_STACK_CONTROL_DIR = str(tmp_path)
    settings.SHOPMAN_FISCAL_ADAPTER = SIMULATED
    fiscal_pool.reset()
    try:
        result = SimulatedFiscalBackend().emit(
            reference="ORD-XML-3", items=REAL_ITEMS, payment={"method": "pix", "amount_q": 3900}
        )
        order = Order.objects.create(
            ref="ORD-XML-3", channel_ref="web", status="completed", total_q=3900,
            data={"nfce_access_key": result.access_key, "nfce_number": result.document_number, "nfce_status": "autorizado"},
        )

        document = build_danfe(order.ref)
    finally:
        fiscal_pool.reset()

    assert document is not None
    assert not document.source_problem
    assert document.item_count == 1


def test_a_production_backend_is_never_asked_for_the_xml(monkeypatch):
    """Backend que não se declara homologação não responde XML: a nota vem do provedor."""
    from shopman.shop.fiscal import fiscal_pool
    from shopman.shop.services.danfe_xml import backend_authorized_xml

    class ProductionLike:
        is_homologation = False

        def authorized_xml(self, key):
            raise AssertionError("backend de produção não fornece XML")

    monkeypatch.setattr(fiscal_pool, "get_backend", lambda *args, **kwargs: ProductionLike())
    assert backend_authorized_xml("4" * 44) is None
