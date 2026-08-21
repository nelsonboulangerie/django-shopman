"""django-eventstream channel permissions for Shopman."""

from __future__ import annotations

import logging

from django_eventstream.channelmanager import DefaultChannelManager

logger = logging.getLogger(__name__)


class ShopmanChannelManager(DefaultChannelManager):
    """Restrict sensitive SSE channels while keeping public stock updates."""

    def is_channel_reliable(self, channel):
        channel = str(channel or "")
        if channel.startswith("stock-") or channel.startswith("fomo-"):
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
#:   orders     → fila do Gestor (``shop.manage_orders``) **e** painel de retirada
#:                do KDS (``backstage.operate_kds``), que consome o mesmo
#:                ``/sse/orders`` no BFF do kds-nuxt. O corpo é ``ref``+``status``,
#:                exatamente o que as duas telas já leem por REST.
#:   kds        → views de KDS (``backstage.operate_kds``).
#:   production → views de produção (``backstage.operate_production``).
#:   alerts     → ⚠️ NÃO é ``can_view_operator_alerts`` (a regra do
#:                ``/api/v1/backstage/alerts/``). Este canal carrega HOJE, além
#:                do alerta, o pedido de troco do balcão com ``amount_q`` e
#:                ``denominations`` — dado de caixa que a lista de alertas não
#:                expõe. Um canal só tem UM gate, então ele vale pelo conteúdo
#:                mais sensível que trafega nele: o do caixa. Nenhuma superfície
#:                assina ``/events/alerts/`` hoje (elas leem alerta por poll),
#:                então isto não fecha porta de ninguém. Quando o pedido de troco
#:                ganhar canal próprio (``backstage-cash-*``), este volta a
#:                espelhar ``can_view_operator_alerts``.
#:
#: São os MESMOS códigos que as views declaram em ``required_permission`` e que o
#: ``HasBackstagePermission`` avalia com ``user.has_perm(code)`` — não uma segunda
#: régua. Ficam aqui como código, e não como import de
#: ``shopman.backstage.permissions``, porque ``shop`` não importa superfície fora
#: de ``adapters/`` (test_architecture / test_import_boundaries), e um seam de
#: adapter para ler quatro strings seria cerimônia sem consumidor.
_BACKSTAGE_CHANNEL_RULES = {
    "orders": ("shop.manage_orders", "backstage.operate_kds"),
    "kds": ("backstage.operate_kds",),
    "production": ("backstage.operate_production",),
    "alerts": ("cashman.operate_pos",),
}
