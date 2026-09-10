"""Trilha de acesso — um escritor, uma origem.

O ponto todo deste módulo é **não** existirem três caminhos paralelos para senha,
PIN e crachá. Existe um fato — "uma sessão de operador foi autenticada" — e ele
nasce de onde não dá para esquecer de emiti-lo:

* **Sucesso** vem do ``user_logged_in`` do próprio Django. Os quatro caminhos do
  escopo (senha do Admin, senha no app, PIN, crachá) terminam todos em
  ``django.contrib.auth.login()``, então um caminho de login que alguém escreva
  amanhã já nasce coberto. Nenhuma view precisa lembrar de gravar.
* **Recusa de PIN/crachá** não tem signal equivalente: ela não passa por
  ``authenticate()``, o serviço só devolve ``False``. Então a única view que a
  produz (``OperatorUnlockView``) chama ``record()`` — a MESMA função. É um
  escritor com duas origens, não dois caminhos.

O método não se descobre do backend de autenticação: senha do Admin e senha do
app são o mesmo backend e a mesma força, enquanto PIN e crachá são o mesmo
backend com forças opostas. Quem sabe por qual porta a pessoa entrou é quem abre
a porta, e por isso as views marcam ``request`` com ``mark_method()``.

**Só operador.** Cliente que entra por OTP/passkey/link não é o pedido, é volume
de outra ordem de grandeza, e seria uma segunda base de PII.

## A política de aviso (decidida pelo dono em 29/08/2026)

* **Todo** login vira aviso para o DONO DA CONTA. Nenhum é suprimido.
* O que a regra de destaque decide é quais chegam **realçados** — crachá,
  estação nunca usada por aquela conta, fora do horário, rajada, acerto logo
  depois de uma recusa. Destaque, nunca silêncio: errar o critério passa a
  custar "não destacou" em vez de "não avisou".
* **Cada um sobre a própria conta.** Ninguém é avisado do login alheio, e a
  lista é filtrada por ``request.user`` na API. Vazar "quem entrou quando" para
  o balcão inteiro seria criar um problema novo ao resolver o antigo.
* **Canal: in-app** (``UserNotification`` + push SSE em ``user-<id>``), que é o
  único que comprovadamente entrega hoje. Contador discreto e lista consultável
  — nada de modal, som ou o que roube foco de quem está atendendo.
  ⚠️ **E-mail está proibido aqui**: o ``EMAIL_BACKEND`` cai no console e o
  adapter devolve ``True`` sem enviar. Num aviso de segurança isso é o pior
  resultado possível — silencioso e reportado como entregue.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: Atributo que a view deixa no ``request`` para dizer por qual porta a pessoa
#: entrou. Lido pelo receiver do ``user_logged_in``.
REQUEST_METHOD_ATTR = "shopman_sign_in_method"

#: O que vai no lugar do nome quando a recusa não tem conta a nomear — um
#: crachá que não bate com ninguém, um PIN sem operador escolhido. Guardar a
#: linha mesmo assim é o ponto: "alguém passou um crachá que não existe" é
#: exatamente o fato que interessa numa trilha de segurança.
UNKNOWN_SUBJECT = "(desconhecido)"

#: Tamanho máximo do user agent guardado. O cabeçalho não tem teto e não vale
#: uma linha de banco de 2KB por acesso.
_USER_AGENT_MAX = 300


def mark_method(request, method: str) -> None:
    """Declarar por qual porta esta requisição está autenticando.

    Chamado logo antes do ``login()``. Sem marcador o receiver grava
    ``unknown`` — que é a resposta honesta, e não um palpite disfarçado de dado.
    """
    if request is not None:
        setattr(request, REQUEST_METHOD_ATTR, method)


def client_ip(request) -> str | None:
    """O IP de quem chamou, atrás do proxy do deployment.

    ``X-Forwarded-For`` é uma lista da borda até aqui; o cliente é o primeiro.
    """
    if request is None:
        return None
    encaminhado = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    return encaminhado or request.META.get("REMOTE_ADDR") or None


def _station_ref(request) -> str:
    """De que balcão veio a requisição, ou ``""`` quando de fora da loja."""
    if request is None:
        return ""
    try:
        from shopman.backstage.station_trust import station_ref

        return station_ref(request)
    except Exception:  # pragma: no cover - trilha nunca derruba um login
        logger.warning("sign_in_audit.station_lookup_failed", exc_info=True)
        return ""


def record(*, user=None, username: str = "", method: str = "", outcome: str = "",
           request=None, notify_owner: bool = True, **contexto):
    """Gravar uma linha na trilha. Devolve o ``SignInEvent``, ou ``None``.

    **Nunca levanta.** Uma trilha que derruba o login que ela observa transforma
    uma feature de segurança numa negação de serviço — o balcão não abriria de
    manhã por causa do log. Falha vai para o logger e a vida segue.

    Devolve ``None`` também quando o sujeito não é operador: cliente não entra
    nesta trilha.
    """
    from shopman.backstage.models import SignInEvent, SignInMethod, SignInOutcome

    try:
        if user is not None and not getattr(user, "is_staff", False):
            return None

        nome = (username or (user.get_username() if user is not None else "") or "").strip()[:150]
        if not nome:
            return None

        metodo = method if method in SignInMethod.values else SignInMethod.UNKNOWN
        resultado = outcome if outcome in SignInOutcome.values else SignInOutcome.SUCCESS

        dados = {k: v for k, v in contexto.items() if v not in (None, "")}
        if request is not None:
            agente = (request.META.get("HTTP_USER_AGENT") or "").strip()
            if agente:
                dados["user_agent"] = agente[:_USER_AGENT_MAX]
            caminho = getattr(request, "path", "") or ""
            if caminho:
                dados["path"] = caminho[:200]

        evento = SignInEvent.objects.create(
            user=user if (user is not None and getattr(user, "pk", None)) else None,
            username=nome,
            method=metodo,
            outcome=resultado,
            station_ref=_station_ref(request)[:80],
            ip_address=client_ip(request),
            data=dados,
        )
        # Gravar e avisar no mesmo lugar: o aviso é sobre TODO acesso, e deixá-lo
        # a cargo de quem chama seria a mesma armadilha que o log tinha antes —
        # um caminho novo nasceria sem ele e ninguém perceberia.
        if notify_owner:
            notify(evento)
        return evento
    except Exception:  # pragma: no cover - ver docstring
        logger.warning(
            "sign_in_audit.record_failed username=%s method=%s", username, method, exc_info=True
        )
        return None


# ── Receivers dos signals de auth do Django ──────────────────────────────────


def on_user_logged_in(sender, request=None, user=None, **kwargs):
    """A origem única do sucesso: tudo que abre sessão passa por aqui."""
    from shopman.backstage.models import SignInMethod, SignInOutcome

    if user is None or not getattr(user, "is_staff", False):
        return
    record(
        user=user,
        method=getattr(request, REQUEST_METHOD_ATTR, None) or SignInMethod.UNKNOWN,
        outcome=SignInOutcome.SUCCESS,
        request=request,
    )


def on_user_login_failed(sender, credentials=None, request=None, **kwargs):
    """Senha recusada.

    O Django já entrega ``credentials`` com a senha removida — só o usuário
    sobra, que é o que interessa. Só grava se o nome digitado for de uma conta de
    operador: nome que não existe, ou de cliente, é ruído de internet, e ruído
    numa trilha de segurança é o que faz ninguém ler a trilha.

    ⚠️ **Recusa de PIN e de crachá NÃO chega aqui** — não passa por
    ``authenticate()``. Quem as grava é a ``OperatorUnlockView``, chamando
    ``record()`` diretamente.
    """
    from django.contrib.auth import get_user_model

    from shopman.backstage.models import SignInMethod, SignInOutcome

    nome = str((credentials or {}).get("username") or "").strip()
    if not nome:
        return
    try:
        conta = get_user_model().objects.filter(username=nome, is_staff=True).first()
    except Exception:  # pragma: no cover
        logger.warning("sign_in_audit.failed_lookup_error", exc_info=True)
        return
    if conta is None:
        return
    # A conta VAI no evento (e não só o nome digitado): "alguém errou a sua
    # senha" é justamente o aviso que interessa ao dono, e sem o vínculo não
    # haveria a quem avisar.
    record(
        user=conta,
        username=nome,
        method=SignInMethod.PASSWORD,
        outcome=SignInOutcome.FAILED,
        request=request,
    )


# ── Destaque: o que o olho do gerente deve pegar ─────────────────────────────
#
# Nada aqui suprime aviso. A lista abaixo só decide quais chegam realçados.

#: Janela em que "recusa seguida de acerto" ainda conta como a mesma tentativa.
_AFTER_FAILURE_MINUTES = 15


def detect_anomalies(event) -> list[str]:
    """Os códigos de destaque deste acesso. Lista vazia = acesso de rotina.

    Nunca levanta: destaque é enfeite de leitura, e um erro aqui não pode
    impedir o aviso de existir — avisar sem realce é degradação aceitável,
    não avisar não é.
    """
    from shopman.backstage.models import SignInEvent, SignInMethod, SignInOutcome

    try:
        from shopman.shop.rules.security import params_or_defaults

        params = params_or_defaults()
        achados: list[str] = []

        if params.get("failure") and event.outcome == SignInOutcome.FAILED:
            achados.append("failure")

        if params.get("badge") and event.method == SignInMethod.BADGE:
            achados.append("badge")

        # Credencial certa, lugar errado. Só faz sentido perguntar quando existe
        # conta a comparar e a requisição veio de ALGUMA estação: sem estação, o
        # acesso é de fora da loja, que é outro fato (e não um lugar "novo").
        if params.get("unknown_station") and event.user_id and event.station_ref:
            ja_usou = (
                SignInEvent.objects.filter(
                    user_id=event.user_id,
                    station_ref=event.station_ref,
                    outcome=SignInOutcome.SUCCESS,
                )
                .exclude(pk=event.pk)
                .exists()
            )
            if not ja_usou:
                achados.append("unknown_station")

        if params.get("outside_hours") and _outside_business_hours(event):
            achados.append("outside_hours")

        limite = int(params.get("burst_count") or 0)
        janela = int(params.get("burst_minutes") or 0)
        if event.user_id and limite > 0 and janela > 0:
            from datetime import timedelta

            desde = event.created_at - timedelta(minutes=janela)
            recentes = (
                SignInEvent.objects.filter(user_id=event.user_id, created_at__gte=desde)
                .exclude(pk=event.pk)
                .count()
            )
            if recentes + 1 >= limite:
                achados.append("burst")

        if params.get("after_failure") and event.user_id and event.outcome == SignInOutcome.SUCCESS:
            from datetime import timedelta

            desde = event.created_at - timedelta(minutes=_AFTER_FAILURE_MINUTES)
            houve_recusa = (
                SignInEvent.objects.filter(
                    user_id=event.user_id,
                    outcome=SignInOutcome.FAILED,
                    created_at__gte=desde,
                )
                .exclude(pk=event.pk)
                .exists()
            )
            if houve_recusa:
                achados.append("after_failure")

        return achados
    except Exception:  # pragma: no cover - ver docstring
        logger.warning("sign_in_audit.anomaly_detection_failed event=%s", event.pk, exc_info=True)
        return []


def _outside_business_hours(event) -> bool:
    """O acesso caiu fora do expediente da loja?

    Quem responde é o ``business_calendar``, e não uma leitura própria de
    ``Shop.opening_hours``: ele já sabe de feriado e férias coletivas, e uma
    segunda implementação de "a loja estava aberta?" divergiria da primeira no
    primeiro feriado — marcando como anômalo o acesso de um dia em que a casa
    de fato abriu, ou deixando passar o de um dia em que não abriu.

    Sem grade configurada, ``is_open_on`` degrada para aberto e nada é "fora do
    horário" — inventar uma janela aqui marcaria a loja inteira como anômala no
    primeiro dia.
    """
    from django.utils import timezone

    from shopman.shop.services.business_calendar import is_open_on, selling_hours_for

    momento = timezone.localtime(event.created_at)
    dia = momento.date()

    if not is_open_on(dia):
        # Dia fechado (feriado, folga semanal): entrar nele é justamente o que
        # se quer ver destacado.
        return True

    janela = selling_hours_for(dia)
    if janela is None:
        return False
    abre, fecha = janela
    return not (abre <= momento.time() <= fecha)


# ── O aviso ──────────────────────────────────────────────────────────────────

#: O que cada código de destaque diz em português, para a linha do aviso.
ANOMALY_LABELS = {
    "failure": "tentativa recusada",
    "badge": "entrou com crachá",
    "unknown_station": "estação nunca usada por esta conta",
    "outside_hours": "fora do horário de funcionamento",
    "burst": "vários acessos em pouco tempo",
    "after_failure": "acertou logo depois de errar",
}

#: Onde a lista de acessos da própria pessoa vai morar nas superfícies de
#: operador. A notificação já aponta para cá para que "conferir sempre que
#: quiser" não dependa de o gerente lembrar de um caminho — e para que, no dia
#: em que a tela existir, os avisos antigos já levem a ela.
SIGN_IN_LOG_PATH = "/account/sign-ins"


def notify(event) -> None:
    """Avisar o dono da conta que ela foi usada. Todo acesso, sem exceção.

    Só não avisa quando não há a quem avisar — uma recusa de crachá que não bate
    com ninguém não tem dono. Essa linha existe no log e em nenhuma caixa.
    """
    from shopman.backstage.models import SignInEvent, SignInOutcome
    from shopman.shop.models import NotificationCategory, UserNotification
    from shopman.shop.services.campaign import push_user_notification

    if event is None or not event.user_id:
        return
    try:
        realces = detect_anomalies(event)
        if realces:
            event.data = {**(event.data or {}), "anomalies": realces}

        notificacao = UserNotification.objects.create(
            user_id=event.user_id,
            category=NotificationCategory.SIGN_IN,
            title=_notification_title(event),
            message=_notification_message(event, realces),
            action_url=SIGN_IN_LOG_PATH,
            action_data={
                "sign_in_event_id": event.pk,
                # O realce é DADO da notificação, e não uma segunda notificação:
                # o gerente varre uma lista só e o olho para no que é anômalo,
                # sem que nada tenha sido escondido dele num silo à parte.
                "anomalies": realces,
                "highlight": bool(realces),
            },
            # "Não fui eu" é ação, e só faz sentido sobre um acesso que
            # aconteceu: numa recusa não há sessão para derrubar.
            is_actionable=event.outcome == SignInOutcome.SUCCESS,
        )
        push_user_notification(notificacao)
        # Um UPDATE só: o realce e o "já avisei" são o mesmo fato — a linha foi
        # avaliada e entregue. Dois updates deixariam uma janela em que o evento
        # está destacado mas ainda não avisado, sem que isso queira dizer nada.
        SignInEvent.objects.filter(pk=event.pk).update(notified=True, data=event.data or {})
    except Exception:  # pragma: no cover - o aviso nunca derruba o login
        logger.warning("sign_in_audit.notify_failed event=%s", event.pk, exc_info=True)


def _notification_title(event) -> str:
    from shopman.backstage.models import SignInOutcome

    metodo = event.get_method_display()
    if event.outcome == SignInOutcome.FAILED:
        return f"Tentativa recusada na sua conta ({metodo})"
    if event.outcome == SignInOutcome.REVOKED:
        return "Acessos da sua conta foram revogados"
    return f"Sua conta foi usada ({metodo})"


def _notification_message(event, realces: list[str]) -> str:
    from django.utils import timezone

    quando = timezone.localtime(event.created_at).strftime("%d/%m às %H:%M")
    onde = event.station_ref or "fora da loja"
    linhas = [f"{quando} · {onde}"]
    if event.ip_address:
        linhas.append(f"IP {event.ip_address}")
    if realces:
        linhas.append("Atenção: " + "; ".join(ANOMALY_LABELS.get(c, c) for c in realces) + ".")
    return "\n".join(linhas)


# ── "Não fui eu" ─────────────────────────────────────────────────────────────


class RevokeError(ValueError):
    """A revogação não pôde acontecer, com um ``code`` estável para a UI."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


