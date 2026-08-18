"""
Shopman Cashman — o caixa do PDV: terminais, turnos e o livro-caixa imutável.

Uso:
    from shopman.cashman import services as cash

    shift = cash.open_shift(operator=user, float_q=10000)      # abre a custódia + fundo de troco
    cash.record("sale", shift=shift, operator=user, amount_q=1500, order_ref="A01", payment_ref="pi_1")
    cash.record("cash_out", shift=shift, operator=user, amount_q=-5000, approved_by=manager, reason="Cofre")
    cash.close_shift(shift, counted_q=6490, actor=user)          # contagem cega = lançamento de ajuste
    cash.difference(shift)                                       # -10 (faltou dez centavos)

Três modelos:
    Terminal — o aparelho (config; não guarda dinheiro)
    Shift    — a custódia (quem, qual gaveta, desde quando; sem coluna de dinheiro)
    Entry    — o livro (uma linha por acontecimento, amount_q assinado, imutável)

Fronteira com o payman: o payman responde "liquidou? quanto, por método?"; o
cashman responde "o que há nesta gaveta e o que aconteceu com ela". O único
fato compartilhado é o tender em dinheiro (captura lá, `sale` aqui), ligado
por `payment_ref`.
"""

from shopman.cashman.exceptions import CashError


def __getattr__(name):
    """Import lazy para não disparar AppRegistryNotReady."""
    if name in {"Terminal", "Shift", "Entry"}:
        import shopman.cashman.models as _models

        return getattr(_models, name)
    if name == "services":
        import shopman.cashman.services as _services

        return _services
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["CashError", "Terminal", "Shift", "Entry", "services"]

__version__ = "0.1.0"
