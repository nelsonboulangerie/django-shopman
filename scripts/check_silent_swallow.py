#!/usr/bin/env python
"""Gate da meia-correção — o arquivo que sabe gritar e mesmo assim se cala.

O problema que este gate existe para matar não é "feature entra sem teste".
A suíte inteira roda em todo PR, com 21 checks obrigatórios e `enforce_admins`
ligado. O problema é a **distribuição do remédio**: dezenas de sessões
trabalham em paralelo, cada uma conserta o site exato que foi reportado, e o
irmão idêntico no mesmo arquivo sobrevive calado.

As provas que motivaram o gate (medidas em 05/09/2026):

- ``payment_stripe.py`` chama ``record_payment_reconciliation_failure`` no
  estorno e na disputa, mas ``authorize`` e ``capture`` são ``except
  PaymentError: pass``. Dinheiro SAINDO alerta; dinheiro ENTRANDO é silêncio.
- ``payment_efi.py`` alerta no refund e engole o authorize — devolvendo
  ``success=True``.
- ``services/notification.py`` tem, escrito no próprio arquivo, o comentário
  "Isto era logger.debug e engoliu em silêncio o defeito que chegou ao
  cliente" — e dois irmãos ainda em ``logger.debug`` no MESMO arquivo.

Daí a regra: se um arquivo **prova que sabe relatar falha** (alerta ao
operador, ``record_*_failure``, ``logger.error``, ``raise`` de erro de
domínio) e ao mesmo tempo tem um **engolimento mudo** (``except: pass``,
``except → logger.debug``, ``.catch(() => {})``, ``catch {}``), isso é uma
contradição interna. Ou o silêncio é deliberado — e então se declara — ou é a
meia-correção que vai voltar como regressão.

Escopo: **apenas os arquivos que o PR toca**. Repositório inteiro nasceria
reprovando dezenas de arquivos e seria desligado no primeiro dia; a dívida
existente mora em ``docs/reference/silencio-inventario.md``, com placar.

Escape hatch (obrigatório, explícito, com razão):

    except StaleDataError:  # silêncio-deliberado: corrida benigna, o worker relê
        pass

    await refreshCart().catch(() => null)  // silêncio-deliberado: refresh oportunista

Degradação deliberada é legítima. O que não pode é ser acidental.

Uso:

    python scripts/check_silent_swallow.py                # escopo do PR (default)
    python scripts/check_silent_swallow.py --all          # repositório inteiro
    python scripts/check_silent_swallow.py --paths a.py b.ts
    python scripts/check_silent_swallow.py --all --json   # para gerar inventário
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

# check_adr015 já resolve a base do diff nos três contextos em que a CI roda
# (pull_request, merge_group, local). Reimplementar aqui seria uma segunda
# verdade sobre "o que este PR tocou" — e uma delas envelheceria.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_adr015 import _git, resolve_diff_base  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

#: O marcador canônico é com acento. A forma sem acento também vale: teclado
#: sem cedilha é realidade, e um gate que reprova por acento ensina a errada.
DELIBERATE_MARKER_RE = re.compile(
    r"(?:sil[êe]ncio-deliberado)\s*:\s*(?P<reason>\S.*)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Escopo: o que é código de produção
# ---------------------------------------------------------------------------

PYTHON_ROOTS = ("shopman/", "packages/", "config/", "tools/")
SURFACE_ROOTS = ("surfaces/",)

#: Diretórios onde um ``except: pass`` não é promessa quebrada com ninguém:
#: teste exercita o caminho de erro de propósito, migração roda uma vez,
#: artefato de build não é fonte.
EXCLUDED_SEGMENTS = (
    "/tests/",
    "/test_",
    "/migrations/",
    "/node_modules/",
    "/build/lib/",
    "/.nuxt/",
    "/.output/",
    "/dist/",
    "/e2e/",
    "/__pycache__/",
)


def is_production_python(path: str) -> bool:
    posix = "/" + path.replace("\\", "/")
    if not posix.endswith(".py"):
        return False
    if any(segment in posix for segment in EXCLUDED_SEGMENTS):
        return False
    if posix.rsplit("/", 1)[-1].startswith("test_"):
        return False
    if posix.rsplit("/", 1)[-1].startswith("conftest"):
        return False
    return any(posix.startswith("/" + root) for root in PYTHON_ROOTS)


def is_production_surface(path: str) -> bool:
    posix = "/" + path.replace("\\", "/")
    if not (posix.endswith(".ts") or posix.endswith(".vue")):
        return False
    if any(segment in posix for segment in EXCLUDED_SEGMENTS):
        return False
    if posix.endswith(".spec.ts") or posix.endswith(".test.ts"):
        return False
    return any(posix.startswith("/" + root) for root in SURFACE_ROOTS)


def in_scope(path: str) -> bool:
    return is_production_python(path) or is_production_surface(path)


# ---------------------------------------------------------------------------
# Vocabulário do relato ALTO — "este arquivo sabe gritar"
# ---------------------------------------------------------------------------

#: Funções cujo nome já diz que a falha vira evento visível para alguém.
LOUD_FUNCTION_RE = re.compile(
    r"^(create_operator_alert|record_[a-z0-9_]*(failure|failures|error)"
    r"|capture_exception|capture_message|report_[a-z0-9_]*(failure|error))$"
)

#: Métodos de logging que alcançam produção com DJANGO_LOG_LEVEL=INFO.
LOUD_LOG_METHODS = frozenset({"error", "exception", "critical", "warning"})

#: ``raise`` só conta como relato alto quando a exceção tem cara de erro de
#: domínio. ``raise ValueError`` de validação de argumento não é o mesmo que
#: ``raise PaymentError`` — mas separar por nome próprio de exceção seria uma
#: lista que envelhece. O sufixo é a heurística estável.
DOMAIN_ERROR_SUFFIX_RE = re.compile(
    r"(Error|Exception|Denied|Failed|Failure|Invalid|Unavailable|NotFound|Conflict)$"
)

#: Builtins de encanamento da linguagem. ``raise ValueError`` conferindo
#: argumento não é o mesmo gesto que ``raise PaymentError`` — o primeiro
#: defende a função de quem a chamou, o segundo relata que o negócio falhou.
#: Contar o primeiro como "este arquivo sabe gritar" faria quase todo arquivo
#: parecer alto, e o gate viraria ruído no primeiro dia.
GENERIC_BUILTIN_ERRORS = frozenset(
    {
        "ValueError",
        "TypeError",
        "KeyError",
        "AttributeError",
        "IndexError",
        "NotImplementedError",
        "StopIteration",
        "AssertionError",
        "RuntimeError",
    }
)

LOUD_SURFACE_RE = re.compile(
    r"\bconsole\.(error|warn)\s*\(|\bthrow\s+new\s+[A-Z]|\bthrow\s+createError\s*\("
    r"|\breportError\s*\(|\bcaptureError\s*\(|\bbuildClientErrorReport\s*\("
)


@dataclass(frozen=True)
class Signal:
    """Um site — alto ou mudo — com onde ele mora e como se parece."""

    path: str
    line: int
    kind: str
    snippet: str


@dataclass(frozen=True)
class FileVerdict:
    path: str
    loud: list[Signal]
    mute: list[Signal]

    @property
    def contradictory(self) -> bool:
        return bool(self.loud) and bool(self.mute)


# ---------------------------------------------------------------------------
# Python — via AST, porque comentário e string não podem contar
# ---------------------------------------------------------------------------


def _logger_target(node: ast.expr) -> str:
    """Nome textual de um alvo de chamada, para reconhecer `logger.error`."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_logger_target(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        return _logger_target(node.func)
    return ""


