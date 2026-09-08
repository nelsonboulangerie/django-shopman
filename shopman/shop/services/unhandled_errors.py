"""Exceção não tratada vira ``OperatorAlert`` — o 500 deixa de morrer no log.

Hoje um erro de programação tem exatamente um caminho até o dono da loja: um
cliente reclamando. O traceback existe, mas mora no log do App Platform, que
ninguém lê enquanto a fila anda. Este módulo dá ao 500 o mesmo destino que a
casa já dá a webhook quebrado, integração falhando e worker parado: uma linha
nos alertas operacionais, com reconhecimento.

## Por que ``got_request_exception`` e não o handler do DRF

O ponto de captura é UM, e é o sinal ``django.core.signals.got_request_exception``.

- O ``EXCEPTION_HANDLER`` do DRF (``shopman.shop.api_errors``) só é chamado
  dentro de uma view DRF. Ele **veria** a exceção não tratada (o handler default
  devolve ``None`` e o DRF re-levanta), mas não veria nada do Admin, dos webhooks
  de Efí/Stripe/iFood, das views de health, nem de um erro em middleware. Metade
  do sistema ficaria de fora, e uma cobertura pela metade é pior que nenhuma:
  ensina a confiar num aviso que não cobre o que quebrou.
- Um middleware novo (``process_exception``) veria mais, mas só o que está
  **abaixo** dele na pilha, e passaria a competir por ordem com os dez que já
  existem. Além disso, ``process_exception`` pode devolver resposta — o convite
  para, um dia, alguém engolir o erro sem querer.
- Um handler de ``logging`` no logger ``django.request`` funcionaria, mas amarra
  observabilidade a configuração de log, e o ``LOGGING`` desta casa troca de
  formatter por variável de ambiente.

``got_request_exception`` é o mesmo gancho que a integração Django do Sentry usa,
dispara para **toda** exceção realmente não tratada (o que o Django converte em
404/403 nunca chega aqui) e não tem como alterar a resposta: o retorno do
receiver é descartado. É o único ponto do sistema onde "houve um 500" é um fato
completo.

## O que ele NUNCA pode fazer

Derrubar a requisição. O sinal é enviado de dentro de ``handle_uncaught_exception``
e o Django **propaga** exceção levantada em receiver — se este código estourasse,
a exceção original (a que interessa) seria perdida e substituída pela nossa, e
até o test client deixaria de reportar o erro de verdade. Por isso o receiver
inteiro é um ``try/except`` de última linha: falhar ao avisar nunca é pior que o
erro que se queria avisar.

## Zero PII

O alerta guarda **tipo da exceção, local (arquivo:linha), rota e rastro curto**.
Não guarda corpo de requisição, cabeçalho, cookie nem query string. O texto que
sobra — a mensagem da exceção — passa por :func:`scrub`, que apaga e-mail,
CPF/CNPJ, sequências longas de dígitos (telefone, cartão) e tokens. É a mesma
régua do ``before_send`` do Sentry, pelo mesmo motivo: o webhook da Efí autentica
por ``?token=`` na URL, e telefone e código OTP viajam no corpo de ``/auth/``.

## Como o dedupe evita tempestade

Um bug numa rota quente dispara mil vezes por minuto. A identidade do alerta é
``(tipo da exceção, arquivo:linha)`` — não a rota, não o pedido, não o horário —
e vale por uma janela (default 60 min). Dois portões, nesta ordem:

1. **memória do processo** — um dicionário pequeno, checado antes de qualquer
   query. É ele que segura a rajada: sob tempestade, o banco é consultado no
   máximo uma vez por chave por janela em cada processo;
2. **banco** — ``recent_exists`` com ``active_only=False``, de modo que um alerta
   já **reconhecido** também segura a janela. Quem deu ciente não merece o mesmo
   aviso de volta no minuto seguinte.
"""

from __future__ import annotations

import logging
import re
import sys
import time
import traceback
from collections import OrderedDict
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

ALERT_TYPE = "unhandled_exception"

#: Janela do dedupe, em minutos. Um bug que dura não vira um alerta por request.
DEFAULT_WINDOW_MINUTES = 60

#: Quantos quadros do rastro entram na mensagem. O suficiente para localizar,
#: pouco o bastante para caber num alerta que alguém vai ler no celular.
MAX_FRAMES = 6

#: Teto do texto da exceção depois de higienizado.
MAX_DETAIL = 200

