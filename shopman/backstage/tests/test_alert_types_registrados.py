"""Todo tipo de alerta gravado pelo código precisa existir em ``TYPE_CHOICES``.

``choices`` do Django não é validado no banco: gravar ``type="qualquer_coisa"``
salva a linha sem reclamar. O preço só aparece na tela — ``get_type_display()``
devolve o slug cru, e o crachá do Admin e do Gestor mostra
``payment_ledger_drift`` no meio de vizinhos que dizem "Estorno falhou".

Foi assim que 25 tipos chegaram ao ar sem rótulo, ao longo de meses: cada um
nasceu num PR que mexia no service, e o model mora noutro app. Nenhum teste
existente pegava — os dois que checavam ``get_type_display()`` (cupom e
observability) olhavam UM tipo cada, o que o PR deles tinha acabado de criar.

Esta varredura fecha o buraco pelo lado certo: ela lê os literais que o código
de fato escreve e cobra o gêmeo no model. Um tipo novo sem rótulo falha aqui,
no PR que o criou, em vez de aparecer cru no crachá meses depois.

Limite conhecido e deliberado: a resolução de nomes é por MÓDULO, não por
escopo léxico — um ``alert_type`` que chega ao sink por variável resolve para
todos os literais atribuídos àquele nome no arquivo. Isso pode coletar um
literal a mais (falso positivo custa uma linha em ``TYPE_CHOICES``, e o tipo
existir sem ser usado não machuca ninguém); o que ele nunca faz é deixar passar
um tipo que o código escreve.
"""

from __future__ import annotations

import ast
from pathlib import Path

from shopman.backstage.models import OperatorAlert

#: Raiz do repositório (este arquivo mora em shopman/backstage/tests/).
_RAIZ = Path(__file__).resolve().parents[3]

#: Árvores de código que gravam alerta. `packages/` fica de fora de propósito:
#: os cores não conhecem o backstage (regra de dependência do CLAUDE.md).
_ARVORES = ("shopman", "config")

#: Chamadas que gravam (ou consultam) um tipo de alerta, e onde o tipo está:
#: índice posicional e/ou nome do keyword.
_SINKS: dict[str, tuple[int | None, str]] = {
    "create_operator_alert": (None, "type"),
    "observability.create_operator_alert": (None, "type"),
    "alert_adapter.create": (0, "type"),
    "alert_adapter.recent_exists": (0, "type"),
    "alert_adapter.acknowledge": (0, "type"),
    "alert.create": (0, "type"),
    "alert.recent_exists": (0, "type"),
    "alert.acknowledge": (0, "type"),
    "OperatorAlert.objects.create": (None, "type"),
}

#: A própria encanação: aqui o tipo é PARÂMETRO por definição, e não há literal
#: para resolver. `services/alerts.py` já valida contra TYPE_CHOICES em runtime;
#: `adapters/alert.py` é o adapter que todo mundo chama. Qualquer OUTRO ponto
#: que a varredura não conseguir resolver é buraco, e falha.
_ENCANAMENTO = frozenset({
    "shopman/backstage/services/alerts.py",
    "shopman/shop/adapters/alert.py",
})


def _dotted(node: ast.expr) -> str:
    """`a.b.c` → "a.b.c"; qualquer outra coisa → o que der."""
    partes: list[str] = []
    atual: ast.expr = node
    while isinstance(atual, ast.Attribute):
        partes.append(atual.attr)
        atual = atual.value
    if isinstance(atual, ast.Name):
        partes.append(atual.id)
    return ".".join(reversed(partes))


