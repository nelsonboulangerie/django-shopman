"""Guardar o CPF/CNPJ da nota no cadastro, quando a pessoa DISSE que quer.

Decisão do dono (25/09/2026): na loja online, "guardar no seu cadastro?" volta
como PERGUNTA, com a matriz do PDV adaptada ao autoatendimento:

- cadastro SEM documento → a tela pergunta, desmarcada; só grava com o "sim";
- documento IGUAL ao do cadastro → só usa, nada a gravar;
- documento DIFERENTE do cadastro → vale só para esta nota; o cadastro fica
  intacto (CPF não muda na vida de ninguém; um CPF diferente é quase sempre a
  nota de outra pessoa, e trocar identidade fiscal é gesto com atrito, do PDV);
- documento que já é de OUTRA conta → vale para a nota e nunca entra no
  cadastro. Quem chama NÃO pode dizer à pessoa que o documento é de outra conta
  (a loja nunca revela isso — PR #553): a resposta para ela é a mesma de
  qualquer outro "não gravou".

Em nenhum caso a nota do pedido muda: ``fiscal.tax_id`` sai com o documento
informado. Aqui só se decide o cadastro.
"""

from __future__ import annotations

SAVED = "saved"
ALREADY_SAVED = "already_saved"
KEPT_EXISTING = "kept_existing"
OWNED_BY_OTHER = "owned_by_other"
NOT_SAVED = "not_saved"


def _digits(value) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def save_to_customer(customer_uuid, tax_id) -> str:
    """Grava ``tax_id`` como ``customer.document`` só onde há lacuna.

    Devolve um dos desfechos do módulo. Só ``SAVED`` e ``ALREADY_SAVED`` querem
    dizer "está no cadastro"; os outros querem dizer "vale só para esta nota".
    """
    from shopman.utils.documents import is_valid_tax_id

    digits = _digits(tax_id)
    if not customer_uuid or not is_valid_tax_id(digits):
        return NOT_SAVED
    from django.db import transaction
    from shopman.guestman.models import Customer
    from shopman.guestman.services import customer as customer_service

    with transaction.atomic():
        customer = Customer.objects.select_for_update().filter(uuid=str(customer_uuid), is_active=True).first()
        if customer is None:
            return NOT_SAVED
        current = _digits(customer.document)
        if current == digits:
            return ALREADY_SAVED
        if current:
            return KEPT_EXISTING
        if Customer.objects.filter(document=digits).exclude(pk=customer.pk).exists():
            return OWNED_BY_OTHER
        customer_service.update(customer.ref, document=digits)
    return SAVED


def is_in_profile(outcome: str) -> bool:
    return outcome in (SAVED, ALREADY_SAVED)