#: Teto de chaves distintas guardadas na memória do processo. Passou disso, a
#: mais antiga sai — o portão do banco continua valendo para ela.
_LOCAL_GATE_SIZE = 512

_local_gate: OrderedDict[str, float] = OrderedDict()


# ── Higienização ─────────────────────────────────────────────────────────────

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_CPF = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
_CNPJ = re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")
_PHONE = re.compile(r"\+?\(?\d{2}\)?[\s-]?\d{4,5}[\s-]?\d{4}")
_DIGIT_RUN = re.compile(r"\d{8,}")
#: Token: 20+ caracteres de alfabeto de segredo, com letra E dígito. O par de
#: lookaheads existe para não comer identificador de código (``MultipleObjects
#: Returned`` não tem dígito) nem ref de pedido (curto demais).
_TOKEN = re.compile(
    r"(?=[A-Za-z0-9_\-]*\d)(?=[A-Za-z0-9_\-]*[A-Za-z])[A-Za-z0-9_\-]{20,}"
)


def scrub(text: str) -> str:
    """Apaga do texto o que não pode sair daqui.

    A ordem importa: e-mail e documentos formatados antes das sequências de
    dígitos, senão ``123.456.789-01`` sairia meio apagado.
    """
    cleaned = str(text or "")
    cleaned = _EMAIL.sub("[email]", cleaned)
    cleaned = _CPF.sub("[documento]", cleaned)
    cleaned = _CNPJ.sub("[documento]", cleaned)
    cleaned = _TOKEN.sub("[token]", cleaned)
    cleaned = _PHONE.sub("[numero]", cleaned)
    cleaned = _DIGIT_RUN.sub("[numero]", cleaned)
    return cleaned


_SAFE_SEGMENT = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{0,30}")


def sanitize_path(path: str) -> str:
    """Devolve o caminho com os segmentos identificáveis trocados por ``*``.

    Um segmento só sobrevive se parecer nome de rota: começa com letra, tem no
    máximo 31 caracteres e não é quase-só-dígito. ``/api/v1/orders/`` passa
    inteiro; ``/pedido/ORD-20260908-0001/`` e ``/auth/5543999998888/`` viram
    ``*`` no lugar que importa. A query string nunca entra.
    """
    raw = str(path or "").split("?", 1)[0]
    parts = []
    for segment in raw.split("/"):
        if not segment:
            parts.append(segment)
        elif _SAFE_SEGMENT.fullmatch(segment) and sum(c.isdigit() for c in segment) <= 4:
            parts.append(segment)
        else:
            parts.append("*")
    return "/".join(parts) or "/"


def _short_file(filename: str) -> str:
    """Últimos três componentes do caminho — ``shop/services/pos.py``."""
    parts = str(filename or "").replace("\\", "/").split("/")
    return "/".join(parts[-3:]) if parts else "?"


def _route(request) -> str:
    """A rota, preferindo o PADRÃO de URL ao caminho concreto.

    ``resolver_match.route`` é o padrão declarado (``api/v1/orders/<str:ref>/``):
    já vem sem dado nenhum do cliente. Sem ele — erro antes da resolução, ou em
    middleware — cai no caminho higienizado.
    """
    if request is None:
        return "(sem request)"
    match = getattr(request, "resolver_match", None)
    route = getattr(match, "route", "") if match is not None else ""
    method = str(getattr(request, "method", "") or "").upper()
    path = f"/{route.lstrip('/')}" if route else sanitize_path(getattr(request, "path", ""))
    return f"{method} {path}".strip()


def _origin_frame(tb) -> tuple[str, int, str]:
    """O último quadro que ainda é código NOSSO — onde o bug mora.

    O quadro mais profundo costuma ser de biblioteca (``psycopg``, ``json``), e
    agrupar por ele juntaria bugs diferentes na mesma chave. O último quadro de
    ``shopman/`` ou ``config/`` é o que responde "quem chamou errado".
    """
    frames = traceback.extract_tb(tb)
    if not frames:
        return ("?", 0, "?")
    ours = [
        frame
        for frame in frames
        if "/shopman/" in frame.filename.replace("\\", "/")
        or "/config/" in frame.filename.replace("\\", "/")
    ]
    frame = (ours or frames)[-1]
    return (_short_file(frame.filename), int(frame.lineno or 0), frame.name or "?")


