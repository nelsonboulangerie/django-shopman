"""Toda ação declarada tem de apontar para um endpoint que EXISTE.

⚠️ Três declarações do contrato do PDV descreviam endpoints diferentes dos reais, e
nada acusava:

- `request_change` exigia `kind`, e `kind` não existe em lugar nenhum — resíduo de um
  tipo que o próprio docstring conta que foi removido. Enquanto isso `denominations`,
  que o endpoint lê, não era declarado.
- `close_cash_shift` não declarava `terminal_ref`, que o endpoint lê — é por ele que o
  fechamento sabe QUAL terminal fechar quando há mais de um na estação.
- `fire_tab` prometia `idempotency="client_request_id"`, e essa chave só vai para o log.
  Quem protege é o ledger de tickets da cozinha, por `line_id`.

Contrato que descreve um endpoint que não existe é pior que contrato nenhum: o cliente
confia nele. Este teste percorre as ações e resolve cada `href` contra a URLconf — não
prova que o corpo declarado bate com o lido (isso pede tipagem que a casa não tem), mas
pega a divergência que mais dói: a rota que sumiu ou nunca existiu.
"""

from __future__ import annotations

import re

import pytest
from django.urls import Resolver404, resolve

pytestmark = pytest.mark.django_db

#: `{order_ref}` no href é um buraco do contrato; para resolver, qualquer valor serve.
_PARAMETRO = re.compile(r"\{[^}]+\}")


def _acoes():
    from shopman.backstage.projections import pos as pos_projection

    return pos_projection._pos_actions()


def test_todo_href_de_acao_resolve_na_urlconf():
    quebradas = []
    for acao in _acoes():
        if not acao.href.startswith("/"):
            continue  # href relativo/externo não é rota desta casa
        # A query é do cliente, não da rota: `?phone={phone}` não entra no resolve.
        caminho = _PARAMETRO.sub("x", acao.href.split("?", 1)[0])
        try:
            resolve(caminho)
        except Resolver404:
            quebradas.append(f"{acao.ref!r} → {acao.href}")
    assert not quebradas, "ação apontando para rota inexistente:\n  " + "\n  ".join(quebradas)


def test_o_guarda_pega_uma_rota_inventada():
    """Assert-negativo: varredura que nunca acusa passa igual estando quebrada."""
    with pytest.raises(Resolver404):
        resolve("/api/v1/backstage/pos/rota-que-nao-existe/")


def test_as_tres_declaracoes_corrigidas_batem_com_o_endpoint():
    """Fixa os três casos concretos — o teste genérico acima não os alcança.

    O `href` dos três sempre resolveu; o que estava errado era o CORPO declarado.
    """
    por_ref = {acao.ref: acao for acao in _acoes()}

    troco = por_ref["request_change"].payload_schema
    assert "kind" not in troco.get("required", []), "`kind` não existe no endpoint"
    assert "amount" in troco["required"]
    assert "denominations" in troco["optional"], "o endpoint lê, o contrato tem de declarar"

    fechar = por_ref["close_cash_shift"].payload_schema
    assert "terminal_ref" in fechar["optional"]

    assert por_ref["fire_tab"].idempotency == "ledger"
