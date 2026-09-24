#!/usr/bin/env python
"""Arquiva a versão PUBLICADA de Privacidade e Termos como cópia permanente.

Uso (depois que o deploy da versão nova subiu):

    python scripts/archive_legal_version.py                      # site de produção
    python scripts/archive_legal_version.py --origin http://127.0.0.1:3000

Lê `/privacy` e `/terms` já renderizados, confere que a página mostra a mesma
data de `LEGAL_UPDATED_AT` (em `shopman/storefront/presentation/legal.py`), e
grava `surfaces/storefront-nuxt/public/legal/<privacy|terms>/<LEGAL_VERSION>.html`.
No fim imprime a linha a colar em `LEGAL_ARCHIVE`.

Por que da página publicada, e não do `.vue`: a lista de operadores sai da
configuração do ambiente (`shopman/shop/privacy_inventory.py`), e o nome, o CNPJ
e o endereço saem do cadastro da loja. Só a página no ar mostra o que o cliente
leu. O script só LÊ o site (GET público); não escreve nada fora do repositório.

Nunca sobrescreve: se o arquivo da versão já existe, recusa. Corrigir texto
publicado é versão nova (`scripts/check_legal_archive.py` cobra isso no CI).
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import urllib.request
from html import escape
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGAL_PY = ROOT / "shopman/storefront/presentation/legal.py"
ARCHIVE_DIR = ROOT / "surfaces/storefront-nuxt/public/legal"
DEFAULT_ORIGIN = "https://www.nelsonboulangerie.com.br"

DOCUMENTS = {
    "privacy": {"path": "/privacy", "title": "Política de privacidade"},
    "terms": {"path": "/terms", "title": "Termos de uso"},
}

# Só a estrutura do documento sobrevive; classe, `data-*` e script ficam para trás.
KEPT_TAGS = {"h1", "h2", "p", "ul", "ol", "li", "strong", "em", "a", "br", "span", "section", "div"}
VOID_TAGS = {"br"}
KEPT_ATTRS = {"a": {"href"}, "section": {"id"}}


CF_EMAIL_HREF = "/cdn-cgi/l/email-protection#"


def _cloudflare_email(encoded: str) -> str:
    """Desfaz a ofuscação de e-mail que o Cloudflare aplica no HTML servido.

    O documento arquivado precisa do endereço que o cliente leu, não do
    `[email protected]` que o proxy injeta para robôs.
    """
    raw = bytes.fromhex(encoded)
    key = raw[0]
    return bytes(byte ^ key for byte in raw[1:]).decode("utf-8")


def _constant(name: str) -> str:
    match = re.search(rf'^{name} = "([^"]+)"', LEGAL_PY.read_text(encoding="utf-8"), re.M)
    if not match:
        raise SystemExit(f"ERRO: {name} não encontrado em {LEGAL_PY}")
    return match.group(1)


class _LegalExtractor(HTMLParser):
    """Recorta título, data e corpo do `<LegalDocument>` renderizado."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.depth = 0  # >0 enquanto dentro de um trecho capturado
        self.stack: list[str] = []
        self.meta_text: list[str] = []
        self._in_meta = 0
        self._in_header = False
        self._cf_email_depth = 0  # dentro do <span data-cfemail>: o texto é trocado

    def _capturing(self) -> bool:
        return self.depth > 0

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        classes = (attr.get("class") or "").split()
        if tag == "header" and attr.get("id") == "legal-top":
            self._in_header = True
        if self._in_header and tag == "h1":
            self.depth += 1
            self.out.append("<h1>")
            return
        if self._in_header and tag == "div" and "shop-muted" in classes:
            self._in_meta += 1
            return
        if self._in_meta:
            self._in_meta += 1 if tag not in VOID_TAGS else 0
            return
        if tag == "div" and "shop-legal" in classes and not self._capturing():
            self.depth += 1
            self.stack.append("__root__")
            return
        if not self._capturing():
            return
        if self._cf_email_depth:
            self._cf_email_depth += 1
            return
        if tag == "span" and attr.get("data-cfemail"):
            self.out.append(escape(_cloudflare_email(attr["data-cfemail"]), quote=False))
            self._cf_email_depth = 1
            return
        if tag not in VOID_TAGS:
            self.stack.append(tag)
        if tag not in KEPT_TAGS:
            return
        kept = KEPT_ATTRS.get(tag, set())
        cleaned = []
        for name, value in attrs:
            if name not in kept:
                continue
            if name == "href" and (value or "").startswith(CF_EMAIL_HREF):
                value = "mailto:" + _cloudflare_email(value[len(CF_EMAIL_HREF):])
            cleaned.append(f' {name}="{escape(value or "", quote=True)}"')
        if tag == "span" and "block" in classes:
            # Linha de endereço: na página é `class="block"`; aqui vira linha própria.
            cleaned.append(' class="line"')
        self.out.append(f"<{tag}{''.join(cleaned)}>")

    def handle_endtag(self, tag):
        if self._in_meta:
            self._in_meta -= 1
            return
        if self._cf_email_depth:
            self._cf_email_depth -= 1
            return
        if tag == "header":
            self._in_header = False
        if not self._capturing():
            return
        if self._in_header and tag == "h1":
            self.out.append("</h1>\n")
            self.depth -= 1
            return
        if tag in VOID_TAGS:
            return
        opened = self.stack.pop() if self.stack else None
        if opened == "__root__":
            self.depth -= 1
            return
        if tag in KEPT_TAGS:
            self.out.append(f"</{tag}>")
            if tag in {"p", "ul", "ol", "li", "h2", "section", "div"}:
                self.out.append("\n")

    def handle_startendtag(self, tag, attrs):
        if self._capturing() and tag in VOID_TAGS:
            self.out.append(f"<{tag}>")

    def handle_data(self, data):
        if self._cf_email_depth:
            return
        if self._in_meta:
            self.meta_text.append(data)
            return
        if self._in_header and self.depth and not self.stack:
            self.out.append(escape(data, quote=False))
            return
        if self._capturing():
            self.out.append(escape(data, quote=False))


