"""Nome de pessoa: a regra única que divide um nome inteiro em nome e sobrenome."""


def split_full_name(full_name: str) -> tuple[str, str]:
    """Divide ``full_name`` em ``(nome, sobrenome)`` pelo primeiro espaço.

    O primeiro token vira o nome; o resto, inteiro, vira o sobrenome.
    ``"Pablo Valentini"`` → ``("Pablo", "Valentini")``; ``"Pablo"`` → ``("Pablo", "")``.

    É a regra da casa para todo nome que chega numa caixa só (pedido do ManyChat,
    iFood, PDV, login por WhatsApp). Ela erra, de propósito, do lado do sobrenome:
    ``"Ana Maria Silva"`` → ``("Ana", "Maria Silva")``. Em português não há regra
    sintática que acerte prenome composto e sobrenome composto ao mesmo tempo, e o
    sobrenome nunca é usado para tratar ninguém (a saudação lê o nome); errar do
    outro lado poria sobrenome no "Oi, ..." que sai para o cliente.
    """
    parts = (full_name or "").strip().split(None, 1)
    return (parts[0] if parts else "", parts[1] if len(parts) > 1 else "")
