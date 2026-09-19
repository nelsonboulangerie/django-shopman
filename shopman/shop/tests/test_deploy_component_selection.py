"""O deploy não pode deixar componente para trás em silêncio.

Dois blocos, e o primeiro é a reconstituição do defeito de 17/09/2026: três
merges na fila, o do meio CANCELADO no assento de espera da `concurrency` (0
jobs), e o run seguinte comparando com o commit morto — que fez os 11 arquivos
de `surfaces/pos-nuxt/**` sumirem da conta. A imagem do PDV não foi construída
por run nenhum, com tudo verde.

O segundo bloco cobre o confronto com o registry, que é o irmão: ele não confia
na decisão e pergunta ao que o App Platform realmente assina.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from check_registry_drift import audit, published_shas  # noqa: E402
from deploy_components import (  # noqa: E402
    build_matrix,
    component_paths,
    decide,
    load_groups,
)

GROUPS = load_groups()


# ---------------------------------------------------------------------------
# Um repositório de mentira, com a forma do de verdade
# ---------------------------------------------------------------------------


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def commit(repo: Path, paths: list[str], message: str) -> str:
    for relative in paths:
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"{message}\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    d = tmp_path / "shopman"
    d.mkdir()
    git(d, "init", "-q", "-b", "main")
    git(d, "config", "user.email", "t@example.com")
    git(d, "config", "user.name", "Teste")
    commit(d, ["README.md"], "raiz")
    return d


def nomes(**kwargs) -> list[str]:
    names, _ = decide(asked="", groups=GROUPS, **kwargs)
    return names


# ---------------------------------------------------------------------------
# O defeito de 17/09/2026
# ---------------------------------------------------------------------------


def test_o_run_do_meio_morre_e_o_pdv_some_da_conta(repo: Path):
    """Reconstituição literal: #816 verde, #815 CANCELADO, #814 verde.

    Comparar com o commit anterior (`github.event.before`) é o que produzia o
    buraco. A asserção grava o comportamento ERRADO para que a de baixo prove
    que ele acabou.
    """
    deploy_ok = commit(repo, ["shopman/a.py"], "#816 — este run publicou")
    commit(repo, ["surfaces/pos-nuxt/app/x.ts"], "#815 — run CANCELADO, 0 jobs")
    topo = commit(repo, ["packages/guestman/b.py"], "#814")

    # Como era: base = commit imediatamente anterior (o do run cancelado).
    anterior = git(repo, "rev-parse", "HEAD~1")
    assert "pos-nuxt" not in nomes(head=topo, base=anterior, per_app=True, repo=repo)

    # Como passa a ser: base = último deploy que DEU CERTO.
    agora = nomes(head=topo, base=deploy_ok, per_app=True, repo=repo)
    assert "pos-nuxt" in agora
    assert "operator-floor" in agora, "o grupo carrega o app; os dois voltam juntos"
    assert "web" in agora


def test_dois_runs_mortos_seguidos_ainda_voltam_para_a_conta(repo: Path):
    """O buraco não tem tamanho fixo. A base recua o quanto precisar."""
    deploy_ok = commit(repo, ["README.md"], "último verde")
    commit(repo, ["surfaces/kds-nuxt/x.ts"], "morto 1")
    commit(repo, ["surfaces/bi-nuxt/y.ts"], "morto 2")
    topo = commit(repo, ["shopman/z.py"], "topo")

    agora = nomes(head=topo, base=deploy_ok, per_app=True, repo=repo)
    assert {"kds-nuxt", "bi-nuxt", "web", "operator-floor", "operator-office"} <= set(
        agora
    )


def test_sem_base_constroi_tudo_e_avisa(repo: Path):
    """Errar para o lado de publicar demais. O outro lado tirou o PDV do ar."""
    topo = commit(repo, ["README.md"], "topo")
    names, avisos = decide(
        head=topo, base=None, asked="", per_app=True, repo=repo, groups=GROUPS
    )
    assert set(names) == set(component_paths(GROUPS))
    assert any("construindo TUDO" in a for a in avisos)


def test_base_que_nao_e_ancestral_constroi_tudo_e_avisa(repo: Path):
    """Histórico reescrito não pode virar 'nada mudou'."""
    topo = commit(repo, ["README.md"], "topo")
    forasteiro = "0" * 40
    names, avisos = decide(
        head=topo, base=forasteiro, asked="", per_app=True, repo=repo, groups=GROUPS
    )
    assert set(names) == set(component_paths(GROUPS))
    assert any("não é ancestral" in a for a in avisos)


# ---------------------------------------------------------------------------
# O que NÃO pode mudar: a seleção de sempre continua seletiva
# ---------------------------------------------------------------------------


def test_push_de_documentacao_nao_publica_nada(repo: Path):
    base = commit(repo, ["README.md"], "base")
    topo = commit(repo, ["docs/x.md"], "só documentação")
    assert nomes(head=topo, base=base, per_app=True, repo=repo) == []


def test_uma_surface_mexida_builda_ela_e_o_grupo_dela(repo: Path):
    base = commit(repo, ["README.md"], "base")
    topo = commit(repo, ["surfaces/marketing-nuxt/app/x.vue"], "marketing")
    assert set(nomes(head=topo, base=base, per_app=True, repo=repo)) == {
        "marketing-nuxt",
        "operator-office",
    }


def test_o_kit_mexido_arrasta_toda_surface(repo: Path):
    base = commit(repo, ["README.md"], "base")
    topo = commit(repo, ["surfaces/operator-kit/app/x.ts"], "kit")
    resultado = set(nomes(head=topo, base=base, per_app=True, repo=repo))
    assert "storefront-nuxt" in resultado
    assert "operator-floor" in resultado and "operator-office" in resultado
    assert "web" not in resultado


def test_per_app_desligado_tira_as_imagens_por_app_e_mantem_o_grupo(repo: Path):
    """A rede de rollback da ADR-030 desligada não pode derrubar o grupo."""
    base = commit(repo, ["README.md"], "base")
    topo = commit(repo, ["surfaces/pos-nuxt/x.ts"], "pdv")
    assert nomes(head=topo, base=base, per_app=False, repo=repo) == ["operator-floor"]


def test_arquivo_solto_da_raiz_e_literal_nao_prefixo(repo: Path):
    """`manage.py` é literal. `manage.py.bak` não pode arrastar a imagem web."""
    base = commit(repo, ["README.md"], "base")
    topo = commit(repo, ["manage.py.bak"], "não é o manage.py")
    assert nomes(head=topo, base=base, per_app=True, repo=repo) == []


def test_as_tags_do_matrix_sao_as_que_o_app_platform_assina(repo: Path):
    tags = {c["name"]: c["tag"] for c in build_matrix(list(component_paths(GROUPS)), GROUPS)}
    assert tags["web"] == "web"
    assert tags["pos-nuxt"] == "pos"
    assert tags["operator-floor"] == "operator-floor"


# ---------------------------------------------------------------------------
# O confronto com o registry
# ---------------------------------------------------------------------------


def tags_do_registry(por_componente: dict[str, str]) -> list[dict]:
    """Cada componente publica DUAS tags apontando para o mesmo digest."""
    saida = []
    for tag, sha in por_componente.items():
        digest = f"sha256:{tag}-{sha}"
        saida.append({"tag": tag, "manifest_digest": digest})
        saida.append({"tag": f"{tag}-{sha}", "manifest_digest": digest})
    return saida


def test_a_tag_movel_revela_o_commit_publicado():
    sha = "a" * 40
    digest, shas, motivo = published_shas(tags_do_registry({"pos": sha}), "pos")
    assert (shas, motivo) == ((sha,), "")
    assert digest == f"sha256:pos-{sha}"


def test_tag_movel_sem_irma_imutavel_nao_da_para_provar():
    tags = [{"tag": "pos", "manifest_digest": "sha256:orfao"}]
    digest, shas, motivo = published_shas(tags, "pos")
    assert shas == ()
    assert "impossível provar" in motivo
    # O digest lido sai junto do motivo: é ele que distingue "li o estado
    # anterior ao push" de "li o certo e não achei a irmã".
    assert digest == "sha256:orfao"


def test_duas_imutaveis_dividindo_um_digest_saem_as_duas():
    """18/09/2026: `210f2164c` e `15cd468f3` publicaram `sha256:97057d40…`.

    Mudança que não altera o `.output` — teste, no caso — produz imagem idêntica.
    A versão anterior devolvia a PRIMEIRA da ordem do dict e chamava aquilo de
    "o commit publicado", o que é escolha arbitrária disfarçada de medida.
    """
    novo, velho = "b" * 40, "a" * 40
    digest = "sha256:mesma-imagem"
    tags = [
        {"tag": "pos", "manifest_digest": digest},
        {"tag": f"pos-{velho}", "manifest_digest": digest},
        {"tag": f"pos-{novo}", "manifest_digest": digest},
    ]
    lido, shas, motivo = published_shas(tags, "pos")
    assert motivo == ""
    assert lido == digest
    assert set(shas) == {velho, novo}


def test_a_mesma_tag_com_dois_digests_e_leitura_AMBIGUA_nao_resposta():
    """A listagem paginada pode trazer a móvel duas vezes enquanto um push a muda.

    Colapsar num dict deixa a última escrita vencer, e nada garante que a última
    seja a mais nova — era assim que a guarda respondia o digest ANTERIOR a um
    push que o log do build provava ter acontecido. Ambiguidade tem que virar
    recusa de responder, não resposta.
    """
    sha = "a" * 40
    tags = [
        {"tag": "pos", "manifest_digest": "sha256:novo"},
        {"tag": "pos", "manifest_digest": "sha256:anterior"},
        {"tag": f"pos-{sha}", "manifest_digest": "sha256:anterior"},
    ]
    _, shas, motivo = published_shas(tags, "pos")
    assert shas == ()
    assert "ambígua" in motivo
    assert "sha256:novo" in motivo and "sha256:anterior" in motivo


def test_o_confronto_nomeia_o_componente_que_ficou_para_tras(repo: Path):
    """O caso de 17/09: `pos` servindo o commit anterior ao conserto."""
    antigo = commit(repo, ["surfaces/pos-nuxt/x.ts"], "antes do conserto")
    atual = commit(repo, ["surfaces/pos-nuxt/x.ts"], "o conserto")
    tags = tags_do_registry(
        {c["tag"]: atual for c in build_matrix(list(component_paths(GROUPS)), GROUPS)}
        | {"pos": antigo}
    )
    problemas, _ = audit(tags, ref="HEAD", per_app=True, repo=repo, groups=GROUPS)
    assert len(problemas) == 1
    assert problemas[0].startswith("pos-nuxt:")
    assert antigo[:9] in problemas[0] and atual[:9] in problemas[0]


def test_republicar_do_topo_e_valido_e_nao_pode_ficar_vermelho(repo: Path):
    """A remediação de 17/09 foi `--ref main`, do TOPO, não do commit do conserto.

    Uma imagem construída de um commit mais novo, que não mexeu naquele
    componente, carrega o mesmo código dele. Cobrar IGUALDADE entre o publicado
    e o último commit que tocou reprovaria exatamente o conserto — o gate
    gritaria contra quem apagou o incêndio.
    """
    commit(repo, ["surfaces/pos-nuxt/x.ts"], "o conserto do PDV")
    topo = commit(repo, ["docs/nada-a-ver.md"], "topo, sem tocar no PDV")
    tags = tags_do_registry(
        {c["tag"]: topo for c in build_matrix(list(component_paths(GROUPS)), GROUPS)}
    )
    assert audit(tags, ref="HEAD", per_app=True, repo=repo, groups=GROUPS)[0] == []


def test_publicado_fora_do_main_e_denunciado(repo: Path):
    """Imagem que não veio do `main` é ambiente vivo servindo o desconhecido."""
    commit(repo, ["surfaces/pos-nuxt/x.ts"], "no main")
    git(repo, "checkout", "-q", "-b", "fora")
    forasteiro = commit(repo, ["surfaces/pos-nuxt/x.ts"], "fora do main")
    git(repo, "checkout", "-q", "main")
    tags = tags_do_registry(
        {c["tag"]: forasteiro for c in build_matrix(list(component_paths(GROUPS)), GROUPS)}
    )
    problemas, _ = audit(tags, ref="HEAD", per_app=True, repo=repo, groups=GROUPS)
    assert any("não é ancestral do topo" in p for p in problemas)


def test_o_confronto_cala_quando_o_vivo_bate_com_o_main(repo: Path):
    atual = commit(repo, ["surfaces/pos-nuxt/x.ts", "shopman/a.py"], "tudo junto")
    tags = tags_do_registry(
        {c["tag"]: atual for c in build_matrix(list(component_paths(GROUPS)), GROUPS)}
    )
    assert audit(tags, ref="HEAD", per_app=True, repo=repo, groups=GROUPS)[0] == []


def test_componente_ausente_do_registry_e_denunciado(repo: Path):
    commit(repo, ["surfaces/pos-nuxt/x.ts"], "primeira publicação")
    assert any(
        "não existe no registry" in p
        for p in audit([], ref="HEAD", per_app=True, repo=repo, groups=GROUPS)[0]
    )


def test_componente_que_a_historia_nunca_tocou_nao_e_cobrado(repo: Path):
    """Cobrar tag de componente sem nenhum commit seria vermelho por nada."""
    commit(repo, ["shopman/a.py"], "só o web existe")
    problemas, _ = audit(
        tags_do_registry({"web": git(repo, "rev-parse", "HEAD")}),
        ref="HEAD",
        per_app=True,
        repo=repo,
        groups=GROUPS,
    )
    assert problemas == []


def test_per_app_desligado_nao_cobra_tag_por_app(repo: Path):
    """Desligar a rede da ADR-030 congela as tags por app DE PROPÓSITO."""
    commit(repo, ["surfaces/pos-nuxt/x.ts"], "pdv")
    atual = git(repo, "rev-parse", "HEAD")
    tags = tags_do_registry({"operator-floor": atual})
    assert audit(tags, ref="HEAD", per_app=False, repo=repo, groups=GROUPS)[0] == []
    assert audit(tags, ref="HEAD", per_app=True, repo=repo, groups=GROUPS)[0] != []


# ---------------------------------------------------------------------------
# O workflow e o script não podem divergir
# ---------------------------------------------------------------------------


def test_o_workflow_nao_tem_mais_lista_de_caminhos_propria():
    """Uma tabela só. Duas divergiriam na primeira surface nova."""
    workflow = (REPO_ROOT / ".github" / "workflows" / "deploy-images.yml").read_text(
        encoding="utf-8"
    )
    # O NOME segue citado no comentário que explica o defeito — é o USO que
    # não pode voltar.
    assert "uses: dorny/paths-filter" not in workflow
    assert "scripts/deploy_components.py" in workflow
    assert "scripts/check_registry_drift.py" in workflow


def test_o_cli_devolve_as_saidas_que_o_workflow_le(repo: Path):
    base = commit(repo, ["README.md"], "base")
    topo = commit(repo, ["surfaces/pos-nuxt/x.ts"], "pdv")
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "deploy_components.py"),
            "--head", topo, "--base", base, "--repo", str(repo), "--per-app", "true",
        ],
        capture_output=True, text=True, check=True,
    )
    saida = dict(line.split("=", 1) for line in result.stdout.strip().splitlines())
    assert saida["any"] == "true"
    assert saida["per_app"] == "true"
    assert {c["name"] for c in json.loads(saida["matrix"])["include"]} == {
        "pos-nuxt",
        "operator-floor",
    }
