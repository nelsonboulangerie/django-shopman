"""Converte o contato gravado no ``Supplier.metadata`` em ``SupplierContact``.

Antes de existir uma pessoa no modelo, o jeito de dizer "o pedido vai para o
Michael" era gravar ``order_contact``/``order_phone`` no ``metadata`` — o escape
hatch que ``_supplier_dispatch_route`` lê até hoje. Quem usou aquilo não deve
precisar redigitar nada, nem ficar com o dado em dois lugares: a rota nova
prefere o ``SupplierContact``, então a chave no metadata viraria uma cópia
sombreada, envelhecendo em silêncio até alguém editar a errada.

Converte só quem tem **nome**. ``order_contact`` também aceitava um e-mail solto,
e um contato sem nome contradiz a razão de o modelo existir: transformá-lo numa
pessoa anônima seria inventar gente. Esses ficam onde estão, e a rota continua
lendo o metadata para eles.
"""

from django.db import migrations

# As chaves que esta migração consome. `order_channel` NÃO está aqui: canal
# preferido é preferência de rota, não pessoa, e continua morando no metadata.
_NAME_KEYS = ("order_contact", "orderContact", "contact")
_EMAIL_KEYS = ("order_email", "orderEmail")
_PHONE_KEYS = ("order_phone", "orderPhone", "whatsapp")


def _first(purchase: dict, keys) -> tuple[str, str]:
    """O primeiro valor preenchido e a chave de onde ele veio."""
    for key in keys:
        value = purchase.get(key)
        if value not in (None, ""):
            return str(value).strip(), key
    return "", ""


def contacts_from_metadata(apps, schema_editor):
    from shopman.utils.phone import normalize_phone

    Supplier = apps.get_model("buyman", "Supplier")
    SupplierContact = apps.get_model("buyman", "SupplierContact")

    for supplier in Supplier.objects.exclude(metadata={}):
        metadata = dict(supplier.metadata or {})
        purchase = dict(metadata.get("purchase") or {})
        if not purchase:
            continue

        name, name_key = _first(purchase, _NAME_KEYS)
        # Um e-mail solto no lugar do nome não é uma pessoa: deixa como está.
        if not name or "@" in name:
            continue

        email, email_key = _first(purchase, _EMAIL_KEYS)
        phone, phone_key = _first(purchase, _PHONE_KEYS)
        if not (email or phone):
            continue  # a CheckConstraint recusaria, e com razão

        if not SupplierContact.objects.filter(supplier=supplier, role="sales").exists():
            SupplierContact.objects.create(
                supplier=supplier,
                name=name,
                role="sales",
                email=email.lower(),
                phone=normalize_phone(phone) if phone else "",
                is_primary=True,
                is_active=True,
            )

        for key in (name_key, email_key, phone_key):
            purchase.pop(key, None)
        metadata["purchase"] = purchase
        supplier.metadata = metadata
        supplier.save(update_fields=["metadata"])


def metadata_from_contacts(apps, schema_editor):
    """Devolve o comercial principal ao metadata — o caminho de volta existe."""
    SupplierContact = apps.get_model("buyman", "SupplierContact")

    for contact in SupplierContact.objects.filter(role="sales", is_primary=True):
        supplier = contact.supplier
        metadata = dict(supplier.metadata or {})
        purchase = dict(metadata.get("purchase") or {})
        purchase["order_contact"] = contact.name
        if contact.email:
            purchase["order_email"] = contact.email
        if contact.phone:
            purchase["order_phone"] = contact.phone
        metadata["purchase"] = purchase
        supplier.metadata = metadata
        supplier.save(update_fields=["metadata"])
    SupplierContact.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("buyman", "0008_supplier_trade_name_alter_supplier_email_and_more"),
    ]

    operations = [
        migrations.RunPython(contacts_from_metadata, metadata_from_contacts),
    ]
