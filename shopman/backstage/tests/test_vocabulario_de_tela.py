"""A palavra da casa para o objeto que se segura é "dispositivo" — e "maquininha", quando
é a do cartão. "Aparelho" não é nenhuma das duas, e não se usa.

O dono já tinha padronizado, mas a regra não estava escrita em lugar nenhum — nem no
glossário, nem no CLAUDE.md. Por isso derivou: 104 arquivos Python diziam a palavra
proibida, e o convite de instalação dos oito apps, escrito em 17/09/2026, nasceu errado
porque quem o escreveu leu os vizinhos.

Regra sem trava é lembrete. Esta é a trava.

## O que mudou em 18/09/2026, e por quê

A primeira versão varria só STRING — o texto que chega a alguém —, e deixava comentário
e docstring livres, "porque a regra é sobre a palavra na tela". O dono ampliou:

    "Maquininha é maquininha mesmo. Aparelho não é maquininha. Não usamos o termo
    aparelho. Aparelho é dispositivo! Então só temos maquininha (a do cartão) e
    dispositivo (celular, tablet, pc, etc)."

Então o CANAL deixou de importar. O que mudou não foi o rigor, foi o sujeito da regra:
era a tela, virou a palavra. Com prosa dentro do alcance, a separação por AST perdeu a
função — o arquivo inteiro conta, e a varredura fica legível por linha, que é também o
que permite apontar onde está.

⚠️ E a ampliação vale para o lado de DENTRO da casa — operador, Admin, Core. Perguntado
sobre a loja na mesma conversa, o dono manteve a concessão: *"pode manter assim só lá:
aparelho"*. Alcance largo no canal, não na superfície.

Isso arrasta **teste para dentro** — prosa de teste é prosa —, e nada mais. O que fica
de fora fica por decisão escrita, não por herança:

  * **O Storefront continua fora, e é deliberado.** A palavra do cliente final é
    "aparelho", autorizada pelo dono e reafirmada por ele em 18/09/2026 — *"pode manter
    assim só lá: aparelho"* —, na mesma conversa em que fechou a regra para as
    superfícies de operador. A loja tem voz própria: quem escreve para o cliente não
    herda o vocabulário de quem escreve para o balcão. Isso alcança
    `shopman/storefront/`, a copy da loja em `shopman/shop/omotenashi/` e o texto de FAQ
    do `apply_search_presence`, que é a mesma voz servida na landing de busca.
  * **Migração aplicada fica fora porque é história.** Reescrevê-la não muda nada no
    banco e quebra o hash do grafo.

## A irmã dela

`surfaces/operator-kit/tests/guardrails.vocabulary.test.ts` faz o mesmo nos `.vue`,
`.ts`, `.mjs` e `.py` das superfícies de operador — o `WP-COPY-VUE-SWEEP` da §5.5 de
`docs/reference/omotenashi-copy.md`. Enquanto ela não existia, esta regra valia em
metade do sistema, o que, como já está escrito no CLAUDE.md sobre URLs, "não é
convenção, é lembrança".

## O que a trava NÃO faz

Ela recusa; não escreve a substituição. "maquininha" não é "dispositivo": o que o
entregador leva tem nome, e o código já dizia as duas coisas na mesma linha
("Maquininha inválida. Atualize os dispositivos disponíveis."). Trocar mecanicamente
produz "aparelho (maquininha)" virado do avesso — quem escreve lê a linha e escolhe.

## A segunda regra deste arquivo

A casa diz "ficar pronto", nunca "sair do forno" (dono, 16/11/2026). Ela mora no fim
do arquivo, com o alcance e as exceções dela escritos lá: é regra sobre o texto que o
OPERADOR lê, não sobre a palavra em qualquer canal.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]

# A palavra proibida, nas duas caixas e no plural.
BANNED = "aparelh"

ROOTS = ("shopman", "packages", "config")

# O único arquivo que PRECISA escrever a palavra, porque é o que ele recusa. Allowlist
# nominal de propósito: a lista que cresce sem ninguém olhar é como a regra morre.
MAY_QUOTE = ("shopman/backstage/tests/test_vocabulario_de_tela.py",)

# Voz do cliente final, por decisão do dono (ver docstring). Não é dívida a pagar.
EXEMPT = (
    "shopman/storefront/",
    "shopman/shop/omotenashi/",
    "config/management/commands/apply_search_presence.py",
)


def _sources() -> list[Path]:
    files: list[Path] = []
    for root in ROOTS:
        for path in sorted((REPO / root).rglob("*.py")):
            if "migrations" in path.parts or "build" in path.parts:
                continue
            relative = path.relative_to(REPO).as_posix()
            if relative in MAY_QUOTE:
                continue
            if any(relative.startswith(prefix) for prefix in EXEMPT):
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


# ─────────────────────────────────────────────────────────────────────────────
# Segunda regra: a casa diz "ficar pronto", nunca "sair do forno" (dono, 16/11/2026).
#
# Quando a produção termina, o lote, o produto e as unidades FICAM PRONTOS. Vale para
# todo tempo do verbo ("sai", "saiu", "saíram", "saindo do forno", "acabou de sair do
# forno", "saída do forno"). O forno continua tendo nome: "Só é possível retirar do
# forno um lote aberto." segue certo, porque quem age ali é o operador.
#
# ## O sujeito desta regra é o texto de OPERADOR, e por isso o alcance é outro
#
# "Aparelho" é palavra que a casa não usa, e a regra de cima varre o arquivo inteiro.
# Esta é sobre o que o operador LÊ: o rótulo do Admin, a frase da projeção, o aviso do
# servidor. Então ela lê só os literais de string do código (sem comentário e sem
# docstring, como a irmã do kit desconta comentário), em ``shopman/backstage`` e em
# ``shopman/shop``, fora dos testes: fixture não chega a ninguém, e as que dizem a
# frase são corpo de anúncio, que é texto para o cliente.
#
# ## Exceções: a voz do cliente, declarada com o motivo
#
# O que a casa escreve PARA o cliente não é este vocabulário. Cada caminho abaixo é
# texto de cliente que mora dentro de ``shopman/shop``; nenhum é texto de operador.
OUT_OF_OVEN_ROOTS = ("shopman/backstage", "shopman/shop")

OUT_OF_OVEN_EXEMPT = {
    # A copy da loja. Tem a regra e a trava dela (#2791), na voz do cliente.
    "shopman/shop/omotenashi/": "copy da loja ao cliente",
    # Os avisos que o cliente recebe por WhatsApp, e-mail e SMS.
    "shopman/shop/notification_copy.py": "avisos ao cliente",
    # O nome e a descrição das seções vivas do cardápio, que o cliente lê na loja.
    "shopman/shop/dynamic_collections.py": "seções do cardápio da loja",
    # Não é frase da casa: é a lista do que a IA pode ter ESCRITO no corpo de um anúncio
    # e que a conferência precisa reconhecer para barrar ocasião inventada. Tirar a
    # frase daqui cegaria a conferência justamente para o texto que não se quer.
    "shopman/shop/services/marketing_ai.py": "frases que a conferência da IA reconhece no anúncio",
}

_OUT_OF_OVEN_VERB = r"(?:sai|saiu|sair|saem|sa[ií]ram|saindo|sairá|sairão|saía|saíam|saída|saídas|saído|saídos)"
OUT_OF_OVEN = re.compile(
    rf"(?<!\w){_OUT_OF_OVEN_VERB}(?:\s+\w+){{0,2}}?\s+dos?\s+fornos?(?!\w)",
    re.IGNORECASE,
)


def _string_literals(path: Path) -> list[tuple[int, str]]:
    """Os literais de string do arquivo, sem as docstrings: ``(linha, texto)``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings
    ]


