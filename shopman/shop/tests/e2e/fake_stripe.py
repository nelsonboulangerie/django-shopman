"""Stripe falso, local, para o E2E do Dia 1 (T13 do laudo de 23/10).

O cartão da loja não tem simulador de propósito: o ``payment_mock`` recusa
``method="card"`` porque o que precisa ser provado no cartão só existe no
gateway. Este servidor NÃO substitui o adapter. O ``payment_stripe`` de produção
roda inteiro, com o SDK oficial, e só o endereço da API muda
(``stripe.api_base``, ligado pelo ``settings_e2e``). Do outro lado da
rede fica isto aqui, que responde o pedaço do contrato do Stripe que a compra
com cartão usa:

* ``POST /v1/checkout/sessions``: cria a sessão hospedada e devolve a ``url``.
* ``GET  /v1/checkout/sessions/<id>`` e ``GET /v1/payment_intents/<id>``: leitura
  de reconciliação, caso o app pergunte. ``expand[]=latest_charge`` devolve a
  cobrança inteira, com ``payment_method_details.card.funding`` (crédito), que é de
  onde o adapter tira o código da NFC-e.
* ``POST /v1/payment_intents/<id>/capture``: captura a autorização (``manual``),
  inteira ou ``amount_to_capture``. Fora de ``requires_capture`` recusa como o Stripe.
* ``POST /v1/payment_intents/<id>/cancel``: anula a autorização. Intent já
  capturado recusa como o Stripe (quem devolve dinheiro capturado é o estorno).
* ``POST /v1/checkout/sessions/<id>/expire``: mata a sessão ainda aberta.
* ``POST /v1/refunds``: estorno do capturado, inteiro ou ``amount``, idempotente
  pelo ``Idempotency-Key`` (o adapter repassa a chave, e o retry devolve o MESMO
  estorno). Nada além do capturado e ainda não devolvido.

Captura, anulação e estorno são o F-7 da revisão da Loja (#2568): sem eles, as
jornadas de cartão (cancelar com cartão, J6; entrega com cartão, J8) morriam na
primeira chamada do adapter depois do pagamento.
* ``GET  /pay/<id>``: a "página do Stripe", com um botão de pagar.
* ``POST /pay/<id>``: o cliente pagou. Entrega o webhook
  ``checkout.session.completed`` ASSINADO ao Django (mesmo HMAC do Stripe, com o
  segredo falso do harness) e só então redireciona ao ``success_url``. Webhook
  antes do redirect deixa o teste determinístico: quando o acompanhamento
  carrega, a autorização já está gravada.

Qualquer outra rota responde 404 no formato de erro do Stripe e fica no log,
para que uma chamada nova do adapter apareça no CI em vez de passar calada.

Uso (o ``scripts/run_storefront_e2e.sh`` sobe sozinho)::

    python -m shopman.shop.tests.e2e.fake_stripe --port 12111 \\
        --webhook-url http://127.0.0.1:8001/api/webhooks/stripe/ \\
        --webhook-secret whsec_e2e_fake
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import html
import json
import secrets
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlparse


def _unflatten(pairs: list[tuple[str, str]]) -> dict:
    """``a[b][0][c]=v`` (form do SDK) → dicionário aninhado."""
    root: dict = {}
    for key, value in pairs:
        parts = key.replace("]", "").split("[")
        node = root
        for index, part in enumerate(parts):
            last = index == len(parts) - 1
            if last:
                node[part] = value
            else:
                node = node.setdefault(part, {})
    return root


def sign(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    """Cabeçalho ``Stripe-Signature`` (esquema v1 do Stripe)."""
    ts = int(timestamp if timestamp is not None else time.time())
    signed = f"{ts}.".encode() + payload
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


class FakeStripe:
    def __init__(self, *, public_base: str, webhook_url: str, webhook_secret: str):
        self.public_base = public_base.rstrip("/")
        self.webhook_url = webhook_url
        self.webhook_secret = webhook_secret
        self.sessions: dict[str, dict] = {}
        self.intents: dict[str, dict] = {}
        self.charges: dict[str, dict] = {}
        self.refunds: dict[str, dict] = {}
        self.refunds_by_key: dict[str, str] = {}
        self.lock = threading.Lock()

    def create_session(self, params: dict) -> dict:
        session_id = f"cs_test_e2e_{secrets.token_hex(8)}"
        line = (params.get("line_items") or {}).get("0") or {}
        amount = int(((line.get("price_data") or {}).get("unit_amount")) or 0)
        session = {
            "id": session_id,
            "object": "checkout.session",
            "livemode": False,
            "mode": params.get("mode", "payment"),
            "status": "open",
            "payment_status": "unpaid",
            "payment_intent": None,
            "amount_total": amount,
            "currency": params.get("currency") or "brl",
            "metadata": params.get("metadata") or {},
            "success_url": params.get("success_url", ""),
            "cancel_url": params.get("cancel_url", ""),
            "url": f"{self.public_base}/pay/{session_id}",
            "_intent_metadata": (params.get("payment_intent_data") or {}).get("metadata") or {},
            "_capture_method": (params.get("payment_intent_data") or {}).get("capture_method") or "automatic",
        }
        with self.lock:
            self.sessions[session_id] = session
        return session

    @staticmethod
    def public(obj: dict) -> dict:
        return {k: v for k, v in obj.items() if not k.startswith("_")}

    def pay(self, session_id: str) -> dict:
        """Cliente pagou: sessão completa, PaymentIntent autorizado."""
        with self.lock:
            session = self.sessions[session_id]
            if session["payment_intent"] is None:
                intent_id = f"pi_test_e2e_{secrets.token_hex(8)}"
                charge_id = f"ch_test_e2e_{secrets.token_hex(8)}"
                manual = session["_capture_method"] == "manual"
                # A cobrança nasce na autorização (como no Stripe): sem capturar no
                # `manual`, capturada no `automatic`. O cartão do teste é crédito.
                self.charges[charge_id] = {
                    "id": charge_id,
                    "object": "charge",
                    "livemode": False,
                    "amount": session["amount_total"],
                    "amount_captured": 0 if manual else session["amount_total"],
                    "amount_refunded": 0,
                    "captured": not manual,
                    "refunded": False,
                    "currency": session["currency"],
                    "payment_intent": intent_id,
                    "status": "succeeded",
                    "payment_method_details": {
                        "type": "card",
                        "card": {"brand": "visa", "funding": "credit", "last4": "4242"},
                    },
                }
                self.intents[intent_id] = {
                    "id": intent_id,
                    "object": "payment_intent",
                    "livemode": False,
                    "amount": session["amount_total"],
                    "amount_received": 0 if manual else session["amount_total"],
                    "currency": session["currency"],
                    "capture_method": session["_capture_method"],
                    "status": "requires_capture" if manual else "succeeded",
                    "metadata": session["_intent_metadata"],
                    "latest_charge": charge_id,
                }
                session.update(
                    payment_intent=intent_id,
                    status="complete",
                    payment_status="unpaid" if manual else "paid",
                )
            return session

    # ── O que o adapter faz depois do pagamento (F-7) ────────────────────────────
    # Cada operação devolve ``(status_http, corpo)``; erro no formato do Stripe, que
    # o SDK oficial transforma na exceção certa (``InvalidRequestError``).

    @staticmethod
    def _error(status: int, message: str, code: str = "") -> tuple[int, dict]:
        error = {"type": "invalid_request_error", "message": message}
        if code:
            error["code"] = code
        return status, {"error": error}

    def intent_view(self, intent: dict, expand: list[str]) -> dict:
        view = dict(intent)
        if "latest_charge" in expand and view.get("latest_charge"):
            view["latest_charge"] = dict(self.charges[view["latest_charge"]])
        return view

    def capture(self, intent_id: str, params: dict, expand: list[str]) -> tuple[int, dict]:
        with self.lock:
            intent = self.intents.get(intent_id)
            if intent is None:
                return self._error(404, f"No such payment_intent: '{intent_id}'", "resource_missing")
            if intent["status"] != "requires_capture":
                return self._error(
                    400,
                    f"This PaymentIntent could not be captured because it has a status of {intent['status']}.",
                    "payment_intent_unexpected_state",
                )
            amount = int(params.get("amount_to_capture") or intent["amount"])
            if amount <= 0 or amount > intent["amount"]:
                return self._error(400, "amount_to_capture fora do autorizado.", "amount_too_large")
            intent.update(status="succeeded", amount_received=amount)
            charge = self.charges[intent["latest_charge"]]
            charge.update(captured=True, amount_captured=amount)
            return 200, self.intent_view(intent, expand)

    def cancel(self, intent_id: str, expand: list[str]) -> tuple[int, dict]:
        with self.lock:
            intent = self.intents.get(intent_id)
            if intent is None:
                return self._error(404, f"No such payment_intent: '{intent_id}'", "resource_missing")
            if intent["status"] in {"succeeded", "canceled"}:
                return self._error(
                    400,
                    f"You cannot cancel this PaymentIntent because it has a status of {intent['status']}.",
                    "payment_intent_unexpected_state",
                )
            intent.update(status="canceled", cancellation_reason="requested_by_customer")
            return 200, self.intent_view(intent, expand)

    def expire(self, session_id: str) -> tuple[int, dict]:
        with self.lock:
            session = self.sessions.get(session_id)
            if session is None:
                return self._error(404, f"No such checkout.session: '{session_id}'", "resource_missing")
            if session["status"] != "open":
                return self._error(
                    400,
                    f"Only Checkout Sessions with a status of `open` can be expired (status={session['status']}).",
                )
            session["status"] = "expired"
            return 200, self.public(session)

    def refund(self, params: dict, idempotency_key: str = "") -> tuple[int, dict]:
        with self.lock:
            if idempotency_key and idempotency_key in self.refunds_by_key:
                return 200, dict(self.refunds[self.refunds_by_key[idempotency_key]])
            intent = self.intents.get(params.get("payment_intent") or "")
            if intent is None:
                return self._error(
                    404, f"No such payment_intent: '{params.get('payment_intent')}'", "resource_missing"
                )
            charge = self.charges[intent["latest_charge"]]
            refundable = charge["amount_captured"] - charge["amount_refunded"]
            if refundable <= 0:
                return self._error(400, f"Charge {charge['id']} has already been refunded.", "charge_already_refunded")
            amount = int(params.get("amount") or refundable)
            if amount <= 0 or amount > refundable:
                return self._error(400, "Refund amount is greater than the unrefunded amount.", "amount_too_large")
            refund_id = f"re_test_e2e_{secrets.token_hex(8)}"
            refund = {
                "id": refund_id,
                "object": "refund",
                "amount": amount,
                "currency": intent["currency"],
                "charge": charge["id"],
                "payment_intent": intent["id"],
                "reason": params.get("reason") or None,
                "status": "succeeded",
                "created": int(time.time()),
            }
            charge["amount_refunded"] += amount
            charge["refunded"] = charge["amount_refunded"] >= charge["amount_captured"]
            self.refunds[refund_id] = refund
            if idempotency_key:
                self.refunds_by_key[idempotency_key] = refund_id
            return 200, dict(refund)

    def deliver_completed_webhook(self, session: dict) -> tuple[int, str]:
        event = {
            "id": f"evt_test_e2e_{secrets.token_hex(8)}",
            "object": "event",
            "type": "checkout.session.completed",
            "livemode": False,
            "created": int(time.time()),
            "data": {"object": self.public(session)},
        }
        payload = json.dumps(event).encode()
        request = urllib.request.Request(
            self.webhook_url,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Stripe-Signature": sign(payload, self.webhook_secret),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, response.read().decode(errors="replace")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode(errors="replace")


def _handler(fake: FakeStripe):
    class Handler(BaseHTTPRequestHandler):
        server_version = "FakeStripe/1"

        def log_message(self, fmt, *args):  # noqa: A003 — assinatura da stdlib
            sys.stderr.write(f"[fake-stripe] {self.command} {self.path} :: {fmt % args}\n")

        def _json(self, status: int, body: dict) -> None:
            raw = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Request-Id", f"req_e2e_{secrets.token_hex(6)}")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _not_found(self) -> None:
            sys.stderr.write(f"[fake-stripe] ROTA NÃO IMPLEMENTADA: {self.command} {self.path}\n")
            self._json(
                404,
                {"error": {"type": "invalid_request_error", "message": f"fake: {self.path}"}},
            )

        def _form(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length).decode() if length else ""
            return _unflatten(parse_qsl(raw, keep_blank_values=True))

        def _html(self, status: int, body: str) -> None:
            raw = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _expand(self, form: dict | None = None) -> list[str]:
            # O SDK manda ``expand[0]=latest_charge``: na query (GET) ou no form (POST).
            pairs = parse_qsl(urlparse(self.path).query, keep_blank_values=True)
            values = [value for key, value in pairs if key.startswith("expand")]
            values += list(((form or {}).get("expand") or {}).values())
            return values

        def do_GET(self):  # noqa: N802 — assinatura da stdlib
            path = urlparse(self.path).path.rstrip("/")
            parts = path.split("/")
            if path == "/health":
                return self._json(200, {"ok": True})
            if path.startswith("/v1/checkout/sessions/") and len(parts) == 5:
                session = fake.sessions.get(parts[4])
                return self._json(200, fake.public(session)) if session else self._not_found()
            if path.startswith("/v1/payment_intents/") and len(parts) == 4:
                intent = fake.intents.get(parts[3])
                if not intent:
                    return self._not_found()
                return self._json(200, fake.intent_view(intent, self._expand()))
            if path.startswith("/pay/") and len(parts) == 3:
                session = fake.sessions.get(parts[2])
                if not session:
                    return self._not_found()
                total = session["amount_total"] / 100
                return self._html(
                    200,
                    "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
                    "<title>Checkout de teste</title></head><body>"
                    "<h1>Checkout de teste (Stripe falso do E2E)</h1>"
                    f"<p>Total: R$ {total:.2f}</p>"
                    f"<form method='post' action='/pay/{html.escape(session['id'])}'>"
                    "<button type='submit'>Pagar</button></form></body></html>",
                )
            return self._not_found()

        def do_POST(self):  # noqa: N802 — assinatura da stdlib
            path = urlparse(self.path).path.rstrip("/")
            parts = path.split("/")
            if path == "/v1/checkout/sessions":
                return self._json(200, fake.public(fake.create_session(self._form())))
            if path.startswith("/v1/checkout/sessions/") and len(parts) == 6 and parts[5] == "expire":
                self._form()
                return self._json(*fake.expire(parts[4]))
            if path.startswith("/v1/payment_intents/") and len(parts) == 5 and parts[4] in {"capture", "cancel"}:
                form = self._form()
                expand = self._expand(form)
                if parts[4] == "capture":
                    return self._json(*fake.capture(parts[3], form, expand))
                return self._json(*fake.cancel(parts[3], expand))
            if path == "/v1/refunds":
                return self._json(*fake.refund(self._form(), self.headers.get("Idempotency-Key") or ""))
            if path.startswith("/pay/") and len(parts) == 3:
                if parts[2] not in fake.sessions:
                    return self._not_found()
                self._form()
                session = fake.pay(parts[2])
                status, body = fake.deliver_completed_webhook(session)
                if not 200 <= status < 300:
                    sys.stderr.write(f"[fake-stripe] webhook recusado {status}: {body}\n")
                    return self._html(
                        502, f"<p>Webhook recusado pelo Django: {status}</p><pre>{html.escape(body)}</pre>"
                    )
                self.send_response(303)
                self.send_header("Location", session["success_url"])
                self.send_header("Content-Length", "0")
                self.end_headers()
                return None
            return self._not_found()

    return Handler


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=12111)
    parser.add_argument("--webhook-url", required=True)
    parser.add_argument("--webhook-secret", required=True)
    args = parser.parse_args(argv)
    fake = FakeStripe(
        public_base=f"http://{args.host}:{args.port}",
        webhook_url=args.webhook_url,
        webhook_secret=args.webhook_secret,
    )
    server = ThreadingHTTPServer((args.host, args.port), _handler(fake))
    sys.stderr.write(f"[fake-stripe] ouvindo em http://{args.host}:{args.port}\n")
    server.serve_forever()


if __name__ == "__main__":
    main()
