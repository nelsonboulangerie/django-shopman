"""Quem pode o quê numa superfície de operador.

**Uma identidade, não duas.** A pessoa que se identificou por PIN ou crachá É a
sessão: ``request.user`` é o operador, e ``has_perm`` responde direto. Não há
"conta do dispositivo" com permissões próprias para conferir depois.

Foi assim que o buraco fechou. Até 21/08/2026 existiam duas identidades — a
sessão do dispositivo (no staging, o ``admin`` superusuário) e o operador ativo
guardado num dicionário de sessão — e a permissão era conferida ora contra uma,
ora contra a outra. Como ``is_superuser`` curto-circuita ``has_perm``, os caminhos
que ainda perguntavam ao dispositivo davam chave-mestra a quem chegasse no balcão; e
o cookie de ``.boulangerie.com.br`` levava essa mesma sessão para o Admin na aba
ao lado.

O dispositivo continua sendo reconhecido — mas por CONFIANÇA DE DISPOSITIVO
(``backstage.station_trust``), que diz de onde a requisição veio e não concede
nada. Uma chave que só abre a antessala: com ela, a tela de identificação
aparece; sem uma pessoa identificada, nenhuma leitura passa.

**Duas espécies de estação**, e a segunda não é exceção à regra acima:

* **atendida** — o balcão. Tem gente na frente, e não faz nada sem PIN.
* **autônoma** — o totem. Não há quem digite PIN, então ela age em NOME PRÓPRIO,
  com uma conta declarada no ``Terminal.metadata`` e cujas permissões são dados
  do deployment. Continua valendo que o dispositivo não concede nada: quem concede é
  a conta, e o gate a trata como trata qualquer operador.
"""

from __future__ import annotations

from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission

from shopman.backstage.station_trust import is_trusted_station, station_operator

#: Código estável da recusa por estação sem ninguém identificado. A superfície
#: REAGE a ele (sobe a tela de identificação) em vez de casar a mensagem em
#: português, que muda com a copy. Sem um código, a tela só sabia "403" —
#: indistinguível de falta de permissão — e seguia desenhando um PDV vazio
#: enquanto toda leitura era negada.
STATION_LOCKED_CODE = "station_locked"

_MSG_LOCKED = "Estação travada. Identifique-se com PIN ou crachá."
_MSG_FORBIDDEN = "Acesso restrito a operadores."


def _recusa_travada():
    """Levanta a recusa da estação travada — com código, e sem passar pelo DRF.

    Um gate que só devolve ``False`` deixa o DRF escolher a exceção, e ele
    escolhe pelo estado da AUTENTICAÇÃO: requisição sem ninguém logado vira
    ``NotAuthenticated``, com a mensagem genérica de credencial ausente. Só que
    a estação travada é EXATAMENTE isso — dispositivo reconhecido, ninguém logado —
    então o código que a tela usa para subir a identificação se perdia justo no
    caso para o qual ele existe. Levantar aqui preserva mensagem e código.
    """
    raise PermissionDenied(_MSG_LOCKED, code=STATION_LOCKED_CODE)


def _operador(request):
    """Quem está operando nesta requisição. Uma pergunta, um dono.

    Em geral é simplesmente quem está logado: a pessoa que provou PIN, crachá ou
    senha VIROU a sessão. Há um segundo caso, e ele é uma decisão de desenho, não
    uma exceção: a estação AUTÔNOMA (o totem) não tem ninguém na frente para
    digitar PIN, então ela age em nome próprio, com uma conta que é dela.

    A conta do totem entra em ``request.user`` — e não num segundo lugar ao lado
    dele — porque foi a existência de dois sujeitos que abriu o buraco de 20/08:
    sempre havia um caminho que perguntava para o errado. Aqui a atribuição
    (``_actor``, ``Entry.operator``) sai certa de graça, e o gate de permissão
    trata o totem como trata qualquer operador: pelo que a conta dele PODE.
    """
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and user.is_staff:
        return user

    totem = station_operator(request)
    if totem is not None:
        # `request.user` é o sujeito que o resto da requisição vai ler. O DRF
        # aceita a atribuição e propaga para o request do Django.
        request.user = totem
        return totem
    return None


