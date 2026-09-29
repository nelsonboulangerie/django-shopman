"""Gestor de pedidos (parte 2): um gesto, um nome; e nada que o operador não veja.

A projeção e a tela davam nomes diferentes ao mesmo botão ("Solicitar
entregador" / "Chamar entregador", "Registrar pagamento da entrega" / "Acertar
entrega", "Registrar devolução da maquininha" / "Maquininha voltou"), o acerto
dizia "turno 42" (o id interno) e a corrida agrupada aparecia como "Agrupada".
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from django.utils import timezone

from shopman.backstage.projections import order_queue


def test_corrida_agrupada_diz_com_o_que_esta_junto():
    assert order_queue.COURIER_STATUS_LABELS["U"] == "Junto com outra corrida"


def test_o_acerto_diz_o_caixa_e_a_hora_do_turno_nao_o_id():
    aberto = timezone.make_aware(datetime(2026, 9, 25, 8, 5))
    shift = SimpleNamespace(pk=42, opened_at=aberto, terminal=SimpleNamespace(label="Balcão", ref="pdv-main"))

    frase = order_queue._settlement_description(shift)

    assert frase == "O dinheiro entra no caixa Balcão, no turno aberto às 08:05."
    assert "42" not in frase


def test_os_nomes_da_projecao_sao_os_da_tela():
    import inspect

    from shopman.shop.services import operator_orders

    fonte = inspect.getsource(order_queue) + inspect.getsource(operator_orders)
    for antigo in ("Solicitar entregador", "Registrar pagamento da entrega", "Registrar devolução da maquininha"):
        assert f'"{antigo}"' not in fonte