def _literais_por_nome(arvore: ast.Module) -> dict[str, set[str]]:
    """Mapeia identificador → literais string que o módulo atribui a ele.

    Cobre atribuição direta, ternário, desempacotamento de tupla e o argumento
    literal passado a uma função do próprio módulo (é assim que
    ``_create_alert(order, "rejected_oos")`` chega ao ``alert_type`` lá dentro).
    """
    valores: dict[str, set[str]] = {}

    def guardar(nome: str, valor: ast.expr) -> None:
        if isinstance(valor, ast.Constant) and isinstance(valor.value, str):
            valores.setdefault(nome, set()).add(valor.value)

    for node in ast.walk(arvore):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        alvos = node.targets if isinstance(node, ast.Assign) else [node.target]
        valor = node.value
        if valor is None:
            continue
        for alvo in alvos:
            if isinstance(alvo, ast.Name):
                guardar(alvo.id, valor)
                if isinstance(valor, ast.IfExp):
                    guardar(alvo.id, valor.body)
                    guardar(alvo.id, valor.orelse)
            elif (
                isinstance(alvo, ast.Tuple)
                and isinstance(valor, ast.Tuple)
                and len(alvo.elts) == len(valor.elts)
            ):
                for nome, item in zip(alvo.elts, valor.elts, strict=True):
                    if isinstance(nome, ast.Name):
                        guardar(nome.id, item)

    funcoes = {
        n.name: n
        for n in ast.walk(arvore)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for node in ast.walk(arvore):
        if not isinstance(node, ast.Call):
            continue
        funcao = funcoes.get(_dotted(node.func).rsplit(".", 1)[-1])
        if funcao is None:
            continue
        posicionais = funcao.args.args
        parametros = {a.arg for a in posicionais} | {a.arg for a in funcao.args.kwonlyargs}
        for i, argumento in enumerate(node.args):
            if i < len(posicionais):
                guardar(posicionais[i].arg, argumento)
        for kw in node.keywords:
            if kw.arg in parametros:
                guardar(kw.arg, kw.value)

    return valores


def _varrer(caminho: Path) -> tuple[set[str], list[str]]:
    """Devolve (tipos gravados neste arquivo, sinks que não deu para resolver)."""
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    valores = _literais_por_nome(arvore)
    tipos: set[str] = set()
    opacos: list[str] = []
    relativo = caminho.relative_to(_RAIZ).as_posix()

    for node in ast.walk(arvore):
        if not isinstance(node, ast.Call):
            continue
        sink = _SINKS.get(_dotted(node.func))
        if sink is None:
            continue
        indice, palavra = sink
        argumento = None
        if indice is not None and len(node.args) > indice:
            argumento = node.args[indice]
        if argumento is None:
            argumento = next((k.value for k in node.keywords if k.arg == palavra), None)
        if argumento is None:
            continue
        if isinstance(argumento, ast.Constant) and isinstance(argumento.value, str):
            tipos.add(argumento.value)
        elif isinstance(argumento, ast.Name) and valores.get(argumento.id):
            tipos |= valores[argumento.id]
        else:
            opacos.append(f"{relativo}:{node.lineno} → {ast.unparse(argumento)}")

    return tipos, opacos


def _arquivos_de_producao() -> list[Path]:
    arquivos: list[Path] = []
    for arvore in _ARVORES:
        for caminho in sorted((_RAIZ / arvore).rglob("*.py")):
            partes = caminho.relative_to(_RAIZ).parts
            if "migrations" in partes or "tests" in partes:
                continue
            if caminho.name.startswith("test_"):
                continue
            arquivos.append(caminho)
    return arquivos


def test_todo_tipo_gravado_tem_rotulo_em_type_choices():
    registrados = {slug for slug, _ in OperatorAlert.TYPE_CHOICES}
    sem_rotulo: dict[str, list[str]] = {}

    for caminho in _arquivos_de_producao():
        tipos, _ = _varrer(caminho)
        for tipo in tipos - registrados:
            sem_rotulo.setdefault(tipo, []).append(caminho.relative_to(_RAIZ).as_posix())

    assert not sem_rotulo, (
        "Tipo de alerta gravado pelo código e ausente de OperatorAlert.TYPE_CHOICES — "
        "o crachá do Admin e do Gestor vai mostrar o slug cru. Acrescente a choice "
        "com rótulo em português e gere a migração:\n"
        + "\n".join(f"  {tipo}: {', '.join(sorted(set(onde)))}" for tipo, onde in sorted(sem_rotulo.items()))
    )


def test_nenhum_ponto_de_gravacao_escapa_da_varredura():
    """Sink com tipo que a varredura não resolve é buraco no teste acima."""
    opacos: list[str] = []
    for caminho in _arquivos_de_producao():
        if caminho.relative_to(_RAIZ).as_posix() in _ENCANAMENTO:
            continue
        opacos += _varrer(caminho)[1]

    assert not opacos, (
        "Alerta gravado com tipo que a varredura não consegue resolver até um "
        "literal — o teste acima não cobre este ponto. Passe o tipo como string "
        "literal (ou por variável do próprio módulo), ou declare o arquivo em "
        "_ENCANAMENTO se ele for plumbing genérica:\n  " + "\n  ".join(opacos)
    )
