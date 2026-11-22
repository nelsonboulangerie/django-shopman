"""ManyChat falso, local, para as jornadas da loja (#3272).

A resposta do login pelo WhatsApp (``shopman/shop/handlers/access_link.py``) é a
casa que manda, pelo ``notification_manychat`` de produção: o "Liberar o Chrome"
e o "Encerrar acesso" (o "Não foi você?") só existem nos botões dessa mensagem.
Sem um ManyChat na pilha, o envio era recusado e a jornada não tinha onde tocar.

Este servidor NÃO substitui o adapter. O adapter roda inteiro e só o endereço da
API muda (``SHOPMAN_MANYCHAT["base_url"]``, o mesmo ``MANYCHAT_API_BASE`` de
sempre, ligado pelo ``settings_e2e``). Do outro lado da rede fica isto aqui, que
aceita o pedaço do contrato do ManyChat que a casa usa e GUARDA cada corpo:

* ``POST /fb/sending/sendContent``: a mensagem de texto (com botões de URL).
* ``POST /fb/sending/sendFlow``: o aviso por flow (template aprovado).
* ``POST /fb/subscriber/setCustomFieldByName``: os campos que o flow lê.

As três exigem ``Authorization: Bearer …`` e ``subscriber_id``, como o ManyChat;
sem eles a resposta é a recusa dele (``status: error``), não um sucesso calado.

E uma rota que o ManyChat não tem, só para a jornada ler o que "chegou" no
WhatsApp da cliente (o celular dela, na pilha):

* ``GET /__sent?subscriber=<id>``: tudo o que foi aceito para esse assinante, do
  mais velho ao mais novo. Cada item traz ``endpoint``, o corpo cru (``body``) e,
  no ``sendContent``, as bolhas (``messages``) e os botões achatados
  (``buttons``: ``[{caption, url}]``). Sem ``subscriber``, tudo.

Qualquer outra rota responde 404 e fica no log, para que uma chamada nova do
adapter apareça na jornada em vez de passar calada.

Uso (o ``scripts/run_storefront_journeys.sh`` sobe sozinho)::

    python -m shopman.shop.tests.e2e.fake_manychat --port 12191
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

#: As rotas do ManyChat que a casa chama (``notification_manychat._api_call``).
ACCEPTED = frozenset({
    "/fb/sending/sendContent",
    "/fb/sending/sendFlow",
    "/fb/subscriber/setCustomFieldByName",
})


class FakeManychat:
    """O que foi aceito, por assinante, na ordem de chegada."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sent: list[dict] = []

    def accept(self, endpoint: str, body: dict) -> dict:
        item = {
            "endpoint": endpoint,
            "subscriber_id": str(body.get("subscriber_id") or ""),
            "received_at": time.time(),
            "body": body,
        }
        if endpoint == "/fb/sending/sendContent":
            messages = list((((body.get("data") or {}).get("content") or {}).get("messages")) or [])
            item["messages"] = messages
            item["buttons"] = [
                {"caption": str(button.get("caption") or ""), "url": str(button.get("url") or "")}
                for message in messages
                for button in (message.get("buttons") or [])
                if button.get("type") == "url"
            ]
        with self._lock:
            self._sent.append(item)
        return item

    def sent(self, subscriber: str = "") -> list[dict]:
        with self._lock:
            return [item for item in self._sent if not subscriber or item["subscriber_id"] == subscriber]


def _refusal(body: dict, endpoint: str, authorization: str) -> str:
    """O motivo da recusa, como o ManyChat recusaria, ou ``""``."""
    if not authorization.startswith("Bearer ") or not authorization[7:].strip():
        return "Authorization header is missing or invalid"
    if not str(body.get("subscriber_id") or "").strip():
        return "subscriber_id is required"
    if endpoint == "/fb/sending/sendContent":
        data = body.get("data") or {}
        content = data.get("content") or {}
        if data.get("version") != "v2" or not content.get("messages"):
            return "data.version v2 and data.content.messages are required"
        if content.get("type") != "whatsapp":
            # O erro que custou caro em produção (3011): sem o canal, o ManyChat avalia a
            # janela de 24h do Messenger. Aqui a recusa vem na hora.
            return "content.type whatsapp is required for a WhatsApp subscriber"
    if endpoint == "/fb/sending/sendFlow" and not str(body.get("flow_ns") or "").strip():
        return "flow_ns is required"
    if endpoint == "/fb/subscriber/setCustomFieldByName" and not str(body.get("field_name") or "").strip():
        return "field_name is required"
    return ""


def _handler(fake: FakeManychat):
    class Handler(BaseHTTPRequestHandler):
        server_version = "FakeManychat/1"

        def log_message(self, fmt, *args):  # noqa: A003 — assinatura da stdlib
            sys.stderr.write(f"[fake-manychat] {self.command} {urlparse(self.path).path} :: {fmt % args}\n")

        def _json(self, status: int, body: dict | list) -> None:
            raw = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _not_found(self) -> None:
            sys.stderr.write(f"[fake-manychat] ROTA NÃO IMPLEMENTADA: {self.command} {self.path}\n")
            self._json(404, {"status": "error", "message": f"fake: {urlparse(self.path).path}"})

        def do_GET(self):  # noqa: N802 — assinatura da stdlib
            url = urlparse(self.path)
            path = url.path.rstrip("/")
            if path == "/health":
                return self._json(200, {"ok": True})
            if path == "/__sent":
                subscriber = (parse_qs(url.query).get("subscriber") or [""])[0].strip()
                return self._json(200, {"sent": fake.sent(subscriber)})
            return self._not_found()

        def do_POST(self):  # noqa: N802 — assinatura da stdlib
            path = urlparse(self.path).path.rstrip("/")
            if path not in ACCEPTED:
                return self._not_found()
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length).decode() if length else "{}")
            except (UnicodeDecodeError, json.JSONDecodeError):
                return self._json(400, {"status": "error", "message": "invalid JSON"})
            if not isinstance(body, dict):
                return self._json(400, {"status": "error", "message": "invalid JSON"})
            refusal = _refusal(body, path, self.headers.get("Authorization") or "")
            if refusal:
                sys.stderr.write(f"[fake-manychat] recusado {path}: {refusal}\n")
                status = 401 if refusal.startswith("Authorization") else 400
                return self._json(status, {"status": "error", "message": refusal})
            fake.accept(path, body)
            return self._json(200, {"status": "success"})

    return Handler


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=12191)
    args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), _handler(FakeManychat()))
    sys.stderr.write(f"[fake-manychat] ouvindo em http://{args.host}:{args.port}\n")
    server.serve_forever()


if __name__ == "__main__":
    main()
