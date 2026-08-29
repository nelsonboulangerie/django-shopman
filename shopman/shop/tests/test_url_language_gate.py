"""A regra "URL é em inglês, ponto" precisa de um guarda, não de memória.

⚠️ A rota do painel público de retirada nasceu `kds/cliente/`, virou `kds/retirada/` e
só chegou a `kds/pickup/` na terceira passada — e a auditoria que a encontrou afirmava,
no item de verificação, que `kds/cliente/` "não existe em nenhum arquivo". Existia, em
quatro. Convenção que vale enquanto alguém lembra não é convenção, é lembrança.

O guarda é uma LISTA de palavras, não um detector de idioma: só acusa termos que este
projeto de fato já usou em rota, e que têm tradução óbvia. Falso positivo aqui custa uma
linha na exceção; falso negativo custa uma rota em português no ar.
"""

from __future__ import annotations

import re

import pytest
from django.urls import URLPattern, URLResolver, get_resolver

#: Palavras pt-BR que já apareceram (ou quase) em rota deste repositório, com o termo
#: inglês que a casa usa no lugar. O valor é só para a mensagem de erro ser acionável.
_PORTUGUES_EM_ROTA = {
    "cliente": "customer/pickup",
    "clientes": "customers",
    "comanda": "tab",
    "comandas": "tabs",
    "pedido": "order",
    "pedidos": "orders",
    "caixa": "cash",
    "fechamento": "closing",
    "producao": "production",
    "produção": "production",
    "retirada": "pickup",
    "gaveta": "drawer",
    "cracha": "badge",
    "crachá": "badge",
    "operador": "operator",
    "operadores": "operators",
    "vitrine": "showcase",
    "fornada": "batch",
    "fornadas": "batches",
    "entrega": "delivery",
    "recebimento": "receipt",
    "compras": "purchases",
    "estoque": "stock",
    "ajuste": "adjust",
    "cancelar": "cancel",
    "configuracao": "settings",
    "configuração": "settings",
}

#: Exceções deliberadas. `cpf`/`cnpj`/`cep` são nome próprio de documento brasileiro —
#: ver a convenção de nomenclatura no CLAUDE.md. Vazio por enquanto: nenhuma rota
#: precisou de exceção, e é bom que continue assim.
_EXCECOES: frozenset[str] = frozenset()

_SEGMENTO = re.compile(r"[a-z0-9áàâãéêíóôõúç]+")


def _segmentos_de_rota() -> list[tuple[str, str]]:
    """Cada (rota completa, segmento) da URLconf inteira."""
    achados: list[tuple[str, str]] = []

    def _andar(patterns, prefixo: str) -> None:
        for entrada in patterns:
            trecho = str(getattr(entrada.pattern, "_route", "") or entrada.pattern)
            rota = f"{prefixo}{trecho}"
            if isinstance(entrada, URLResolver):
                _andar(entrada.url_patterns, rota)
            elif isinstance(entrada, URLPattern):
                # Só o texto literal: o nome do parâmetro (`<str:ref>`) é código, não URL.
                literal = re.sub(r"<[^>]*>", " ", rota)
                achados.extend((rota, s) for s in _SEGMENTO.findall(literal.lower()))

    _andar(get_resolver().url_patterns, "")
    return achados


@pytest.mark.django_db
def test_nenhuma_rota_fala_portugues():
    culpados = [
        f"/{rota} — o segmento {segmento!r} deveria ser {_PORTUGUES_EM_ROTA[segmento]!r}"
        for rota, segmento in _segmentos_de_rota()
        if segmento in _PORTUGUES_EM_ROTA and segmento not in _EXCECOES
    ]
    assert not culpados, "URL é em inglês, ponto:\n  " + "\n  ".join(sorted(set(culpados)))


def test_o_guarda_realmente_pega_alguma_coisa():
    """Assert-negativo do próprio guarda.

    Uma varredura que nunca acusa nada passa igual estando quebrada. Este teste prova
    que a lista casa com o formato de segmento que a varredura produz.
    """
    assert "cliente" in _PORTUGUES_EM_ROTA
    assert _SEGMENTO.findall("kds/cliente/") == ["kds", "cliente"]
