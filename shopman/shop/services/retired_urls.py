"""Registrar que um SKU saiu do catálogo — para a loja responder 410, não 404.

Quem apaga produto chama isto **dentro da mesma transação do delete**, e antes
dele: o vínculo com a coleção é ``CASCADE``, então no instante em que o produto
some a prateleira de origem some junto. Depois do delete a informação não existe
mais em lugar nenhum, e teria de ser digitada por alguém — a fonte da verdade
deixaria de ser o catálogo.

Uso::

    from shopman.shop.services.retired_urls import record

    with transaction.atomic():
        record(sku=produto.sku, collection_refs=refs_do_produto, note="fora do cardápio 2027")
        produto.delete()
"""

from __future__ import annotations

from collections.abc import Iterable


def record(*, sku: str, collection_refs: Iterable[str] = (), note: str = "") -> None:
    """Grava (ou atualiza) a lápide de um SKU.

    Idempotente: chamar de novo com as mesmas refs não duplica nem apaga o que
    já estava lá. Ref vazia e espaço em branco caem fora.
    """
    from shopman.shop.models import RetiredProduct

    limpo = [str(ref).strip() for ref in collection_refs if str(ref).strip()]
    RetiredProduct.objects.update_or_create(
        sku=sku.strip(),
        defaults={"collection_refs": ",".join(dict.fromkeys(limpo)), "note": note.strip()},
    )
