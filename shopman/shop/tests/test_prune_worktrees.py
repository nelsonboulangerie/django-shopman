"""A trava de limpeza de worktrees — sessão viva nunca é removida.

Cobre ``scripts/prune_worktrees.py``. O defeito que ela existe para impedir tem
data: em 15/10/2026, 185 worktrees foram removidas com o critério "branch já no
main e árvore limpa" e **duas sessões Claude vivas** perderam o diretório de
trabalho, junto do que é gitignored e não volta num `git worktree add` (``.env``,
``node_modules``, ``.nuxt``).

O script vive fora da árvore do pacote, então o módulo é carregado por caminho
(mesmo padrão de ``test_adr015_gate.py``).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "prune_worktrees.py"
_spec = importlib.util.spec_from_file_location("prune_worktrees", _SCRIPT)
prune = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = prune
_spec.loader.exec_module(prune)


def _worktree(**kwargs):
    defaults = {
        "path": Path("/tmp/worktree-x"),
        "branch": "claude/algo",
        "dirty": 0,
        "merged": True,
        "sessions": [],
    }
    defaults.update(kwargs)
    return prune.Worktree(**defaults)


# ---------------------------------------------------------------------------
# A regra: sessão viva vence o "git diz que pode"
# ---------------------------------------------------------------------------


def test_arvore_limpa_e_mergeada_e_segura():
    assert _worktree().safe is True


def test_sessao_viva_torna_a_worktree_intocavel():
    """O caso do incidente: git limpo, branch no main, sessão de pé."""
    session = prune.Session(
        session_id="71d2a05a-0000-0000-0000-000000000000",
        cwd="/tmp/worktree-x",
        last_activity=0.0,
        live=True,
    )
    worktree = _worktree(sessions=[session])
    assert worktree.safe is False, "worktree com sessao viva NUNCA e segura para remover"


def test_sessao_conhecida_mas_morta_ainda_protege_por_padrao():
    """Sem `--recent-hours`, qualquer sessão conhecida ali já bloqueia a remoção."""
    session = prune.Session(session_id="abc", cwd="/tmp/worktree-x", last_activity=0.0)
    assert _worktree(sessions=[session]).safe is False


def test_arvore_suja_nao_e_segura():
    assert _worktree(dirty=1).safe is False


def test_branch_fora_do_main_nao_e_segura():
    assert _worktree(merged=False).safe is False


def test_sessao_viva_vence_ate_arvore_suja_e_branch_solto():
    session = prune.Session(session_id="abc", cwd="/tmp/worktree-x", last_activity=0.0, live=True)
    assert _worktree(dirty=9, merged=False, sessions=[session]).safe is False


# ---------------------------------------------------------------------------
# Identificação da sessão viva
# ---------------------------------------------------------------------------


def test_encontra_o_id_no_processo_claude(monkeypatch):
    linha = (
        "/usr/bin/claude --output-format stream-json "
        "--resume=5bf308ed-bdde-4901-80cf-5e3d034d53fa --permission-mode=auto"
    )

    class _Result:
        stdout = linha

    monkeypatch.setattr(prune.subprocess, "run", lambda *a, **k: _Result())
    assert prune.live_session_ids() == {"5bf308ed-bdde-4901-80cf-5e3d034d53fa"}


def test_processo_sem_resume_nao_conta(monkeypatch):
    class _Result:
        stdout = "/usr/bin/claude --some-other-flag"

    monkeypatch.setattr(prune.subprocess, "run", lambda *a, **k: _Result())
    assert prune.live_session_ids() == set()


def test_le_o_cwd_do_transcript(tmp_path):
    transcript = tmp_path / "abc.jsonl"
    transcript.write_text('{"type":"summary"}\n{"cwd":"/repo/.claude/worktrees/alvo","type":"user"}\n')
    assert prune._read_cwd(transcript) == "/repo/.claude/worktrees/alvo"


def test_transcript_vazio_nao_quebra(tmp_path):
    transcript = tmp_path / "vazio.jsonl"
    transcript.write_text("")
    assert prune._read_cwd(transcript) == ""


# ---------------------------------------------------------------------------
# O casamento de caminho (o falso positivo que a primeira versão tinha)
# ---------------------------------------------------------------------------


def test_casamento_de_caminho_e_exato_e_nao_por_basename(tmp_path, monkeypatch):
    """`~/.codex/worktrees/<nome>/django-shopman` não é o checkout principal.

    A primeira versão comparava o basename (ou usava `Path.resolve()`, que
    colapsa caminho inexistente) e marcava como protegido todo worktree do Codex,
    cujo diretório final também se chama `django-shopman`. O worktree do Codex
    pode ATÉ aparecer na lista — ele é um worktree legítimo —, mas não pode ser
    protegido por uma sessão que na verdade rodava no checkout principal.
    """
    main_checkout = tmp_path / "principal" / "django-shopman"
    codex_worktree = tmp_path / "codex" / "django-shopman"
    main_checkout.mkdir(parents=True)
    codex_worktree.mkdir(parents=True)
    session = prune.Session(
        session_id="sessao-principal",
        cwd=str(main_checkout),
        last_activity=0.0,
        live=True,
    )

    def fake_git(*args, cwd=None):
        if args == ("worktree", "list", "--porcelain"):
            return (
                f"worktree {main_checkout}\nHEAD 1111111\nbranch refs/heads/main\n\n"
                f"worktree {codex_worktree}\nHEAD 2222222\nbranch refs/heads/codex/algo\n"
            )
        if args == ("rev-parse", "--show-toplevel"):
            return f"{main_checkout}\n"
        if args == ("rev-parse", "--abbrev-ref", "HEAD") and cwd == codex_worktree:
            return "codex/algo\n"
        if args == ("status", "--porcelain") and cwd == codex_worktree:
            return ""
        raise AssertionError((args, cwd))

    class _Merged:
        returncode = 0

    monkeypatch.setattr(prune, "_git", fake_git)
    monkeypatch.setattr(prune, "known_sessions", lambda: [session])
    monkeypatch.setattr(prune.subprocess, "run", lambda *a, **k: _Merged())

    worktrees, detected_main = prune.inspect(recent_hours=0)
    assert detected_main == main_checkout
    # A árvore principal fica de fora por identidade de caminho, não por nome.
    assert main_checkout not in [w.path for w in worktrees]
    assert [w.path for w in worktrees] == [codex_worktree]
    assert worktrees[0].sessions == []
    assert worktrees[0].managed is False
    assert worktrees[0].safe is False


def test_worktree_de_outro_gerenciador_nunca_e_removida_automaticamente():
    assert _worktree(managed=False).safe is False


def test_worktree_de_onde_o_script_roda_nunca_e_removida():
    assert _worktree(current=True).safe is False
