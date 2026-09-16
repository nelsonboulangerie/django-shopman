"""De que balcão esta requisição veio — e por que isso não dá permissão nenhuma.

Duas identidades convivem numa superfície de operador, e confundi-las é o defeito
que a auditoria de 20/08 encontrou:

* a **ESTAÇÃO** é o dispositivo: o balcão, o totem. Ela responde "de onde", nunca
  "quem pode". Uma estação confiável não abre caixa, não autoriza sangria e não
  vê apuração — ela só permite que a tela de identificação apareça.
* o **OPERADOR** é a pessoa, e é dele toda permissão.

Até 21/08/2026 a estação era uma sessão Django comum, e no staging essa sessão
era o ``admin`` — superusuário. Como ``is_superuser`` curto-circuita ``has_perm``,
qualquer pessoa em frente ao balcão tinha, na prática, chave-mestra; e como o
cookie vale em ``.boulangerie.com.br``, a mesma sessão abria o Admin na aba ao
lado. O buraco não era de permissão mal configurada: era de identidade trocada.

A confiança de dispositivo do ``doorman`` resolve isso porque separa as duas
coisas fisicamente. O dispositivo carrega um cookie HttpOnly durável, revogável por
dispositivo no Admin, com ``label``/``ip_address``/``last_used_at`` para
auditoria. Ninguém digita senha de manhã, e não há credencial em URL nem em
histórico de navegador.

O provisionamento é o mesmo do quadro de menu (``shop/menuboard_access.py``), que
já roda em produção: alguém com permissão abre a tela UMA vez naquele dispositivo, e
a resposta grava a confiança. Nada de token em URL, nada de re-digitar a cada
duas semanas.
"""

from __future__ import annotations

import logging

from django.db import transaction
from shopman.doorman.models import SubjectType

logger = logging.getLogger("shopman.backstage.station_trust")

#: Quem pode transformar um dispositivo em estação confiável. É ato de gestão — quem
#: provisiona decide que aquele balcão passa a poder pedir identificação — e por
#: isso não é a permissão de operar, é a de gerir operadores.
PROVISION_PERM = "cashman.manage_operators"

#: Estação ATENDIDA: tem gente na frente, e não faz nada sem PIN ou crachá. É o
#: balcão, e é o default de qualquer terminal que não diga o contrário.
ATTENDED = "attended"

#: Estação AUTÔNOMA: o totem. Não há ninguém para digitar PIN, então ela age em
#: NOME PRÓPRIO — com uma conta de operador que é dela, e cujas permissões são
#: dados do deployment, não código.
#:
#: A diferença com o desenho que a D1-B derrubou é o que a conta pode: aquela era
#: o ``admin`` superusuário e dava chave-mestra a quem chegasse; esta tem o que a
#: loja lhe conceder, e recusar superusuário aqui é regra, não recomendação.
AUTONOMOUS = "autonomous"


def station_cookie_name(terminal_ref: str) -> str:
    """O nome do cookie de estação daquele terminal — uma pergunta, um dono.

    O ``doorman`` sanitiza o ``ref`` dentro do nome. Montá-lo à mão aqui
    (``f"{base}_{ref}"``) funcionava por acaso enquanto todo terminal se chamou
    ``pdv-main``, e erraria no primeiro ref com espaço ou acento — a revogação
    apagaria um cookie que não existe e o dispositivo seguiria confiável.
    """
    from shopman.doorman.services.device_trust import DeviceTrustService

    return DeviceTrustService.cookie_name_for(SubjectType.STATION, terminal_ref)


def station_ref(request) -> str:
    """O ``Terminal.ref`` da estação confiável desta requisição, ou ``""``.

    Só devolve uma identidade inequívoca. Dois vínculos válidos exigem reparar
    o provisionamento; a ordem dos cookies nunca escolhe a gaveta.
    """
    refs = {
        device.subject_id
        for nome, device in _present_station_bindings(request)
        if nome == station_cookie_name(device.subject_id)
    }
    return next(iter(refs)) if len(refs) == 1 else ""


