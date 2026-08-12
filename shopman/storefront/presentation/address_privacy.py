"""O endereço salvo, em dois graus: inteiro e reduzido.

⚠️ Existe porque a redução nasceu só no checkout, e isso a tornava contornável: a tela da
conta devolvia o endereço completo, então bastava abrir `/conta` para ler a rua. Cerca que
vale num caminho e não no outro não é cerca — é decoração.

E porque checkout e conta montavam o `SavedAddressProjection` **à mão, cada um por sua
conta**: duas cópias do mesmo mapeamento, que já haviam começado a divergir (a da conta
mandava `complement`, a do checkout também, mas nada garantia que continuassem iguais). Um
construtor, dois modos.

O grau depende de quanto sabemos de quem está do outro lado (`storefront/identity.py`):

- **inteiro** — sessão em aparelho conhecido, ou login normal. Nada a esconder de quem já
  provou que é ela.
- **reduzido** — sessão que conhece o NÚMERO e não as MÃOS (chegou por link de campanha,
  e mensagem se encaminha). Desce rótulo, bairro e cidade; a rua e o número ficam no
  servidor.

A redução é grátis para a experiência porque **escolher nunca exigiu ler**: a seleção é por
`id`, e o pedido é montado no servidor a partir dele (ver a precedência em
`api/views.py`, onde o endereço salvo vence o texto que vem da tela).
"""

from __future__ import annotations

from shopman.shop.projections.types import SavedAddressProjection


def address_projection(addr, *, reduced: bool = False) -> SavedAddressProjection:
    """Um endereço salvo projetado para a tela, inteiro ou reduzido."""
    if reduced:
        return _reduced(addr)
    return _full(addr)


def _full(addr) -> SavedAddressProjection:
    return SavedAddressProjection(
        id=addr.id,
        formatted_address=addr.formatted_address,
        complement=addr.complement,
        label=addr.label,
        is_default=addr.is_default,
        label_key=addr.label_key,
        label_custom=addr.label_custom,
        route=addr.route,
        street_number=addr.street_number,
        neighborhood=addr.neighborhood,
        city=addr.city,
        state_code=addr.state_code,
        postal_code=addr.postal_code,
        latitude=addr.latitude,
        longitude=addr.longitude,
        place_id=addr.place_id,
        delivery_instructions=addr.delivery_instructions,
    )


def _reduced(addr) -> SavedAddressProjection:
    """Rótulo, bairro e cidade. Sem rua, sem número, sem coordenada.

    Os componentes estruturados (`route`, `street_number`, lat/lng, `place_id`) existem para
    reidratar o formulário de EDIÇÃO — que não é o que se faz aqui — então também não descem.
    Deixá-los seria esconder a rua no texto e entregá-la no campo ao lado.

    `complement` sai igualmente: "apto 42, fundos" é endereço tanto quanto a rua.
    """
    place = " · ".join(part for part in (addr.neighborhood, addr.city) if part)
    return SavedAddressProjection(
        id=addr.id,
        formatted_address=place or "endereço salvo",
        complement="",
        label=addr.label,
        is_default=addr.is_default,
        label_key=addr.label_key,
        label_custom=addr.label_custom,
        neighborhood=addr.neighborhood,
        city=addr.city,
    )
