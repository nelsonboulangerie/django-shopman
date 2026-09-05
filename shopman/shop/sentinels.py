"""Ausência de valor, distinta de valor vazio.

`""` e `None` já significam alguma coisa nos contratos desta casa — quase sempre
"apague este campo". Quando um endpoint precisa distinguir *"a requisição não
falou deste campo"* de *"a requisição mandou limpá-lo"*, faltava um terceiro
valor, e a falta custou dado de cliente: `PATCH /api/v1/account/profile/` lia os
quatro campos incondicionalmente, então o portão de boas-vindas — que manda só
`first_name` — chegava ao serviço com e-mail `""` e aniversário `None`, e `""`
no e-mail significa apagar o ContactPoint primário.

Mora em `shop` (e não em `storefront/intents`) por causa da regra de dependência:
`storefront` e `backstage` importam `shop`, nunca o contrário. O serviço que
consome o sentinel é `shop.services.account`.
"""

from __future__ import annotations


class UnsetType:
    """O valor que significa "esta chave não veio"."""

    __slots__ = ()

    _instance: UnsetType | None = None

    def __new__(cls) -> UnsetType:
        # Singleton: o teste é sempre `is UNSET`, então duas instâncias seriam
        # um bug silencioso — a segunda nunca casaria.
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover - diagnóstico
        return "UNSET"

    def __bool__(self) -> bool:
        return False


#: Use com `is`: ``if intent.email is not UNSET:``.
UNSET = UnsetType()