def _fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "shopman-legal-archive/1"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 — URL do operador
        if response.status != 200:
            raise SystemExit(f"ERRO: {url} respondeu {response.status}")
        return response.read().decode("utf-8")


def render_archive(*, kind: str, version: str, source_url: str, page_html: str) -> tuple[str, str]:
    """Devolve (html arquivado, data lida na página)."""
    parser = _LegalExtractor()
    parser.feed(page_html)
    body = re.sub(r"\n{2,}", "\n", "".join(parser.out)).strip()
    meta = " ".join(" ".join(parser.meta_text).split())
    if "<h1>" not in body or "<section" not in body:
        raise SystemExit(f"ERRO: {source_url} não trouxe o documento legal renderizado")
    title = DOCUMENTS[kind]["title"]
    current = DOCUMENTS[kind]["path"]
    document = f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{escape(title)} — versão {version}</title>
<style>
body{{margin:0;font:16px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif;color:#2b1d1a;background:#fcf7ee}}
main{{max-width:65ch;margin:0 auto;padding:24px 16px 48px}}
.archive-note{{border:1px solid #d9cbb8;border-radius:8px;padding:12px 16px;background:#fff;font-size:14px}}
h1{{font-size:28px;line-height:1.2;margin:32px 0 4px}}
.version{{color:#6b5a52;margin:0 0 24px}}
.document{{counter-reset:section}}
section{{margin-top:28px}}
section>h2{{font-size:20px;line-height:1.3;margin:0 0 8px}}
section>h2::before{{counter-increment:section;content:counter(section) ". "}}
ul{{padding-left:20px}}
.line{{display:block}}
a{{color:inherit}}
</style>
</head>
<body>
<main>
<p class="archive-note">Cópia arquivada da versão {version}. Este texto não muda mais.
O texto que vale hoje está em <a href="{current}">{current}</a>.</p>
<article>
{body.split("</h1>", 1)[0]}</h1>
<p class="version">{escape(meta)}</p>
<div class="document">
{body.split("</h1>", 1)[1].strip()}
</div>
</article>
</main>
</body>
</html>
"""
    return document, meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--origin", default=DEFAULT_ORIGIN, help=f"site publicado (padrão {DEFAULT_ORIGIN})")
    args = parser.parse_args(argv)

    version = _constant("LEGAL_VERSION")
    updated_at = _constant("LEGAL_UPDATED_AT")
    origin = args.origin.rstrip("/")

    rendered: dict[str, str] = {}
    for kind, spec in DOCUMENTS.items():
        target = ARCHIVE_DIR / kind / f"{version}.html"
        if target.exists():
            print(f"ERRO: {target.relative_to(ROOT)} já existe — versão arquivada não se reescreve.")
            return 1
        source_url = f"{origin}{spec['path']}"
        document, meta = render_archive(
            kind=kind, version=version, source_url=source_url, page_html=_fetch(source_url)
        )
        if updated_at not in meta:
            print(
                f"ERRO: {source_url} mostra {meta!r}, e o código está em {updated_at!r}. "
                "O deploy da versão nova já subiu?"
            )
            return 1
        rendered[kind] = document

    hashes = {}
    for kind, document in rendered.items():
        target = ARCHIVE_DIR / kind / f"{version}.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        data = document.encode("utf-8")
        target.write_bytes(data)
        hashes[kind] = hashlib.sha256(data).hexdigest()
        print(f"gravado {target.relative_to(ROOT)}")

    print("\nCole em LEGAL_ARCHIVE (shopman/storefront/presentation/legal.py):")
    print(f'    "{version}": {{')
    for kind in DOCUMENTS:
        print(f'        "{kind}": "{hashes[kind]}",')
    print("    },")
    return 0


if __name__ == "__main__":
    sys.exit(main())
