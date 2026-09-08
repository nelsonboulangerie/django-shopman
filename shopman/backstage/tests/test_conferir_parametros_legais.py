"""O comando que põe o sistema e a norma lado a lado.

Quem responde por cumprir a lei é o gestor, não o repositório. Estes testes
guardam que a cobrança **chega até ele** e que não vira ruído:

- o comando mostra a norma, o valor assumido e **onde ler** — a conferência tem
  de ser clique, não caçada;
- parâmetro vencido vira `OperatorAlert`, porque teste vermelho só quem
  programa vê;
- o alerta **não se repete** enquanto o anterior não for reconhecido — alerta
  diário é alerta que se aprende a ignorar.
"""

from __future__ import annotations

from datetime import date, timedelta
from io import StringIO

import pytest
from django.core.management import call_command

from shopman.shop import legal_parameters as lp


def _rodar(*args, **kwargs):
    out = StringIO()
    call_command("conferir_parametros_legais", *args, stdout=out, stderr=out, **kwargs)
    return out.getvalue()


def test_mostra_a_norma_o_valor_e_onde_ler():
    """Pinado nas chaves REAIS, não no global — que outro teste desta suíte troca."""
    saida = _rodar()
    for chave in (
        "alergenos_declaracao_obrigatoria",
        "limiar_sem_lactose",
        "declaracao_gluten",
        "pode_conter_contaminacao_cruzada",
    ):
        assert chave in saida
    assert "RDC 135/2017" in saida, "a norma tem de aparecer, não só a chave"
    assert "planalto.gov.br" in saida, "sem o link, 'confira a lei' vira caçada"


def test_sem_vencidos_o_comando_diz_isso_e_para():
    saida = _rodar("--vencidos")
    assert "Nenhum parâmetro vencido" in saida


def _vencido(monkeypatch):
    velho = lp.ParametroLegal(
        chave="teste_vencido", norma="RDC 999/1999", valor="v",
        conferido_em=date.today() - timedelta(days=lp.JANELA_DE_REVISAO_DIAS + 1),
        conferido_por="ninguém", fonte="https://exemplo.gov.br/norma",
    )
    import shopman.backstage.management.commands.conferir_parametros_legais as cmd

    # O comando importa os nomes no topo, então trocar só o módulo de origem não
    # basta — os dois lados precisam do patch.
    monkeypatch.setattr(lp, "PARAMETROS", (velho,))
    monkeypatch.setattr(cmd, "PARAMETROS", (velho,))
    monkeypatch.setattr(cmd, "vencidos", lambda hoje=None: [velho])
    return velho


def test_vencido_aparece_marcado(monkeypatch):
    _vencido(monkeypatch)
    saida = _rodar("--vencidos")
    assert "VENCIDO" in saida
    assert "precisam de conferência" in saida
    assert "Mexer só na data sem ler" in saida, "o comando tem de dizer o que NÃO fazer"


@pytest.mark.django_db
def test_vencido_vira_alerta_para_o_gestor(monkeypatch):
    from shopman.backstage.models import OperatorAlert

    _vencido(monkeypatch)
    _rodar("--vencidos", "--alertar")

    alerta = OperatorAlert.objects.filter(type="legal_parameter_stale").first()
    assert alerta is not None, "a cobrança precisa chegar a quem responde pela lei"
    assert "teste_vencido" in alerta.message
    assert "conferir_parametros_legais" in alerta.message, "diga ao gestor o que rodar"


@pytest.mark.django_db
def test_o_alerta_nao_se_repete_todo_ciclo(monkeypatch):
    from shopman.backstage.models import OperatorAlert

    _vencido(monkeypatch)
    _rodar("--vencidos", "--alertar")
    _rodar("--vencidos", "--alertar")
    _rodar("--vencidos", "--alertar")

    assert OperatorAlert.objects.filter(type="legal_parameter_stale").count() == 1, (
        "o worker roda todo ciclo; alerta repetido é alerta que se aprende a ignorar"
    )


@pytest.mark.django_db
def test_reconhecido_o_alerta_pode_voltar(monkeypatch):
    """Se o gestor reconheceu e não conferiu, a cobrança volta — não some."""
    from shopman.backstage.models import OperatorAlert

    _vencido(monkeypatch)
    _rodar("--vencidos", "--alertar")
    OperatorAlert.objects.filter(type="legal_parameter_stale").update(acknowledged=True)
    _rodar("--vencidos", "--alertar")

    assert OperatorAlert.objects.filter(type="legal_parameter_stale").count() == 2


def test_o_worker_roda_a_conferencia_com_alerta():
    """De nada adianta o comando existir se ninguém o chama."""
    from shopman.shop.management.commands.maintenance_worker import MAINTENANCE_COMMANDS

    entrada = next(
        (e for e in MAINTENANCE_COMMANDS
         if isinstance(e, tuple) and e[0] == "conferir_parametros_legais"),
        None,
    )
    assert entrada is not None, "a conferência periódica precisa estar no ciclo do worker"
    assert entrada[1].get("alertar") is True, "no worker ela existe para ALERTAR"
