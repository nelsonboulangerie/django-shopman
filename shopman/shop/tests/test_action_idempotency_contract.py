"""Contrato: acao mutavel nao sai com ``idempotency="none"`` sem justificativa nomeada.

O ``Action`` (``shopman/shop/projections/types.py``) declara, por acao, se a
superficie precisa mandar chave de idempotencia. Ate 29/08 o default do campo era
``"none"`` — e sete acoes do PDV nem o declaravam. O silencio decidia: toda acao
nova nascia "nao precisa de chave" sem ninguem ter pensado no assunto, inclusive o
cancelamento de venda e o DELETE de comanda.

O default agora e ``"required"``. Este teste e a outra metade do conserto: quem
declara ``"none"`` numa acao que MUTA precisa aparecer aqui, com uma linha dizendo
por que. Uma acao nova que degrade para o permissivo reprova o CI em vez de entrar
calada — que e a regua da casa para dinheiro, auth e fiscal (falhar fechado, ou
falhar gritando; nunca falhar aberto e calado).

A varredura le o FONTE (nao importa nada): as tres construcoes de acao do
repositorio sao literais, entao o AST ve exatamente o que a projection emite, sem
banco e sem app carregado.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from shopman.shop.projections.types import Action

_ROOT = Path(__file__).resolve().parents[2]  # shopman/

# As tres formas de construir uma acao no repositorio.
ACTION_CALLS = {"Action", "_action", "action_payload"}
# As duas fabricas que repassam o campo — o default DELAS tambem precisa ser
# restritivo, senao a inversao no dataclass e cosmetica.
ACTION_FACTORIES = {"_action", "action_payload"}

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# ── Acoes que declaram "none" com razao ────────────────────────────────────
# Repetir a chamada e inofensivo: ou e leitura disfarcada de POST, ou a operacao
# e endereçada por identidade (o segundo disparo vira no-op).
IDEMPOTENT_BY_NATURE = {
    "review_sale": "calcula a previa do checkout e nao grava nada — POST so por causa do tamanho do payload",
    "reverse_geocode": "leitura pura: resolve lat/lng em endereco",
    "customer_lookup": "GET",
    "customer_search": "GET",
    "open_tab": "abre a comanda pelo ref — abrir duas vezes deixa a mesma comanda aberta",
    "save_tab": "grava a lista inteira da comanda (replace por session_key), nao acumula",
    "rename_tab": "renomear para X duas vezes deixa o nome X",
    "clear_tab": "DELETE por session_key — o segundo disparo nao acha o que liberar",
    "unfire_tab": "cancela o envio de line_ids nomeados; repetir nao desfaz nada a mais",
    "move_tab_lines": "move line_ids nomeados; na segunda vez eles ja nao estao na origem",
    "cancel_recent_sale": "cancela um order_ref nomeado; a venda ja cancelada nao cancela de novo",
    "drawer_open": "abre a gaveta fisica — repetir abre a gaveta de novo, nao gera lancamento",
    "drawer_unlock_attempt": "telemetria da tela de PIN",
    "drawer_left_open": "telemetria: a gaveta ficou aberta sem venda",
    "drawer_block": "telemetria: quanto tempo a gaveta ficou aberta",
    "drawer_blind": "telemetria: o sensor da gaveta parou de responder",
    "drawer_unlock": "libera a proxima venda com a gaveta aberta; liberar duas vezes libera uma vez",
    "create_tab": "cria a comanda pelo tab_ref informado — o segundo POST esbarra no ref que ja existe",
    "set_available_qty": "PUT que fixa a qty num valor CONSTANTE do payload — repetir deixa a mesma qty",
    "notify_when_available": "a assinatura de aviso dedupe por (sku, alert_type, alvo) em stock_alerts.subscribe",
}

# ── Divida nomeada: mutacao de dinheiro ainda sem chave ────────────────────
# ✅ ESVAZIADA na Onda 2. As oito mutacoes do caixa passaram a declarar
# `client_request_id`, e o servidor as embrulha em `_cash_idempotent`
# (`shopman/backstage/api/operations.py`), que reusa o `run_idempotent_mutation` e a
# `IdempotencyKey` do orderman — sem modelo novo e sem migracao.
#
# A lista fica aqui VAZIA de proposito, e nao apagada: ela e o lugar onde a proxima
# mutacao de dinheiro sem chave teria de ser escrita, e um dicionario vazio com esta
# docstring diz isso melhor do que a ausencia do simbolo.
DIVIDA_ONDA_2: dict[str, str] = {}

ALLOWLIST = {**IDEMPOTENT_BY_NATURE, **DIVIDA_ONDA_2}


def _literal(node):
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def _action_sites() -> list[tuple[str, int, str, str, str | None]]:
    """(arquivo, linha, ref, method, idempotency-declarada-ou-None)."""
    sites = []
    for path in sorted(_ROOT.rglob("*.py")):
        if "tests" in path.parts or "migrations" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        if not any(f"{name}(" in source for name in ACTION_CALLS):
            continue
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Call):
                continue
            if getattr(node.func, "id", "") not in ACTION_CALLS:
                continue
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            ref = _literal(kw.get("ref")) if "ref" in kw else None
            if not isinstance(ref, str):
                continue  # repasse dentro da propria fabrica
            method = _literal(kw.get("method")) if "method" in kw else ""
            idem = _literal(kw["idempotency"]) if "idempotency" in kw else None
            rel = str(path.relative_to(_ROOT.parent))
            sites.append((rel, node.lineno, ref, method or "", idem))
    return sites


def test_default_do_dataclass_e_restritivo() -> None:
    """Omissao no dataclass nao pode significar "nao precisa de chave"."""
    assert Action(ref="x", kind="mutation", label="X").idempotency == "required"


def test_as_fabricas_de_acao_herdam_o_default_restritivo() -> None:
    """Uma fabrica com default "none" tornaria a inversao no dataclass cosmetica."""
    encontradas = {}
    for path in sorted(_ROOT.rglob("*.py")):
        if "tests" in path.parts or "migrations" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        if not any(f"def {name}(" in source for name in ACTION_FACTORIES):
            continue
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.FunctionDef) or node.name not in ACTION_FACTORIES:
                continue
            args = node.args
            nomes = [a.arg for a in args.kwonlyargs]
            if "idempotency" not in nomes:
                continue
            default = args.kw_defaults[nomes.index("idempotency")]
            rel = str(path.relative_to(_ROOT.parent))
            encontradas[f"{rel}:{node.lineno} {node.name}"] = _literal(default)

    assert encontradas, "nenhuma fabrica de Action encontrada — a varredura quebrou"
    permissivas = {k: v for k, v in encontradas.items() if v != "required"}
    assert not permissivas, (
        "fabrica de Action com default permissivo: "
        + "; ".join(f"{k} → {v!r}" for k, v in sorted(permissivas.items()))
        + '. Use idempotency: str = "required" e declare "none" no call site.'
    )


def test_toda_acao_mutavel_declara_idempotencia() -> None:
    """Ausencia do campo nao e decisao — em mutacao, o campo e obrigatorio."""
    mudas = [
        f"{rel}:{line} ref={ref!r} method={method}"
        for rel, line, ref, method, idem in _action_sites()
        if method in MUTATING_METHODS and idem is None
    ]
    assert not mudas, (
        "acao mutavel sem `idempotency=` declarado:\n  "
        + "\n  ".join(mudas)
        + '\nDeclare "required"/"client_request_id"/"recommended", ou "none" '
        "com uma linha de justificativa na allowlist deste teste."
    )


def test_nenhuma_acao_mutavel_sai_com_none_fora_da_allowlist() -> None:
    """"none" numa mutacao precisa de dono: ou e inofensivo, ou e divida nomeada."""
    orfas = [
        f"{rel}:{line} ref={ref!r} method={method}"
        for rel, line, ref, method, idem in _action_sites()
        if method in MUTATING_METHODS and idem == "none" and ref not in ALLOWLIST
    ]
    assert not orfas, (
        'acao mutavel com idempotency="none" sem justificativa:\n  '
        + "\n  ".join(orfas)
        + "\nSe repetir a chamada e inofensivo, adicione o ref a IDEMPOTENT_BY_NATURE "
        "com a razao. Se nao e, a acao precisa de chave de idempotencia."
    )


def test_a_divida_do_caixa_nao_cresce() -> None:
    """A lista da Onda 2 so encolhe: mutacao de dinheiro nova ja nasce com chave."""
    com_none = {
        ref
        for _rel, _line, ref, method, idem in _action_sites()
        if method in MUTATING_METHODS and idem == "none"
    }
    resolvidas = set(DIVIDA_ONDA_2) - com_none
    assert not resolvidas, (
        "estas acoes sairam do 'none' — otimo: remova-as de DIVIDA_ONDA_2 para a "
        f"lista nao mentir sobre o tamanho da divida: {sorted(resolvidas)}"
    )


@pytest.mark.parametrize("ref", sorted(ALLOWLIST))
def test_allowlist_nao_guarda_entrada_morta(ref: str) -> None:
    """Entrada que nao corresponde a nenhuma acao viva vira folclore."""
    refs_vivos = {r for _rel, _line, r, _m, _i in _action_sites()}
    assert ref in refs_vivos, (
        f"{ref!r} esta na allowlist mas nao existe mais nenhuma acao com esse ref. "
        "Remova a entrada."
    )
