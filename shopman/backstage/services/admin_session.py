"""Sessão do Admin: vale enquanto é usada, e morre depois de 14 dias parada.

Gêmea de :mod:`shopman.backstage.services.operator_session`, com outro número e
outra evidência de identidade — e nasceu por um motivo bem concreto.

Em 17/09/2026 a zona de operador passou a renovar a sessão com o uso, e o Admin
ficou **de fora**, com o default do Django: 14 dias contados do LOGIN, sem
renovação. O efeito prático é um corte seco de duas em duas semanas, mesmo para
quem entra no Admin todo santo dia — e, com 2FA inscrito, cada corte custa o
TOTP. Era a queixa que continuava voltando depois daquela correção: ela tratou a
metade errada do sistema.

A regra aqui é a mesma da outra ponta: cada dia com uso empurra o prazo. O
NÚMERO não muda — continua 14 dias, o mesmo que o Admin sempre teve —, só o
ponto de partida: 14 dias desde o último uso, em vez de 14 dias desde o login.
Isso não afrouxa o prazo de um navegador esquecido; só para de punir quem usa.

**Como esta sessão se reconhece.** Pelo CAMINHO, não por marca: quem responde
por ``/admin/`` é o Admin. Não há marca a gravar no login porque a sessão nasce
no ``LoginView`` do Django, que não é nosso. Duas recusas explícitas evitam o
falso positivo:

- **sessão de operador sob `/admin/` não é uso do Admin** — o BFF de operador
  bate em ``/admin/login/`` só para buscar CSRF, e isso não é ninguém
  trabalhando. A marca do operador manda; quem a tem segue a regra de lá.
- **sem `is_staff` não há Admin** — visitante anônimo e cliente da loja não
  renovam nada.

**Uma gravação por dia, no máximo**, pelo mesmo motivo da gêmea: o prazo só é
reescrito quando o que resta cai abaixo de ``IDLE - RENEW_INTERVAL``.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings

from shopman.backstage.services import operator_session

#: Onde o Django guarda o prazo DENTRO da sessão (``SessionBase.set_expiry``).
#: A ausência dela é o que distingue "prazo nunca escrito" de "prazo curto".
SESSION_EXPIRY_KEY = "_session_expiry"


def idle_seconds() -> int:
    """Quanto tempo a sessão do Admin sobrevive sem uso."""
    return int(settings.SHOPMAN_ADMIN_SESSION_IDLE_SECONDS)


def renew_interval_seconds() -> int:
    """De quanto em quanto tempo, no máximo, o uso regrava o prazo."""
    return int(settings.SHOPMAN_ADMIN_SESSION_RENEW_INTERVAL_SECONDS)


def renew_if_due(request) -> bool:
    """Empurrar o prazo para ``IDLE`` à frente, se o último empurrão tem mais de um dia.

    Devolve ``True`` quando renovou. A sessão fica ``modified`` e o
    ``SessionMiddleware`` grava e reemite o cookie com o novo ``max-age``.
    """
    if operator_session.is_operator_session(request):
        return False
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated or not getattr(user, "is_staff", False):
        return False
    session = getattr(request, "session", None)
    if session is None:
        return False

    # ⚠️ PLANTAR O RELÓGIO ANTES DE PODER EMPURRÁ-LO. ``get_expiry_age()`` não
    # olha o banco: ele lê ``_session_expiry`` de DENTRO da sessão e, quando
    # essa chave não existe, devolve ``SESSION_COOKIE_AGE`` — o número do
    # settings, não o que falta. A sessão do Admin nasce sem a chave, porque
    # quem a cria é o ``LoginView`` do Django, que não chama ``set_expiry``.
    # Sem plantar, a conta abaixo daria "cheio" para sempre e a renovação seria
    # letra morta. A primeira requisição no Admin planta; as seguintes empurram.
    # Isso também acerta as sessões que já existiam antes desta mudança.
    if session.get(SESSION_EXPIRY_KEY) is None:
        session.set_expiry(timedelta(seconds=idle_seconds()))
        return True

    if session.get_expiry_age() >= idle_seconds() - renew_interval_seconds():
        return False
    session.set_expiry(timedelta(seconds=idle_seconds()))
    return True