def _is_logging_call(node: ast.AST, methods: frozenset[str] | set[str]) -> bool:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr not in methods:
        return False
    target = _logger_target(node.func.value).lower()
    return "log" in target


def _is_mute_body(body: list[ast.stmt]) -> str | None:
    """Classifica o corpo de um ``except``. Devolve o tipo de mudez, ou None.

    Duas formas de mudez, e só duas:

    - ``pass`` / ``...`` — nada acontece, nem uma linha em lugar nenhum.
    - só ``logger.debug(...)`` — com ``DJANGO_LOG_LEVEL`` no default ``INFO``,
      isso não emite nada em produção. É ``pass`` com aparência de cuidado,
      que é pior: parece tratado na revisão de código.

    Um ``raise``, um ``return`` que sinaliza, um ``logger.error``, uma
    chamada a serviço — qualquer coisa que não seja essas duas — não é mudez.
    """
    statements = [
        stmt for stmt in body if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str))
    ]
    if not statements:
        return "except_pass"
    if all(
        isinstance(stmt, ast.Pass)
        or (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and stmt.value.value is Ellipsis)
        for stmt in statements
    ):
        return "except_pass"
    if all(
        isinstance(stmt, ast.Pass)
        or (isinstance(stmt, ast.Expr) and _is_logging_call(stmt.value, {"debug"}))
        for stmt in statements
    ):
        return "except_debug"
    return None


