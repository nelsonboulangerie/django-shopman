"""Gate de versões das superfícies — as quatro regras que não são óbvias.

O guard responde "todos os apps de `surfaces/` estão na mesma versão?", e três
decisões dentro dele já nasceram erradas uma vez. Estes testes existem para que
elas não voltem:

1. **A referência é a versão mais ALTA, nunca a mais comum.** A primeira versão
   do guard elegia a maioria, e contra a medição de 19/09/2026 isso mandava
   REBAIXAR `@nuxt/eslint` (1.17.0 em dois apps, 1.16.0 em sete) e `@nuxt/icon`
   (2.5.1 contra 2.2.2 em cinco) — alinhado e velho, o oposto da decisão do dono.
2. **O lock conta tanto quanto a faixa.** `@nuxt/test-utils` tinha `^4.0.3`
   declarado nos dez apps — faixa idêntica, zero alarme — e três versões
   travadas diferentes. Quem instala no CI e no deploy é o `npm ci`, que lê o
   lock.
3. **Exceção autoriza divergir, não ficar para trás.** Senão ela vira
   esconderijo para a deriva que deveria conter.
4. **Exceção sem motivo escrito o script recusa.** É o que separa decisão de
   descuido com permissão.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "check_surface_versions.py"


def build_surface(
    root: Path,
    name: str,
    declared: dict[str, str],
    locked: dict[str, str] | None = None,
) -> None:
    """Cria um `surfaces/<name>/` de mentira, com manifesto e lock."""
    app = root / "surfaces" / name
    app.mkdir(parents=True, exist_ok=True)
    (app / "package.json").write_text(
        json.dumps({"name": name, "dependencies": declared}, indent=2) + "\n"
    )
    if locked is not None:
        packages = {"": {"dependencies": declared}}
        for package, version in locked.items():
            packages[f"node_modules/{package}"] = {"version": version}
        (app / "package-lock.json").write_text(
            json.dumps({"name": name, "lockfileVersion": 3, "packages": packages})
        )


def run_gate(root: Path) -> subprocess.CompletedProcess:
    """Roda o guard contra a árvore de mentira, sem tocar o repositório."""
    stub = root / "scripts" / "check_surface_versions.py"
    stub.parent.mkdir(parents=True, exist_ok=True)
    stub.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(stub), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )


def findings_of(result: subprocess.CompletedProcess) -> list[dict]:
    return json.loads(result.stdout)["findings"]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "repo"


def test_acordo_completo_passa(root: Path) -> None:
    """Faixa e lock iguais nos dois apps: nada a reportar."""
    build_surface(root, "a-nuxt", {"vue": "^3.5.42"}, {"vue": "3.5.42"})
    build_surface(root, "b-nuxt", {"vue": "^3.5.42"}, {"vue": "3.5.42"})

    result = run_gate(root)

    assert result.returncode == 0, result.stdout + result.stderr
    assert findings_of(result) == []


def test_a_referencia_e_a_mais_alta_e_nao_a_maioria(root: Path) -> None:
    """Sete apps velhos não rebaixam os dois novos.

    Este é o caso do `@nuxt/eslint` medido em 19/09/2026. Por maioria, o guard
    mandaria os dois apps de 1.17.0 voltarem para 1.16.0.
    """
    for name in "abcdefg":
        build_surface(
            root, f"{name}-nuxt", {"@nuxt/eslint": "^1.16.0"}, {"@nuxt/eslint": "1.16.0"}
        )
    for name in "hi":
        build_surface(
            root, f"{name}-nuxt", {"@nuxt/eslint": "^1.17.0"}, {"@nuxt/eslint": "1.17.0"}
        )

    findings = findings_of(run_gate(root))

    assert {f["expected"] for f in findings} == {"^1.17.0", "1.17.0"}
    atrasados = {f["app"] for f in findings}
    assert atrasados == {f"{n}-nuxt" for n in "abcdefg"}
    assert "h-nuxt" not in atrasados and "i-nuxt" not in atrasados


def test_faixa_identica_com_lock_divergente_reprova(root: Path) -> None:
    """O defeito que um gate só-de-faixa deixaria passar inteiro."""
    build_surface(
        root, "a-nuxt", {"@nuxt/test-utils": "^4.0.3"}, {"@nuxt/test-utils": "4.0.3"}
    )
    build_surface(
        root, "b-nuxt", {"@nuxt/test-utils": "^4.0.3"}, {"@nuxt/test-utils": "4.1.0"}
    )

    findings = findings_of(run_gate(root))

    assert [f["dimension"] for f in findings] == ["lock"]
    assert findings[0]["app"] == "a-nuxt"
    assert findings[0]["found"] == "4.0.3"
    assert findings[0]["expected"] == "4.1.0"


def test_lock_identico_com_faixa_divergente_reprova(root: Path) -> None:
    """O inverso: faixa larga demais é permissão para divergir amanhã.

    É o caso do `vitest` do `purchase-nuxt` — `^4.0.14` contra `^4.1.11`, com o
    lock coincidindo em 4.1.11 só porque a última resolução subiu junto.
    """
    build_surface(root, "a-nuxt", {"vitest": "^4.0.14"}, {"vitest": "4.1.11"})
    build_surface(root, "b-nuxt", {"vitest": "^4.1.11"}, {"vitest": "4.1.11"})

    findings = findings_of(run_gate(root))

    assert [f["dimension"] for f in findings] == ["faixa"]
    assert findings[0]["found"] == "^4.0.14"
    assert findings[0]["expected"] == "^4.1.11"


def test_ordem_e_numerica_e_nao_textual(root: Path) -> None:
    """`^1.2.9` não pode ganhar de `^1.2.11` por comparação de string."""
    build_surface(root, "a-nuxt", {"pkg": "^1.2.9"}, {"pkg": "1.2.9"})
    build_surface(root, "b-nuxt", {"pkg": "^1.2.11"}, {"pkg": "1.2.11"})

    findings = findings_of(run_gate(root))

    assert {f["expected"] for f in findings} == {"^1.2.11", "1.2.11"}
    assert {f["app"] for f in findings} == {"a-nuxt"}


def test_pacote_de_um_app_so_nao_e_compartilhado(root: Path) -> None:
    """Dependência exclusiva de um app não tem com quem concordar."""
    build_surface(root, "a-nuxt", {"vue": "^3.5.42", "so-meu": "^1.0.0"}, {"vue": "3.5.42", "so-meu": "1.0.0"})
    build_surface(root, "b-nuxt", {"vue": "^3.5.42"}, {"vue": "3.5.42"})

    result = run_gate(root)

    assert result.returncode == 0
    assert findings_of(result) == []


def test_app_sem_dependencia_nao_entra_na_conta(root: Path) -> None:
    """O `operator-router` declara zero deps de propósito (ADR-030)."""
    build_surface(root, "a-nuxt", {"vue": "^3.5.42"}, {"vue": "3.5.42"})
    build_surface(root, "b-nuxt", {"vue": "^3.5.42"}, {"vue": "3.5.42"})
    build_surface(root, "operator-router", {})

    result = run_gate(root)

    assert result.returncode == 0
    assert findings_of(result) == []


def test_excecao_declarada_silencia_o_app_excetuado(root: Path) -> None:
    """O pino exato do kit não é reportado — e não dita a faixa dos irmãos."""
    build_surface(
        root, "a-nuxt", {"@iconify-json/lucide": "^1.2.132"}, {"@iconify-json/lucide": "1.2.132"}
    )
    build_surface(
        root, "b-nuxt", {"@iconify-json/lucide": "^1.2.132"}, {"@iconify-json/lucide": "1.2.132"}
    )
    build_surface(
        root, "operator-kit", {"@iconify-json/lucide": "1.2.133"}, {"@iconify-json/lucide": "1.2.133"}
    )

    result = run_gate(root)

    assert result.returncode == 0, result.stdout
    assert findings_of(result) == []


def test_excecao_nao_autoriza_ficar_para_tras(root: Path) -> None:
    """Exceção não é esconderijo: o kit atrás dos irmãos volta a ser reportado."""
    build_surface(
        root, "a-nuxt", {"@iconify-json/lucide": "^1.2.140"}, {"@iconify-json/lucide": "1.2.140"}
    )
    build_surface(
        root, "b-nuxt", {"@iconify-json/lucide": "^1.2.140"}, {"@iconify-json/lucide": "1.2.140"}
    )
    build_surface(
        root, "operator-kit", {"@iconify-json/lucide": "1.2.133"}, {"@iconify-json/lucide": "1.2.133"}
    )

    result = run_gate(root)

    assert result.returncode == 1
    findings = findings_of(result)
    assert {f["app"] for f in findings} == {"operator-kit"}
    assert all(f["lagging_exception"] for f in findings)


def test_excecao_sem_motivo_o_script_recusa(root: Path, tmp_path: Path) -> None:
    """Exceção muda é a próxima deriva com crachá."""
    build_surface(root, "a-nuxt", {"vue": "^3.5.42"}, {"vue": "3.5.42"})
    build_surface(root, "b-nuxt", {"vue": "^3.5.42"}, {"vue": "3.5.42"})

    stub = root / "scripts" / "check_surface_versions.py"
    stub.parent.mkdir(parents=True, exist_ok=True)
    source = SCRIPT.read_text(encoding="utf-8")
    marker = 'EXCEPTIONS: dict[tuple[str, str], str] = {'
    assert marker in source
    stub.write_text(
        source.replace(marker, marker + '\n    ("a-nuxt", "vue"): "",'),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(stub)], capture_output=True, text=True, check=False
    )

    assert result.returncode == 2
    assert "sem motivo escrito" in result.stderr


def test_toda_excecao_do_repositorio_tem_motivo() -> None:
    """A trava valendo para o arquivo de verdade, não só para o de mentira."""
    spec = importlib.util.spec_from_file_location("check_surface_versions", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # o `if __name__ == "__main__"` segura o main()
    exceptions = module.EXCEPTIONS

    assert exceptions, "sem exceção declarada não há o que conferir aqui"
    for key, reason in exceptions.items():
        assert reason.strip(), f"EXCEPTIONS[{key!r}] está sem motivo"
        assert len(reason) > 40, f"EXCEPTIONS[{key!r}]: motivo curto demais para valer"
