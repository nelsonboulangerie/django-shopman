"""Sessão dos apps de operador: vale enquanto é usada, e morre depois de 7 dias parada.

Decisão do dono (17/09/2026). O default do Django — 14 dias contados do login, e o
uso não renova — derrubava o gestor em uso no meio da semana e, ao mesmo tempo,
mantinha viva por duas semanas a sessão de um aparelho esquecido. A regra passa a
ser a do uso: cada dia com uso empurra o prazo para 7 dias à frente.

**Quem é sessão de operador.** A que nasceu numa das portas de operador —
``OperatorLoginView`` (senha no app) e ``OperatorUnlockView`` (PIN ou crachá) —,
marcada com :data:`SESSION_MARKER` logo depois do ``login()``. A marca mora DENTRO
da sessão, gravada pelo servidor; nenhum header que o chamador escreva a produz. A
sessão do Admin nasce no ``LoginView`` do Django, sem marca, e tem regra
própria em :mod:`shopman.backstage.services.admin_session` — mesma ideia, 14
dias, reconhecida pelo CAMINHO em vez da marca. (Até 17/09 ela ficava com o
default do Django, 14 dias fixos a partir do login; foi o que fez a queixa do
"login do Django caindo" sobreviver à correção da zona de operador.)

**Uma gravação por dia, no máximo.** A renovação só acontece quando o prazo
restante cai abaixo de ``IDLE - RENEW_INTERVAL`` (6 dias). Poll de 5 s não vira
``UPDATE`` a cada 5 s: no dia em que renovou, o restante fica acima do limiar até
o dia seguinte.

O prazo é gravado como DATA (``set_expiry(timedelta)`` → ISO), não como segundos:
com segundos, ``get_expiry_age()`` devolve o número guardado, e não o que falta —
seria impossível saber quando renovar.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings

#: Chave em ``request.session`` que diz "esta sessão nasceu numa porta de operador".
SESSION_MARKER = "shopman_operator_session"


def idle_seconds() -> int:
    """Quanto tempo a sessão de operador sobrevive sem uso."""
    return int(settings.SHOPMAN_OPERATOR_SESSION_IDLE_SECONDS)


def renew_interval_seconds() -> int:
    """De quanto em quanto tempo, no máximo, o uso regrava o prazo."""
    return int(settings.SHOPMAN_OPERATOR_SESSION_RENEW_INTERVAL_SECONDS)


def start(request) -> None:
    """Marcar a sessão recém-aberta como de operador e dar a ela o prazo de ociosidade.

    Chamado logo DEPOIS do ``login()``: o login troca a chave (e, se era outra
    pessoa, esvazia a sessão), então marcar antes seria marcar a sessão que morreu.
    """
    request.session[SESSION_MARKER] = True
    request.session.set_expiry(timedelta(seconds=idle_seconds()))


def is_operator_session(request) -> bool:
    session = getattr(request, "session", None)
    return bool(session is not None and session.get(SESSION_MARKER))


def renew_if_due(request) -> bool:
    """Empurrar o prazo para ``IDLE`` à frente, se o último empurrão tem mais de um dia.

    Devolve ``True`` quando renovou. A sessão fica ``modified`` e o
    ``SessionMiddleware`` grava e reemite o cookie com o novo ``max-age`` — que o
    BFF repassa ao navegador com o nome do pote de operador.
    """
    if not is_operator_session(request):
        return False
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return False
    remaining = request.session.get_expiry_age()
    if remaining >= idle_seconds() - renew_interval_seconds():
        return False
    request.session.set_expiry(timedelta(seconds=idle_seconds()))
    return True