class IsBackstageOperator(BasePermission):
    """Alguém identificado, e que é da casa.

    Recusa de dois jeitos, de propósito: LEVANTA ``station_locked`` quando a
    requisição vem de uma estação reconhecida e ninguém se identificou (o balcão
    de manhã), e devolve ``False`` quando nem isso. A tela precisa distinguir
    "peça o PIN" de "você não deveria estar aqui".
    """

    message = _MSG_FORBIDDEN

    def has_permission(self, request, view) -> bool:
        if _operador(request) is not None:
            return True
        if is_trusted_station(request):
            _recusa_travada()
        return False


class HasBackstagePermission(BasePermission):
    """Confere uma permissão declarada na view, contra QUEM ESTÁ OPERANDO.

    A view declara ``required_permission = "backstage.operate_kds"`` — ou uma
    tupla, e aí TODAS são exigidas (ex.: o painel de caixa do B.I.:
    ``("backstage.view_bi", "cashman.audit_shift")``, porque apuração de caixa é
    mais restrita que o resto do B.I.). Sem declaração, basta ser da casa.

    Não há mais o ramo da "Opção C" (resolver um operador ativo guardado na
    sessão e conferir contra ele): a sessão É do operador, então ``has_perm``
    pergunta para a pessoa certa por construção — e não existe caminho que
    esqueça de perguntar, que era como o buraco nascia.
    """

    message = _MSG_FORBIDDEN

    def has_permission(self, request, view) -> bool:
        self.message = _MSG_FORBIDDEN
        operador = _operador(request)
        if operador is None:
            if is_trusted_station(request):
                _recusa_travada()
            return False
        perms = _required_codes(getattr(view, "required_permission", None))
        if not all(operador.has_perm(code) for code in perms):
            self.message = "Operador sem permissão para esta ação."
            return False
        return True


class IsTrustedStation(BasePermission):
    """A requisição vem de um dispositivo que a loja reconhece — e só isso.

    É o gate da ANTESSALA: listar quem pode destravar, mostrar o estado da trava,
    receber o PIN. Nada além disso, e nada que mexa em dinheiro, estoque ou
    pedido.

    Precisa existir porque, com uma identidade só, o balcão travado não tem
    ninguém logado: exigir sessão aqui tornaria o destrave inalcançável e a loja
    não abriria de manhã. Quem já está identificado também passa — o operador
    troca de turno sem o dispositivo deixar de ser confiável.
    """

    message = "Este dispositivo não é uma estação da loja."

    def has_permission(self, request, view) -> bool:
        # `_operador` PRIMEIRO, e a ordem é o bug: com `is_trusted_station` na
        # frente, o `or` curto-circuita e a estação autônoma nunca resolve a
        # própria conta — a antessala responderia "travada" a um totem que não
        # tem quem digite PIN.
        return bool(_operador(request) is not None or is_trusted_station(request))


def _required_codes(perm) -> tuple[str, ...]:
    """``None`` → nada exigido; string → uma; tupla/lista → todas."""
    if perm is None:
        return ()
    if isinstance(perm, str):
        return (perm,)
    return tuple(perm)


class CanViewOperatorAlerts(BasePermission):
    """Qualquer persona de operador que possa ver alertas.

    Embrulha o predicado canônico ``can_view_operator_alerts`` (da casa + alguma
    capacidade de operador) para os endpoints de alerta compartilharem a mesma
    regra do badge da sidebar.
    """

    message = _MSG_FORBIDDEN

    def has_permission(self, request, view) -> bool:
        from shopman.backstage.permissions import can_view_operator_alerts

        operador = _operador(request)
        return bool(operador is not None and can_view_operator_alerts(operador))
