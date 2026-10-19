"""O identificador de login sai junto com o contato que ele espelha.

Desde que o porto de identidade passou a ler ``CustomerIdentifier`` (o login
OTP grava um a cada handle verificado), um identificador de telefone, WhatsApp
ou e-mail é uma CHAVE da conta, tanto quanto o ``ContactPoint``. Se o contato
sai do cadastro (troca de número, troca de e-mail, liberação no balcão,
exclusão no Admin, unificação) e o identificador fica, a chave velha continua
abrindo a conta: quem recebe da operadora o número reciclado entra por OTP.

Por isso a retirada mora aqui, no dono do identificador, e não em cada caminho
que apaga contato: o ``post_delete`` do ``ContactPoint`` roda dentro da mesma
transação do ``delete()``, então o contato e a chave saem no mesmo ato, ou
nenhum dos dois sai. Nenhum chamador precisa lembrar.

O identificador só fica se o mesmo cadastro ainda tiver outro contato da mesma
família com o mesmo valor (telefone e WhatsApp são o mesmo número): apagar só o
contato de voz de um número que segue como WhatsApp não tira a chave.
"""

from __future__ import annotations

#: Tipos de contato que são chave de login, e a família de cada um. Telefone e
#: WhatsApp dividem o número; o porto resolve um pelo outro.
_PHONE_FAMILY = ("phone", "whatsapp")
LOGIN_FAMILIES: dict[str, tuple[str, ...]] = {
    "phone": _PHONE_FAMILY,
    "whatsapp": _PHONE_FAMILY,
    "email": ("email",),
}


def retire_unbacked_login_identifiers(customer_id, contact_type: str, value: str) -> int:
    """Apaga os identificadores de login de ``value`` que nenhum contato sustenta.

    Devolve quantos saíram. Tipos fora de ``LOGIN_FAMILIES`` (Instagram,
    ManyChat, CPF, iFood) não são chave de OTP e ficam como estão.
    """
    from shopman.guestman.contrib.identifiers.models import CustomerIdentifier
    from shopman.guestman.models import ContactPoint

    family = LOGIN_FAMILIES.get(contact_type)
    if not family or not value or customer_id is None:
        return 0

    still_backed = ContactPoint.objects.filter(
        customer_id=customer_id,
        type__in=family,
        value_normalized=value,
    ).exists()
    if still_backed:
        return 0

    deleted, _detail = CustomerIdentifier.objects.filter(
        customer_id=customer_id,
        identifier_type__in=family,
        identifier_value=value,
    ).delete()
    return deleted


def _retire_identifier_with_contact(sender, instance, **kwargs) -> None:
    retire_unbacked_login_identifiers(
        instance.customer_id,
        instance.type,
        instance.value_normalized,
    )


def connect() -> None:
    from django.db.models.signals import post_delete
    from shopman.guestman.models import ContactPoint

    post_delete.connect(
        _retire_identifier_with_contact,
        sender=ContactPoint,
        dispatch_uid="guestman_identifiers_retire_with_contact",
    )
