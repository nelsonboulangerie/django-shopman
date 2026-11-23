# ruff: noqa: F401, F811
"""Os cinco cartões do ensaio do pedido (WP-14), de ponta a ponta, como o dono vai escrever.

Cada cartão é a conversa inteira, até o pedido registrado (ou nenhum, no 4), pelo turno de
verdade, com a leitura da casa sem o modelo. ``CARTOES_RELATORIO=<arquivo>`` grava a
transcrição de cada turno, para a coordenação ler antes de chamar o dono de novo.

O cartão 1 do roteiro diz "hoje às 16h"; aqui é "amanhã às 16h" (a frase real do dono no
ensaio de 22/11), porque "hoje às 16h" depende da hora em que a CI roda: depois das 16h, a
janela já passou e a recusa é a resposta certa.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, timedelta

import pytest
from shopman.orderman.models import Order
from shopman.payman import PaymentService

from shopman.storefront.concierge import intents
from shopman.storefront.tests.test_concierge_bateria_pedidos import bateria
from shopman.storefront.tests.test_concierge_engine import (
    _geocode_text,
    _tomorrow,
    conversation,
    customer,
    outbox,
    surface,
)
from shopman.storefront.tests.test_concierge_fechar_pedido import _session, _turn

pytestmark = pytest.mark.django_db


class Conversa:
    """A conversa do cartão: cada fala vira um turno, e a transcrição fica guardada."""

    def __init__(self, conversation, cartao: str):
        self.conversation, self.cartao, self.turnos = conversation, cartao, []

    def diz(self, texto: str) -> str:
        respostas = _turn(self.conversation, texto)
        self.turnos.append({"cliente": texto, "concierge": respostas})
        return "\n".join(respostas)

    def codigo(self, resposta: str) -> str:
        found = re.search(r"confirmo (\d{4})", resposta)
        assert found, f"sem código no resumo: {resposta}"
        return found.group(1)

    def relatar(self, passou, nota: str = "") -> None:
        destino = os.environ.get("CARTOES_RELATORIO")
        if destino:
            with open(destino, "a", encoding="utf-8") as saida:
                saida.write(json.dumps({"cartao": self.cartao, "passou": passou, "nota": nota,
                                        "turnos": self.turnos}, ensure_ascii=False) + "\n")


@pytest.fixture
def ensaio(conversation, outbox, bateria, request):
    conversa = Conversa(conversation, request.node.name)
    yield conversa
    conversa.relatar(passou=None)  # quem passou ou não diz o pytest; aqui fica a transcrição


def _linhas(order) -> list[tuple[str, int]]:
    return [(item.sku, int(item.qty)) for item in order.items.all()]


def test_cartao_1_retirada(ensaio):
    resumo_sacola = ensaio.diz("quero 2 croissants para retirar amanhã às 16h")
    assert "Combinado: retirada amanhã, a partir das 15h." in resumo_sacola, resumo_sacola
    pagamento = ensaio.diz("pode fechar")
    assert pagamento.startswith("Como você prefere pagar?"), pagamento
    resumo = ensaio.diz("pix")
    assert "Retirada:" in resumo and "a partir das 15h" in resumo, resumo
    registrado = ensaio.diz(f"confirmo {ensaio.codigo(resumo)}")

    order = Order.objects.get()
    assert registrado.startswith(f"Pedido {order.ref} registrado."), registrado
    assert (order.data["fulfillment_type"], order.data["delivery_date"], order.data["delivery_time_slot"]) == (
        "pickup", _tomorrow(), "slot-15")
    assert _linhas(order) == [("CROISSANT", 2)]


def test_cartao_2_entrega(ensaio, monkeypatch):
    _geocode_text(monkeypatch, route="Rua das Flores", street_number="120", neighborhood="Centro",
                  city="Londrina", state_code="PR", postal_code="86010-000")
    primeira = ensaio.diz("quero 1 pão de campanha com entrega")
    assert "1 × “Pão de Campanha”" in primeira and primeira.endswith("Para quando é o pedido? Hoje, amanhã ou outro dia (dia/mês)?"), primeira
    assert "pode fechar" not in primeira and "Entrega: \n" not in primeira, primeira
    endereco = ensaio.diz("amanhã")
    assert "endereço" in endereco.casefold() or "localização" in endereco.casefold(), endereco
    complemento = ensaio.diz("Rua das Flores, 120, Centro, Londrina, CEP 86010-000")
    assert "complemento" in complemento, complemento
    pagamento = ensaio.diz("sem complemento")
    assert pagamento.startswith("Como você prefere pagar?"), pagamento
    resumo = ensaio.diz("pix")
    assert "Entrega:" in resumo and "Rua das Flores" in resumo, resumo
    ensaio.diz(f"confirmo {ensaio.codigo(resumo)}")

    order = Order.objects.get()
    assert order.data["fulfillment_type"] == "delivery" and "Rua das Flores" in order.data["delivery_address"]
    assert _linhas(order) == [("PAO-CAMPANHA", 1)]


def _ate_o_resumo(ensaio, pedido: str) -> str:
    ensaio.diz(pedido)
    ensaio.diz("pode fechar")
    ensaio.diz("amanhã")
    ensaio.diz("vou retirar")
    ensaio.diz("às 13h")
    return ensaio.diz("pix")


def test_cartao_3_mudar_no_meio(ensaio):
    resumo = _ate_o_resumo(ensaio, "quero 2 croissants")
    antigo = ensaio.codigo(resumo)
    mudou = ensaio.diz("na verdade 3")
    assert mudou.count("3 × “Croissant”") == 1 and "pode fechar" not in mudou, mudou  # o resumo novo, sem repetir
    recusado = ensaio.diz(f"confirmo {antigo}")
    assert not Order.objects.exists(), recusado  # o código antigo não fecha nada
    novo_resumo = recusado if "confirmo " in recusado else ensaio.diz("pode fechar")
    novo = ensaio.codigo(novo_resumo)
    assert novo != antigo
    ensaio.diz(f"confirmo {novo}")

    assert _linhas(Order.objects.get()) == [("CROISSANT", 3)]


def test_cartao_4_desistir(ensaio):
    _ate_o_resumo(ensaio, "quero 2 croissants")
    resposta = ensaio.diz("deixa pra lá")

    assert not Order.objects.exists()
    assert "Os itens continuam na sacola" in resposta, resposta
    assert {i["sku"]: int(i["qty"]) for i in _session(ensaio.conversation).items} == {"CROISSANT": 2}


@pytest.mark.django_db(transaction=True)
def test_cartao_5_pix(ensaio, settings):
    """Sem transação por fora, como no ar (#3340): o Pix nasce no commit do pedido e o
    copia-e-cola chega à cliente numa mensagem própria, logo depois do "registrado"."""
    from shopman.shop.services import pix_confirmation

    # O Pix de teste, como no alpha (``payment_mock``): sem a Efí, o pedido sai sem cobrança.
    settings.SHOPMAN_PAYMENT_ADAPTERS = {**settings.SHOPMAN_PAYMENT_ADAPTERS, "pix": "shopman.shop.adapters.payment_mock"}
    resumo = _ate_o_resumo(ensaio, "quero 2 croissants")
    registrado = ensaio.diz(f"confirmo {ensaio.codigo(resumo)}")
    order = Order.objects.get()
    assert registrado.startswith(f"Pedido {order.ref} registrado."), registrado
    assert "ainda não está disponível" not in registrado, registrado
    copia_e_cola = order.data["payment"]["copy_paste"]
    assert copia_e_cola and copia_e_cola in registrado, registrado  # o código Pix, na conversa
    (intent,) = list(PaymentService.get_by_order(order.ref))
    pix_confirmation.confirm_pix(txid=intent.gateway_id, e2e_id="ensaio-e2e",
                                 amount=f"{order.total_q / 100:.2f}")

    assert PaymentService.captured_total(intent.ref) == order.total_q