def _station_cookie_names(request) -> list[str]:
    """Cookies que se apresentam como estação, válidos ou não.

    A resposta de reparo precisa apagar também lixo expirado/corrompido. O nome
    sozinho nunca autentica nada; ele serve apenas para limitar a limpeza ao
    namespace de estação, sem tocar em cliente ou quadro.
    """
    from shopman.doorman.conf import doorman_settings

    base = doorman_settings.DEVICE_TRUST_STATION_COOKIE_NAME
    return sorted(nome for nome in request.COOKIES if nome.startswith(f"{base}_"))


def _present_station_bindings(request):
    """Vínculos válidos cujos tokens ESTE navegador apresentou.

    O ``subject_id`` vem da linha autenticada no banco, nunca do sufixo do cookie.
    Isso evita escolher terminal por ordem de cookies e também lida corretamente
    com refs sanitizados no nome (espaço/acento). Tokens de outros tipos são
    ignorados: um cookie renomeado não transforma cliente ou quadro em estação.
    """
    from shopman.doorman.conf import doorman_settings
    from shopman.doorman.models import TrustedDevice

    if not doorman_settings.DEVICE_TRUST_ENABLED:
        return []

    verified = {}
    bindings = []
    for nome in _station_cookie_names(request):
        token = request.COOKIES.get(nome)
        if not token:
            continue
        if token not in verified:
            verified[token] = TrustedDevice.verify_token(token)
        device = verified[token]
        if device is not None and device.subject_type == SubjectType.STATION:
            bindings.append((nome, device))
    return bindings


def is_trusted_station(request) -> bool:
    """Esta requisição vem de um dispositivo que a loja reconhece?"""
    return bool(station_ref(request))


def _station_config(terminal_ref: str) -> dict:
    """O bloco ``station`` do ``Terminal.metadata`` daquele ref, ou ``{}``."""
    from shopman.cashman.models import Terminal

    terminal = Terminal.objects.filter(ref=terminal_ref, is_active=True).first()
    if terminal is None:
        return {}
    bloco = (terminal.metadata or {}).get("station")
    return bloco if isinstance(bloco, dict) else {}


def station_mode(request) -> str:
    """``ATTENDED`` ou ``AUTONOMOUS`` para a estação desta requisição.

    Sem estação, ou com um valor que não reconhecemos, a resposta é ``ATTENDED``.
    O default fecha a porta: um modo escrito errado no Admin não pode transformar
    um balcão em dispositivo que age sozinho.
    """
    ref = station_ref(request)
    if not ref:
        return ATTENDED
    modo = str(_station_config(ref).get("mode") or "").strip().lower()
    return AUTONOMOUS if modo == AUTONOMOUS else ATTENDED


def station_operator(request):
    """A conta em cujo nome uma estação AUTÔNOMA age, ou ``None``.

    Tudo aqui falha fechado, e cada recusa tem uma razão vivida:

    * estação atendida, ou sem conta declarada → ``None``. O balcão continua
      pedindo PIN; nenhum dispositivo ganha identidade por omissão.
    * conta inexistente, inativa ou fora da casa → ``None``. Desativar a conta do
      totem no Admin é como se desliga um totem, e tem de bastar.
    * conta SUPERUSUÁRIA → ``None``, e um aviso no log. Era exatamente esse o
      buraco de 20/08: um dispositivo logado como ``admin``, ``is_superuser``
      curto-circuitando ``has_perm``, e o cookie levando a sessão para o Admin na
      aba ao lado. Um totem com chave-mestra é o mesmo defeito com outro nome.

    O que a conta PODE fazer não se decide aqui: são as permissões que a loja lhe
    conceder. Enquanto a superfície do totem não existir, ela não precisa de
    nenhuma — e o gate já a trata como qualquer operador sem permissão.
    """
    ref = station_ref(request)
    if not ref or station_mode(request) != AUTONOMOUS:
        return None
    username = str(_station_config(ref).get("operator") or "").strip()
    if not username:
        return None

    from django.contrib.auth import get_user_model

    conta = get_user_model().objects.filter(
        username=username, is_active=True, is_staff=True
    ).first()
    if conta is None:
        return None
    if conta.is_superuser:
        logger.error(
            "Estação autônoma aponta para conta SUPERUSUÁRIA — recusada.",
            extra={"station": ref, "account": username},
        )
        return None
    return conta


