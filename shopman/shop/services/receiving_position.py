"""Onde a mercadoria que chega fica guardada — pelo papel do SKU.

O Compras recebia tudo na posição **padrão** do Stockman (``is_default``), que
no Nelson é ``massa`` — a massa em processo da Produção. A geleia recebida
contava como "em produção" e nunca ficava à venda até alguém a mover à mão.

A régua agora é o papel do SKU (``sku_records``):

- **revenda** (tem cadastro de venda com a venda ligada, e não é produzido
  aqui) → a posição que **conta para a venda**. A disponibilidade do Stockman
  só conta posição ``is_saleable`` (``availability`` / ``StockQueries``); no
  Nelson é a ``vitrine`` — a loja inteira, prateleira de mercearia incluída;
- **insumo** (só comprável) → o estoque de insumos, que não é vendável e é de
  onde a Produção consome (``deposito``). Nunca a ``massa``: ela é WIP.

Configurável por papel em ``Shop.defaults["purchase"]``:
``receive_position_resale`` e ``receive_position_material`` (``Position.ref``).
Sem configuração, vale o padrão acima; posição configurada que não existe (ou
que contradiz o papel — revenda numa posição que não vende, insumo numa que
vende) é ignorada e cai no padrão, em vez de esconder mercadoria.

Um SKU que é revenda E vai direto numa ficha, na mesma unidade, é recebido
para a venda; a produção o alcança abrindo a embalagem
(``package_opening``), que tira da loja por último.
"""

from __future__ import annotations

RESALE = "resale"
MATERIAL = "material"

#: Refs preferidos quando nada está configurado.
DEFAULT_REFS = {RESALE: "vitrine", MATERIAL: "deposito"}
CONFIG_KEYS = {RESALE: "receive_position_resale", MATERIAL: "receive_position_material"}


def role_for(sku: str) -> str:
    """``resale`` quando o SKU está à venda e não é produzido aqui; senão ``material``."""
    from shopman.shop.services.sku_records import sku_roles

    roles = sku_roles(sku)
    return RESALE if roles.sellable and not roles.produced else MATERIAL


def _configured_ref(role: str) -> str:
    from shopman.shop.models import Shop

    shop = Shop.load()
    defaults = getattr(shop, "defaults", None) if shop else None
    block = defaults.get("purchase") if isinstance(defaults, dict) else None
    value = block.get(CONFIG_KEYS[role]) if isinstance(block, dict) else None
    return str(value or "").strip()


def _fits(position, role: str) -> bool:
    if position is None or position.kind != "physical":
        return False
    return bool(position.is_saleable) is (role == RESALE)


def position_for_role(role: str):
    """A posição de recebimento do papel: configurada, senão a padrão, senão a primeira que serve."""
    from shopman.stockman import Position

    for ref in (_configured_ref(role), DEFAULT_REFS[role]):
        if ref:
            position = Position.objects.filter(ref=ref).first()
            if _fits(position, role):
                return position
    return (
        Position.objects.filter(kind="physical", is_saleable=(role == RESALE)).order_by("ref").first()
        or Position.objects.filter(is_default=True).first()
        or Position.objects.order_by("ref").first()
    )


def receiving_position(sku: str):
    """Onde a mercadoria de ``sku`` é recebida (compra, sobra de contagem, saldo de abertura)."""
    return position_for_role(role_for(sku))