#: Por que o acesso foi revogado.
REASON_NOT_ME = "not_me"
REASON_LOST = "lost"

_REASON_LABELS = {
    REASON_NOT_ME: "não reconheceu um acesso",
    REASON_LOST: "perdeu o crachá",
}


def revoke_access(*, user, requested_by, reason=REASON_NOT_ME, event=None, request=None) -> dict:
    """Derrubar as sessões da conta E invalidar o crachá.

    Dois gatilhos, um caminho: ``not_me`` (o dono não reconhece um acesso) e
    ``lost`` (o dono perdeu o crachá e não espera o ladrão usar). O efeito é o
    mesmo, então o código é o mesmo.

    **O PIN fica de pé.** PIN é conhecimento, não se acha no chão. Quem perdeu o
    crachá continua operando no mesmo turno — ninguém para de trabalhar.

    ⚠️ **Isto NUNCA pode virar um link.** Roda dentro da superfície autenticada,
    onde ``request.user`` está provado. Um aviso que saia por WhatsApp no futuro
    só pode dizer "abra o app": um botão "clique aqui para bloquear" numa
    mensagem é phishing pronto, escrito pela própria casa.

    A sessão de QUEM PEDIU sobrevive: quem aperta o botão acabou de se
    autenticar, e derrubá-la seria um logout confuso no meio do expediente.
    """
    from django.contrib.sessions.models import Session
    from django.utils import timezone

    from shopman.backstage.models import SignInEvent, SignInMethod, SignInOutcome

    if user is None or not getattr(user, "pk", None):
        raise RevokeError("no_user", "Nenhuma conta para revogar.")
    if getattr(requested_by, "pk", None) != user.pk:
        # Só sobre a PRÓPRIA conta: um botão de derrubar o colega não existe.
        raise RevokeError("not_owner", "Só o dono da conta pode revogar os acessos dela.")

    # Varredura, e não índice: o Django não guarda sessão por usuário, e a
    # tabela inclui as dos clientes do storefront. Aceitável porque isto roda só
    # a pedido; se um dia doer, a saída é guardar a chave no login.
    atual = getattr(getattr(request, "session", None), "session_key", None)
    derrubadas = 0
    for sessao in Session.objects.filter(expire_date__gte=timezone.now()).iterator():
        try:
            dados = sessao.get_decoded()
        except Exception:  # pragma: no cover - sessão corrompida não trava a ação
            # Pular calado seria dizer "revoguei tudo" sem saber: a sessão
            # ilegível pode ser a do intruso.
            logger.warning("sign_in_audit.session_undecodable key=%s", sessao.session_key)
            continue
        if str(dados.get("_auth_user_id") or "") != str(user.pk):
            continue
        if sessao.session_key == atual:
            continue
        sessao.delete()
        derrubadas += 1

    cracha_morreu = _clear_badge(user)

    record(
        user=user,
        method=(event.method if event is not None else SignInMethod.BADGE),
        outcome=SignInOutcome.REVOKED,
        request=request,
        reason=reason,
        revoked_sign_in_event_id=(event.pk if event is not None else None),
        sessions_revoked=derrubadas,
        badge_revoked=cracha_morreu,
        requested_by=requested_by.get_username(),
    )
    if event is not None:
        SignInEvent.objects.filter(pk=event.pk).update(
            data={**(event.data or {}), "revoked_at": timezone.now().isoformat()}
        )
    if cracha_morreu:
        _notify_badge_reissue(user, reason)

    return {
        "sessions_revoked": derrubadas,
        "badge_revoked": cracha_morreu,
        # PIN continua valendo, e a tela precisa dizer isso: senão a pessoa
        # acha que ficou sem entrar e para de trabalhar por engano.
        "pin_still_valid": True,
    }


