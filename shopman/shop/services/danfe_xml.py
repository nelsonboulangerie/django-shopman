"""Leitura do XML autorizado para o DANFE; nunca recompõe valores comerciais."""

from __future__ import annotations

import hashlib
from urllib.parse import parse_qs, urlsplit

import requests
from defusedxml import ElementTree
from django.conf import settings
from django.core.cache import cache

MAX_XML_BYTES = 2_000_000
NS = {"n": "http://www.portalfiscal.inf.br/nfe"}


class DanfeSourceError(ValueError):
    """A fonte fiscal não pôde ser lida com segurança."""


def read_authorized_xml(url: str, key: str):
    """Busca limitada no provedor já configurado, sem redirects nem credenciais na URL."""
    parsed = urlsplit(url)
    configured = urlsplit(str(getattr(settings, "SHOPMAN_FOCUS_NFE", {}).get("base_url") or ""))
    hosts = {"api.focusnfe.com.br", "homologacao.focusnfe.com.br"}
    if configured.hostname:
        hosts.add(configured.hostname)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in hosts
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise DanfeSourceError("XML autorizado indisponível no provedor configurado.")
    cache_key = "danfe-xml:" + hashlib.sha256(f"{key}:{url}".encode()).hexdigest()
    content = cache.get(cache_key)
    if content is None:
        try:
            with requests.get(url, timeout=(3, 8), stream=True, allow_redirects=False) as response:
                if response.status_code != 200:
                    raise DanfeSourceError(
                        "Não foi possível obter o XML autorizado. Tente novamente ou abra o DANFE no Focus."
                    )
                chunks, length = [], 0
                for chunk in response.iter_content(65536):
                    length += len(chunk)
                    if length > MAX_XML_BYTES:
                        raise DanfeSourceError("XML fiscal excede o limite de leitura.")
                    chunks.append(chunk)
                content = b"".join(chunks)
        except requests.RequestException as exc:
            raise DanfeSourceError("Provedor fiscal indisponível. Tente novamente ou abra o DANFE no Focus.") from exc
    root = parse_authorized_xml(content, key)
    cache.set(cache_key, content, 86400)
    return root


def value(node, path: str) -> str:
    return (node.findtext("/".join("n:" + part for part in path.split("/")), default="", namespaces=NS) or "").strip()


def parse_authorized_xml(content: bytes, key: str):
    try:
        root = ElementTree.fromstring(content)
    except Exception as exc:
        raise DanfeSourceError("XML fiscal inválido.") from exc
    info = root.find("n:NFe/n:infNFe", NS)
    protocol = root.find("n:protNFe/n:infProt", NS)
    if info is None or protocol is None or info.get("Id") != f"NFe{key}" or value(protocol, "chNFe") != key:
        raise DanfeSourceError("XML e chave de acesso não correspondem ao pedido.")
    if value(info, "ide/mod") != "65" or value(protocol, "cStat") not in {"100", "150"}:
        raise DanfeSourceError("O XML não é uma NFC-e autorizada.")
    for path in ("ide/dhEmi", "ide/tpAmb", "ide/nNF", "ide/serie", "emit/xNome", "total/ICMSTot/vNF"):
        if not value(info, path):
            raise DanfeSourceError("XML fiscal incompleto para impressão.")
    if not value(protocol, "nProt") or not value(protocol, "dhRecbto"):
        raise DanfeSourceError("Protocolo de autorização incompleto.")
    if len(key) != 44 or not key.isdigit():
        raise DanfeSourceError("Chave de acesso inválida.")
    if value(info, "ide/tpAmb") not in {"1", "2"} or value(info, "ide/tpAmb") != value(protocol, "tpAmb"):
        raise DanfeSourceError("Ambiente do protocolo difere do XML.")
    if not value(root, "NFe/infNFeSupl/qrCode") or not value(root, "NFe/infNFeSupl/urlChave"):
        raise DanfeSourceError("XML sem QR Code ou endereço de consulta.")
    qr = urlsplit(value(root, "NFe/infNFeSupl/qrCode"))
    query = urlsplit(value(root, "NFe/infNFeSupl/urlChave"))
    fields = parse_qs(qr.query).get("p", [""])[0].split("|")
    if (
        qr.scheme not in {"http", "https"}
        or query.scheme not in {"http", "https"}
        or len(fields) < 3
        or fields[0] != key
        or fields[2] != value(info, "ide/tpAmb")
    ):
        raise DanfeSourceError("QR Code não corresponde à chave e ao ambiente do XML.")
    if not (value(info, "emit/CNPJ") or value(info, "emit/CPF")) or not value(info, "emit/enderEmit/xLgr"):
        raise DanfeSourceError("Identificação do emitente incompleta.")
    for item in info.findall("n:det", NS):
        if any(not value(item, f"prod/{tag}") for tag in ("cProd", "xProd", "qCom", "uCom", "vUnCom", "vProd")):
            raise DanfeSourceError("Item fiscal incompleto.")
    if value(info, "ide/indPres") == "4" and not (value(info, "dest/xNome") and value(info, "dest/enderDest/xLgr")):
        raise DanfeSourceError("XML de entrega sem destinatário/endereço para imprimir.")
    # A emissão atual usa ICMSTot. Não omitir totais RTC ainda não homologados
    # neste compositor; a via do provedor continua disponível.
    if any(info.find(f"n:total/n:{tag}", NS) is not None for tag in ("IBSCBSTot", "ISTot", "vNFTot")):
        raise DanfeSourceError("Este XML contém totais RTC ainda não validados na bobina. Abra o DANFE no Focus.")
    return root
