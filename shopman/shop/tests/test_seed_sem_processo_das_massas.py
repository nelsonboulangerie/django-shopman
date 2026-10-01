"""As 92 etapas das 11 massas são RASCUNHO, não dado da casa (D20, dono, 01/10/2026).

``docs/reference/processo-das-massas-proposta-2026-09-05.md`` é a proposta que o
Claude escreveu em 05/09 (tempo, temperatura e nota por etapa, de literatura de
panificação, não do caderno do padeiro). O dono vai revisá-la no chat; até lá,
nada dela pode virar etapa gravada, e o campo de temperatura que nasceu no D19
(``temperature_celsius``) é justamente o lugar onde um agente apressado a
despejaria.

Três travas, do mais barato ao mais forte:

1. **Ninguém aponta para o arquivo.** Nenhum código ou dado de ``config/``,
   ``shopman/`` e ``packages/`` cita o nome dele (este teste é a exceção, por
   definição). Um carregador que lesse o markdown teria de citá-lo.
2. **O conteúdo não foi copiado.** As frases das colunas "Etapa" e "Nota" da
   proposta (só as compridas, que não colidem com nome genérico como "Forno")
   não aparecem em nenhum arquivo de código ou dado desses diretórios. É o que
   pega o copiar e colar, que a trava 1 não vê.
3. **O seed, rodado, não grava nada dela** (``assert_seed_steps_are_not_the_proposal``,
   chamada no teste que já roda o seed inteiro em
   ``backstage/tests/test_nelson_seed_operational.py``): nenhuma etapa de ficha
   ou de versão sai com temperatura, e nenhuma etapa tem nome, instrução ou
   anotação igual a uma linha da proposta.

Quando o dono validar uma massa, o número dele entra pelo caminho normal
(inventário de receitas) e a linha correspondente sai deste rascunho; se for
para o seed, este teste muda junto, no mesmo PR, dizendo que a massa foi
validada.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROPOSAL = ROOT / "docs/reference/processo-das-massas-proposta-2026-09-05.md"
SCANNED_DIRS = ("config", "shopman", "packages")
CODE_AND_DATA = {".py", ".json", ".yaml", ".yml", ".csv", ".toml", ".ts", ".vue"}
#: Frase curta ("Forno", "Modelagem", "Autólise") é vocabulário da casa e pode
#: estar no seed por direito. Só a frase comprida identifica a proposta.
MIN_DISTINCTIVE = 25


def proposal_rows() -> list[dict[str, str]]:
    """As linhas das tabelas da proposta: fase, etapa, tempo, temperatura, nota."""
    rows = []
    for line in PROPOSAL.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or line.startswith("|---") or line.startswith("| Fase |"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 5:
            continue
        rows.append(dict(zip(("phase", "step", "time", "temperature", "note"), cells, strict=True)))
    return rows


def distinctive_phrases() -> set[str]:
    phrases = set()
    for row in proposal_rows():
        for cell in (row["step"], row["note"]):
            if len(cell) >= MIN_DISTINCTIVE:
                phrases.add(cell)
    return phrases


def _scanned_files():
    for directory in SCANNED_DIRS:
        for path in (ROOT / directory).rglob("*"):
            if not path.is_file() or path.suffix not in CODE_AND_DATA:
                continue
            if "node_modules" in path.parts or ".nuxt" in path.parts or path.resolve() == Path(__file__).resolve():
                continue
            yield path


def test_the_proposal_is_marked_as_an_unvalidated_draft():
    head = PROPOSAL.read_text(encoding="utf-8")[:600]
    assert "RASCUNHO NÃO VALIDADO" in head
    assert "Não é dado da casa" in head


def test_the_proposal_still_has_its_92_steps():
    """Sem as linhas, as travas abaixo passariam por vazio."""
    assert len(proposal_rows()) == 92
    assert len(distinctive_phrases()) > 40


def test_no_code_or_data_names_the_proposal_file():
    stem = PROPOSAL.stem
    offenders = [
        str(path.relative_to(ROOT))
        for path in _scanned_files()
        if stem in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert offenders == [], f"Rascunho do D20 citado por código ou dado: {offenders}"


def test_no_code_or_data_carries_a_line_of_the_proposal():
    phrases = distinctive_phrases()
    pattern = re.compile("|".join(re.escape(phrase) for phrase in sorted(phrases, key=len, reverse=True)))
    offenders = []
    for path in _scanned_files():
        match = pattern.search(path.read_text(encoding="utf-8", errors="ignore"))
        if match:
            offenders.append(f"{path.relative_to(ROOT)}: {match.group(0)!r}")
    assert offenders == [], f"Linha do rascunho do D20 copiada para código ou dado: {offenders}"


def assert_seed_steps_are_not_the_proposal() -> None:
    """Chamada depois de ``call_command("seed")``: o banco semeado não carrega a proposta."""
    from shopman.craftsman.models import Recipe, RecipeVersion

    phrases = {row["step"] for row in proposal_rows() if len(row["step"]) >= MIN_DISTINCTIVE}
    phrases |= {row["note"] for row in proposal_rows() if row["note"]}
    steps = [
        (f"ficha {ref}", step)
        for ref, recipe_steps in Recipe.objects.values_list("ref", "steps")
        for step in recipe_steps or []
    ] + [
        (f"versão {pk}", step)
        for pk, version_steps in RecipeVersion.objects.values_list("pk", "steps")
        for step in version_steps or []
    ]
    assert steps, "o seed deveria gravar etapas (só os nomes)"
    with_temperature = [where for where, step in steps if "temperature_celsius" in step]
    assert with_temperature == [], f"Etapa semeada com temperatura (D20: não há dado validado): {with_temperature}"
    copied = [
        (where, text)
        for where, step in steps
        for text in (step.get("name", ""), step.get("instructions", ""), step.get("note", ""))
        if text and text in phrases
    ]
    assert copied == [], f"Etapa semeada com texto do rascunho do D20: {copied}"
