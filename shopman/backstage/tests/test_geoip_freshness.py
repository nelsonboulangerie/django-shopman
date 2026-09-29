"""A base de cidade velha GRITA — e grita uma vez por faixa, não toda passada.

O buraco que esta frente fecha: a base entra na imagem no build, só troca por bump
manual, e velha ela não falha — **responde errado em silêncio**, com raio de precisão bom
e a confiança de sempre. Não havia job, nem Dependabot, nem alerta. O guia dizia que a
atualização não era automática, e documentação não é mecanismo.

⚠️ O teste do tipo em ``TYPE_CHOICES`` não é zelo: nesta casa `choices` não é constraint,
então um tipo não registrado GRAVA e some da coluna do Admin — 25 tipos de alerta já
apareceram sem tipo nenhum na tela por isso (PR #565). O alerta que ninguém vê é o mesmo
que não existir, que é justamente o defeito que este comando veio corrigir.
"""

from __future__ import annotations

import datetime
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from shopman.backstage.management.commands.check_geoip_freshness import (
    ALERT_TYPE,
    grade,
    message,
)
from shopman.backstage.models import OperatorAlert
from shopman.shop.services import ip_location
from shopman.shop.services.ip_location import DatabaseFreshness

pytestmark = pytest.mark.django_db


def _frescor(*, idade: int | None, mostra: bool = True, presente: bool = True) -> DatabaseFreshness:
    construida = None
    if idade is not None:
        construida = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=idade)
    return DatabaseFreshness(
        present=presente,
        built_at=construida,
        age_days=idade,
        stale=presente and (idade is None or idade >= 21),
        too_old_to_show=presente and not mostra,
    )


def _rodar(monkeypatch, frescor, **opcoes) -> str:
    monkeypatch.setattr(ip_location, "database_freshness", lambda: frescor)
    saida = StringIO()
    call_command("check_geoip_freshness", stdout=saida, **opcoes)
    return saida.getvalue()


# ── O tipo precisa existir no catálogo, senão o alerta nasce invisível ───────


def test_o_tipo_esta_registrado_em_type_choices():
    """Sem isto o alerta grava e a coluna do Admin aparece VAZIA. Armadilha da casa."""
    registrados = {chave for chave, _ in OperatorAlert.TYPE_CHOICES}

    assert ALERT_TYPE in registrados


def test_o_alerta_grava_com_rotulo_legivel(monkeypatch):
    """O crachá do Admin mostra a frase em português, e não o slug cru."""
    _rodar(monkeypatch, _frescor(idade=40))

    alerta = OperatorAlert.objects.get(type=ALERT_TYPE)
    assert alerta.get_type_display() == "Base de cidade dos dispositivos desatualizada"


# ── As duas faixas ───────────────────────────────────────────────────────────


def test_base_nova_nao_alerta(monkeypatch):
    """O caso de controle. Sem ele, "alertou" não distingue de "alerta sempre"."""
    _rodar(monkeypatch, _frescor(idade=5))

    assert not OperatorAlert.objects.filter(type=ALERT_TYPE).exists()


def test_base_envelhecendo_avisa_e_a_tela_segue_mostrando(monkeypatch):
    _rodar(monkeypatch, _frescor(idade=30))

    alerta = OperatorAlert.objects.get(type=ALERT_TYPE)
    assert alerta.severity == "warning"
    assert "30 dias" in alerta.message
    # O gesto tem de estar escrito: quem lê a tela de alertas é o gestor, que não sabe de
    # cor o nome de um ARG de Dockerfile.
    assert "GEOLITE2_SNAPSHOT" in alerta.message
    assert "docs/guides/geolite2-city.md" in alerta.message


def test_base_velha_demais_sobe_a_severidade_e_diz_que_a_cidade_sumiu(monkeypatch):
    """Passado o limiar largo a tela perdeu a linha — isso é regressão visível."""
    _rodar(monkeypatch, _frescor(idade=120, mostra=False))

    alerta = OperatorAlert.objects.get(type=ALERT_TYPE)
    assert alerta.severity == "error"
    assert "DEIXOU DE APARECER" in alerta.message


def test_data_ilegivel_diz_a_verdade_em_vez_de_inventar_numero(monkeypatch):
    """Idade desconhecida não vira "0 dias" nem um palpite: vira a frase que admite isso."""
    _rodar(monkeypatch, _frescor(idade=None, mostra=False))

    alerta = OperatorAlert.objects.get(type=ALERT_TYPE)
    assert "não informa a data" in alerta.message
    assert "dias" not in alerta.message.split("Para atualizar")[0].replace("provavelmente", "")


# ── A base ausente é silêncio deliberado ─────────────────────────────────────


def test_base_ausente_nao_vira_alerta(monkeypatch):
    """Ausência não é atraso: não há idade e não há o que bumpar.

    Este é o teste que impede o alerta de virar ruído diário no alpha, onde a
    ``MAXMIND_LICENSE_KEY`` ainda não existe e a imagem sobe SEM base de propósito. Um
    aviso que aparece todo dia sobre um estado previsto ensina a ignorar o tipo inteiro —
    e aí o aviso que importa chega num canal já surdo.
    """
    saida = _rodar(monkeypatch, _frescor(idade=None, presente=False))

    assert not OperatorAlert.objects.filter(type=ALERT_TYPE).exists()
    assert "sem base" in saida


