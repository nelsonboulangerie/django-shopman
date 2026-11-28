"""Decide se um conteúdo PÚBLICO de Marketing pode sair com os links que tem.

Anúncio e publicação vão para fora da loja (Instagram, Facebook, Google, WhatsApp).
Lá, "/produto/KUP" não abre nada: falta o endereço do site. O rascunho continua
nascendo com o caminho relativo (a criação automática não cai por isso), mas a prévia
mostra este motivo e a aprovação e o envio recusam enquanto ele durar (MKT-20, beta
05/11). Política pura: quem chama diz se a loja tem o endereço do site configurado.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

STORE_ADDRESS_MISSING = "marketing_link_store_address_missing"

# Caminho da loja solto no texto ("Peça já: /produto/KUP"): começo de linha, espaço ou
# abertura de pontuação antes da barra. Com o endereço configurado o texto traz
# "https://loja/produto/KUP", e a barra ali vem depois de uma letra: não casa.
_RELATIVE_STORE_PATH_IN_TEXT = re.compile(
    r"(?:^|(?<=[\s(\[<\"']))/(?:produto|oferta)/[A-Za-z0-9_.:-]",
    re.MULTILINE,
)


@dataclass(frozen=True, slots=True)
class PublicLinkProblem:
    code: str
    detail: str
    field: str
    repair: str

    def field_errors(self) -> dict[str, tuple[str, ...]]:
        return {self.field: (self.repair,)}

    def as_payload(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail, "field_detail": self.repair}


def public_link_problem(
    content: object,
    platform_content: object = None,
    *,
    store_address_configured: bool,
) -> PublicLinkProblem | None:
    """O motivo de o conteúdo ainda não poder sair, ou ``None``.

    Olha o ``link`` do conteúdo e de cada variante de plataforma, e o caminho da loja
    solto no texto (``body``).
    """

    candidates: list[tuple[str, str, bool]] = []

    def collect(value: object, prefix: str) -> None:
        if not isinstance(value, Mapping):
            return
        candidates.append((f"{prefix}.link", str(value.get("link") or "").strip(), True))
        candidates.append((f"{prefix}.body", str(value.get("body") or ""), False))

    collect(content, "content")
    if isinstance(platform_content, Mapping):
        for platform, variant in sorted(platform_content.items()):
            collect(variant, f"platform_content.{platform}")

    for field, value, is_link in candidates:
        if not value:
            continue
        relative = (
            value.startswith("/") and not value.startswith("//")
            if is_link
            else bool(_RELATIVE_STORE_PATH_IN_TEXT.search(value))
        )
        if not relative:
            continue
        return PublicLinkProblem(
            code=STORE_ADDRESS_MISSING,
            detail=(
                "O link do anúncio está sem o endereço do site da loja. "
                "Fora da loja, o cliente não conseguiria abrir."
            ),
            field=field,
            repair=(
                "Use o endereço completo do produto ou da oferta, começando com https://."
                if store_address_configured
                else (
                    "Peça ao suporte técnico para configurar o endereço do site da loja. "
                    "Depois, atualize a prévia."
                )
            ),
        )
    return None
