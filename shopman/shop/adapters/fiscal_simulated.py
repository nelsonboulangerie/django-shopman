"""Adapter fiscal de simulação da pilha de teste local (#2585).

O único emissor de verdade é a Focus NFe (``fiscal_focusnfe``), um serviço externo:
sem ele a pilha local subia com ``SHOPMAN_W003`` e nenhum estado de nota (autorizada,
recusada, reprocessada, cancelada) se exercitava pela UI. Este adapter responde como
a SEFAZ responderia, sem rede, e se declara homologação: nota sem valor fiscal, que
é o que deixa a porta fiscal emitir sobre pagamento simulado
(``services/fiscal.simulated_payment_blocks_emission``).

Liga-se com ``SHOPMAN_FISCAL_ADAPTER=shopman.shop.adapters.fiscal_simulated.SimulatedFiscalBackend``
e pede a pasta de controle da pilha (``TEST_STACK_CONTROL_DIR``), onde guarda:

- ``fiscal-notes/<ref>.json``: a nota de cada pedido, lida pela consulta e pelo
  cancelamento (o worker emite, o runserver consulta: dois processos);
- ``fiscal.json``, escrito pela suíte: o roteiro de recusa. ``{"deny_next": 1,
  "error_message": "Rejeição 778: ..."}`` recusa a próxima emissão com esse motivo
  e consome a ordem; a emissão seguinte, a do "Reprocessar NFC-e", autoriza. Sem o
  arquivo, toda nota autoriza.

Fora de DEBUG ele não sobe (``SHOPMAN_E029``): a pilha local é o único lugar dele.
"""

from __future__ import annotations

import fcntl
import json
import re
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone
from shopman.fiscalman.contracts import FiscalCancellationResult, FiscalDocumentResult

#: Recusa que não é transitória e não aponta item (não dispara a reemissão sem GTIN).
DEFAULT_REJECTION = "Rejeição 999: Erro não catalogado (nota simulada da pilha de teste)."
REJECTION_CODE = "simulated_sefaz_rejection"
UF_PR = "41"
SERIES = 1