def _clear_badge(user) -> bool:
    """Matar o crachá. True se havia um."""
    from shopman.doorman.models import PinCredential

    try:
        cred = user.pin_credential
    except (PinCredential.DoesNotExist, AttributeError):
        return False
    if not cred.badge_hash:
        return False
    cred.clear_badge()
    return True


def _notify_badge_reissue(user, reason: str) -> None:
    """Avisar quem reemite. Crachá que morre calado vira fila às 6h.

    Isto NÃO é o log de acessos alheios (que ninguém lê fora da própria conta):
    é um pedido operacional — "o fulano precisa de crachá novo" — para quem já
    administra credencial no Admin.
    """
    from shopman.shop.models import NotificationCategory, UserNotification
    from shopman.shop.services.campaign import push_user_notification

    nome = user.get_full_name().strip() or user.get_username()
    motivo = _REASON_LABELS.get(reason, reason)
    for gerente in _badge_managers(exclude=user):
        notificacao = UserNotification.objects.create(
            user=gerente,
            category=NotificationCategory.SIGN_IN,
            title=f"Crachá de {nome} foi invalidado",
            message=f"Motivo: {motivo}. O PIN segue valendo. Reemita em Operadores, no Admin.",
        )
        push_user_notification(notificacao)


def _badge_managers(*, exclude=None):
    """Quem pode reemitir crachá (``cashman.manage_operators``)."""
    from django.contrib.auth import get_user_model

    qs = get_user_model().objects.with_perm(
        "cashman.manage_operators",
        is_active=True,
        backend="django.contrib.auth.backends.ModelBackend",
    )
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return qs


# ── Retenção ─────────────────────────────────────────────────────────────────


def purge(*, days: int | None = None) -> int:
    """Apagar a trilha mais velha que a retenção. Devolve quantas linhas saíram.

    180 dias por padrão: longo o bastante para uma investigação de "mês passado",
    curto o bastante para a tabela nunca virar problema (a ordem de grandeza é
    dezenas de linhas por dia).
    """
    from datetime import timedelta

    from django.conf import settings
    from django.utils import timezone

    from shopman.backstage.models import SignInEvent

    prazo = days if days is not None else getattr(settings, "SHOPMAN_SIGN_IN_AUDIT_RETENTION_DAYS", 180)
    corte = timezone.now() - timedelta(days=int(prazo))
    removidas, _ = SignInEvent.objects.filter(created_at__lt=corte).delete()
    return removidas
