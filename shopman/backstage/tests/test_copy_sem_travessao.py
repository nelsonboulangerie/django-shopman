"""Copy que chega ao operador não usa travessão (CLAUDE.md, "Copy sem travessão").

A regra vale para defaults, fallbacks, seeds, notificações e textos configuráveis, e
até 03/10/2026 só tinha trava em dois cantos: os defaults da `OmotenashiCopy`
(`shopman/shop/tests/test_omotenashi_copy_keys.py`) e o separador do `__str__`
(`test_separador_de_nome.py`). A mensagem de erro que o PDV mostra, a copy de
projection, o `help_text` do Admin e o assunto do e-mail passavam por baixo das duas.

Esta trava lê os literais de string do servidor, pelo AST:

  * **Docstring não conta**: é prosa de programador, como o comentário (que o AST nem
    enxerga).
  * **Argumento de log não conta**: `logger.warning("... — ...")` vai para o log, não
    para a tela.
  * **Documentação da API não conta**: `extend_schema(summary=..., description=...)` e
    seus `OpenApi*` são texto para quem integra, em inglês, e não chegam ao operador.
  * **Comentário de arquivo gerado não conta**: `"// AUTO-GENERATED — ..."` vira
    comentário no `.ts` gerado.
  * **A instrução que cita a regra passa**: o prompt da IA diz "sem travessão (—)".
  * **O travessão sozinho passa** ("—" como literal inteiro): é o sinal de "sem valor"
    numa célula, não pontuação de frase. A irmã das superfícies faz o mesmo.

Fora do alcance, cada um com motivo:

  * `shopman/storefront/`: a voz da loja tem frente própria.
  * `management/commands/`: a saída vai para o terminal de quem roda o comando.
  * `migrations/`: é história.
  * `shopman/shop/checks.py` e `migration_safety.py`: falam com quem sobe o servidor.
  * `shopman/shop/omotenashi/`: os defaults já têm a trava deles.
  * **Texto que mora no estado da migração** (`help_text`, `verbose_name`,
    `violation_error_message` de constraint e rótulo de
    `TextChoices` nos models): trocar exige `AlterField` em seis apps, quatro deles no
    Core, e colide numeração de migração com as frentes em voo. É WP próprio, com
    migração, como o `MovementType` do caixa. A mensagem de `ValidationError` dos
    mesmos arquivos conta normalmente.

A irmã das superfícies: `surfaces/operator-kit/tests/guardrails.noEmDash.test.ts`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]

ROOTS = ("shopman/shop", "shopman/backstage", "packages")

SKIP_PARTS = {"tests", "migrations", "build", "node_modules"}

SKIP_PREFIXES = (
    "shopman/shop/omotenashi/",
    "shopman/shop/checks.py",
    "shopman/shop/migration_safety.py",
)

LOG_METHODS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}

API_DOC_CALLS = {"extend_schema", "OpenApiParameter", "OpenApiResponse", "OpenApiExample", "inline_serializer"}


def _sources() -> list[Path]:
    files: list[Path] = []
    for root in ROOTS:
        for path in sorted((REPO / root).rglob("*.py")):
            relative = path.relative_to(REPO).as_posix()
            if SKIP_PARTS.intersection(path.parts):
                continue
            if "/management/commands/" in relative:
                continue
            if relative.startswith(SKIP_PREFIXES):
                continue
            files.append(path)
    return files


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


LOGGER_NAMES = {"logger", "log", "_logger", "_log", "LOGGER", "logging"}


def _is_logger_call(node: ast.Call) -> bool:
    """`logger.warning(...)`, não `messages.warning(...)`: este vai para a tela."""
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr in LOG_METHODS):
        return False
    target = func.value
    if isinstance(target, ast.Name):
        return target.id in LOGGER_NAMES
    return isinstance(target, ast.Attribute) and target.attr in LOGGER_NAMES


def _ignored_constants(tree: ast.AST) -> set[int]:
    """Ids dos literais que não chegam à tela: docstring, log e documentação da API."""
    ignored: set[int] = set()
    for node in ast.walk(tree):
        # Docstring e "docstring de atributo" (string solta depois de uma atribuição).
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            ignored.add(id(node.value))
        if isinstance(node, ast.Call) and (_is_logger_call(node) or _call_name(node) in API_DOC_CALLS):
            for child in ast.walk(node):
                if isinstance(child, ast.Constant):
                    ignored.add(id(child))
    return ignored


MODEL_STATE_KWARGS = {"help_text", "verbose_name", "verbose_name_plural", "violation_error_message"}

CHOICES_BASES = {"TextChoices", "IntegerChoices", "Choices"}


def _constants_under(node: ast.AST) -> set[int]:
    return {id(child) for child in ast.walk(node) if isinstance(child, ast.Constant)}


def _model_state_constants(tree: ast.AST) -> set[int]:
    """Texto que mora no estado da migração: trocar exige `AlterField` (ver docstring)."""
    ignored: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg in MODEL_STATE_KWARGS:
                    ignored |= _constants_under(keyword.value)
            name = _call_name(node)
            if (name.endswith("Field") or name == "ForeignKey") and node.args:
                ignored |= _constants_under(node.args[0])
        if isinstance(node, ast.ClassDef):
            bases = {base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", "") for base in node.bases}
            if bases & CHOICES_BASES:
                ignored |= _constants_under(node)
    return ignored


def em_dash_literals(source: str, model_file: bool = False) -> list[tuple[int, str]]:
    tree = ast.parse(source)
    ignored = _ignored_constants(tree)
    if model_file:
        ignored |= _model_state_constants(tree)
    # Pedaço de f-string não é literal inteiro: `f"{ref} — {name}"` tem o pedaço " — ".
    fstring_parts = {
        id(part) for node in ast.walk(tree) if isinstance(node, ast.JoinedStr) for part in node.values
    }
    lines = source.splitlines()
    found: set[tuple[int, str]] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if id(node) in ignored or "—" not in node.value:
            continue
        if node.value.strip() == "—" and id(node) not in fstring_parts:
            continue
        # Cabeçalho de comentário de arquivo GERADO (`// AUTO-GENERATED — ...`).
        if node.value.startswith("// "):
            continue
        # A instrução que CITA a regra ("sem travessão (—)", no prompt da IA).
        if "travess" in node.value:
            continue
        # Concatenação implícita ocupa várias linhas: aponta a linha do travessão.
        for lineno in range(node.lineno, (node.end_lineno or node.lineno) + 1):
            if "—" in lines[lineno - 1]:
                found.add((lineno, lines[lineno - 1].strip()[:120]))
    return sorted(found)


SOURCES = _sources()


def test_the_rule_reads_text_and_skips_prose() -> None:
    sample = '''
"""Docstring — prosa."""
import logging
logger = logging.getLogger(__name__)

def view():
    """Outra docstring — livre."""
    logger.warning("log — livre %s", 1)
    empty = "—"
    raise ValueError("Carrinho vazio — adicione produtos.")
'''
    assert em_dash_literals(sample) == [(10, 'raise ValueError("Carrinho vazio — adicione produtos.")')]


def test_the_rule_reads_fstring_pieces_and_django_messages() -> None:
    sample = '''
def view(request, ref, name):
    messages.error(request, "Selecione um — só um.")
    label = f"{ref} — {name}"
    prompt = "Escreva sem travessão (—)."
'''
    assert [line for line, _ in em_dash_literals(sample)] == [3, 4]


def test_the_sweep_actually_reads_something() -> None:
    assert len(SOURCES) > 500, f"a varredura achou só {len(SOURCES)} arquivos"


def is_model_file(path: Path) -> bool:
    return "models" in path.parts or path.name == "models.py"


def test_model_state_text_is_left_for_its_own_work_package() -> None:
    sample = '''
from django.db import models

class Kind(models.TextChoices):
    ESTIMATE = "estimate", _("estimativa — falta calibrar")

class Card(models.Model):
    seen = models.DateTimeField("ciente — em", help_text="Baixa — sai do board.")

    def clean(self):
        raise ValidationError("Contato precisa de e-mail — ou telefone.")
'''
    assert [line for line, _ in em_dash_literals(sample, model_file=True)] == [11]


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.relative_to(REPO).as_posix())
def test_copy_sem_travessao(path: Path) -> None:
    offenders = em_dash_literals(path.read_text(encoding="utf-8"), model_file=is_model_file(path))
    assert offenders == [], (
        f"{path.relative_to(REPO)}: copy com travessão (reescreva com ponto, vírgula, "
        f"dois-pontos ou parênteses, lendo a frase): {offenders}"
    )
