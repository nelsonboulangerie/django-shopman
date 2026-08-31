"""A entrega do balcão para de ser digitada.

Achado do QA do dono: no checkout do PDV a **taxa** era um campo livre, o
**horário combinado** era texto solto ("Ex: 14:00-14:30") e a **data** nascia em
branco. Três perguntas que a casa já sabe responder, transferidas para a memória
de quem está com o cliente na frente.

Taxa digitada é um segundo dono do preço: a zona de CEP, a faixa de distância e o
frete grátis acima de um valor — tudo configurado no Admin, tudo já aplicado na
loja — passavam ao largo, e duas vendas do mesmo endereço saíam diferentes
conforme quem estava no caixa. Aqui se prova que o balcão passou a ler o MESMO
motor da loja, que os horários saem do expediente do dia, e que a única porta
que restou para digitar é a exceção explícita.
"""

from __future__ import annotations

from datetime import date, datetime, time

import pytest
from django.utils import timezone

from shopman.shop.models import Channel, DeliveryZone, Shop
from shopman.shop.services import business_calendar
from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import PosIntentError

pytestmark = pytest.mark.django_db

ENDERECO = {
    "formatted_address": "Rua Pará, 86 - Centro, Londrina - PR",
    "postal_code": "86010-000",
    "neighborhood": "Centro",
}


@pytest.fixture
def loja():
    shop = Shop.objects.create(
        name="Test Shop",
        brand_name="Test",
        # Expediente curto de propósito: as janelas do dia cabem na asserção.
        opening_hours={
            day: {"open": "09:00", "close": "11:00"}
            for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
        },
    )
    Channel.objects.create(
        ref="pdv",
        name="PDV",
        is_active=True,
        config={
            "confirmation": {"mode": "immediate"},
            "payment": {"method": "cash", "timing": "external"},
            "stock": {"check_on_commit": False},
        },
    )
    return shop