@transaction.atomic
def provision(request, response, terminal_ref: str):
    """Torna ESTE dispositivo uma estação confiável para ``terminal_ref``.

    Chamado a partir de uma tela que já exigiu ``PROVISION_PERM``: quem provisiona
    está logado e autorizado, e é esse ato — não o cookie — que carrega a decisão.
    Depois disso o dispositivo não precisa mais de ninguém logado para exibir a tela
    de identificação.

    Idempotente: não grava uma segunda linha de ``TrustedDevice`` se a confiança
    daquele terminal já existe naquele navegador.

    Também é a reparação explícita do caso legado em que o navegador acumulou
    dois vínculos. Só os tokens apresentados por ESTE request são revogados; os
    demais dispositivos do mesmo terminal continuam ativos. A escolha vem do
    ``terminal_ref`` validado pela view autorizada — nunca da ordem dos cookies.
    """
    from shopman.doorman.conf import doorman_settings
    from shopman.doorman.models import TrustedDevice
    from shopman.doorman.services.device_trust import DeviceTrustService

    ref = str(terminal_ref or "").strip()
    if not ref:
        raise ValueError("estação precisa de um terminal")

    if not doorman_settings.DEVICE_TRUST_ENABLED:
        return response

    canonical_name = station_cookie_name(ref)
    bindings = _present_station_bindings(request)
    kept = next(
        (
            device
            for nome, device in bindings
            if nome == canonical_name and device.subject_id == ref
        ),
        None,
    )

    presented_ids = {device.pk for _nome, device in bindings}
    if presented_ids:
        # O lock faz revogação + criação/retensão uma única troca observável no
        # banco. O filtro pelos PKs apresentados é o limite de escopo do aparelho.
        locked = {
            device.pk: device
            for device in TrustedDevice.objects.select_for_update().filter(
                pk__in=presented_ids
            )
        }
        if kept is not None:
            kept = locked.get(kept.pk)
            if kept is not None and not kept.is_valid:
                kept = None
        revoke_ids = presented_ids - ({kept.pk} if kept is not None else set())
        TrustedDevice.objects.filter(pk__in=revoke_ids, is_active=True).update(
            is_active=False,
        )

    for nome in _station_cookie_names(request):
        if kept is None or nome != canonical_name:
            response.delete_cookie(nome)

    if kept is not None:
        return response

    DeviceTrustService.trust(
        response=response,
        subject_type=SubjectType.STATION,
        subject_id=ref,
        request=request,
    )
    return response


@transaction.atomic
def revoke(request, response, terminal_ref: str):
    """Tira a confiança DESTE dispositivo para aquele terminal.

    O dispositivo perdido continua revogável pelo Admin (é lá que a lista de
    dispositivos vive); isto é o caminho local, para quem está com a máquina na
    mão — desativar um quiosque que vai sair da loja, por exemplo.
    """
    from shopman.doorman.models import TrustedDevice

    ref = str(terminal_ref or "").strip()
    nome = station_cookie_name(ref)
    token = request.COOKIES.get(nome)
    if token:
        dispositivo = TrustedDevice.verify_token(token)
        if (
            dispositivo is not None
            and dispositivo.subject_type == SubjectType.STATION
            and dispositivo.subject_id == ref
        ):
            dispositivo.revoke()
    response.delete_cookie(nome)
    return response
