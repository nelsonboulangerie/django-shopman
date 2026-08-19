"""Reexibir não é reemitir — e emitir deixa trilha.

O token vivia só na primeira requisição. A intenção era boa e a consequência era
ruim: impressora que emperra custava um crachá. O antigo já tinha morrido e o
novo não existia em papel — numa padaria em hora de pico, é uma pessoa sem
conseguir entrar no PDV.

⚠️ A janela NÃO é segurança, e o teste diz isso de propósito para ninguém
confundir depois: contra a cópia não declarada (quem emite fotografa a tela) o
prazo não faz nada. O que cerca aquele risco é a permissão de emitir, a TRILHA,
e poder matar um crachá a qualquer momento.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone
from shopman.doorman.models import PinCredential

from shopman.backstage.admin_console.operator_badge import (
    BADGE_SESSION_KEY,
    JANELA_DE_REIMPRESSAO,
    dentro_da_janela,
)

pytestmark = pytest.mark.django_db

BADGE_URL = "/admin/operators/badge/"


@pytest.fixture(autouse=True)
def _loja():
    """Sem `Shop`, o middleware de onboarding redireciona tudo para criar a loja."""
    from shopman.shop.models import Shop

    return Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})[0]


@pytest.fixture
def gerente(client):
    user = get_user_model().objects.create_user(
        username="gestor", password="x", is_staff=True, is_superuser=True
    )
    client.force_login(user)
    return user


@pytest.fixture
def operador():
    user = get_user_model().objects.create_user(username="fran", password="x", is_staff=True)
    PinCredential.set_for(user, "1234")
    return user


# ── A regra de tempo, pura ────────────────────────────────────────────────


def test_carimbo_recente_pode_reexibir():
    agora = timezone.now()
    assert dentro_da_janela(agora.isoformat(), agora=agora)


def test_carimbo_velho_nao_pode():
    agora = timezone.now()
    velho = (agora - JANELA_DE_REIMPRESSAO - timedelta(seconds=1)).isoformat()
    assert not dentro_da_janela(velho, agora=agora)


@pytest.mark.parametrize("ruim", ["", None, "ontem", "2026-13-45"])
def test_carimbo_ausente_ou_ilegivel_responde_NAO(ruim):
    """Sessão de versão anterior não tem carimbo. Na dúvida, não se mostra credencial."""
    assert not dentro_da_janela(ruim)


# ── Reexibir ──────────────────────────────────────────────────────────────


def test_recarregar_dentro_da_janela_mostra_o_MESMO_cracha(client, gerente, operador):
    token = PinCredential.issue_badge(operador)
    sessao = client.session
    sessao[BADGE_SESSION_KEY] = {
        "token": token, "name": "Fran", "username": "fran",
        "issued_at": timezone.now().isoformat(),
    }
    sessao.save()

    primeira = client.get(BADGE_URL)
    segunda = client.get(BADGE_URL)

    assert token in primeira.content.decode()
    # A segunda visita é o ponto todo: antes ela vinha vazia e o crachá se perdia.
    assert token in segunda.content.decode()


def test_reexibir_nao_cria_credencial_nova(client, gerente, operador):
    token = PinCredential.issue_badge(operador)
    digest_antes = PinCredential.objects.get(user=operador).badge_hash
    sessao = client.session
    sessao[BADGE_SESSION_KEY] = {
        "token": token, "name": "Fran", "username": "fran",
        "issued_at": timezone.now().isoformat(),
    }
    sessao.save()

    client.get(BADGE_URL)
    client.get(BADGE_URL)

    assert PinCredential.objects.get(user=operador).badge_hash == digest_antes


def test_fora_da_janela_o_codigo_some_da_sessao(client, gerente, operador):
    """Credencial guardada sem utilidade é superfície de risco por nada."""
    token = PinCredential.issue_badge(operador)
    sessao = client.session
    sessao[BADGE_SESSION_KEY] = {
        "token": token, "name": "Fran", "username": "fran",
        "issued_at": (timezone.now() - JANELA_DE_REIMPRESSAO - timedelta(minutes=1)).isoformat(),
    }
    sessao.save()

    corpo = client.get(BADGE_URL).content.decode()

    assert token not in corpo
    assert BADGE_SESSION_KEY not in client.session
    # E a tela EXPLICA, em vez de dizer só "nada para mostrar": o crachá emitido
    # continua valendo, e quem lê precisa saber disso antes de emitir outro à toa.
    assert "continua VÁLIDO" in corpo


# ── Trilha ────────────────────────────────────────────────────────────────


def _acao_no_changelist(client, operador, acao: str):
    return client.post(
        reverse("admin:doorman_pincredential_changelist"),
        {"action": acao, "_selected_action": [str(PinCredential.objects.get(user=operador).pk)]},
        follow=True,
    )


def _historico(operador):
    ct = ContentType.objects.get_for_model(operador)
    return LogEntry.objects.filter(content_type=ct, object_id=str(operador.pk))


def test_emitir_cracha_deixa_linha_no_historico(client, gerente, operador):
    """Antes não deixava rastro NENHUM — o digest mudava em silêncio no banco."""
    _acao_no_changelist(client, operador, "issue_badge")

    linhas = _historico(operador)
    assert linhas.count() == 1
    assert "Crachá emitido" in linhas.first().change_message
    assert linhas.first().user_id == gerente.pk


def test_revogar_cracha_tambem(client, gerente, operador):
    PinCredential.issue_badge(operador)
    _historico(operador).delete()

    _acao_no_changelist(client, operador, "revoke_badge")

    assert "Crachá revogado" in _historico(operador).first().change_message


def test_a_trilha_diz_QUEM_emitiu_para_QUEM(client, gerente, operador):
    """É o que se compara quando um crachá destrava o PDV em dia de folga."""
    _acao_no_changelist(client, operador, "issue_badge")

    linha = _historico(operador).first()
    assert linha.user_id == gerente.pk           # quem emitiu
    assert linha.object_repr == "fran"           # para quem
    assert linha.action_time                     # quando


# ── A folha não pode sair em branco ───────────────────────────────────────


def _pagina(client) -> str:
    return client.get(BADGE_URL).content.decode()


def test_o_cracha_nao_e_filho_direto_do_body(client, gerente, operador):
    """É o FATO que torna `display:none` nos filhos do body fatal.

    O crachá mora fundo dentro do chrome do Admin (medido: 18 níveis). Qualquer
    regra de impressão que esconda "os filhos do body menos o crachá" esconde a
    linhagem dele junto — e a folha sai vazia, que foi o que aconteceu.
    """
    import re

    corpo = re.search(r"<body[^>]*>(.*)</body>", _pagina(client), re.S).group(1)
    antes = corpo[: corpo.find('id="badge-print-root"')]
    abertas = len(re.findall(r"<(?!/)(?!br|hr|img|input|meta|link|path)[a-zA-Z][^>]*?(?<!/)>", antes))
    fechadas = len(re.findall(r"</[a-zA-Z]+>", antes))

    assert abertas - fechadas > 0, "se um dia virar filho direto, reveja o CSS de impressão"


def test_a_impressao_esconde_por_visibility_e_nao_por_display(client, gerente, operador):
    """`display: none` num ancestral tira o ramo da árvore de caixas.

    Descendente nenhum consegue voltar de lá — nem com `visibility: visible`.
    `visibility: hidden` mantém as caixas e deixa o crachá se reafirmar. É a
    diferença entre a folha sair vazia e sair com o código de barras.
    """
    import re

    # Tira os comentários ANTES de olhar: o comentário do próprio arquivo cita a
    # regra antiga para explicar por que ela some, e um `not in` ingênuo bateria
    # nela. Comentário não é regra — o navegador não o executa, e o teste também
    # não deve lê-lo.
    css = re.sub(r"/\*.*?\*/", "", _pagina(client), flags=re.S)

    assert "body * { visibility: hidden; }" in css
    assert "display: none" not in css.split("@media print")[1].split("}")[0] + "}"
    assert "body > *:not(#badge-print-root)" not in css
    assert "#badge-print-root, #badge-print-root * { visibility: visible; }" in css


def test_o_codigo_de_barras_esta_na_pagina(client, gerente, operador):
    """Sem SVG não há o que imprimir, com CSS certo ou errado."""
    token = PinCredential.issue_badge(operador)
    sessao = client.session
    sessao[BADGE_SESSION_KEY] = {
        "token": token, "name": "Fran", "username": "fran",
        "issued_at": timezone.now().isoformat(),
    }
    sessao.save()

    corpo = _pagina(client)

    assert 'id="badge-print-root"' in corpo
    assert "<svg" in corpo
    assert token in corpo
