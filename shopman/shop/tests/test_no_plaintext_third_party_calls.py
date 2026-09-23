"""Trava: nada de terceiro em `http://` puro no código do servidor.

Em 23/09/2026 `shopman/shop/services/devices.py` mandava o IP do titular para
`ip-api.com` em HTTP sem TLS, a cada carga da tela "Segurança e dados" da loja, só para
escrever o nome da cidade ao lado do dispositivo confiável. Duas coisas erradas de uma vez:
o dado pessoal saía para um terceiro que não constava da lista de operadores da política
de privacidade (que se declara "a lista inteira"), e saía **em claro**, legível por
qualquer um no caminho. A chamada foi removida; esta varredura é o que impede a volta.

⚠️ A regra é sobre o ESQUEMA, não sobre o dado: `http://` num endereço de terceiro é
reprovado mesmo quando quem escreveu jura que não passa dado pessoal ali. Quem revisa não
tem como auditar essa promessa linha a linha, e o custo de escrever `https://` é zero.
Trocar o esquema, porém, NÃO é licença para mandar dado de cliente para fora: TLS conserta
a escuta no meio, não a decisão de compartilhar. Terceiro novo é decisão de produto e de
política de privacidade, não de implementação.

O que a varredura deliberadamente NÃO pega, e por quê:

- **Verificação de esquema** (`url.startswith(("http://", "https://"))`). O padrão exige
  pelo menos um caractere de host depois das barras, então `"http://"` sozinho não casa.
  Isso é de propósito: ali o `http://` é o assunto da linha, não um destino.
- **Localhost e laço local** (`localhost`, `127.x`, `0.0.0.0`). O PDV falando com a
  maquininha na própria máquina e os apps Nuxt em desenvolvimento não atravessam rede
  pública. TLS ali resolveria nada e custaria certificado local.
- **Namespace de XML/SVG** (`w3.org`, `portalfiscal.inf.br`). Parece URL e não é endereço:
  é identificador fixo, escrito na especificação, que ninguém busca. Trocar para `https`
  inválida o documento.
- **A própria suíte** (`tests/`). Lá `http://testserver` e `http://example.com` são
  encenação: nada disso sobe na imagem, e é justamente contra essas URLs que se prova que
  o código de produção NÃO sai para a rede. Medido ao escrever esta trava: 17 arquivos de
  teste casariam, e nenhum arquivo de produção casa.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]

ROOTS = ("shopman", "packages", "config")

# `http://` seguido de host de verdade. Sem o `+` final, a verificação de esquema
# (`startswith(("http://", "https://"))`) cairia aqui e a trava viraria ruído.
_PLAINTEXT_URL = re.compile(r"http://([A-Za-z0-9._-]+)")

# Host local: não atravessa rede pública.
_LOCAL = ("localhost", "0.0.0.0")

# Identificador de especificação que se parece com endereço, mas não é buscado.
_NAMESPACES = ("www.w3.org", "www.portalfiscal.inf.br")

# Exceção nominal, cada uma com motivo. Esta lista só pode ENCOLHER.
EXEMPT: dict[str, tuple[str, str]] = {
    # Citação bibliográfica num docstring: a origem das receitas de pão. Ninguém busca.
    "packages/craftsman/shopman/craftsman/models/recipe.py": (
        "techno.boulangerie.free.fr",
        "referência bibliográfica em docstring, não é chamada",
    ),
    # A URL de consulta da NFC-e impressa no QR do cupom. Quem abre é o CONSUMIDOR, no
    # celular dele; o servidor nunca busca este endereço. O esquema vem da especificação
    # da SEFAZ-PR e trocá-lo por conta própria quebraria a leitura do cupom.
    "config/management/commands/seed.py": (
        "www.fazenda.pr.gov.br",
        "URL do QR da NFC-e, definida pela SEFAZ-PR e lida pelo consumidor",
    ),
}


def _sources() -> list[Path]:
    found: list[Path] = []
    for root in ROOTS:
        for path in sorted((REPO / root).rglob("*.py")):
            parts = path.parts
            if "migrations" in parts or "build" in parts or ".venv" in parts:
                continue
            if "tests" in parts:
                continue
            found.append(path)
    return found


SOURCES = _sources()


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.relative_to(REPO).as_posix())
def test_no_plaintext_third_party_url(path: Path):
    relative = path.relative_to(REPO).as_posix()
    allowed_host = EXEMPT.get(relative, ("", ""))[0]

    offenders = []
    for number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        for host in _PLAINTEXT_URL.findall(line):
            if host in _LOCAL or host.startswith("127."):
                continue
            if host in _NAMESPACES:
                continue
            if host == allowed_host:
                continue
            offenders.append(f"linha {number}: http://{host}  —  {line.strip()}")

    assert offenders == [], (
        f"{relative} fala com terceiro em HTTP puro (sem TLS).\n"
        + "\n".join(offenders)
        + "\n\nTLS não é o conserto sozinho: se há dado de cliente nessa chamada, a "
        "pergunta anterior é se esse terceiro pode receber o dado e se ele está "
        "declarado na política de privacidade. Ver o docstring desta trava."
    )


def test_the_sweep_actually_reads_something():
    """Varredura que não varre nada passa sempre."""
    assert len(SOURCES) > 1000, f"varredura leu só {len(SOURCES)} arquivos"