class SimulatedFiscalBackend:
    """FiscalBackend sem rede: autoriza, recusa por roteiro, consulta e cancela."""

    is_homologation = True

    def __init__(self) -> None:
        root = getattr(settings, "TEST_STACK_CONTROL_DIR", None)
        if not root:
            raise ImproperlyConfigured(
                "O adapter fiscal de simulação guarda as notas na pasta de controle da pilha: "
                "defina TEST_STACK_CONTROL_DIR."
            )
        self.root = Path(root)
        self.notes = self.root / "fiscal-notes"
        self.notes.mkdir(parents=True, exist_ok=True)

    # ── contrato ──────────────────────────────────────────────────────────

    def emit(
        self,
        *,
        reference: str,
        items: list[dict],
        customer: dict | None = None,
        payment: dict,
        additional_info: str | None = None,
        delivery: dict | None = None,
        intermediary: dict | None = None,
    ) -> FiscalDocumentResult:
        rejection = self._take_scripted_rejection()
        if rejection is not None:
            return FiscalDocumentResult(
                success=False,
                status="denied",
                error_code=REJECTION_CODE,
                error_message=rejection,
            )
        existing = self._read_note(reference)
        if existing is not None:
            return self._result(existing)
        with self._locked():
            number = self._next_number()
            now = timezone.localtime()
            note = {
                "reference": reference,
                "number": number,
                "series": SERIES,
                "access_key": access_key(now.strftime("%y%m"), _digits(_shop_document()), number),
                "authorization_date": now.isoformat(),
                "protocol": f"1{UF_PR}{now:%y}{number:010d}",
                "status": "authorized",
                "customer_tax_id": _digits((customer or {}).get("cpf") or (customer or {}).get("cnpj")),
                "delivery": bool(delivery),
            }
            self._write_note(reference, note)
        return self._result(note)

    def query_status(self, *, reference: str) -> FiscalDocumentResult:
        note = self._read_note(reference)
        if note is None:
            return FiscalDocumentResult(success=False, status="not_found", error_code="simulated_not_found")
        return self._result(note)

    def send_email(self, *, reference: str, emails: list[str]) -> tuple[bool, str]:
        cleaned = [str(e or "").strip() for e in emails if str(e or "").strip()]
        if not cleaned:
            return False, "Nenhum e-mail para enviar."
        if self._read_note(reference) is None:
            return False, "A NFC-e ainda não está autorizada. Reenvie quando autorizar."
        return True, "Nota simulada: nenhum e-mail sai da pilha de teste."

    def cancel(self, *, reference: str, reason: str) -> FiscalCancellationResult:
        note = self._read_note(reference)
        if note is None:
            return FiscalCancellationResult(
                success=False, error_code="simulated_not_found", error_message="Nota não encontrada."
            )
        now = timezone.localtime()
        note["status"] = "cancelled"
        note["cancellation_reason"] = str(reason or "")
        self._write_note(reference, note)
        return FiscalCancellationResult(
            success=True,
            protocol_number=f"2{UF_PR}{now:%y}{note['number']:010d}",
            cancellation_date=now.isoformat(),
        )

    # ── pasta de controle ─────────────────────────────────────────────────

    def _take_scripted_rejection(self) -> str | None:
        script = self.root / "fiscal.json"
        with self._locked():
            if not script.exists():
                return None
            data = json.loads(script.read_text(encoding="utf-8") or "{}")
            remaining = int(data.get("deny_next") or 0)
            if remaining <= 0:
                return None
            data["deny_next"] = remaining - 1
            script.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return str(data.get("error_message") or DEFAULT_REJECTION)

    def _next_number(self) -> int:
        counter = self.notes / "_sequence"
        number = int(counter.read_text() or "0") + 1 if counter.exists() else 1
        counter.write_text(str(number))
        return number

    def _note_path(self, reference: str) -> Path:
        return self.notes / f"{re.sub(r'[^A-Za-z0-9_-]', '_', reference)}.json"

    def _read_note(self, reference: str) -> dict | None:
        path = self._note_path(reference)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_note(self, reference: str, note: dict) -> None:
        self._note_path(reference).write_text(json.dumps(note, ensure_ascii=False), encoding="utf-8")

    @contextmanager
    def _locked(self):
        with open(self.root / ".fiscal.lock", "a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    @staticmethod
    def _result(note: dict) -> FiscalDocumentResult:
        key = note["access_key"]
        return FiscalDocumentResult(
            success=note["status"] == "authorized",
            document_id=note["reference"],
            document_number=note["number"],
            document_series=note["series"],
            access_key=key,
            authorization_date=note["authorization_date"],
            protocol_number=note["protocol"],
            # Sem XML nem DANFE hospedados: não há provedor para buscar, e a pilha
            # não inventa um endereço que pareça real.
            xml_url=None,
            danfe_url=None,
            qrcode_url=None,
            status=note["status"],
        )


def access_key(yymm: str, cnpj: str, number: int) -> str:
    """Chave de acesso de 44 dígitos no leiaute da NFC-e (modelo 65), com DV módulo 11."""
    cnpj = (cnpj or "").rjust(14, "0")[-14:]
    body = f"{UF_PR}{yymm}{cnpj}65{SERIES:03d}{number:09d}1{number:08d}"
    return body + str(_mod11(body))


def _mod11(digits: str) -> int:
    weights = [2, 3, 4, 5, 6, 7, 8, 9]
    total = sum(int(d) * weights[i % 8] for i, d in enumerate(reversed(digits)))
    rest = total % 11
    return 0 if rest < 2 else 11 - rest


def _digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _shop_document() -> str:
    from shopman.shop.models import Shop

    shop = Shop.load()
    return str(getattr(shop, "document", "") or "")
