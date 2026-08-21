"""Confiança de ESTAÇÃO: diz de onde veio a requisição, e não dá permissão nenhuma.

A distinção é o assunto inteiro. Até 21/08/2026 a estação era uma sessão Django
comum — no staging, o `admin` superusuário — e quem estivesse em frente ao balcão
tinha chave-mestra, com o cookie alcançando o Admin na aba ao lado.

A estação confiável é o oposto disso: uma chave que só abre a antessala.
"""

from __future__ import annotations

import pytest
from django.test import Client
from shopman.doorman.models.device_trust import SubjectType, TrustedDevice

from shopman.backstage import station_trust

pytestmark = pytest.mark.django_db


class _Resposta:
    """Resposta mínima: só o que ``set_cookie``/``delete_cookie`` precisam."""

    def __init__(self):
        self.cookies = {}

    def set_cookie(self, nome, valor, **kw):
        self.cookies[nome] = valor

    def delete_cookie(self, nome, **kw):
        self.cookies.pop(nome, None)


def _provisiona(cliente: Client, ref: str) -> str:
    """Provisiona e devolve o token, como o navegador o guardaria."""
    requisicao = type("R", (), {"COOKIES": dict(cliente.cookies), "META": {}})()
    resposta = _Resposta()
    station_trust.provision(requisicao, resposta, ref)
    nome, token = next(iter(resposta.cookies.items()))
    cliente.cookies[nome] = token
    return nome


def test_aparelho_novo_nao_e_estacao(client):
    assert station_trust.station_ref(_req(client)) == ""
    assert station_trust.is_trusted_station(_req(client)) is False


def test_provisionado_uma_vez_o_aparelho_se_identifica_sozinho(client):
    _provisiona(client, "balcao")

    assert station_trust.station_ref(_req(client)) == "balcao"
    assert station_trust.is_trusted_station(_req(client)) is True


def test_um_computador_pode_ser_DUAS_estacoes(client):
    """Balcão e totem no mesmo aparelho: o nome do cookie carrega o ref.

    Com um nome só, provisionar o segundo sobrescreveria o token do primeiro e os
    dois se derrubariam em revezamento — foi o defeito que o quadro de menu já
    teve, e a razão de o nome levar o ``subject_id``.
    """
    _provisiona(client, "balcao")
    _provisiona(client, "totem")

    assert station_trust.station_ref(_req(client)) in {"balcao", "totem"}
    from shopman.doorman.services.device_trust import DeviceTrustService

    assert DeviceTrustService.check(_req(client), SubjectType.STATION, "balcao")
    assert DeviceTrustService.check(_req(client), SubjectType.STATION, "totem")


def test_a_confianca_de_uma_estacao_nao_serve_para_outra(client):
    _provisiona(client, "balcao")
    from shopman.doorman.services.device_trust import DeviceTrustService

    assert not DeviceTrustService.check(_req(client), SubjectType.STATION, "totem")


def test_confianca_de_QUADRO_nao_vira_estacao(client):
    """Sujeitos não se emprestam: uma TV autorizada não é um balcão."""
    from shopman.doorman.services.device_trust import DeviceTrustService

    resposta = _Resposta()
    DeviceTrustService.trust(
        response=resposta, subject_type=SubjectType.DISPLAY,
        subject_id="menuboard", request=_req(client),
    )
    for nome, valor in resposta.cookies.items():
        client.cookies[nome] = valor

    assert station_trust.station_ref(_req(client)) == ""


def test_revogar_apaga_a_confianca_de_verdade(client):
    """Não basta tirar o cookie: o dispositivo tem de morrer no banco.

    Senão um token copiado antes da revogação continuaria valendo.
    """
    nome = _provisiona(client, "balcao")
    assert TrustedDevice.objects.filter(subject_type=SubjectType.STATION, is_active=True).count() == 1

    resposta = _Resposta()
    station_trust.revoke(_req(client), resposta, "balcao")

    assert not TrustedDevice.objects.filter(
        subject_type=SubjectType.STATION, is_active=True
    ).exists()
    assert nome  # o cookie existia antes


def test_provisionar_duas_vezes_nao_cria_duas_linhas(client):
    """Idempotente: abrir a tela de novo no mesmo aparelho não polui a auditoria."""
    _provisiona(client, "balcao")
    requisicao = _req(client)
    station_trust.provision(requisicao, _Resposta(), "balcao")

    assert TrustedDevice.objects.filter(subject_type=SubjectType.STATION).count() == 1


def test_estacao_sem_terminal_e_recusada():
    with pytest.raises(ValueError):
        station_trust.provision(None, _Resposta(), "")


def _req(cliente: Client):
    return type("R", (), {"COOKIES": {k: v.value for k, v in cliente.cookies.items()}, "META": {}})()