def _trace(tb) -> str:
    """Rastro curto: ``arquivo:linha em função``, sem argumento nem variável."""
    frames = traceback.extract_tb(tb)[-MAX_FRAMES:]
    return "\n".join(
        f"  {_short_file(f.filename)}:{f.lineno} em {f.name}" for f in frames
    )


# ── Portão de memória ────────────────────────────────────────────────────────


def _local_gate_closed(key: str, window_minutes: int) -> bool:
    """``True`` quando esta chave já foi avisada por este processo na janela."""
    now = time.monotonic()
    seen = _local_gate.get(key)
    if seen is not None and (now - seen) < window_minutes * 60:
        return True
    _local_gate[key] = now
    _local_gate.move_to_end(key)
    while len(_local_gate) > _LOCAL_GATE_SIZE:
        _local_gate.popitem(last=False)
    return False


def reset_local_gate() -> None:
    """Esvazia a memória do processo. Existe para os testes e para o shell."""
    _local_gate.clear()


# ── Registro ─────────────────────────────────────────────────────────────────


def record_unhandled_exception(exc: BaseException, *, request=None):
    """Registra o 500 como ``OperatorAlert``. Devolve o alerta ou ``None``.

    ``None`` quando o dedupe segurou, quando a criação falhou ou quando não há
    exceção — nenhum desses casos é erro deste módulo, e nenhum levanta.
    """
    from shopman.shop.adapters import alert as alert_adapter
    from shopman.shop.services.observability import create_operator_alert

    window_minutes = max(
        1, int(getattr(settings, "SHOPMAN_UNHANDLED_EXCEPTION_WINDOW_MINUTES", DEFAULT_WINDOW_MINUTES))
    )

    exc_type = type(exc).__name__
    file_name, lineno, func = _origin_frame(exc.__traceback__)
    location = f"{file_name}:{lineno}"
    dedupe_key = f"{ALERT_TYPE}:{exc_type}@{location}"

    if _local_gate_closed(dedupe_key, window_minutes):
        return None

    cutoff = timezone.now() - timedelta(minutes=window_minutes)
    # ``active_only=False``: alerta reconhecido também segura a janela. Sem isto,
    # dar ciente durante uma tempestade devolveria o mesmo aviso no request
    # seguinte — o oposto do que "ciente" significa.
    if alert_adapter.recent_exists(ALERT_TYPE, cutoff, message_contains=dedupe_key, active_only=False):
        logger.info("unhandled_exception: já avisado nesta janela (%s).", dedupe_key)
        return None

    detail = scrub(str(exc))[:MAX_DETAIL]
    message = (
        f"Erro não tratado em {_route(request)}: {exc_type}"
        + (f": {detail}" if detail else "")
        + f"\nLocal: {location} em {func}"
        + f"\nRastro:\n{scrub(_trace(exc.__traceback__))}"
    )

    return create_operator_alert(
        type=ALERT_TYPE,
        # "error", não "critical": nesta casa o crítico é reservado ao dinheiro
        # e ao worker morto (reconciliação, `directive_worker_stale`). Um 500 é
        # bug, e bug que vira crítico todo dia esvazia o crítico que importa.
        severity="error",
        message=message,
        dedupe_key=dedupe_key,
        debounce_minutes=window_minutes,
        exception_class=exc_type,
        location=location,
    )


def on_request_exception(sender, request=None, **kwargs) -> None:
    """Receiver de ``got_request_exception``. Nunca levanta, nunca muda a resposta.

    O ``except BaseException`` largo é deliberado: o Django propaga exceção de
    receiver, e uma falha aqui trocaria o erro real do cliente por um erro nosso.
    """
    try:
        exc = sys.exc_info()[1]
        if exc is None:
            return
        record_unhandled_exception(exc, request=request)
    except BaseException:  # noqa: BLE001 - avisar nunca pode derrubar a request
        try:
            logger.exception("unhandled_exception_alert.failed")
        except BaseException:  # noqa: BLE001 - nem o log pode derrubar
            pass


def connect() -> None:
    """Liga o receiver ao sinal. Chamado uma vez, do ``ShopmanConfig.ready``."""
    from django.core.signals import got_request_exception

    got_request_exception.connect(
        on_request_exception,
        dispatch_uid="shopman.shop.unhandled_errors",
        weak=False,
    )


__all__ = [
    "ALERT_TYPE",
    "connect",
    "on_request_exception",
    "record_unhandled_exception",
    "reset_local_gate",
    "sanitize_path",
    "scrub",
]