def _out_of_oven_sources() -> list[Path]:
    files: list[Path] = []
    for root in OUT_OF_OVEN_ROOTS:
        for path in sorted((REPO / root).rglob("*.py")):
            if {"migrations", "tests", "build"} & set(path.parts):
                continue
            relative = path.relative_to(REPO).as_posix()
            if any(relative.startswith(prefix) for prefix in OUT_OF_OVEN_EXEMPT):
                continue
            files.append(path)
    return files


OUT_OF_OVEN_SOURCES = _out_of_oven_sources()


def test_the_out_of_oven_detector_knows_the_forms() -> None:
    for text in (
        "Produto saiu do forno",
        "Unidades que não saíram do forno",
        "O pão acabou de sair do forno!",
        "o lote sai do forno já classificado",
        "Saiu agora do forno",
        "Aviso na saída do forno",
    ):
        assert OUT_OF_OVEN.search(text), text
    for text in (
        "Só é possível retirar do forno um lote aberto.",
        "Esta tentativa de forno já pertence a outro lote.",
        "Saiu para entrega",
        "Produto ficou pronto",
        "Reserva na fila de espera. O preparo abre quando o lote ficar pronto.",
    ):
        assert not OUT_OF_OVEN.search(text), text


def test_nenhum_texto_de_operador_diz_sair_do_forno() -> None:
    offenders = [
        f"{path.relative_to(REPO).as_posix()}:{lineno}: {' '.join(text.split())[:120]}"
        for path in OUT_OF_OVEN_SOURCES
        for lineno, text in _string_literals(path)
        if OUT_OF_OVEN.search(text)
    ]
    assert offenders == [], (
        "A casa diz 'ficar pronto', nunca 'sair do forno' (dono, 16/11/2026). O verbo concorda "
        "com o que ficou pronto: 'Produto ficou pronto', 'Unidades que ficaram prontas'. Se o "
        "texto é para o CLIENTE, ele não é texto de operador: declare o caminho em "
        f"OUT_OF_OVEN_EXEMPT, com o motivo. Onde: {offenders}"
    )


def test_the_out_of_oven_sweep_reads_the_operator_side() -> None:
    """A varredura enxerga os dois lugares que diziam a frase, e as exceções existem."""
    seen = {path.relative_to(REPO).as_posix() for path in OUT_OF_OVEN_SOURCES}
    assert "shopman/shop/services/marketing_platform_configuration.py" in seen
    assert "shopman/shop/services/operator_orders.py" in seen
    assert "shopman/backstage/projections/production.py" in seen
    assert len(OUT_OF_OVEN_SOURCES) > 300, f"a varredura achou só {len(OUT_OF_OVEN_SOURCES)} arquivos"
    for prefix in OUT_OF_OVEN_EXEMPT:
        assert (REPO / prefix).exists(), f"exceção para um caminho que não existe mais: {prefix}"
