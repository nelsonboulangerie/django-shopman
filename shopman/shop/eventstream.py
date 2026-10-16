"""django-eventstream para o Shopman: a view de stream e as permissões de canal.

Toda rota SSE passa por :func:`events`, nunca pela view crua do
``django_eventstream``. A diferença é a conexão de banco: a view crua lê o banco
(permissão do canal, histórico do ``DjangoModelStorage``) e deixa a conexão aberta
pela vida inteira do stream, porque o Django só a devolve no fim do request. Com
um ``EventSource`` de KDS ou PDV aberto o dia todo, cada tela prendia uma conexão
que não fazia nada. :func:`events` devolve a conexão depois de cada leitura.

Duas higienes de processo moram aqui também (incidente de 14/10/2026):

- **vida máxima** (``SHOPMAN_SSE_MAX_LIFETIME_SECONDS``): o stream termina sozinho e
  o ``EventSource`` reconecta. Stream de cliente que sumiu sem fechar o TCP (aba de
  dispositivo que dormiu, rede que caiu) deixa de durar até o TCP desistir;
- **teto por sessão** (``SHOPMAN_SSE_MAX_STREAMS_PER_SESSION``): o mesmo navegador
  não abre streams sem fim; o excedente recebe 429 e a tela segue no poll de
  fallback. Recusar o novo, e não derrubar o mais velho, é de propósito: derrubar
  faria o velho reconectar e derrubar outro, em roda.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import threading
from collections import Counter

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import connections
from django.http import JsonResponse
from django_eventstream.channelmanager import DefaultChannelManager
from django_eventstream.views import events as _eventstream_events

logger = logging.getLogger(__name__)


def release_db_connections() -> None:
    """Devolve as conexões de banco abertas neste contexto (ao pool, ou fecha).

    Conexão dentro de ``atomic`` fica onde está: fechar ali marcaria a transação
    para rollback. Nenhum caminho de SSE abre transação, então na prática isso só
    protege o ``TestCase``, que embrulha tudo num ``atomic``.
    """
    for conn in connections.all(initialized_only=True):
        if conn.connection is not None and not conn.in_atomic_block:
            conn.close()


#: Streams abertos agora, por chave de sessão. Escrito pelo loop (início e fim de
#: cada stream) e lido pela view (thread do request), daí o lock.
_open_streams: Counter[str] = Counter()
_open_lock = threading.Lock()


def open_streams(key: str) -> int:
    with _open_lock:
        return _open_streams[key]


def _stream_opened(key: str | None) -> None:
    if key:
        with _open_lock:
            _open_streams[key] += 1


def _stream_closed(key: str | None) -> None:
    if key:
        with _open_lock:
            _open_streams[key] -= 1
            if _open_streams[key] <= 0:
                del _open_streams[key]


async def _release_between_reads(content, *, max_lifetime: float = 0, session_key: str | None = None):
    """Repassa o stream devolvendo a conexão antes de cada espera.

    A primeira devolução cobre o que a view e os middlewares abriram (sessão,
    permissão do canal). As seguintes vêm depois de cada pedaço, e todo pedaço
    sai logo depois de uma leitura do histórico ou de um keep-alive, ou seja,
    imediatamente antes de o stream voltar a esperar evento.

    Com ``max_lifetime`` o stream termina quando o prazo vence, mesmo esperando
    evento: o ``EventSource`` reconecta e a contagem da sessão cai na hora.
    """
    release = sync_to_async(release_db_connections)
    _stream_opened(session_key)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max_lifetime if max_lifetime > 0 else None
    source = aiter(content)
    pending: asyncio.Future | None = None
    try:
        await release()
        while True:
            pending = asyncio.ensure_future(anext(source))
            timeout = None if deadline is None else max(0.0, deadline - loop.time())
            done, _ = await asyncio.wait({pending}, timeout=timeout)
            if pending not in done:
                logger.info("sse_stream_closed reason=max_lifetime seconds=%d", int(max_lifetime))
                return
            try:
                chunk = pending.result()
            except StopAsyncIteration:
                return
            finally:
                if pending.done():
                    pending = None
            await release()
            yield chunk
    finally:
        # O cliente saiu (o Django cancela o envio) ou o prazo venceu: a leitura em
        # curso é cancelada DENTRO do stream do django_eventstream, para o ``finally``
        # dele rodar e tirar o listener. Sem isso, o listener ficava para trás.
        if pending is not None and not pending.done():
            pending.cancel()
            with contextlib.suppress(BaseException):
                await asyncio.shield(_settle(pending))
        with contextlib.suppress(Exception):
            await source.aclose()
        _stream_closed(session_key)


async def _settle(future) -> None:
    with contextlib.suppress(BaseException):
        await future


def _session_bucket(request) -> str | None:
    """A chave da contagem: o cookie de sessão resumido (o valor cru não fica em memória)."""
    raw = request.COOKIES.get(settings.SESSION_COOKIE_NAME)
    return hashlib.sha256(raw.encode()).hexdigest()[:16] if raw else None


def _too_many_streams_response(key: str) -> JsonResponse:
    logger.warning("sse_stream_refused reason=per_session_cap open=%d", open_streams(key))
    response = JsonResponse({"detail": "Muitas atualizações abertas neste navegador."}, status=429)
    response["Retry-After"] = "60"
    response["Cache-Control"] = "no-store"
    return response


def events(request, **kwargs):
    """A view de stream do ``django_eventstream``, sem prender conexão de banco."""
    session_key = _session_bucket(request)
    cap = int(getattr(settings, "SHOPMAN_SSE_MAX_STREAMS_PER_SESSION", 0) or 0)
    if session_key and cap > 0 and open_streams(session_key) >= cap:
        return _too_many_streams_response(session_key)
    response = _eventstream_events(request, **kwargs)
    if getattr(response, "streaming", False) and getattr(response, "is_async", False):
        response.streaming_content = _release_between_reads(
            response.streaming_content,
            max_lifetime=float(getattr(settings, "SHOPMAN_SSE_MAX_LIFETIME_SECONDS", 0) or 0),
            session_key=session_key,
        )
    return response


class ShopmanChannelManager(DefaultChannelManager):
    """Restrict sensitive SSE channels while keeping public stock updates."""

    def is_channel_reliable(self, channel):
        channel = str(channel or "")
        if channel.startswith("stock-") or channel.startswith("fomo-") or channel == "pickup-board":
            # Efêmeros: sem histórico/resume — a verdade é refeita no fetch canônico.
            return False
        return super().is_channel_reliable(channel)

    def can_read_channel(self, user, channel):
        channel = str(channel or "")
        if channel.startswith("order-"):
            return self._can_read_order_channel(user, channel.removeprefix("order-"))
        if channel.startswith("user-"):
            return self._can_read_user_channel(user, channel.removeprefix("user-"))
        if channel.startswith("backstage-"):
            return self._can_read_backstage_channel(user, channel.removeprefix("backstage-"))
        return super().can_read_channel(user, channel)

    @staticmethod
    def _can_read_backstage_channel(user, suffix: str) -> bool:
        """Canal de operador: exige a MESMA permissão da tela que ele alimenta.

        Antes bastava ``is_staff``. Isso fazia do SSE a porta larga ao lado da
        porta estreita: o cozinheiro (só ``backstage.operate_kds``) assinava
        ``/events/alerts/`` e recebia todo pedido de troco do balcão com valor,
        cédulas, terminal e quem pediu — dado que o endpoint equivalente nunca
        lhe entregaria. E o cookie do operador é cross-subdomínio, então a
        sessão da cozinha já alcança o host do gestor.

        Pior que o vazamento era a forma: como o teste era só prefixo + staff,
        TODO canal ``backstage-*`` novo nascia legível para todo staff, em
        silêncio, sem ninguém decidir nada. Por isso ``kind`` desconhecido é
        NEGADO: um canal novo não estreia aberto, estreia inacessível até
        alguém escrever aqui de quem ele é.

        O ``kind`` é o primeiro segmento (``backstage-<kind>-<scope>``); o
        escopo pode ter hífen (``backstage-kds-bancada-2``), o kind não.
        """
        if not (user and getattr(user, "is_authenticated", False)):
            return False
        if not (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
            return False

        kind = suffix.split("-", 1)[0]
        codes = _BACKSTAGE_CHANNEL_RULES.get(kind)
        if codes is None:
            logger.warning("eventstream_backstage_channel_unmapped kind=%s", kind)
            return False
        try:
            # ``has_perm`` já devolve True para superusuário — mesma avaliação do
            # ``HasBackstagePermission`` da API, para o canal e o endpoint não
            # divergirem no caso do dono.
            return any(user.has_perm(code) for code in codes)
        except Exception:
            logger.warning("eventstream_backstage_permission_failed kind=%s", kind, exc_info=True)
            return False

    @staticmethod
    def _can_read_user_channel(user, user_id: str) -> bool:
        """Canal pessoal: só o próprio dono. Nem staff lê a caixa alheia."""
        if not user_id.isdigit() or not getattr(user, "is_authenticated", False):
            return False
        return str(getattr(user, "pk", "")) == user_id

    @staticmethod
    def _can_read_order_channel(user, order_ref: str) -> bool:
        if not order_ref:
            return False
        try:
            from shopman.orderman.models import Order

            from shopman.shop.services import customer_orders

            order = Order.objects.filter(ref=order_ref).first()
            if order is None:
                return False
            if order_ref in set(getattr(user, "_shopman_order_sse_refs", ()) or ()):
                return True
            return customer_orders.user_can_access_order(user, order)
        except Exception:
            logger.warning("eventstream_order_permission_failed order=%s", order_ref, exc_info=True)
            return False


#: ``backstage-<kind>`` → quem pode ler. Cada entrada é a permissão da TELA que
#: mostra aquele mesmo conteúdo; quando mais de uma tela legítima o mostra, vale
#: qualquer uma delas (o canal é o push de um fetch canônico, e quem já pode
#: fazer o fetch não descobre nada de novo pelo push).
#:
#:   orders     → fila do Gestor (``shop.manage_orders``) **e** a cozinha
#:                (``backstage.operate_kds``), as duas réguas de
#:                ``ORDER_BOARD_PERMISSIONS``. O painel de retirada NÃO usa este
#:                canal: tem o seu, público e de corpo vazio (``pickup-board``).
#:   kds        → views de KDS (``backstage.operate_kds``).
#:   production → qualquer grant nominal que torne ``can_access_board``
#:                verdadeiro no resolvedor da superfície de produção.
#:   cash       → o PDV (``cashman.operate_pos``, a mesma régua do ``POSView``).
#:                Pedido de troco, devolução pendente e turno aberto/fechado —
#:                o push que faz outra estação refazer o fetch da Projection sem
#:                F5. O corpo é ``kind``+``ref`` (sinal mínimo, ADR-016): valor e
#:                cédulas ficam onde sempre estiveram, no fetch canônico gateado.
#:   alerts     → ``can_view_operator_alerts`` na sua metade estática: o canal
#:                voltou a carregar SÓ o ``OperatorAlert`` (id/tipo/severidade)
#:                depois que o pedido de troco ganhou o canal ``cash``, então o
#:                gate volta a ser o da lista de alertas. A metade dinâmica do
#:                predicado (``resolve_production_access``, acesso por coluna)
#:                não cabe num mapa de códigos — quem só entra por ela segue no
#:                poll do endpoint, que já a avalia.
#:
#: São os MESMOS códigos que os gates das views resolvem — não uma segunda
#: régua. Ficam aqui como código, e não como import de
#: ``shopman.backstage.permissions``, porque ``shop`` não importa superfície fora
#: de ``adapters/`` (test_architecture / test_import_boundaries), e um seam de
#: adapter para ler cinco strings seria cerimônia sem consumidor.
_BACKSTAGE_CHANNEL_RULES = {
    "catalog": ("shop.manage_catalog",),
    "orders": ("shop.manage_orders", "backstage.operate_kds"),
    "kds": ("backstage.operate_kds",),
    "production": (
        "shop.manage_production",
        "backstage.operate_production",
        "shop.view_production_suggested",
        "shop.edit_production_suggested",
        "shop.view_production_planned",
        "shop.edit_production_planned",
        "shop.view_production_started",
        "shop.edit_production_started",
        "shop.view_production_finished",
        "shop.edit_production_finished",
        "shop.view_production_unsold",
        "shop.edit_production_unsold",
    ),
    "cash": ("cashman.operate_pos",),
    # O balcão precisa saber que a COZINHA mexeu numa comanda dele (o badge "Na
    # cozinha" vira "Pronto", "Cancelado"). Assinar o canal `kds` resolveria o
    # push e abriria demais: ali trafega o board inteiro da cozinha, e quem opera
    # o caixa não tem `operate_kds`. Então existe um canal próprio, com a
    # permissão do PDV, carregando SINAL MÍNIMO — a chave da comanda e mais nada.
    # Quem recebe refaz o fetch canônico da Projection do terminal, que já é
    # filtrada pelo gate do balcão (ADR-016).
    "tabs": ("cashman.operate_pos",),
    "alerts": (
        "shop.manage_orders",
        "shop.manage_production",
        "cashman.operate_pos",
        "backstage.operate_kds",
        "backstage.operate_production",
    ),
}
