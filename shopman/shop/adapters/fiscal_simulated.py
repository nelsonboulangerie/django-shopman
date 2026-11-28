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
- ``fiscal-notes/<chave>.xml``: o XML autorizado da nota (#3124), de onde a DANFE
  da pilha é composta (``authorized_xml``, lido por ``danfe_xml.backend_authorized_xml``);
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
                "customer_tax_id": _digits(
                    (customer or {}).get("tax_id") or (customer or {}).get("cpf") or (customer or {}).get("cnpj")
                ),
                "delivery": bool(delivery),
            }
            self._write_note(reference, note)
            self._write_xml(note, items=items, customer=customer, payment=payment, delivery=delivery)
        return self._result(note)

    def authorized_xml(self, access_key: str) -> bytes | None:
        """O XML autorizado da nota simulada, pela chave de acesso (#3124).

        A DANFE (tela e bobina) é composta só do XML autorizado. Em produção ele
        vem do provedor, pela URL; aqui não há provedor, e a view pergunta ao
        backend antes (``danfe_xml.backend_authorized_xml``). O XML passa pela
        mesma validação da Focus (``parse_authorized_xml``).
        """
        path = self.notes / f"{_digits(access_key)}.xml"
        return path.read_bytes() if path.exists() else None

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

    def _write_xml(self, note: dict, *, items, customer, payment, delivery) -> None:
        content = authorized_nfce_xml(note, items=items, customer=customer, payment=payment, delivery=delivery)
        (self.notes / f"{note['access_key']}.xml").write_bytes(content)

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
            # Sem endereço de XML nem de DANFE: a pilha não inventa uma URL que pareça
            # de provedor. O XML autorizado sai do próprio backend (``authorized_xml``).
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


#: O meio de pagamento da nota (tPag): dinheiro, cartão de crédito, Pix; o resto é "outros".
_TPAG = {"cash": "01", "card": "03", "credit": "03", "debit": "04", "pix": "17"}
#: Padrão da SEFAZ para endereço vazio: o emitente e o destinatário sempre têm logradouro.
_NO_STREET = "Endereço não cadastrado"


def authorized_nfce_xml(note: dict, *, items, customer, payment, delivery) -> bytes:
    """Um ``nfeProc`` de NFC-e autorizada em homologação, com o que a emissão recebeu.

    O mesmo molde da fixture ``shop/tests/fixtures/danfe-authorized.xml``: nota sem
    assinatura e sem valor fiscal (``tpAmb`` 2), com os campos que a bobina e a tela
    da DANFE leem. Entrega com documento e endereço sai não presencial (``indPres``
    4, com destinatário); o resto sai presencial (``indPres`` 1).
    """
    from xml.etree import ElementTree as ET

    from shopman.shop.models import Shop

    ns = "http://www.portalfiscal.inf.br/nfe"
    ET.register_namespace("", ns)

    def sub(parent, tag: str, text: object = None, **attrs):
        node = ET.SubElement(parent, f"{{{ns}}}{tag}", attrs)
        if text is not None:
            node.text = str(text)
        return node

    def money(cents) -> str:
        return f"{int(cents or 0) / 100:.2f}"

    shop = Shop.load()
    key = note["access_key"]
    tax_id = note.get("customer_tax_id") or ""
    address = dict((delivery or {}).get("address") or {})
    remote = bool(tax_id and address.get("route"))

    proc = ET.Element(f"{{{ns}}}nfeProc", {"versao": "4.00"})
    nfe = sub(proc, "NFe")
    info = sub(nfe, "infNFe", Id=f"NFe{key}", versao="4.00")
    ide = sub(info, "ide")
    for tag, text in (
        ("mod", "65"), ("nNF", note["number"]), ("serie", note["series"]), ("dhEmi", note["authorization_date"]),
        ("tpAmb", "2"), ("tpEmis", "1"), ("indPres", "4" if remote else "1"),
    ):
        sub(ide, tag, text)
    emit = sub(info, "emit")
    sub(emit, "CNPJ", _digits(getattr(shop, "document", "")) or "00000000000191")
    sub(emit, "xNome", getattr(shop, "legal_name", "") or getattr(shop, "name", "") or "Loja")
    sub(emit, "xFant", getattr(shop, "name", "") or "Loja")
    ender = sub(emit, "enderEmit")
    sub(ender, "xLgr", getattr(shop, "route", "") or _NO_STREET)
    sub(ender, "nro", getattr(shop, "street_number", "") or "S/N")
    sub(ender, "xBairro", getattr(shop, "neighborhood", "") or "Centro")
    sub(ender, "xMun", getattr(shop, "city", "") or "Londrina")
    sub(ender, "UF", "PR")
    sub(ender, "CEP", _digits(getattr(shop, "postal_code", "")) or "86000000")
    if tax_id:
        dest = sub(info, "dest")
        sub(dest, "CPF" if len(tax_id) == 11 else "CNPJ", tax_id)
        sub(dest, "xNome", str((customer or {}).get("name") or "Consumidor"))
        if remote:
            ender = sub(dest, "enderDest")
            sub(ender, "xLgr", address.get("route") or _NO_STREET)
            sub(ender, "nro", address.get("street_number") or "S/N")
            if address.get("complement"):
                sub(ender, "xCpl", address["complement"])
            sub(ender, "xBairro", address.get("neighborhood") or "Centro")
            sub(ender, "xMun", address.get("city") or "Londrina")
            sub(ender, "UF", address.get("state_code") or "PR")
            sub(ender, "CEP", _digits(address.get("postal_code")) or "86000000")
    total_q = 0
    for index, item in enumerate(items or (), start=1):
        det = sub(info, "det", nItem=str(index))
        prod = sub(det, "prod")
        line_q = int(item.get("total_q") or 0)
        total_q += line_q
        sub(prod, "cProd", item.get("sku") or index)
        sub(prod, "xProd", item.get("name") or item.get("description") or item.get("sku") or "Item")
        sub(prod, "qCom", f"{float(item.get('qty') or item.get('quantity') or 0):.4f}")
        sub(prod, "uCom", str(item.get("unit") or "UN").upper())
        sub(prod, "vUnCom", f"{int(item.get('unit_price_q') or 0) / 100:.10f}")
        sub(prod, "vProd", money(line_q))
    paid_q = int((payment or {}).get("amount_q") or total_q)
    icms = sub(sub(info, "total"), "ICMSTot")
    sub(icms, "vProd", money(total_q))
    sub(icms, "vNF", money(paid_q))
    sub(icms, "vTotTrib", "0.00")
    pag = sub(info, "pag")
    detpag = sub(pag, "detPag")
    sub(detpag, "tPag", _TPAG.get(str((payment or {}).get("method") or ""), "99"))
    sub(detpag, "vPag", money(paid_q))
    adic = sub(info, "infAdic")
    sub(adic, "infAdFisco", "Nota simulada da pilha de teste, sem valor fiscal.")
    sub(adic, "infCpl", f"Pedido {note['reference']}.")
    supl = sub(nfe, "infNFeSupl")
    sub(supl, "qrCode", f"http://www.fazenda.pr.gov.br/nfce/qrcode?p={key}|3|2")
    sub(supl, "urlChave", "http://www.fazenda.pr.gov.br/nfce/consulta")
    prot = sub(sub(proc, "protNFe"), "infProt")
    for tag, text in (
        ("tpAmb", "2"), ("chNFe", key), ("dhRecbto", note["authorization_date"]),
        ("nProt", note["protocol"]), ("cStat", "100"),
    ):
        sub(prot, tag, text)
    return ET.tostring(proc, encoding="utf-8", xml_declaration=True)
