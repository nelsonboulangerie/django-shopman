"""Boundary to backstage physical custody, following the host adapter contract."""


def reference_prefix():
    from shopman.backstage.services.delivery_devices import PREFIX

    return PREFIX


def needs_card_machine(order):
    from shopman.backstage.services.delivery_devices import needs_card_machine as implementation

    return implementation(order)


def has_available(order):
    from shopman.backstage.services.delivery_devices import has_available as implementation

    return implementation(order)


def allocate(order, equipment, *, allowed):
    from shopman.backstage.services.delivery_devices import allocate as implementation

    return implementation(order, equipment, allowed=allowed)


def release(order):
    from shopman.backstage.services.delivery_devices import release as implementation

    return implementation(order)
