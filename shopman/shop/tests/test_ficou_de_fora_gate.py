"""A trava do "ficou de fora" (dono, 12/11/2026).

O que um PR decide NÃO fazer vira issue com o label ``ficou-de-fora``, citada na
seção ``## Ficou de fora`` do corpo. Sem isso, o adiado morava num parágrafo do
relatório no chat e dormia para sempre.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("check_ficou_de_fora", REPO_ROOT / "scripts" / "check_ficou_de_fora.py")
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def test_body_without_the_section_fails():
    errors, _ = gate.problems_in_text("## O que muda\n\nUma coisa.")
    assert errors and "não tem a seção" in errors[0]


def test_empty_section_fails_even_with_the_template_comment():
    body = "## Ficou de fora\n\n<!-- escreva nada ou liste -->\n\n## Atenção do revisor\n- x"
    errors, _ = gate.problems_in_text(body)
    assert errors and "vazia" in errors[0]


def test_nothing_left_out_is_said_in_one_word():
    for text in ("nada", "Nada.", "- nada"):
        assert gate.problems_in_text(f"## Ficou de fora\n{text}\n") == ([], [])


def test_each_item_needs_an_issue():
    body = "## Ficou de fora\n- tela de Admin (#2301)\n- tempos do B.I., em PR de seguimento\n"
    errors, refs = gate.problems_in_text(body)
    assert refs == [2301]
    assert errors == ["item sem issue: '- tempos do B.I., em PR de seguimento'"]


def test_prose_after_the_list_is_not_an_item_but_prose_alone_declares_nothing():
    footer = "\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)\n"
    assert gate.problems_in_text("## Ficou de fora\n- tela (#7)" + footer) == ([], [7])
    assert gate.problems_in_text("## Ficou de fora\nnada" + footer) == ([], [])
    errors, _ = gate.problems_in_text("## Ficou de fora\nOs tempos do B.I. ficam para depois.\n")
    assert errors and "não diz 'nada' nem lista itens" in errors[0]


def test_section_ends_at_the_next_heading_and_ignores_links():
    body = (
        "## Ficou de fora\n- tela (#10)\n- ver https://x/y#3 e &#39;\n"
        "## Atenção do revisor\n- sem issue aqui\n"
    )
    errors, refs = gate.problems_in_text(body)
    assert refs == [10]
    assert errors == ["item sem issue: '- ver https://x/y#3 e &#39;'"]


def test_referenced_issue_must_be_a_labelled_issue_not_a_pr():
    issues = {
        1: {"labels": [{"name": "ficou-de-fora"}]},
        2: {"labels": [{"name": "bug"}]},
        3: {"pull_request": {}, "labels": []},
    }

    def fetch(n):
        if n not in issues:
            raise subprocess.CalledProcessError(1, "gh")
        return issues[n]

    errors = gate.problems_in_issues("o/r", [1, 2, 3, 4, 1], fetch=fetch)
    assert errors == [
        "a issue #2 não tem o label 'ficou-de-fora' (gh issue edit 2 --add-label ficou-de-fora)",
        "#3 é um PR, não uma issue: o que ficou de fora precisa de issue própria",
        "#4 não existe",
    ]


def test_exemptions_are_bots_drafts_and_prs_older_than_the_rule():
    fresh = {"author": "pablo", "isDraft": False, "createdAt": "2026-11-13T10:00:00Z"}
    assert gate.exemption(fresh) is None
    assert gate.exemption({**fresh, "author": "dependabot[bot]"})
    assert gate.exemption({**fresh, "author": "app/dependabot"})
    assert gate.exemption({**fresh, "isDraft": True})
    assert gate.exemption({**fresh, "createdAt": "2026-11-11T10:00:00Z"})


def test_merge_group_has_nothing_to_check(monkeypatch):
    monkeypatch.setenv("GITHUB_EVENT_NAME", "merge_group")
    assert gate.main([]) == 0


def test_the_pr_template_carries_the_section_and_passes_once_filled():
    template = (REPO_ROOT / ".github" / "pull_request_template.md").read_text()
    assert gate.section(template) == "", "o molde traz a seção vazia: quem abre o PR precisa preenchê-la"
    filled = template.replace("## Ficou de fora\n", "## Ficou de fora\nnada\n", 1)
    assert gate.problems_in_text(filled) == ([], [])
