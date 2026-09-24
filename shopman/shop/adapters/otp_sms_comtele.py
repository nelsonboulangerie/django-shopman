"""SMS OTP sender via Comtele — Brazilian SMS provider (better BR deliverability).

Delivers the login verification code by SMS through Comtele's REST API. Chosen over a
US-number provider for native carrier delivery in Brazil and lower per-message cost.
Implements the Doorman ``send_code(target, code, method) -> bool`` contract behind the
``sms`` sender seam; swap the class in DOORMAN['DELIVERY_SENDERS']['sms'] to change provider.

Config in settings.SHOPMAN_SMS (env-driven). Inert (returns False) until api_key + route are set.
API (portal novo): POST https://api.comtele.com.br/messages/sms/send, header ``x-api-key``,
JSON {receivers:[...], message, route}. A ``route`` é o ID da rota de envio da conta
(``GET https://api.comtele.com.br/routes`` lista; use a rota transacional/Premium para OTP).
Sucesso = HTTP 200 com ``{"hasError": false, ...}``.
"""

from __future__ import annotations

import json
import logging
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

from ._sms import render_message, to_digits

logger = logging.getLogger(__name__)

_COMTELE_SEND_URL = "https://api.comtele.com.br/messages/sms/send"


def _get_config() -> dict:
    return getattr(settings, "SHOPMAN_SMS", {}) or {}


#: Acima disto, o aceite da Comtele já é lento o bastante para o cliente sentir:
#: o envio é SÍNCRONO na request de ``request-code`` (a tela só troca de passo
#: quando a Comtele responde). O evento sai em WARNING para aparecer no log sem
#: virar alerta — lentidão isolada não é falha, mas precisa ser medível.
SLOW_ACCEPT_MS = 5000


def _masked(target: str) -> str:
    """Só os 4 últimos dígitos: o log não precisa do telefone para correlacionar."""
    digits = to_digits(target)
    return f"***{digits[-4:]}" if digits else ""


def _record_failure(detail: str, *, exc: BaseException | None = None, **context) -> None:
    """Falha de envio GRITA: evento ERROR (vira evento no Sentry pela integração de
    logging), ``OperatorAlert`` ``integration_failed`` com debounce e aviso no sino do
    gestor. Sem isto a falha morria num ``logger.warning`` e só o cliente sabia.

    ``detail`` não leva telefone nem código: é a chave de dedupe do alerta, então
    tem de ser a CAUSA (a mesma para todos os clientes), não o caso.
    """
    try:
        from shopman.shop.services.observability import record_integration_failure

        record_integration_failure(
            provider="comtele_sms",
            operation="envio do código de login por SMS",
            detail=detail,
            exc=exc,
            context=context,
        )
    except Exception:  # pragma: no cover - observabilidade nunca derruba o login
        logger.exception("Comtele SMS: falha ao registrar a falha de envio")


class ComteleSMSSender:
    """Send OTP codes by SMS via the Comtele API."""

    def send_code(self, target: str, code: str, method: str) -> bool:
        cfg = _get_config()
        api_key = cfg.get("api_key")
        route = str(cfg.get("route") or "").strip()

        from ._external import inert

        if inert("SHOPMAN_SMS_ALLOW_IN_DEBUG"):
            # Inerte em DEBUG → devolve False para a cadeia do Doorman cair no
            # console (o código de OTP já é exposto em dev). Opt-in real:
            # SHOPMAN_SMS_ALLOW_IN_DEBUG=true.
            logger.info("OTP SMS externo inerte (trava dev/seed) para %s — caindo para o próximo sender (console)", _masked(target))
            return False

        if not api_key or not route:
            # Credencial ausente não alerta daqui: é estado de CONFIGURAÇÃO, e quem o
            # acusa é a prontidão (`backstage/services/integration_readiness.py`).
            # Alertar por request multiplicaria o mesmo fato por cliente.
            missing = "api_key" if not api_key else "route"
            logger.warning("Comtele SMS not configured (%s) — cannot send OTP via %s", missing, method)
            return False

        payload = {
            "receivers": [to_digits(target)],
            "contactGroups": [],
            "message": render_message(cfg, code),
            "route": route,
            "tag": str(cfg.get("tag") or "otp"),
        }
        request = Request(
            _COMTELE_SEND_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"x-api-key": api_key, "content-type": "application/json"},
            method="POST",
        )
        started = time.monotonic()

        def elapsed_ms() -> int:
            return int((time.monotonic() - started) * 1000)

        try:
            with urlopen(request, timeout=cfg.get("timeout", 15)) as response:
                body = json.loads(response.read().decode("utf-8"))
                # Comtele returns HTTP 200 with {"hasError": true/false, ...}; trust the flag.
                if body.get("hasError") is False:
                    duration = elapsed_ms()
                    _accepted_event(duration, route=route, target=target)
                    return True
                reason = str(body.get("message"))[:300]
                logger.warning("Comtele SMS rejected: %s", reason)
                _record_failure(f"recusado pela Comtele: {reason[:120]}", duration_ms=elapsed_ms(), route=route)
                return False
        except HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            logger.warning("Comtele SMS send failed: HTTP %s: %s", e.code, error_body[:300])
            _record_failure(f"HTTP {e.code}", exc=e, duration_ms=elapsed_ms(), route=route)
            return False
        except URLError as e:
            logger.warning("Comtele SMS send failed: URL error: %s", e.reason)
            _record_failure(f"sem resposta ({e.reason})"[:160], exc=e, duration_ms=elapsed_ms(), route=route)
            return False
        except TimeoutError as e:
            logger.warning("Comtele SMS send failed: timeout after %sms", elapsed_ms())
            _record_failure("sem resposta (tempo esgotado)", exc=e, duration_ms=elapsed_ms(), route=route)
            return False
        except Exception as e:  # pragma: no cover - defensive
            logger.exception("Comtele SMS send: unexpected error")
            _record_failure(f"erro inesperado ({e.__class__.__name__})", exc=e, duration_ms=elapsed_ms(), route=route)
            return False


def _accepted_event(duration_ms: int, *, route: str, target: str) -> None:
    """Latência do ACEITE (não da entrega): quanto a request do cliente esperou a
    Comtele. A entrega no celular só a Comtele sabe (painel, relatório por ``tag``)."""
    try:
        from shopman.shop.services.observability import operational_event

        operational_event(
            "otp.sms.accepted",
            level=logging.WARNING if duration_ms >= SLOW_ACCEPT_MS else logging.INFO,
            provider="comtele",
            duration_ms=duration_ms,
            slow=duration_ms >= SLOW_ACCEPT_MS,
            route=route,
            target=_masked(target),
        )
    except Exception:  # pragma: no cover
        logger.info("Comtele SMS OTP sent to %s in %sms", _masked(target), duration_ms)