def _handler_span(handler: ast.ExceptHandler) -> tuple[int, int]:
    end = handler.end_lineno or handler.lineno
    return handler.lineno, end


def _has_marker(lines: list[str], start: int, end: int) -> bool:
    """O marcador vale na linha do ``except``, dentro do corpo, ou logo acima.

    "Logo acima" existe porque a razão costuma ser longa demais para caber
    depois de dois-pontos sem estourar a linha.
    """
    first = max(1, start - 1)
    for number in range(first, end + 1):
        if number - 1 < len(lines) and DELIBERATE_MARKER_RE.search(lines[number - 1]):
            return True
    return False


def scan_python(path: str, source: str) -> FileVerdict:
    lines = source.splitlines()
    loud: list[Signal] = []
    mute: list[Signal] = []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Arquivo que não parseia reprova em outro gate; aqui vira no-op em
        # vez de exceção, para o gate nunca ser o motivo de um PR travar.
        return FileVerdict(path=path, loud=[], mute=[])

    def snippet(line: int) -> str:
        return lines[line - 1].strip() if 0 < line <= len(lines) else ""

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            if LOUD_FUNCTION_RE.match(name or ""):
                loud.append(Signal(path, node.lineno, f"call:{name}", snippet(node.lineno)))
            elif _is_logging_call(node, LOUD_LOG_METHODS):
                method = node.func.attr  # type: ignore[union-attr]
                loud.append(Signal(path, node.lineno, f"logger.{method}", snippet(node.lineno)))
        elif isinstance(node, ast.Raise) and node.exc is not None:
            raised = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            name = raised.attr if isinstance(raised, ast.Attribute) else getattr(raised, "id", "")
            if name and name not in GENERIC_BUILTIN_ERRORS and DOMAIN_ERROR_SUFFIX_RE.search(name):
                loud.append(Signal(path, node.lineno, f"raise:{name}", snippet(node.lineno)))
        elif isinstance(node, ast.ExceptHandler):
            kind = _is_mute_body(node.body)
            if kind is None:
                continue
            start, end = _handler_span(node)
            if _has_marker(lines, start, end):
                continue
            mute.append(Signal(path, start, kind, snippet(start)))

    return FileVerdict(path=path, loud=loud, mute=mute)


# ---------------------------------------------------------------------------
# TS / Vue — sem parser, então comentário e string saem antes do regex
# ---------------------------------------------------------------------------

MUTE_CATCH_ARROW_RE = re.compile(
    r"\.catch\(\s*(?:\(\s*[A-Za-z_$][\w$]*?\s*\)|\(\s*\)|[A-Za-z_$][\w$]*)\s*=>\s*"
    r"(?:\{\s*\}|null|undefined|void\s+0)\s*\)"
)
MUTE_CATCH_BLOCK_RE = re.compile(r"\bcatch\s*(?:\(\s*[^)]*\))?\s*\{\s*\}")


def _blank_out_comments_and_strings(text: str) -> str:
    """Substitui comentário e literal de string por espaço, preservando offsets.

    Preservar o offset importa: a linha do achado é calculada contando ``\\n``
    até a posição do match, e um buffer encurtado apontaria para a linha errada
    — que é pior do que não apontar.
    """
    out = list(text)
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        nxt = text[index + 1] if index + 1 < length else ""
        if char == "/" and nxt == "/":
            while index < length and text[index] != "\n":
                out[index] = " "
                index += 1
            continue
        if char == "/" and nxt == "*":
            while index < length and not (text[index] == "*" and index + 1 < length and text[index + 1] == "/"):
                if text[index] != "\n":
                    out[index] = " "
                index += 1
            for _ in range(2):
                if index < length:
                    out[index] = " "
                    index += 1
            continue
        if char in "\"'`":
            quote = char
            index += 1
            while index < length and text[index] != quote:
                if text[index] == "\\":
                    out[index] = " "
                    index += 1
                if index < length:
                    if text[index] != "\n":
                        out[index] = " "
                    index += 1
            if index < length:
                index += 1
            continue
        index += 1
    return "".join(out)