# ── O dedupe: um lembrete por faixa, e o bump recomeça a história ────────────


def test_a_mesma_base_na_mesma_janela_nao_alerta_duas_vezes(monkeypatch):
    frescor = _frescor(idade=30)
    _rodar(monkeypatch, frescor)
    _rodar(monkeypatch, frescor)

    assert OperatorAlert.objects.filter(type=ALERT_TYPE).count() == 1


def test_alerta_ja_reconhecido_ainda_segura_a_janela(monkeypatch):
    """Reconhecer é dar ciência, não é bumpar a base — o dedupe olha resolvido, não visto."""
    frescor = _frescor(idade=30)
    _rodar(monkeypatch, frescor)
    OperatorAlert.objects.filter(type=ALERT_TYPE).update(
        acknowledged=True, acknowledged_at=timezone.now()
    )

    _rodar(monkeypatch, frescor)

    assert OperatorAlert.objects.filter(type=ALERT_TYPE).count() == 1


def test_trocar_de_faixa_e_fato_novo_e_sai_na_hora(monkeypatch):
    """21 → 90 não espera a janela da faixa antiga vencer: a tela mudou de comportamento."""
    _rodar(monkeypatch, _frescor(idade=30))
    _rodar(monkeypatch, _frescor(idade=95, mostra=False))

    alertas = OperatorAlert.objects.filter(type=ALERT_TYPE).order_by("created_at")
    assert [a.severity for a in alertas] == ["warning", "error"]


def test_bumpar_a_base_recomeca_a_historia(monkeypatch):
    """Base nova é data nova, logo chave de dedupe nova.

    Importa porque o oposto seria pior do que parece: se a chave ignorasse a data, uma
    base bumpada e velha DE NOVO três meses depois ficaria silenciada pelo alerta antigo.
    """
    _rodar(monkeypatch, _frescor(idade=30))
    OperatorAlert.objects.filter(type=ALERT_TYPE).update(resolved_at=timezone.now())

    # Mesma idade relativa, base construída em outro dia: é outra base.
    _rodar(monkeypatch, _frescor(idade=25))

    assert OperatorAlert.objects.filter(type=ALERT_TYPE).count() == 2


# ── O ensaio não escreve ─────────────────────────────────────────────────────


def test_dry_run_reporta_e_nao_alerta(monkeypatch):
    saida = _rodar(monkeypatch, _frescor(idade=200, mostra=False), dry_run=True)

    assert not OperatorAlert.objects.filter(type=ALERT_TYPE).exists()
    assert "idade=200" in saida


# ── As funções puras, sem banco ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "mostra, severidade, faixa",
    [(True, "warning", "envelhecendo"), (False, "error", "sem-cidade")],
)
def test_a_regua_de_severidade(mostra, severidade, faixa):
    assert grade(_frescor(idade=40, mostra=mostra))[0] == severidade
    assert grade(_frescor(idade=40, mostra=mostra))[2] == faixa


def test_a_mensagem_sempre_termina_no_gesto():
    """Toda variação da mensagem fecha com o que fazer. Aviso sem gesto é só má notícia."""
    for frescor in (_frescor(idade=30), _frescor(idade=200, mostra=False), _frescor(idade=None)):
        assert "Para atualizar" in message(frescor)


# ── A cadeia inteira, sem mock nenhum ────────────────────────────────────────


def test_do_arquivo_velho_no_disco_ate_o_alerta(settings, tmp_path):
    """Um `.mmdb` de verdade, velho de verdade, vira alerta — sem trocar nada por falso.

    ⚠️ Os testes acima trocam `database_freshness` por uma resposta pronta, o que é certo
    para a régua e errado para esta pergunta: as pontas se encontram? O caminho tem quatro
    elos (arquivo no disco → `maxminddb` lê o `build_epoch` → `database_freshness` calcula
    a idade → o comando grava o alerta), e uma frente que prova cada elo separadamente
    pode ter todos verdes com a corrente arrebentada no meio. Foi assim que um resolver
    fiscal desta casa subiu inerte para o ar.
    """
    from shopman.shop.tests.mmdb_fixtures import mmdb_minimo

    construida = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=200)
    arquivo = tmp_path / "GeoLite2-City.mmdb"
    arquivo.write_bytes(mmdb_minimo(int(construida.timestamp())))

    settings.GEOIP_CITY_DATABASE_PATH = str(arquivo)
    settings.GEOIP_CITY_STALE_ALERT_DAYS = 21
    settings.GEOIP_CITY_MAX_AGE_DAYS = 90
    ip_location.reset_reader_cache()
    try:
        call_command("check_geoip_freshness", stdout=StringIO())
    finally:
        ip_location.reset_reader_cache()

    alerta = OperatorAlert.objects.get(type=ALERT_TYPE)
    assert alerta.severity == "error"
    assert "200 dias" in alerta.message
    assert f"{construida:%d/%m/%Y}" in alerta.message
