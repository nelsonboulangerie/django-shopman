"""A palavra da casa para o objeto que se segura é "dispositivo" — e "maquininha", quando
é a do cartão. "Aparelho" não existe.

O dono já tinha padronizado, mas a regra não estava escrita em lugar nenhum — nem no
glossário, nem no CLAUDE.md. Por isso derivou: 104 arquivos Python diziam a palavra
proibida, e o convite de instalação dos oito apps, escrito em 17/09/2026, nasceu errado
porque quem o escreveu leu os vizinhos.

Regra sem trava é lembrete. Esta é a trava.

## O que mudou em 18/09/2026, e por quê

A primeira versão varria só STRING — o texto que chega a alguém —, e deixava comentário
e docstring livres, "porque a regra é sobre a palavra na tela". O dono ampliou:

    "Não usamos o termo aparelho em lugar algum. Aparelho é dispositivo! Então só temos
    maquininha (a do cartão) e dispositivo (celular, tablet, pc, etc)."

Então o CANAL deixou de importar. O que mudou não foi o rigor, foi o sujeito da regra:
era a tela, virou a palavra. Com prosa dentro do alcance, a separação por AST perdeu a
função — o arquivo inteiro conta, e a varredura fica legível por linha, que é também o
que permite apontar onde está.

Isso arrasta duas exenções que existiam e não existem mais:

  * **O Storefront entra.** Ele ficava de fora por concessão do dono (05/2026, e de novo
    em 17/09/2026): superfície de cliente final, com voz própria. A frase de 18/09 é
    absoluta e alcança a loja também, inclusive o `omotenashi/copy.py`. A concessão
    anterior está NOMEADA no PR que fez esta troca, para veto em um comentário.
  * **Teste entra.** Prosa de teste é prosa.

Fica de fora só o que é história: **migração aplicada**. Reescrevê-la não muda nada no
banco e quebra o hash do grafo.

## A irmã dela

`surfaces/operator-kit/tests/guardrails.vocabulary.test.ts` faz o mesmo nos `.vue`,
`.ts`, `.mjs` e `.py` das nove superfícies — o `WP-COPY-VUE-SWEEP` da §5.5 de
`docs/reference/omotenashi-copy.md`. Enquanto ela não existia, esta regra valia em
metade do sistema, o que, como já está escrito no CLAUDE.md sobre URLs, "não é
convenção, é lembrança".

## O que a trava NÃO faz

Ela recusa; não escreve a substituição. "maquininha" não é "dispositivo": o que o
entregador leva tem nome, e o código já dizia as duas coisas na mesma linha
("Maquininha inválida. Atualize os dispositivos disponíveis."). Trocar mecanicamente
produz "aparelho (maquininha)" virado do avesso — quem escreve lê a linha e escolhe.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]

# A palavra proibida, nas duas caixas e no plural.
BANNED = "aparelh"

ROOTS = ("shopman", "packages", "config")

# O único arquivo que PRECISA escrever a palavra, porque é o que ele recusa. Allowlist
# nominal de propósito: a lista que cresce sem ninguém olhar é como a regra morre.
MAY_QUOTE = ("shopman/backstage/tests/test_vocabulario_de_tela.py",)


def _sources() -> list[Path]:
    files: list[Path] = []
    for root in ROOTS:
        for path in sorted((REPO / root).rglob("*.py")):
            if "migrations" in path.parts or "build" in path.parts:
                continue
            relative = path.relative_to(REPO).as_posix()
            if relative in MAY_QUOTE:
                continue
            files.append(path)
    return files


SOURCES = _sources()


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.relative_to(REPO).as_posix())
def test_a_palavra_da_casa_e_dispositivo(path: Path) -> None:
    offenders = [
        f"linha {lineno}: {line.strip()}"
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if BANNED in line.lower()
    ]
    assert offenders == [], (
        f"{path.relative_to(REPO)}: a palavra da casa é 'dispositivo' (ou 'maquininha', "
        f"quando é a maquininha de cartão): {offenders}"
    )


def test_the_sweep_actually_reads_something() -> None:
    """Varredura que não varre nada passa sempre; esta tem de ver o repositório."""
    assert len(SOURCES) > 200, f"a varredura achou só {len(SOURCES)} arquivos"
