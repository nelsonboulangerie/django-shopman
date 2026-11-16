"""A hora que alguém LÊ é "12h45". O formato "12:45" não se escreve mais na tela.

Decisão do dono (16/11/2026), para a suíte inteira, operador e cliente: "12h45",
"9h05", "9h". A regra está em ``docs/reference/suite-vocabulary.md``, seção "Hora".
Até essa data o código tinha as duas formas ao mesmo tempo ("Aberto até 19h" na
loja e "aceite até 18:05" no Gestor), porque cada tela formatava a própria hora.

Regra sem trava é lembrete. Esta é a trava da metade do servidor: reprova o
FORMATADOR antigo, não a frase. Hora lida por gente passa por
``shopman.utils.formatting.format_clock`` (ou ``format_local`` com a marca
``{clock}``), e mais nada formata hora.

## O que fica de fora, e como se declara

* **Formato de máquina.** O ``"HH:MM"`` que se grava e trafega (``opens_at``,
  ``ready_from``, ref de horário), ISO e payload de terceiro. Quem lê é código.
  Cada linha leva o marcador ``# hora-ok: <motivo>``; a trava exige o motivo.
* **Campo de formulário.** ``input_formats=`` e ``Widget(format=`` do Admin são a
  forma que o campo de hora aceita, como o ``<input type="time">`` do browser.
  A trava conhece as duas formas e não pede marcador.
* **Carimbo com segundos** (``%H:%M:%S``): auditoria, DANFE, log. Não é hora de
  relance, é registro, e o DANFE tem leiaute legal.
* **Migração aplicada** é história, e **teste** não é tela.

## A irmã dela

``surfaces/operator-kit/tests/guardrails.clock.test.ts`` faz o mesmo nos apps de
operador, e ``surfaces/storefront-nuxt/tests/guardrails.clock.test.ts`` na loja.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]

ROOTS = ("shopman", "packages", "config")
SUFFIXES = (".py", ".html", ".txt")

#: O formatador de hora da casa: o único arquivo que monta a hora à mão.
MAY_FORMAT = ("packages/utils/shopman/utils/formatting.py",)

#: Cada forma antiga de escrever a hora, com o nome que aparece na reprovação.
OLD_FORMS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("strftime com hora:minuto", re.compile(r"(?<!T)%H:%M(?!:%S)")),
    ("strftime com 'h' montado à mão", re.compile(r"%-?Hh")),
    ("formato de data do Django com H:i", re.compile(r"""["'][^"'\n]*\bH:i\b""")),
    ("filtro |time do template", re.compile(r"\{\{[^}\n]*\|\s*time\b")),
    ("hora montada à mão com dois-pontos", re.compile(r":02d\}:\{")),
    ("hora montada à mão com 'h'", re.compile(r"\.hour\}h")),
)

#: Campo de formulário: a forma que o campo aceita, não o que a tela mostra.
FORM_FIELD = re.compile(r"input_formats\s*=|Widget\(format=")

#: A exceção declarada na linha. O motivo é obrigatório.
MARKER = re.compile(r"hora-ok:\s*\S")


def _sources() -> list[Path]:
    files: list[Path] = []
    for root in ROOTS:
        for path in sorted((REPO / root).rglob("*")):
            if path.suffix not in SUFFIXES or not path.is_file():
                continue
            if {"migrations", "build", "tests", "node_modules"} & set(path.parts):
                continue
            if path.relative_to(REPO).as_posix() in MAY_FORMAT:
                continue
            files.append(path)
    return files


SOURCES = _sources()


def offenders_in(text: str) -> list[str]:
    found: list[str] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if FORM_FIELD.search(line) or MARKER.search(line):
            continue
        for name, pattern in OLD_FORMS:
            if pattern.search(line):
                found.append(f"linha {lineno} ({name}): {line.strip()}")
                break
    return found


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.relative_to(REPO).as_posix())
def test_hora_lida_por_gente_passa_pelo_formatador_da_casa(path: Path) -> None:
    offenders = offenders_in(path.read_text(encoding="utf-8"))
    assert offenders == [], (
        f"{path.relative_to(REPO)}: a hora na tela é '12h45'. Use "
        "shopman.utils.formatting.format_clock (ou format_local com '{clock}'). "
        "Se é formato de máquina, declare na linha: '# hora-ok: <motivo>'. "
        f"Achado: {offenders}"
    )


def test_a_trava_reprova_cada_forma_antiga() -> None:
    """Trava que não reprova nada passa sempre; esta tem de morder."""
    old = (
        'when = local.strftime("%H:%M")',
        'label = f"até {deadline:%d/%m %H:%M}"',
        'return local.strftime("%d/%m às %Hh%M")',
        'date_format(value, "d/m H:i")',
        '{{ change.history_date|date:"d/m H:i" }}',
        "{{ order.created_at|time }}",
        'return f"{hour:02d}:{minute:02d}"',
        'return f"{local.hour}h{local.minute:02d}"',
    )
    for line in old:
        assert offenders_in(line), f"a trava deixou passar: {line}"


def test_a_trava_conhece_o_que_fica_de_fora() -> None:
    allowed = (
        'input_formats=["%H:%M"],',
        'widget=UnfoldAdminTimeWidget(format="%H:%M"),',
        'stamp = value.strftime("%d/%m/%Y %H:%M:%S")',
        'return value.astimezone(zone).strftime("%Y-%m-%dT%H:%M")',
        'return value.strftime("%H:%M")  # hora-ok: contrato HH:MM, lido por código',
        'return format_local(dt, "%d/%m às {clock}")',
    )
    for line in allowed:
        assert offenders_in(line) == [], f"a trava reprovou o que fica de fora: {line}"
    # Marcador sem motivo não é exceção declarada.
    assert offenders_in('return value.strftime("%H:%M")  # hora-ok:')


def test_the_sweep_actually_reads_something() -> None:
    """Varredura que não varre nada passa sempre; esta tem de ver o repositório."""
    assert len(SOURCES) > 500, f"a varredura achou só {len(SOURCES)} arquivos"
