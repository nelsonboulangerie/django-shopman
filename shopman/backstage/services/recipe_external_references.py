"""Referências externas da receita: livros, vídeos e artigos de onde ela veio (D6).

Moram em ``RecipeEntry.meta["external_references"]`` (``docs/reference/
data-schemas.md``), uma lista de ``{title, url?, note?}``. São da RECEITA, não
da versão: o livro de onde a baguete veio continua sendo a fonte quando a
hidratação muda na v3, e a versão publicada é imutável (#1308), então uma
referência acrescentada depois da publicação não teria onde morar nela.

A forma é validada aqui, na porta (o Core guarda o JSON sem interpretar):
lista de objetos, título obrigatório, link só ``http``/``https``, tamanhos
máximos. Anexo de arquivo (foto, PDF) NÃO mora aqui: é outra frente, com
armazenamento de objeto.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from shopman.backstage.services.exceptions import RecipeBookServiceError

META_KEY = "external_references"
FIELD = "external_references"

MAX_REFERENCES = 30
MAX_TITLE = 200
MAX_URL = 500
MAX_NOTE = 500

_ALLOWED_KEYS = frozenset({"title", "url", "note"})


def _fail(detail: str, *, index: int | None = None, key: str = "") -> RecipeBookServiceError:
    field = FIELD if index is None else f"{FIELD}[{index}]" + (f".{key}" if key else "")
    return RecipeBookServiceError(detail, field=field, code="INVALID_PAYLOAD")


def is_web_url(url: str) -> bool:
    """Link aceitável: ``http`` ou ``https``, com host. Nada de ``javascript:``, ``data:``, ``file:``."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(parts.netloc) and not any(ch.isspace() for ch in url)


def _text(raw: Any, *, index: int, key: str, limit: int, label: str) -> str:
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raise _fail(f"{label} precisa ser texto.", index=index, key=key)
    value = raw.strip()
    if len(value) > limit:
        raise _fail(f"{label} passa de {limit} caracteres.", index=index, key=key)
    return value


def validate(value: Any) -> list[dict]:
    """O corpo do ``PATCH`` (a lista INTEIRA) na forma gravada. Recusa apontando o item.

    Vazio e ``None`` limpam a lista. Chave vazia sai do objeto gravado: ``url`` e
    ``note`` só aparecem quando foram escritos.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        raise _fail("As referências precisam ser uma lista.")
    if len(value) > MAX_REFERENCES:
        raise _fail(f"No máximo {MAX_REFERENCES} referências por receita.")
    cleaned: list[dict] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise _fail("Cada referência precisa ser um objeto com título.", index=index)
        unknown = sorted(set(item) - _ALLOWED_KEYS)
        if unknown:
            raise _fail(f"Campo desconhecido na referência: {', '.join(unknown)}.", index=index, key=unknown[0])
        title = _text(item.get("title"), index=index, key="title", limit=MAX_TITLE, label="O título")
        if not title:
            raise _fail("Dê um título à referência (o livro, o vídeo ou o artigo).", index=index, key="title")
        url = _text(item.get("url"), index=index, key="url", limit=MAX_URL, label="O link")
        if url and not is_web_url(url):
            raise _fail("O link precisa começar com http:// ou https://.", index=index, key="url")
        note = _text(item.get("note"), index=index, key="note", limit=MAX_NOTE, label="A nota")
        reference = {"title": title}
        if url:
            reference["url"] = url
        if note:
            reference["note"] = note
        cleaned.append(reference)
    return cleaned


def read(meta: Any) -> list[dict]:
    """O que está gravado, para a leitura. Tolerante: item fora da forma é pulado, link inseguro sai.

    O Admin edita ``meta`` à mão; a tela nunca recebe um link que a porta
    recusaria (``javascript:`` num ``href`` é o perigo concreto).
    """
    raw = meta.get(META_KEY) if isinstance(meta, dict) else None
    if not isinstance(raw, list):
        return []
    references: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        url = str(item.get("url") or "").strip()
        references.append({
            "title": title,
            "url": url if url and is_web_url(url) else "",
            "note": str(item.get("note") or "").strip(),
        })
    return references
