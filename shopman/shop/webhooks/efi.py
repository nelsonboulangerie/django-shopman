"""EFI PIX webhook — receives payment notifications from EFI gateway.

Authentication contract
-----------------------

EFI authenticates itself to this endpoint in two layers:

1. **mTLS (canonical, production).** EFI's servers present a client
   certificate to a fronting proxy (nginx/traefik). The proxy validates the
   cert against EFI's CA and sets a header (configurable via
   ``SHOPMAN_EFI_WEBHOOK["mtls_header"]``, default ``X-SSL-Client-Verify``)
   to ``SUCCESS``. This is the canonical mechanism supported by EFI.

2. **IP allowlist (optional, off by default).** EFI documents an IP allowlist
   as one of its three mechanisms. ``SHOPMAN_EFI_WEBHOOK["ip_allowlist"]``
   (env ``EFI_WEBHOOK_IP_ALLOWLIST``, comma-separated CIDRs) turns it on.

   **Empty means no enforcement, and empty is the default** — a list nobody
   configured must never be the reason production stops receiving payment
   notifications. Configured, it is checked before the token.

   It is still empty, and the recommendation as of 2026-08-19 is to keep it so:
   EFI notifies from AWS elastic IPs and its two official pages disagree on the
   value (the current PIX doc publishes one address; the help-center article
   publishes 28, and is dated 2017). The survey, the trap of the e-mail block on
   that same page, and the procedure to follow if it is ever switched on live in
   ``docs/runbooks/release-secrets-runbook.md``, section "Allowlist de IP".

   *What is trusted as the source IP:* the **last** entry of
   ``X-Forwarded-For``, falling back to ``REMOTE_ADDR`` when the header is
   absent. On DO App Platform this service is not fronted by a proxy of ours:
   the platform's edge appends the peer address it saw to whatever the caller
   sent, so the last position is the only one a caller cannot forge (it can
   prepend as many fake hops as it likes). Add a hop in front of the app and
   this assumption has to be revisited — the value the app would then read is
   that hop, not EFI. Rejections log the address that was read, which is how
   an operator finds out the CIDR list needs the platform's egress range.

3. **Shared token (always required).** A secret shared between this service
   and the EFI dashboard, verified with :func:`hmac.compare_digest`. Accepted
   in the ``X-Efi-Webhook-Token`` header **or** the ``token`` query parameter.

   ⚠️ **A query string is not our preference — it is EFI's only option.** EFI
   cannot send custom headers on outbound notifications: their documented
   mechanisms are mTLS, an IP allowlist, and "a hash appended to the end of the
   registered webhook URL". The header branch stays for local dev and for any
   future proxy that can inject it; production authenticates by query.

   That secret therefore lands in the provider's access logs, so two
   mitigations are mandatory and NOT optional hygiene:

   * the Sentry ``before_send`` in ``config/settings.py`` strips the query
     string off ``request.url`` — without it every error event carries the
     token in plain text (``send_default_pii=False`` does NOT remove it).
     It is implemented (``_strip_query_string``) and locked by
     ``shopman/shop/tests/test_sentry_query_scrubbing.py``;
   * ``EFI_WEBHOOK_TOKEN`` is rotated like any leaked-by-design credential.
     Rotating means re-registering the webhook URL on EFI's side with the new
     value, because the secret IS part of the URL.

   Because the deployment has no mTLS proxy in front (DO App Platform serves
   this directly, so layer 1's header never arrives), this token is the
   endpoint's only authentication whenever the IP allowlist is empty.

Both layers use **the same code path in dev and prod** — there is no
"skip signature" flag. In local development, a developer must set
``EFI_WEBHOOK_TOKEN`` in ``.env`` to any non-empty value and use the test
helper that POSTs payloads with that token. The verification logic is
identical to production; only the token value differs.

If the token is not configured, all requests are rejected with 401 — in any
environment, including dev. That is deliberate: the "correct" integration is
the one that runs, full stop.

Downstream
----------

On successful authentication and payload parse, this view updates the
payment intent via :class:`PaymentService` and calls
``shopman.shop.lifecycle.dispatch(order, "on_paid")``.

MED (devolução especial do Pix) — o que a Efí NÃO manda
-------------------------------------------------------

O análogo Pix da disputa de cartão é o **MED**: o banco do pagador toma o
dinheiro de volta por suspeita de fraude, sem a loja decidir nada. No cartão,
o Stripe anuncia isso em ``charge.dispute.*`` e o adapter traduz para o
snapshot de chargeback do Payman (ver
``shopman/shop/adapters/payment_stripe.py::handle_dispute_event``).

**Aqui não há equivalente.** A lista documentada de eventos deste webhook (Efí,
`dev.efipay.com.br`, lida em 19/08/2026) tem quatro entradas — ``PIX_RECEBIDO``,
``PIX_ENVIADO``, ``DEVOLUCAO_RECEBIDA``, ``DEVOLUCAO_ENVIADA`` — mais os estados
do Pix Automático. Nenhuma delas é MED ou relato de infração, e a API de gestão
de Pix expõe apenas a devolução que **nós** pedimos
(``PUT``/``GET /v2/pix/:e2eid/devolucao/:id``): não há endpoint de MED nem de
infração para consultar.

Consequências, escritas para não serem redescobertas:

* **o chargeback de Pix continua entrando por reconciliação manual** — o
  operador soube pelo painel/e-mail da Efí e lança pelo mesmo
  ``reconcile_gateway_status(chargeback_q=...)`` que o Stripe usa. Não há
  caminho automático a implementar enquanto a Efí não publicar o evento;
* as notificações ``DEVOLUCAO_*`` que ela **manda** também não são consumidas
  hoje: este view lê só a lista ``pix`` e trata cada item como pagamento
  recebido (``confirm_pix``). O estorno que a loja pede já é gravado no ato da
  chamada à API (``adapters/payment_efi.py::refund``), então a notificação
  seria confirmação, não fonte;
* se a Efí passar a anunciar MED, o lugar de tratar é aqui, e o destino é o
  mesmo ``chargeback_q`` — o Payman não precisa de nada novo.
"""

