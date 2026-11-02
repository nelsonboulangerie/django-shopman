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
  de reconciliação, caso o app pergunte.
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
                manual = session["_capture_method"] == "manual"
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
                    "latest_charge": None,
                }
                session.update(
                    payment_intent=intent_id,
                    status="complete",
                    payment_status="unpaid" if manual else "paid",
                )
            return session

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
                return self._json(200, intent) if intent else self._not_found()
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