def scan_surface(path: str, source: str) -> FileVerdict:
    lines = source.splitlines()
    stripped = _blank_out_comments_and_strings(source)
    loud: list[Signal] = []
    mute: list[Signal] = []

    def line_of(offset: int) -> int:
        return stripped.count("\n", 0, offset) + 1

    def snippet(line: int) -> str:
        return lines[line - 1].strip() if 0 < line <= len(lines) else ""

    for match in LOUD_SURFACE_RE.finditer(stripped):
        line = line_of(match.start())
        loud.append(Signal(path, line, "surface_loud", snippet(line)))

    for regex, kind in ((MUTE_CATCH_ARROW_RE, "catch_arrow"), (MUTE_CATCH_BLOCK_RE, "catch_block")):
        for match in regex.finditer(stripped):
            start = line_of(match.start())
            end = line_of(match.end())
            if _has_marker(lines, start, end):
                continue
            mute.append(Signal(path, start, kind, snippet(start)))

    return FileVerdict(path=path, loud=loud, mute=mute)


# ---------------------------------------------------------------------------
# Varredura
# ---------------------------------------------------------------------------


def scan_file(repo_root: Path, path: str) -> FileVerdict | None:
    full = repo_root / path
    if not full.is_file():
        return None
    try:
        source = full.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if is_production_python(path):
        return scan_python(path, source)
    if is_production_surface(path):
        return scan_surface(path, source)
    return None


def changed_paths(repo_root: Path) -> tuple[list[str], str]:
    base, description = resolve_diff_base(repo_root)
    if base is None:
        return [], description
    diff = _git(["diff", "--name-only", "--diff-filter=ACMR", base, "HEAD"], cwd=repo_root)
    if diff.returncode != 0:
        return [], f"{description} (git diff falhou: {diff.stderr.strip()})"
    return [line for line in diff.stdout.splitlines() if line.strip()], description


def all_paths(repo_root: Path) -> list[str]:
    listed = _git(["ls-files"], cwd=repo_root)
    return [line for line in listed.stdout.splitlines() if line.strip()]


HOWTO = (
    "Como resolver — uma das duas, nunca nenhuma:\n"
    "  1. Faça o irmão gritar como o vizinho já grita neste arquivo\n"
    "     (create_operator_alert / record_*_failure / logger.error / raise).\n"
    "  2. Declare que o silêncio é de propósito, com a razão:\n"
    "         except FooError:  # silêncio-deliberado: corrida benigna, o worker relê\n"
    "             pass\n"
    "         await refresh().catch(() => null)  // silêncio-deliberado: refresh oportunista\n"
    "\n"
    "Por que este gate existe: a suíte pega o que ela cobre; ela não pega o\n"
    "IRMÃO que ficou para trás. Ver docs/reference/silencio-inventario.md."
)


def report(verdicts: list[FileVerdict], *, scope: str, stream=sys.stdout) -> int:
    offenders = [v for v in verdicts if v.contradictory]
    print(f"Gate da meia-correção — escopo: {scope}", file=stream)
    print(f"  arquivos analisados: {len(verdicts)}", file=stream)
    if not offenders:
        print("- [OK] silent_swallow: nenhum arquivo grita e se cala ao mesmo tempo.", file=stream)
        return 0

    print(
        f"- [FAIL] silent_swallow: {len(offenders)} arquivo(s) com contradição interna.",
        file=stream,
    )
    for verdict in offenders:
        loudest = verdict.loud[0]
        print(f"\n  {verdict.path}", file=stream)
        print(
            f"    alguém já soube gritar na linha {loudest.line} ({loudest.kind}): {loudest.snippet}",
            file=stream,
        )
        for signal in verdict.mute:
            print(
                f"    o irmão está calado na linha {signal.line} ({signal.kind}): {signal.snippet}",
                file=stream,
            )
    print("", file=stream)
    print(HOWTO, file=stream)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gate da meia-correção")
    parser.add_argument("--all", action="store_true", help="varre o repositório inteiro (inventário)")
    parser.add_argument("--paths", nargs="*", default=None, help="varre caminhos explícitos")
    parser.add_argument("--json", action="store_true", help="saída legível por máquina")
    args = parser.parse_args(argv)

    repo_root = REPO_ROOT
    if args.paths is not None:
        paths, scope = args.paths, "caminhos explícitos"
    elif args.all:
        paths, scope = all_paths(repo_root), "repositório inteiro"
    else:
        paths, scope = changed_paths(repo_root)
        scope = f"diff do PR ({scope})"

    verdicts = []
    for path in sorted(set(paths)):
        if not in_scope(path):
            continue
        verdict = scan_file(repo_root, path)
        if verdict is not None:
            verdicts.append(verdict)

    if args.json:
        payload = [
            {"path": v.path, "loud": [asdict(s) for s in v.loud], "mute": [asdict(s) for s in v.mute]}
            for v in verdicts
            if v.contradictory
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1 if payload else 0

    return report(verdicts, scope=scope)


if __name__ == "__main__":
    raise SystemExit(main())
