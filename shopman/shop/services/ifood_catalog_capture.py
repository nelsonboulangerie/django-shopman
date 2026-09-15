"""Captura somente leitura, com escopo explícito e evidência integral dos GETs."""

import hashlib
import json
import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import requests
from django.conf import settings

from shopman.shop.services import ifood_auth
from shopman.shop.services.ifood_catalog_review import validate_review_snapshot

OFFICIAL_BASE = "https://merchant-api.ifood.com.br"
MAX_RESPONSE = 5 * 1024 * 1024
MAX_TOTAL = 8 * 1024 * 1024
MAX_CATEGORIES = 100
MAX_SECONDS = 180


class CaptureError(ValueError):
    """Erro seguro; não inclui corpos remotos, headers ou credenciais."""


def canonical_uuid(value):
    try:
        if not isinstance(value, str) or str(uuid.UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise CaptureError("Identificador exige UUID canônico.") from None
    return value


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CaptureError("JSON remoto contém chave repetida.")
        result[key] = value
    return result


def _constant(value):
    raise CaptureError("JSON remoto contém número não finito.")


def _now():
    return datetime.now(UTC).isoformat()


def _encode_json(value):
    """Serializa Decimal como número JSON sem arredondar nem mudar seu tipo."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Número não finito.")
        return str(value)
    if isinstance(value, dict):
        return "{" + ",".join(json.dumps(key, ensure_ascii=False) + ":" + _encode_json(item)
                              for key, item in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ",".join(_encode_json(item) for item in value) + "]"
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class _Reader:
    def __init__(self, headers):
        self.headers = headers
        self.started = time.monotonic()
        self.total = 0
        self.receipts = []

    def get(self, path):
        remaining = MAX_SECONDS - (time.monotonic() - self.started)
        if remaining <= 0:
            raise CaptureError("Prazo de captura excedido; nenhuma saída concluída.")
        response = None
        try:
            response = requests.get(OFFICIAL_BASE + path, headers=self.headers,
                                    timeout=(min(5, remaining), min(15, remaining)),
                                    allow_redirects=False, stream=True)
            if response.status_code != 200:
                raise CaptureError(f"GET de catálogo retornou HTTP {response.status_code}; captura incompleta.")
            chunks = []
            size = 0
            for chunk in response.iter_content(chunk_size=65536):
                size += len(chunk)
                self.total += len(chunk)
                if size > MAX_RESPONSE or self.total > MAX_TOTAL:
                    raise CaptureError("Resposta excedeu o limite de tamanho da captura.")
                if time.monotonic() - self.started > MAX_SECONDS:
                    raise CaptureError("Prazo de captura excedido.")
                chunks.append(chunk)
            raw = b"".join(chunks)
            text = raw.decode("utf-8")
            body = json.loads(text, parse_float=Decimal, parse_constant=_constant, object_pairs_hook=_object)
        except CaptureError:
            raise
        except (requests.RequestException, UnicodeError, ValueError, TypeError, RecursionError):
            raise CaptureError("Falha de transporte ou JSON inválido; captura incompleta.") from None
        finally:
            if response is not None:
                response.close()
        self.receipts.append({"method": "GET", "url": OFFICIAL_BASE + path, "status": 200,
                              "received_at": _now(), "sha256": hashlib.sha256(raw).hexdigest(),
                              "raw_body": text})
        return body


def _catalog_scope(catalogs, catalog_id, context):
    if not isinstance(catalogs, list):
        raise CaptureError("Lista de catálogos inválida.")
    matches = [row for row in catalogs if isinstance(row, dict) and row.get("catalogId") == catalog_id]
    if len(matches) != 1 or not isinstance(matches[0].get("context"), list) or not all(isinstance(value, str) for value in matches[0]["context"]) or context not in matches[0]["context"]:
        raise CaptureError("Catálogo/contexto não confirmado na loja selecionada.")
    return matches[0]


def capture_catalog(*, merchant_id, catalog_id, context):
    """Não consulta modelos nem executa diretivas; apenas OAuth canônico e GETs."""
    canonical_uuid(merchant_id)
    canonical_uuid(catalog_id)
    cfg = getattr(settings, "SHOPMAN_IFOOD", {})
    if not isinstance(cfg, dict) or cfg.get("merchant_id") != merchant_id:
        raise CaptureError("Merchant explícito difere da configuração ativa.")
    if cfg.get("api_base", OFFICIAL_BASE) not in (OFFICIAL_BASE, OFFICIAL_BASE + "/"):
        raise CaptureError("Captura exige a origem HTTPS oficial do iFood.")
    if not isinstance(context, str) or not context.strip() or len(context) > 100:
        raise CaptureError("Contexto inválido.")
    try:
        timeout = int(cfg.get("timeout") or 30)
        if timeout < 1 or timeout > 30:
            raise ValueError
    except (ValueError, TypeError):
        raise CaptureError("Timeout OAuth precisa estar entre 1 e 30 segundos.") from None
    try:
        # Evita reutilizar o cache global de outro cliente/base neste processo.
        token = ifood_auth.get_access_token(force=True)
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        raise CaptureError("Não foi possível autenticar a captura.") from None
    if not token:
        raise CaptureError("Não foi possível autenticar a captura.")
    reader = _Reader({"Authorization": f"Bearer {token}", "Accept": "application/json",
                      "User-Agent": ifood_auth.USER_AGENT})
    prefix = f"/catalog/v2.0/merchants/{merchant_id}"
    catalogs_path = prefix + "/catalogs"
    categories_path = prefix + f"/catalogs/{catalog_id}/categories?includeItems=true"
    catalog = _catalog_scope(reader.get(catalogs_path), catalog_id, context)
    categories = reader.get(categories_path)
    if not isinstance(categories, list) or len(categories) > MAX_CATEGORIES:
        raise CaptureError("Lista de categorias inválida ou acima do limite.")
    details = []
    seen = set()
    for category in categories:
        if not isinstance(category, dict):
            raise CaptureError("Categoria inválida.")
        ref = canonical_uuid(category.get("id"))
        if ref in seen:
            raise CaptureError("Categoria repetida.")
        seen.add(ref)
        details.append(reader.get(prefix + f"/categories/{ref}/items"))
    # Duas leituras iguais detectam mudanças observáveis, sem prometer snapshot atômico.
    for ref, detail in zip((row["id"] for row in categories), details, strict=True):
        if reader.get(prefix + f"/categories/{ref}/items") != detail:
            raise CaptureError("Itens mudaram durante a captura; refaça a leitura.")
    if reader.get(categories_path) != categories:
        raise CaptureError("Categorias mudaram durante a captura; refaça a leitura.")
    if _catalog_scope(reader.get(catalogs_path), catalog_id, context) != catalog:
        raise CaptureError("Escopo do catálogo mudou durante a captura.")
    snapshot = {"schema_version": 1, "merchant_id": merchant_id, "catalog_id": catalog_id,
                "context": context, "captured_at": _now(), "source": "api_capture",
                "categories": categories, "category_items": details,
                "provenance": {"completed": True, "rechecked": True, "atomic_snapshot": False,
                               "responses": reader.receipts}}
    try:
        validate_review_snapshot(snapshot)
        encoded = _encode_json(snapshot).encode("utf-8")
    except (ValueError, TypeError, RecursionError):
        raise CaptureError("Cobertura incompleta ou inconsistente; refaça a captura.") from None
    if len(encoded) > 20 * 1024 * 1024:
        raise CaptureError("Snapshot final excede 20 MiB.")
    return encoded