def _payload(**overrides) -> dict:
    payload = {
        "items": [{"sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 1200}],
        "fulfillment_type": "delivery",
        "delivery_address": ENDERECO["formatted_address"],
        "delivery_address_structured": dict(ENDERECO),
        "payment_method": "cash",
    }
    payload.update(overrides)
    return payload


def _review(**overrides):
    return pos_service.review_sale(
        channel_ref="pdv", payload=_payload(**overrides), operator_username="marina"
    )


# ── A taxa vem do motor ───────────────────────────────────────────────────


def test_a_taxa_vem_da_zona_do_endereco_nao_da_digitacao(loja):
    """Zona de bairro configurada no Admin: o balcão cobra o que a loja cobra."""
    DeliveryZone.objects.create(
        shop=loja, name="Centro", zone_type=DeliveryZone.ZONE_TYPE_NEIGHBORHOOD,
        match_value="Centro", mode=DeliveryZone.MODE_OVERRIDE, fee_q=600, is_active=True,
    )

    review = _review()

    assert review.delivery_fee_q == 600
    assert review.delivery_fee_source == "zone"
    assert review.total_q == 1200 + 600


def test_taxa_digitada_pelo_operador_nao_e_aceita_nem_em_silencio(loja):
    """O campo livre morreu, e a recusa é ALTA.

    `delivery_fee_q` saiu do intent. Recusar é melhor que ignorar: um payload
    que ainda mande a taxa vem de uma tela que acha que a está definindo, e
    engolir o número calado deixaria o operador certo de ter cobrado algo que
    o servidor descartou. Se esta asserção cair, o balcão voltou a ter dois
    donos do preço da entrega — e o segundo é quem estiver no caixa.
    """
    with pytest.raises(PosIntentError) as excinfo:
        _review(delivery_fee_q=9900)

    assert excinfo.value.code == "unexpected_intent_field"
    assert excinfo.value.field == "delivery_fee_q"


def test_a_excecao_do_operador_continua_existindo_mas_e_explicita(loja):
    """Combinado de porta, cortesia: a porta existe, e ela tem nome."""
    DeliveryZone.objects.create(
        shop=loja, name="Centro", zone_type=DeliveryZone.ZONE_TYPE_NEIGHBORHOOD,
        match_value="Centro", mode=DeliveryZone.MODE_OVERRIDE, fee_q=600, is_active=True,
    )

    review = _review(delivery_fee_override_q=0)

    assert review.delivery_fee_q == 0
    assert review.delivery_fee_source == "manual"


def test_endereco_em_branco_nao_e_taxa_zero_e_sim_pendente(loja):
    """Zero com origem vazia se lê como "ainda não sei", não como "de graça".

    Direto no resolvedor: a review exige endereço para finalizar, e o estado
    "ainda digitando" é justamente o que ela não deixa passar — mas a tela o
    atravessa a cada tecla, e é ali que a distinção importa.
    """
    resolution = pos_service._resolve_delivery_fee({
        "fulfillment_type": "delivery",
        "items": [{"sku": "PAO", "qty": 1, "unit_price_q": 1200}],
    })

    assert resolution.fee_q == 0
    assert resolution.source == ""


def test_zona_de_exclusao_avisa_o_balcao_sem_bloquear(loja):
    """Fora da área é fato do endereço: o operador VÊ antes de prometer.

    Não bloqueia — o combinado da porta é decisão de quem atende —, mas nunca
    acontece calado, que era o comportamento anterior.
    """
    DeliveryZone.objects.create(
        shop=loja, name="Longe", zone_type=DeliveryZone.ZONE_TYPE_NEIGHBORHOOD,
        match_value="Centro", mode=DeliveryZone.MODE_EXCLUDE, fee_q=0, is_active=True,
    )

    review = _review()

    assert review.delivery_fee_source == "blocked"
    assert any(w["code"] == "delivery_out_of_area" for w in review.warnings)


def test_retirada_nao_tem_taxa_mas_TEM_horario(loja):
    """A retirada não paga frete — mas ela combina hora como qualquer pedido.

    ⚠️ Este teste já afirmou o contrário (`delivery_slots == ()`,
    `delivery_date == ""`), e afirmava um DEFEITO: a data nasceu dentro do
    formulário de entrega, então retirada agendada era impossível no balcão. A
    casa recebe encomenda por telefone para retirar na quinta, e o operador não
    tinha onde escrever isso. *Quando* é fato do PEDIDO; só *onde* e *quanto*
    são fatos da entrega.
    """
    review = _review(fulfillment_type="pickup")

    assert review.delivery_fee_q == 0
    # Data em branco continua sendo HOJE, e agora ela CHEGA na retirada.
    assert review.delivery_date == timezone.localdate().isoformat()


def test_retirada_agenda_para_data_futura(loja):
    """A encomenda por telefone para retirar na quinta cabe no balcão.

    Data futura de propósito: as janelas de HOJE dependem do relógio de quem roda
    a suíte (depois das 11h o expediente desta loja já acabou, e a lista vazia
    seria correta). O eixo aqui é a retirada, não a hora do CI.
    """
    quinta = timezone.localdate() + timezone.timedelta(days=4)

    review = _review(fulfillment_type="pickup", delivery_date=quinta.isoformat())

    assert review.delivery_date == quinta.isoformat()
    assert [s["ref"] for s in review.delivery_slots] == [
        "09:00-09:30", "09:30-10:00", "10:00-10:30", "10:30-11:00",
    ]


def test_frete_gratis_acima_do_limiar_vale_no_balcao_tambem(loja):
    """A renúncia por valor de compra é política da loja, não da superfície."""
    DeliveryZone.objects.create(
        shop=loja, name="Centro", zone_type=DeliveryZone.ZONE_TYPE_NEIGHBORHOOD,
        match_value="Centro", mode=DeliveryZone.MODE_OVERRIDE, fee_q=600, is_active=True,
    )
    shop = Shop.objects.first()
    defaults = dict(shop.defaults or {})
    defaults["rules"] = {**(defaults.get("rules") or {}), "free_delivery_above_q": 1000}
    shop.defaults = defaults
    shop.save(update_fields=["defaults"])

    review = _review()

    assert review.delivery_fee_q == 0  # R$ 12,00 de mercadoria passa do limiar


# ── Os horários vêm do expediente ─────────────────────────────────────────


def test_os_horarios_saem_do_expediente_do_dia_de_meia_em_meia_hora(loja):
    """Expediente 09:00-11:00 comporta quatro janelas de meia hora."""
    amanha = timezone.localdate() + timezone.timedelta(days=1)

    review = _review(delivery_date=amanha.isoformat())

    assert review.delivery_date == amanha.isoformat()
    assert [s["ref"] for s in review.delivery_slots] == [
        "09:00-09:30", "09:30-10:00", "10:00-10:30", "10:30-11:00",
    ]
    assert review.delivery_slots[0]["label"] == "09:00 às 09:30"


def test_data_em_branco_e_hoje_pelo_relogio_da_loja(loja):
    """Um tablet com fuso errado agendaria a entrega para ontem."""
    review = _review()

    assert review.delivery_date == timezone.localdate().isoformat()


def test_hoje_so_oferece_o_que_ainda_da_para_cumprir(loja):
    """Às 09:45, "09:00" não é oferta — é promessa quebrada no ato.

    Com meia hora de antecedência, a primeira janela combinável começa às 10:30.
    """
    hoje = date(2026, 8, 25)  # segunda
    agora = timezone.make_aware(datetime.combine(hoje, time(9, 45)))

    slots = business_calendar.delivery_slots_for(hoje, now=agora)

    assert [s["ref"] for s in slots] == ["10:30-11:00"]


def test_expediente_ja_encerrado_nao_inventa_janela(loja):
    hoje = date(2026, 8, 25)
    agora = timezone.make_aware(datetime.combine(hoje, time(12, 30)))

    assert business_calendar.delivery_slots_for(hoje, now=agora) == []
