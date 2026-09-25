"""Sinais do orquestrador.

Um sinal aqui existe quando o shop precisa ANUNCIAR um fato e não espera
resposta de ninguém (ADR-001). Quando precisa de retorno, o instrumento é
adapter/Protocol; quando precisa de retry, é Directive.
"""

from __future__ import annotations

from django.dispatch import Signal

#: O titular exerceu o direito de exclusão (art. 18 da LGPD) e o shop já apagou
#: o que é dele: Customer, contatos, identidades, perfil de RFM, e o rastro em
#: Order/Session.
#:
#: Existe porque a exclusão precisa alcançar dado guardado FORA do shop — os
#: favoritos e os avisos de reposição vivem em `storefront`, e `shop` não pode
#: importar `storefront` (a seta de dependência só aponta para cá). Sem este
#: anúncio, cada superfície nova que guardasse dado do cliente sairia de fábrica
#: fora da exclusão, em silêncio.
#:
#: Argumentos: ``customer_ref``, ``phone`` (o original, já apagado do Customer)
#: e ``pseudonym`` (o handle estável que substituiu o telefone nos pedidos).
customer_anonymized = Signal()


#: A NFC-e de um pedido vivo acabou de ser AUTORIZADA e gravada em
#: ``order.data`` (``handlers/fiscal.NFCeEmitHandler._after_authorized``).
#:
#: Existe porque a DANFE da entrega sai pela impressora do despacho, e quem sabe
#: imprimir é o ``backstage`` (``services/order_danfe.py``), que o shop não pode
#: importar. Pedido desfeito não anuncia: a nota dele vai para o cancelamento.
#:
#: Argumento: ``order``.
nfce_authorized = Signal()