from __future__ import annotations

import hmac
import ipaddress
import logging

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.shop.services import webhook_idempotency
from shopman.shop.services.pix_confirmation import confirm_pix

logger = logging.getLogger(__name__)


def _get_efi_webhook_setting(key: str, default=None):
    cfg = getattr(settings, "SHOPMAN_EFI_WEBHOOK", {})
    return cfg.get(key, default)


@extend_schema(exclude=True)
class EfiPixWebhookView(APIView):
    """Endpoint para receber notificações de pagamento PIX da EFI."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        return Response(status=status.HTTP_200_OK)

    def post(self, request: Request) -> Response:
        if not self._check_source_ip(request):
            return Response({"error": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

        if not self._check_auth(request):
            return Response({"error": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

        if not request.data:
            return Response({"status": "ok", "check": "accepted"}, status=status.HTTP_200_OK)
        if request.data.get("evento") == "teste_webhook":
            return Response({"status": "ok", "check": "accepted"}, status=status.HTTP_200_OK)

        pix_list = request.data.get("pix", [])
        if not pix_list or not isinstance(pix_list, list):
            return Response({"error": "No pix data in payload"}, status=status.HTTP_400_BAD_REQUEST)

        processed = 0
        replays = 0
        in_progress = 0
        errors = 0
        invalid = 0

        for pix_item in pix_list:
            if not isinstance(pix_item, dict):
                invalid += 1
                continue

            txid = str(pix_item.get("txid") or "").strip()
            e2e_id = str(pix_item.get("endToEndId") or "").strip()
            # ``valor`` é o nome do campo NA EFI, e ele morre aqui: para
            # dentro o pagamento viaja como ``amount``.
            amount = str(pix_item.get("valor") or "").strip()

            if not txid:
                invalid += 1
                continue

            claim = webhook_idempotency.claim(
                "webhook:efi-pix",
                _pix_idempotency_key(txid=txid, e2e_id=e2e_id),
            )
            if claim.replayed:
                replays += 1
                continue
            if claim.in_progress:
                in_progress += 1
                continue

            try:
                confirm_pix(txid=txid, e2e_id=e2e_id, amount=amount)
                webhook_idempotency.mark_done(
                    claim,
                    response_body={"status": "processed", "txid": txid, "e2e_id": e2e_id},
                )
                processed += 1
            except Exception as exc:
                logger.debug("efi.post degraded; using fallback", exc_info=True)
                webhook_idempotency.mark_failed(claim)
                from shopman.shop.services import observability

                observability.record_webhook_failure(
                    provider="efi-pix",
                    reason="processing_failed",
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    external_ref=txid,
                    exc=exc,
                    context={"txid": txid, "e2e_id": e2e_id},
                )
                logger.exception("EfiPixWebhook: error processing txid=%s", txid)
                errors += 1

        # Falha de processamento → 5xx: a EFI só reentrega em não-2xx. O guard
        # de idempotência torna o replay dos itens já processados um no-op.
        # Itens malformados (invalid) não entram: reentrega nunca vai curá-los.
        if errors:
            response_status = status.HTTP_500_INTERNAL_SERVER_ERROR
        elif in_progress:
            response_status = status.HTTP_409_CONFLICT
        else:
            response_status = status.HTTP_200_OK
        return Response(
            {
                "status": "ok" if not errors else "retry",
                "processed": processed,
                "replays": replays,
                "in_progress": in_progress,
                "errors": errors,
                "invalid": invalid,
            },
            status=response_status,
        )

    def _check_source_ip(self, request: Request) -> bool:
        """Aplica a allowlist de CIDRs, quando houver uma configurada.

        Lista vazia devolve ``True`` sem olhar nada: ausência de configuração
        não é motivo para recusar dinheiro. Com lista, o endereço avaliado é o
        descrito no contrato no topo do módulo (última entrada do
        ``X-Forwarded-For``, senão ``REMOTE_ADDR``).
        """
        allowlist = _get_efi_webhook_setting("ip_allowlist") or ()
        if not allowlist:
            return True

        client_ip = _client_ip(request)
        if not client_ip:
            logger.warning("EfiPixWebhook: sem IP de origem legível — rejeitando (allowlist ativa)")
            return False

        try:
            address = ipaddress.ip_address(client_ip)
        except ValueError:
            logger.warning("EfiPixWebhook: IP de origem ilegível (%s) — rejeitando", client_ip)
            return False

        for entry in allowlist:
            try:
                network = ipaddress.ip_network(entry, strict=False)
            except ValueError:
                logger.error(
                    "EfiPixWebhook: CIDR inválido na allowlist (%s) — corrija EFI_WEBHOOK_IP_ALLOWLIST",
                    entry,
                )
                continue
            if address.version == network.version and address in network:
                return True

        logger.warning(
            "EfiPixWebhook: IP %s fora da allowlist %s — rejeitando",
            client_ip,
            list(allowlist),
        )
        return False

    def _check_auth(self, request: Request) -> bool:
        """Authenticate an inbound EFI webhook.

        Always enforces the shared token check. When the proxy has already
        validated EFI's mTLS cert, the ``X-SSL-Client-Verify`` header (or
        whatever is configured in ``SHOPMAN_EFI_WEBHOOK["mtls_header"]``)
        arrives with value ``SUCCESS`` and is logged as additional evidence
        — but the token is still checked on every request, so that dev
        environments (where no proxy exists) use the exact same code path.

        Returns ``True`` if and only if the token is configured and matches.
        Returns ``False`` (→ 401 to the caller) in every other case.
        """
        expected_token = _get_efi_webhook_setting("webhook_token") or ""
        if not expected_token:
            logger.error(
                "EfiPixWebhook: SHOPMAN_EFI_WEBHOOK['webhook_token'] is not "
                "configured — rejecting request. Set EFI_WEBHOOK_TOKEN in the "
                "environment (including local dev) to enable this endpoint.",
            )
            return False

        # Defense-in-depth: if the proxy signalled successful mTLS, log it.
        # Absence is fine in dev; presence in prod just means an extra layer
        # passed before we even got here.
        mtls_header = _get_efi_webhook_setting("mtls_header") or "HTTP_X_SSL_CLIENT_VERIFY"
        mtls_status = request.META.get(mtls_header, "")
        if mtls_status:
            logger.debug("EfiPixWebhook: mTLS pre-auth header %s=%s", mtls_header, mtls_status)

        # Header primeiro (dev local, e qualquer proxy futuro que injete), com
        # fallback para a query. A query NÃO é preferência nossa: a Efí não
        # envia cabeçalho customizado — o mecanismo dela é hash no fim da URL
        # registrada. Como o deploy não tem proxy mTLS (DO App Platform direto,
        # o `X-SSL-Client-Verify` nunca chega), este token é a autenticação
        # ÚNICA daqui, e por isso o vazamento em log é tratado no `before_send`
        # do Sentry (que corta a query string) + rotação.
        token = request.META.get("HTTP_X_EFI_WEBHOOK_TOKEN", "")
        if not token:
            token = request.query_params.get("token", "")

        if not token:
            logger.warning("EfiPixWebhook: missing token — rejecting")
            return False

        if not hmac.compare_digest(token, expected_token):
            logger.warning("EfiPixWebhook: token mismatch — rejecting")
            return False

        return True


def _client_ip(request: Request) -> str:
    """O endereço de origem em que este endpoint confia.

    Última entrada do ``X-Forwarded-For`` — a que a borda da plataforma
    acrescentou, e a única que o chamador não consegue forjar (ele só
    prepende) — com fallback para o ``REMOTE_ADDR`` quando não há header.
    """
    forwarded = str(request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
    if forwarded:
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        if hops:
            return hops[-1]
    return str(request.META.get("REMOTE_ADDR") or "").strip()


def _pix_idempotency_key(*, txid: str, e2e_id: str) -> str:
    if e2e_id:
        return f"e2e:{webhook_idempotency.stable_webhook_key(e2e_id)}"
    return f"txid:{webhook_idempotency.stable_webhook_key(txid)}"
