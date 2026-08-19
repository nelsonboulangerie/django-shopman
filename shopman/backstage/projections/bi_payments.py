"""Forma de pagamento como recorte do B.I. (BI-QUESTION-CATALOG §3.3/F1).

O dado sempre existiu e ninguém lia direito: cada pedido guarda os pagamentos
linha a linha (``order.data.payment.tenders[]``) e o histórico externo traz a
forma crua de cada venda. Até aqui isso só aparecia como **total do dia** no
painel de caixa — e só em dia com fechamento feito, porque a leitura era do
``DayClosing``. Lendo do pedido, o recorte passa a existir todo dia e a cruzar
com hora, canal, produto e contexto do dia.

Duas honestidades que o módulo carrega:

1. **Recebido não é o mesmo que faturado.** Cobrança na entrega ainda não
   recebida sai da métrica de recebido e tem métrica própria — dinheiro na rua
   é dinheiro na rua, não caixa.
2. **A forma crua do histórico não é traduzida no chute.** O vocabulário
   conhecido é normalizado; o resto **preserva o texto original** no rótulo, em
   vez de virar um balde "(outros)" que esconde o que o sistema antigo escreveu.
"""

from __future__ import annotations

_LABELS: dict[str, str] = {
    "cash": "Dinheiro",
    "pix": "PIX",
    "card": "Cartão",
    "credit": "Cartão de crédito",
    "debit": "Cartão de débito",
    "voucher": "Vale",
    "ifood": "iFood",
    "external": "Outro meio",
    "mixed": "Dividido",
}

UNKNOWN_PREFIX = "raw:"
"""Chave de forma não reconhecida no histórico. O rótulo é o texto original."""


def payment_vocabulary() -> tuple[tuple[str, str], ...]:
    """(trecho, forma canônica) confirmados, na ordem em que casam.

    O vocabulário do histórico vive em ``PaymentMethodAlias`` (mapeamento é
    dado, não código): casamento por substring, na ordem — a primeira que casa
    vence, então o específico vem antes do genérico ("vale refeição" antes de
    "vale", "cartão de crédito" antes de "cartão"). Só linhas **confirmadas**
    entram. Uma consulta por leitura; quem varre milhares de vendas carrega
    uma vez e passa adiante.
    """
    from shopman.backstage.models import PaymentMethodAlias

    return tuple(
        PaymentMethodAlias.objects.confirmed()
        .exclude(method_key="")
        .order_by("position", "id")
        .values_list("pattern", "method_key")
    )


def normalize_historical_payment(
    raw: str | None,
    vocabulary: tuple[tuple[str, str], ...] | None = None,
) -> tuple[str, str]:
    """(chave, rótulo) da forma de pagamento crua de uma venda histórica.

    O que o vocabulário conhece vira forma canônica e soma com o nativo. O que
    ele não conhece **não é jogado num balde mudo**: a chave carrega o texto
    original e o rótulo o exibe, para que uma forma que a casa usava e eu não
    previ apareça na tela em vez de sumir dentro de "(outros)".

    ``vocabulary`` vem de ``payment_vocabulary()``; quem chama em laço carrega
    uma vez. Sem ele, carrega aqui (uma consulta).
    """
    text = (raw or "").strip()
    if not text:
        return "external", payment_method_label("external")
    lowered = text.lower()
    if vocabulary is None:
        vocabulary = payment_vocabulary()
    for needle, method in vocabulary:
        if needle in lowered:
            return method, payment_method_label(method)
    return f"{UNKNOWN_PREFIX}{lowered}", text


def payment_method_label(method: str) -> str:
    """Rótulo de exibição de uma forma de pagamento."""
    if method.startswith(UNKNOWN_PREFIX):
        return method[len(UNKNOWN_PREFIX):]
    if method in _LABELS:
        return _LABELS[method]
    # Forma nova cadastrada em outro lugar: aparece como veio, nunca traduzida
    # no chute nem escondida.
    return method
