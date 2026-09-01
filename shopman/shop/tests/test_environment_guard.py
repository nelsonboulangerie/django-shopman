"""``SHOPMAN_ENVIRONMENT`` responde a UMA pergunta, com UM vocabulário.

O defeito que originou este módulo: a mesma variável era lida de três jeitos, e
os leitores discordavam justamente no caso perigoso. ``seed --flush`` perguntava
``== "production"``; escrever ``prod`` fazia o guard achar que não era produção
e apagar a loja inteira sem nem exigir ``--force``.

Os testes abaixo prendem a assimetria que conserta isso: **só os quatro nomes
não-produtivos abrem a porta; todo o resto é produção.**
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from shopman.shop.checks import check_environment_name_recognized
from shopman.shop.environment import (
    NON_PRODUCTION_ENVIRONMENTS,
    environment_name,
    is_production,
    is_recognized_environment,
)

#: Grafias de produção que ANTES passavam reto pelos guards destrutivos.
GRAFIAS_DE_PRODUCAO = ["production", "prod", "producao", "produção", "live"]

#: Valores que ninguém quis escrever. O que importa não é adivinhar a intenção
#: — é que nenhum deles destranque um comando destrutivo.
VALORES_IRRECONHECIVEIS = ["prodction", "stagin", "homologacao", "qa", "", "   "]


@pytest.mark.parametrize("nome", sorted(NON_PRODUCTION_ENVIRONMENTS))
def test_nomes_nao_produtivos_abrem_a_porta(nome):
    with override_settings(SHOPMAN_ENVIRONMENT=nome):
        assert is_production() is False


@pytest.mark.parametrize("nome", GRAFIAS_DE_PRODUCAO)
def test_toda_grafia_de_producao_fecha_a_porta(nome):
    with override_settings(SHOPMAN_ENVIRONMENT=nome):
        assert is_production() is True


@pytest.mark.parametrize("nome", VALORES_IRRECONHECIVEIS)
def test_valor_irreconhecivel_e_tratado_como_producao(nome):
    """Falhar FECHADO: quem não se declarou não ganha o benefício da dúvida."""
    with override_settings(SHOPMAN_ENVIRONMENT=nome):
        assert is_production() is True


def test_variavel_ausente_e_producao():
    """Instância que não se declarou é tratada como a loja de verdade."""
    with patch("shopman.shop.environment.settings", spec=[]):
        assert environment_name() == "production"
        assert is_production() is True


@pytest.mark.parametrize("bruto", ["  STAGING  ", "Staging", "DEV"])
def test_espaco_e_caixa_nao_mudam_o_veredito(bruto):
    """Um espaço colado no spec da DO não pode virar produção sem querer."""
    with override_settings(SHOPMAN_ENVIRONMENT=bruto):
        assert is_production() is False
        assert environment_name() == bruto.strip().lower()


# ─────────────────────────────────────────────────────────────────────────────
# Os quatro comandos destrutivos — a regressão de verdade.
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("nome", GRAFIAS_DE_PRODUCAO + VALORES_IRRECONHECIVEIS)
def test_seed_flush_recusa_em_toda_grafia_de_producao(nome):
    """O caso que custaria a loja: `prod` fazia o flush correr sem `--force`."""
    with override_settings(SHOPMAN_ENVIRONMENT=nome):
        with pytest.raises(CommandError, match="Recusando `seed --flush`"):
            call_command("seed", "--flush")


@pytest.mark.django_db
@pytest.mark.parametrize("nome", GRAFIAS_DE_PRODUCAO + VALORES_IRRECONHECIVEIS)
def test_qa_scenarios_recusa_em_toda_grafia_de_producao(nome):
    with override_settings(SHOPMAN_ENVIRONMENT=nome):
        with pytest.raises(CommandError, match="Recusando qa_scenarios"):
            call_command("qa_scenarios")


@pytest.mark.django_db
@pytest.mark.parametrize("nome", GRAFIAS_DE_PRODUCAO + VALORES_IRRECONHECIVEIS)
def test_refresh_seed_dates_recusa_em_toda_grafia_de_producao(nome):
    with override_settings(SHOPMAN_ENVIRONMENT=nome):
        with pytest.raises(CommandError, match="Recusando refresh_seed_dates"):
            call_command("refresh_seed_dates")


@pytest.mark.django_db
@pytest.mark.parametrize("nome", GRAFIAS_DE_PRODUCAO + VALORES_IRRECONHECIVEIS)
def test_import_backup_apply_exige_force_em_toda_grafia_de_producao(nome, tmp_path):
    with override_settings(SHOPMAN_ENVIRONMENT=nome):
        with pytest.raises(CommandError, match="exige --force"):
            call_command("import_backup", str(tmp_path / "qualquer.xlsx"), "--apply")


@pytest.mark.django_db
def test_staging_segue_livre_para_os_comandos_de_qa():
    """A trava não pode custar o fluxo de teste — senão alguém a desliga.

    O comando ainda falha (o arquivo não existe), mas por OUTRO motivo: o que
    se prova aqui é que o guard de ambiente não é quem barra.
    """
    with override_settings(SHOPMAN_ENVIRONMENT="staging"):
        with pytest.raises(Exception) as excinfo:
            call_command("import_backup", "/caminho/que/nao/existe.xlsx", "--apply")
        assert "exige --force" not in str(excinfo.value)


# ─────────────────────────────────────────────────────────────────────────────
# Falhar fechado E gritando.
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("nome", VALORES_IRRECONHECIVEIS)
def test_valor_irreconhecivel_avisa_no_boot(nome):
    with override_settings(SHOPMAN_ENVIRONMENT=nome):
        assert is_recognized_environment() is False
        assert [m.id for m in check_environment_name_recognized(None)] == ["SHOPMAN_W017"]


@pytest.mark.parametrize("nome", sorted(NON_PRODUCTION_ENVIRONMENTS) + GRAFIAS_DE_PRODUCAO)
def test_nome_conhecido_nao_faz_barulho(nome):
    with override_settings(SHOPMAN_ENVIRONMENT=nome):
        assert is_recognized_environment() is True
        assert check_environment_name_recognized(None) == []


# ─────────────────────────────────────────────────────────────────────────────
# Anti-deriva: quem mantém uma segunda lista tem de manter a MESMA lista.
# ─────────────────────────────────────────────────────────────────────────────


def test_a_fita_de_ambiente_cobre_exatamente_os_nomes_nao_produtivos():
    """A tarja da loja tem o próprio dicionário (env → frase). As CHAVES dele
    precisam ser o conjunto canônico: uma loja não-produtiva sem frase ficaria
    calada dizendo ser a de verdade — que é o defeito que a tarja existe para
    impedir.
    """
    from shopman.storefront.presentation.home import _ENVIRONMENT_NOTICES

    assert set(_ENVIRONMENT_NOTICES) == NON_PRODUCTION_ENVIRONMENTS
