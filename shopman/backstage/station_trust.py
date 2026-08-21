"""De que balcão esta requisição veio — e por que isso não dá permissão nenhuma.

Duas identidades convivem numa superfície de operador, e confundi-las é o defeito
que a auditoria de 20/08 encontrou:

* a **ESTAÇÃO** é o aparelho: o balcão, o totem. Ela responde "de onde", nunca
  "quem pode". Uma estação confiável não abre caixa, não autoriza sangria e não
  vê apuração — ela só permite que a tela de identificação apareça.
* o **OPERADOR** é a pessoa, e é dele toda permissão.

Até 21/08/2026 a estação era uma sessão Django comum, e no staging essa sessão
era o ``admin`` — superusuário. Como ``is_superuser`` curto-circuita ``has_perm``,
qualquer pessoa em frente ao balcão tinha, na prática, chave-mestra; e como o
cookie vale em ``.boulangerie.com.br``, a mesma sessão abria o Admin na aba ao
lado. O buraco não era de permissão mal configurada: era de identidade trocada.

A confiança de dispositivo do ``doorman`` resolve isso porque separa as duas
coisas fisicamente. O aparelho carrega um cookie HttpOnly durável, revogável por
dispositivo no Admin, com ``label``/``ip_address``/``last_used_at`` para
auditoria. Ninguém digita senha de manhã, e não há credencial em URL nem em
histórico de navegador.

O provisionamento é o mesmo do quadro de menu (``shop/menuboard_access.py``), que
já roda em produção: alguém com permissão abre a tela UMA vez naquele aparelho, e
a resposta grava a confiança. Nada de token em URL, nada de re-digitar a cada
duas semanas.
"""

from __future__ import annotations

from shopman.doorman.models import SubjectType

#: Quem pode transformar um aparelho em estação confiável. É ato de gestão — quem
#: provisiona decide que aquele balcão passa a poder pedir identificação — e por
#: isso não é a permissão de operar, é a de gerir operadores.
PROVISION_PERM = "cashman.manage_operators"


def station_ref(request) -> str:
    """O ``Terminal.ref`` da estação confiável desta requisição, ou ``""``.

    Percorre os cookies de estação presentes no navegador e devolve o primeiro
    cuja confiança o ``doorman`` valida. São vários porque um mesmo computador
    pode ser provisionado como balcão E como totem — o nome do cookie carrega o
    ``ref``, exatamente como o do quadro.
    """
    from shopman.doorman.conf import doorman_settings
    from shopman.doorman.services.device_trust import DeviceTrustService

    base = doorman_settings.DEVICE_TRUST_STATION_COOKIE_NAME
    for nome in request.COOKIES:
        if not nome.startswith(f"{base}_"):
            continue
        ref = nome[len(base) + 1:]
        if DeviceTrustService.check(request, SubjectType.STATION, ref):
            return ref
    return ""


def is_trusted_station(request) -> bool:
    """Esta requisição vem de um aparelho que a loja reconhece?"""
    return bool(station_ref(request))


def provision(request, response, terminal_ref: str):
    """Torna ESTE aparelho uma estação confiável para ``terminal_ref``.

    Chamado a partir de uma tela que já exigiu ``PROVISION_PERM``: quem provisiona
    está logado e autorizado, e é esse ato — não o cookie — que carrega a decisão.
    Depois disso o aparelho não precisa mais de ninguém logado para exibir a tela
    de identificação.

    Idempotente: não grava uma segunda linha de ``TrustedDevice`` se a confiança
    daquele terminal já existe naquele navegador.
    """
    from shopman.doorman.services.device_trust import DeviceTrustService

    ref = str(terminal_ref or "").strip()
    if not ref:
        raise ValueError("estação precisa de um terminal")
    if DeviceTrustService.check(request, SubjectType.STATION, ref):
        return response
    DeviceTrustService.trust(
        response=response,
        subject_type=SubjectType.STATION,
        subject_id=ref,
        request=request,
    )
    return response


def revoke(request, response, terminal_ref: str):
    """Tira a confiança DESTE aparelho para aquele terminal.

    O aparelho perdido continua revogável pelo Admin (é lá que a lista de
    dispositivos vive); isto é o caminho local, para quem está com a máquina na
    mão — desativar um quiosque que vai sair da loja, por exemplo.
    """
    from shopman.doorman.conf import doorman_settings
    from shopman.doorman.models import TrustedDevice

    ref = str(terminal_ref or "").strip()
    nome = f"{doorman_settings.DEVICE_TRUST_STATION_COOKIE_NAME}_{ref}"
    token = request.COOKIES.get(nome)
    if token:
        dispositivo = TrustedDevice.verify_token(token)
        if dispositivo is not None:
            dispositivo.revoke()
    response.delete_cookie(nome)
    return response
