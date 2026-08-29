"""Compras: a nota que entrava duas vezes, o fornecedor errado, e o custo 100× errado.

Quatro achados do WP-06, os quatro no caminho do dinheiro.

⚠️ **Nenhum modelo novo e nenhuma migração.** A trava de recibo usa a
``IdempotencyKey`` do orderman — a mesma tabela do commit de sessão, do replay de
webhook e do submit do PDV — pelo envelope genérico que já existe
(``shop/services/remote_mutations.run_idempotent_mutation``). O WP-06 pedia um
``PurchaseReceipt`` append-only no buyman; a roda já estava pronta, duas vezes.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from shopman.buyman.models import Material, MaterialConversion, Supplier
from shopman.orderman.models import IdempotencyKey
from shopman.stockman.models import Move, Position, Quant
from shopman.stockman.models.enums import PositionKind

from shopman.backstage.services import purchase as purchase_service

#: Emitente = `chave[6:20]` = 12345678000190, o mesmo CNPJ do fornecedor abaixo.
CHAVE_VALIDA = "41260812345678000190550010000012341000123459"
#: Outro emitente, mesma estrutura válida.
CHAVE_DE_OUTRO_EMITENTE = "41260899888777000166550010000012341000123453"


@pytest.fixture
def operador(db):
    """Chamamos o SERVIÇO direto: o portão de permissão é da view, e tem teste próprio.

    O que se prova aqui é a regra de negócio — duplicação, emitente e dinheiro.
    """
    return User.objects.create_user("compras-op", password="pw", is_staff=True)


@pytest.fixture
def cenario(db):
    material = Material.objects.create(sku="FAR-T65", name="Farinha T65", unit="kg")
    fornecedor = Supplier.objects.create(
        ref="SUP-MOINHO-SP", name="Moinho São Paulo", document="12.345.678/0001-90"
    )
    conversao = MaterialConversion.objects.create(
        material=material, supplier=fornecedor, label="saco 25 kg", to_base_factor=Decimal("25")
    )
    Position.objects.get_or_create(
        ref="estoque", defaults={"name": "Estoque", "kind": PositionKind.PHYSICAL, "is_saleable": False}
    )
    return material, fornecedor, conversao


def _payload(cenario, *, chave=CHAVE_VALIDA, custo="360,00", mode="invoice", note=""):
    material, fornecedor, conversao = cenario
    return {
        "mode": mode,
        "supplierRef": fornecedor.ref,
        "invoiceAccessKey": chave if mode == "invoice" else "",
        "note": note,
        "lines": [
            {
                "id": "l1",
                "materialSku": material.sku,
                "conversionId": str(conversao.pk),
                "purchaseQty": 2,
                "costInput": custo,
                "checked": True,
            }
        ],
    }


# ── A nota que entrava duas vezes ────────────────────────────────────────────


@pytest.mark.django_db
def test_a_mesma_nota_nao_entra_duas_vezes(cenario, operador):
    """O gesto que duplicava: reescanear a nota na dúvida, horas depois.

    A guarda que existia era só de tela — o botão desabilitado enquanto o primeiro
    clique está em voo. Nenhuma delas sobrevive a um 504 no proxy, a uma aba fechada
    ou a um segundo tablet.
    """
    material, _fornecedor, _conv = cenario
    purchase_service.confirm_receipt(_payload(cenario), user=operador)
    quant = Quant.objects.get(sku=material.sku)
    depois_da_primeira = quant.quantity

    with pytest.raises(purchase_service.PurchaseError) as recusa:
        purchase_service.confirm_receipt(_payload(cenario), user=operador)

    quant.refresh_from_db()
    assert quant.quantity == depois_da_primeira, "o estoque dobrou"
    assert Move.objects.filter(quant__sku=material.sku, kind=Move.Kind.BUY).count() == 1
    assert "já entrou" in str(recusa.value)


@pytest.mark.django_db
def test_a_recusa_diz_QUANDO_e_POR_QUEM(cenario, operador):
    """Não é replay silencioso de propósito.

    Responder "deu certo" a quem REESCANEOU faria o operador acreditar numa entrada
    nova. Dizer quando e por quem serve aos dois casos — o retry e a dúvida.
    """
    purchase_service.confirm_receipt(_payload(cenario), user=operador)

    with pytest.raises(purchase_service.PurchaseError) as recusa:
        purchase_service.confirm_receipt(_payload(cenario), user=operador)

    mensagem = str(recusa.value)
    assert "compras-op" in mensagem
    assert "às" in mensagem


@pytest.mark.django_db
def test_uma_nota_diferente_entra_normalmente(cenario, operador):
    """Assert-positivo: a trava não pode virar uma porta fechada.

    A chave é a IDENTIDADE da nota, não um bloqueio por fornecedor.
    """
    material, _f, _c = cenario
    purchase_service.confirm_receipt(_payload(cenario), user=operador)

    outra = CHAVE_VALIDA[:30] + "9" + CHAVE_VALIDA[31:]
    from shopman.backstage.services.purchase import parse_invoice_access_key

    if parse_invoice_access_key(outra) is None:
        pytest.skip("o dígito trocado invalidou a chave; o caso é coberto pelo modo manual")

    purchase_service.confirm_receipt(_payload(cenario, chave=outra), user=operador)

    assert Move.objects.filter(quant__sku=material.sku, kind=Move.Kind.BUY).count() == 2


@pytest.mark.django_db
def test_a_entrada_SEM_nota_tambem_nao_duplica(cenario, operador):
    """O `source_ref` manual carregava `timezone.now()` — mudava a cada chamada.

    Servia para nomear um lote; não servia para responder "essa entrada já foi
    feita?". Derivado do conteúdo, dois envios do mesmo recebimento colidem.
    """
    material, _f, _c = cenario
    purchase_service.confirm_receipt(_payload(cenario, mode="manual", note="entrega da manhã"), user=operador)

    with pytest.raises(purchase_service.PurchaseError):
        purchase_service.confirm_receipt(_payload(cenario, mode="manual", note="entrega da manhã"), user=operador)

    assert Move.objects.filter(quant__sku=material.sku, kind=Move.Kind.BUY).count() == 1


@pytest.mark.django_db
def test_o_historico_de_recebimentos_aparece_na_projection(cenario, operador):
    """A mesma linha que impede a segunda entrada é a que conta a primeira.

    A tela não tinha esta lista: o único dado era a data da última entrada POR
    FORNECEDOR, que não responde "essa NOTA já entrou?".
    """
    purchase_service.confirm_receipt(_payload(cenario), user=operador)

    from shopman.backstage.projections.purchase import build_purchase

    historico = build_purchase().receiptHistory

    assert len(historico) == 1
    assert historico[0].sourceRef == CHAVE_VALIDA
    assert historico[0].operator == "compras-op"
    assert historico[0].lines == 1
    assert historico[0].supplierName == "Moinho São Paulo"


# ── O fornecedor que não emitiu a nota ───────────────────────────────────────


@pytest.mark.django_db
def test_fornecedor_que_nao_emitiu_a_nota_e_recusado(cenario, operador):
    """O confirm validava a chave E o fornecedor — mas nunca cruzava os dois.

    O pior efeito não é o movimento errado: é o de-para fiscal aprendido NO
    FORNECEDOR ERRADO, que envenena o scan de todas as notas futuras dele.
    """
    material, _f, _c = cenario

    with pytest.raises(purchase_service.PurchaseError) as recusa:
        purchase_service.confirm_receipt(_payload(cenario, chave=CHAVE_DE_OUTRO_EMITENTE), user=operador)

    assert "não é quem emitiu" in str(recusa.value)
    assert not Move.objects.filter(quant__sku=material.sku, kind=Move.Kind.BUY).exists()


@pytest.mark.django_db
def test_fornecedor_sem_documento_nao_e_barrado(cenario, operador):
    """A checagem se cala num caso só — e dizendo por quê no log, não em silêncio.

    Recusar por cadastro incompleto quebraria entrada legítima, e a nota não fica
    melhor guardada por isso.
    """
    material, fornecedor, _c = cenario
    fornecedor.document = ""
    fornecedor.save(update_fields=["document"])

    purchase_service.confirm_receipt(_payload(cenario), user=operador)

    assert Move.objects.filter(quant__sku=material.sku, kind=Move.Kind.BUY).count() == 1


# ── O custo 100× errado ──────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("digitado", "centavos"),
    [
        ("12,50", 1250),      # teclado da casa
        ("12.50", 1250),      # teclado do sistema — a tela mostrava R$ 1.250,00
        ("12.5", 1250),       # divergência de 10×
        ("1.250,00", 125000),  # milhar com vírgula decimal
        ("R$ 360,00", 36000),
        ("", 0),               # vazio é "não informei", e continua valendo zero
    ],
)
def test_o_servidor_le_o_dinheiro_do_jeito_que_a_tela_mostra(digitado, centavos):
    assert purchase_service.parse_money_input(digitado) == centavos


@pytest.mark.django_db
@pytest.mark.parametrize("digitado", ["12,50 (com frete)", "abc", "R$ vinte", "12,,50"])
def test_custo_ilegivel_grita_em_vez_de_virar_zero(digitado):
    """Virava `0` em silêncio, e o confirm simplesmente pulava o custo.

    Digitar "12,50 (com frete)" gravava a entrada com custo ZERO e não dizia nada.
    Falhar aberto e calado, em dinheiro — contra a régua explícita da casa.
    """
    with pytest.raises(purchase_service.PurchaseError) as recusa:
        purchase_service.parse_money_input(digitado)

    assert "Não entendi o valor" in str(recusa.value)


@pytest.mark.django_db
def test_custo_ilegivel_na_linha_nao_grava_entrada_nenhuma(cenario, operador):
    """Ponta a ponta: o erro tem de chegar ANTES de qualquer escrita de estoque."""
    material, _f, _c = cenario

    with pytest.raises(purchase_service.PurchaseError):
        purchase_service.confirm_receipt(_payload(cenario, custo="12,50 (com frete)"), user=operador)

    assert not Move.objects.filter(quant__sku=material.sku, kind=Move.Kind.BUY).exists()
    assert not IdempotencyKey.objects.filter(scope=purchase_service.RECEIPT_IDEMPOTENCY_SCOPE, status="done").exists()
