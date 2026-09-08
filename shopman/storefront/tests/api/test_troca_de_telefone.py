"""Mudar o número de telefone mantendo a conta.

Trocar o número nunca existiu: a tela só sabia "entrar com outro número", que
abre OUTRA conta e deixa o histórico para trás. O que faltava não era um campo —
era o caminho certo para escrever o contato.

⚠️ O caminho ERRADO é o intuitivo. ``customer.phone = novo; customer.save()``
estoura no banco, porque ``Customer._sync_contact_points`` cria o ContactPoint
novo já primário antes de demover o antigo. ``Customer.phone`` é CACHE; a fonte
da verdade é o ``ContactPoint``, e quem troca contato é ``set_as_primary()``.
O primeiro teste aqui é a prova disso — e a razão de o Core não ter mudado.
"""

from __future__ import annotations

import pytest
from django.test import Client
from shopman.guestman.models import ContactPoint, Customer

pytestmark = pytest.mark.django_db

NUMERO_ANTIGO = "+5543999990001"
NUMERO_NOVO = "+5543999990002"


DEBUG_OTP_TOKEN = "segredo-da-suite"


@pytest.fixture(autouse=True)
def _disable_request_rate_limits(settings, monkeypatch):
    settings.RATELIMIT_ENABLE = False
    # O código só volta na resposta pelo portão real do OTP de depuração — o
    # mesmo do login, com segredo conferido no cabeçalho. A suíte passa pela
    # porta em vez de contorná-la.
    settings.SHOPMAN_EXPOSE_DEBUG_OTP = True
    settings.SHOPMAN_DEBUG_OTP_TOKEN = DEBUG_OTP_TOKEN

    # A portaria de intervalo entre envios (G11) é por NÚMERO e não olha a
    # finalidade: quem acabou de confirmar o número novo espera o intervalo
    # antes de pedir um código de login para ele. É o comportamento certo em
    # produção e um estorvo aqui, onde os dois passos acontecem no mesmo
    # segundo — então o relógio sai do caminho, e só ele.
    from shopman.doorman.conf import doorman_settings

    monkeypatch.setattr(doorman_settings, "ACCESS_CODE_COOLDOWN_SECONDS", 0)


def _make_customer(ref: str = "CUS-TEL-01", phone: str = NUMERO_ANTIGO) -> Customer:
    return Customer.objects.create(ref=ref, first_name="Ana", last_name="Silva", phone=phone)


def _login_as_customer(client: Client, customer: Customer):
    from shopman.doorman.protocols.customer import AuthCustomerInfo
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

    info = AuthCustomerInfo(
        uuid=customer.uuid,
        name=customer.name,
        phone=customer.phone,
        email=getattr(customer, "email", None) or None,
        is_active=True,
    )
    user, _ = get_or_create_user_for_customer(info)
    client.force_login(user, backend="shopman.doorman.backends.PhoneOTPBackend")
    return user


def _csrf_headers(client: Client) -> dict[str, str]:
    response = client.get("/api/v1/storefront/cart/")
    return {"HTTP_X_CSRFTOKEN": response.cookies["csrftoken"].value}


def _pedir_codigo(client: Client, phone: str = NUMERO_NOVO):
    return client.post(
        "/api/v1/account/phone/request/",
        data={"phone": phone},
        content_type="application/json",
        HTTP_X_SHOPMAN_DEBUG_OTP=DEBUG_OTP_TOKEN,
        **_csrf_headers(client),
    )


def _confirmar(client: Client, code: str, phone: str = NUMERO_NOVO):
    return client.post(
        "/api/v1/account/phone/confirm/",
        data={"phone": phone, "code": code},
        content_type="application/json",
        **_csrf_headers(client),
    )


def _trocar_numero(client: Client, phone: str = NUMERO_NOVO):
    """Faz a troca inteira e devolve a resposta da confirmação."""
    resposta = _pedir_codigo(client, phone)
    assert resposta.status_code == 200, resposta.content
    codigo = resposta.json()["debug_otp_code"]
    return _confirmar(client, codigo, phone)


# ---------------------------------------------------------------------------
# A razão de o Core não ter mudado
# ---------------------------------------------------------------------------


def test_escrever_no_cache_e_salvar_estoura__por_isso_o_caminho_e_o_contact_point():
    """A proposta de mudar o guestman nasce daqui — e morre aqui.

    Quem vê este ``IntegrityError`` conclui que ``_sync_contact_points`` está
    errado. Não está: ele é atalho para o PRIMEIRO contato, e escrever no cache
    para TROCAR contato é usar a API errada. O Core já oferece a certa, e o
    teste seguinte a exercita.
    """
    from django.db import IntegrityError

    customer = _make_customer()

    customer.phone = NUMERO_NOVO
    with pytest.raises(IntegrityError):
        customer.save()


def test_set_as_primary_troca_na_ordem_certa_sem_violar_constraint():
    customer = _make_customer(ref="CUS-TEL-CORE")

    novo = ContactPoint.objects.create(
        customer=customer,
        type=ContactPoint.Type.PHONE,
        value_normalized=NUMERO_NOVO,
        value_display=NUMERO_NOVO,
    )
    novo.set_as_primary()

    customer.refresh_from_db()
    assert customer.phone == NUMERO_NOVO
    primarios = ContactPoint.objects.filter(
        customer=customer, type=ContactPoint.Type.PHONE, is_primary=True
    )
    assert primarios.count() == 1
    assert primarios.first().value_normalized == NUMERO_NOVO


# ---------------------------------------------------------------------------
# 1. Troca com número novo verificado
# ---------------------------------------------------------------------------


def test_troca_verificada_promove_o_novo_e_leva_o_cache_junto(client: Client):
    customer = _make_customer()
    _login_as_customer(client, customer)

    resposta = _trocar_numero(client)

    assert resposta.status_code == 200, resposta.content
    assert resposta.json()["phone"] == NUMERO_NOVO

    customer.refresh_from_db()
    # O cache acompanhou — mas quem mandou foi o ContactPoint.
    assert customer.phone == NUMERO_NOVO

    contatos = ContactPoint.objects.filter(customer=customer, type__in=("phone", "whatsapp"))
    assert {c.value_normalized for c in contatos} == {NUMERO_NOVO}
    assert all(c.is_primary for c in contatos)
    assert all(c.is_verified for c in contatos)


def test_troca_verificada_nao_viola_nenhuma_constraint(client: Client):
    """Um primário por tipo, e nenhum valor duplicado — conferido no banco."""
    customer = _make_customer()
    _login_as_customer(client, customer)

    assert _trocar_numero(client).status_code == 200

    for tipo in ("phone", "whatsapp"):
        assert (
            ContactPoint.objects.filter(
                customer=customer, type=tipo, is_primary=True
            ).count()
            == 1
        )

    # A constraint global (type, value_normalized) continua de pé.
    from django.db import IntegrityError

    outro = Customer.objects.create(ref="CUS-TEL-OUTRO", first_name="Bia")
    with pytest.raises(IntegrityError):
        ContactPoint.objects.create(
            customer=outro,
            type=ContactPoint.Type.PHONE,
            value_normalized=NUMERO_NOVO,
            value_display=NUMERO_NOVO,
        )


def test_pedir_codigo_nao_cria_cadastro_fantasma_no_numero_novo(client: Client):
    """A finalidade `verify_contact` não resolve nem cria cliente.

    É o que dispensa o `verify_code` que o plano previa acrescentar ao doorman:
    o `verify_for_login` criaria um cadastro no número novo só por perguntar.
    """
    customer = _make_customer()
    _login_as_customer(client, customer)

    antes = Customer.objects.count()
    assert _pedir_codigo(client).status_code == 200

    assert Customer.objects.count() == antes
    assert Customer.objects.filter(phone=NUMERO_NOVO).exclude(pk=customer.pk).count() == 0


# ---------------------------------------------------------------------------
# 2. Troca sem verificar → recusada
# ---------------------------------------------------------------------------


def test_confirmar_sem_pedir_codigo_e_recusado(client: Client):
    customer = _make_customer()
    _login_as_customer(client, customer)

    resposta = _confirmar(client, "123456")

    assert resposta.status_code == 400
    assert resposta.json()["field"] == "code"
    customer.refresh_from_db()
    assert customer.phone == NUMERO_ANTIGO


def test_codigo_errado_e_recusado_e_o_numero_nao_muda(client: Client):
    customer = _make_customer()
    _login_as_customer(client, customer)

    correto = _pedir_codigo(client).json()["debug_otp_code"]
    errado = "000000" if correto != "000000" else "111111"

    resposta = _confirmar(client, errado)

    assert resposta.status_code == 400
    assert resposta.json()["error_code"] == "code_invalid"
    customer.refresh_from_db()
    assert customer.phone == NUMERO_ANTIGO
    assert not ContactPoint.objects.filter(
        customer=customer, value_normalized=NUMERO_NOVO
    ).exists()


def test_codigo_de_login_nao_serve_para_trocar_de_numero(client: Client):
    """As duas finalidades são cofres separados.

    Sem isso, "confirme seu número novo" geraria um código que também ABRE a
    sessão de quem atender aquele telefone.
    """
    from shopman.shop.services import auth as auth_service

    customer = _make_customer()
    _login_as_customer(client, customer)

    login_result = auth_service.request_code(
        phone=NUMERO_NOVO, delivery_method="whatsapp", ip_address=None
    )
    assert login_result.success

    resposta = _confirmar(client, login_result.debug_code)

    assert resposta.status_code == 400
    customer.refresh_from_db()
    assert customer.phone == NUMERO_ANTIGO


def test_anonimo_nao_troca_numero_de_ninguem(client: Client):
    _make_customer()

    assert _pedir_codigo(client).status_code == 401
    assert _confirmar(client, "123456").status_code == 401


# ---------------------------------------------------------------------------
# 3. Número que já é de outro cadastro → recusa rica, sem vazar identidade
# ---------------------------------------------------------------------------


def _dono_do_numero() -> Customer:
    return Customer.objects.create(
        ref="CUS-TEL-DONO",
        first_name="Joana",
        last_name="Prado",
        phone=NUMERO_NOVO,
    )


def test_numero_de_outro_cadastro_recusa_com_saida(client: Client):
    customer = _make_customer()
    _dono_do_numero()
    _login_as_customer(client, customer)

    resposta = _pedir_codigo(client)

    assert resposta.status_code == 409
    corpo = resposta.json()
    assert corpo["field"] == "phone"
    assert corpo["error_code"] == "contact_already_taken"
    assert corpo["errors"]["phone"] == [corpo["detail"]]
    assert corpo["title"] == "Confira o número"
    # A saída existe: entrar naquela conta prova a posse pelo OTP.
    assert any(a["ref"] == "sign_in_with_phone" for a in corpo["actions"])


def test_a_recusa_nao_diz_de_quem_e_o_numero(client: Client):
    """A loja é superfície de CLIENTE — nomear o dono seria vazamento.

    Aqui aperta mais que no e-mail: o número é a identidade de quem entra.
    """
    customer = _make_customer()
    dono = _dono_do_numero()
    _login_as_customer(client, customer)

    corpo = _pedir_codigo(client).content.decode().lower()

    assert "joana" not in corpo
    assert "prado" not in corpo
    assert dono.ref.lower() not in corpo
    assert "candidates" not in corpo


def test_numero_de_outro_cadastro_recusado_tambem_na_confirmacao(client: Client):
    """A checagem do pedido não basta: o dono pode aparecer no meio do caminho."""
    customer = _make_customer()
    _login_as_customer(client, customer)

    codigo = _pedir_codigo(client).json()["debug_otp_code"]
    _dono_do_numero()

    resposta = _confirmar(client, codigo)

    assert resposta.status_code == 409
    assert resposta.json()["error_code"] == "contact_already_taken"
    customer.refresh_from_db()
    assert customer.phone == NUMERO_ANTIGO


# ---------------------------------------------------------------------------
# 4. O que get_by_phone passa a responder
# ---------------------------------------------------------------------------


def test_get_by_phone_acha_pelo_numero_novo_e_esquece_o_antigo(client: Client):
    """O número antigo SAI do cadastro — e essa é a metade que protege.

    ``get_by_phone`` acha por qualquer ContactPoint de telefone, primário ou
    não. Um número velho deixado como secundário continuaria abrindo esta conta
    por OTP, e a operadora recicla número em poucos meses.
    """
    from shopman.guestman.services import customer as customer_service

    customer = _make_customer()
    _login_as_customer(client, customer)

    assert _trocar_numero(client).status_code == 200

    achado = customer_service.get_by_phone(NUMERO_NOVO)
    assert achado is not None
    assert achado.pk == customer.pk

    assert customer_service.get_by_phone(NUMERO_ANTIGO) is None


def test_o_numero_antigo_fica_livre_para_quem_o_receber_depois(client: Client):
    """Consequência da mesma decisão: o número solto não fica preso a esta conta."""
    customer = _make_customer()
    _login_as_customer(client, customer)
    assert _trocar_numero(client).status_code == 200

    outro = Customer.objects.create(ref="CUS-TEL-NOVO-DONO", first_name="Caio")
    contato = ContactPoint.objects.create(
        customer=outro,
        type=ContactPoint.Type.PHONE,
        value_normalized=NUMERO_ANTIGO,
        value_display=NUMERO_ANTIGO,
    )

    assert contato.pk is not None


# ---------------------------------------------------------------------------
# 5. O login continua íntegro pelo número novo
# ---------------------------------------------------------------------------


def test_o_cliente_entra_com_o_numero_novo(client: Client):
    customer = _make_customer()
    _login_as_customer(client, customer)
    assert _trocar_numero(client).status_code == 200
    client.logout()

    pedido = client.post(
        "/api/v1/auth/request-code/",
        data={"phone": NUMERO_NOVO},
        content_type="application/json",
        HTTP_X_SHOPMAN_DEBUG_OTP=DEBUG_OTP_TOKEN,
    )
    assert pedido.status_code == 200, pedido.content
    codigo = pedido.json()["debug_otp_code"]

    entrada = client.post(
        "/api/v1/auth/verify-code/",
        data={"phone": NUMERO_NOVO, "code": codigo},
        content_type="application/json",
        **_csrf_headers(client),
    )

    assert entrada.status_code == 200, entrada.content

    sessao = client.get("/api/v1/auth/session/").json()
    assert sessao["is_authenticated"] is True
    assert sessao["customer_ref"] == customer.ref
    assert sessao["customer_phone"] == NUMERO_NOVO


def test_entrar_pelo_numero_antigo_nao_abre_a_conta_de_quem_o_deixou(client: Client):
    """A prova de que a chave velha não abre mais a porta."""
    customer = _make_customer()
    _login_as_customer(client, customer)
    assert _trocar_numero(client).status_code == 200
    client.logout()

    pedido = client.post(
        "/api/v1/auth/request-code/",
        data={"phone": NUMERO_ANTIGO},
        content_type="application/json",
        HTTP_X_SHOPMAN_DEBUG_OTP=DEBUG_OTP_TOKEN,
    )
    assert pedido.status_code == 200
    codigo = pedido.json()["debug_otp_code"]

    entrada = client.post(
        "/api/v1/auth/verify-code/",
        data={"phone": NUMERO_ANTIGO, "code": codigo},
        content_type="application/json",
        **_csrf_headers(client),
    )
    assert entrada.status_code == 200

    sessao = client.get("/api/v1/auth/session/").json()
    # Entrou — mas numa conta NOVA, vazia. Nunca na que mudou de número.
    assert sessao["customer_ref"] != customer.ref


# ---------------------------------------------------------------------------
# Arestas
# ---------------------------------------------------------------------------


def test_pedir_o_proprio_numero_e_recusado_sem_gastar_codigo(client: Client):
    customer = _make_customer()
    _login_as_customer(client, customer)

    resposta = _pedir_codigo(client, NUMERO_ANTIGO)

    assert resposta.status_code == 400
    assert resposta.json()["error_code"] == "phone_unchanged"


def test_numero_invalido_e_recusado_com_o_campo_certo(client: Client):
    customer = _make_customer()
    _login_as_customer(client, customer)

    resposta = _pedir_codigo(client, "123")

    assert resposta.status_code == 400
    corpo = resposta.json()
    assert corpo["field"] == "phone"
    assert corpo["error_code"] == "invalid_phone"


def test_o_codigo_nao_serve_duas_vezes(client: Client):
    customer = _make_customer()
    _login_as_customer(client, customer)

    codigo = _pedir_codigo(client).json()["debug_otp_code"]
    assert _confirmar(client, codigo).status_code == 200

    terceiro = Customer.objects.create(ref="CUS-TEL-TERCEIRO", first_name="Dario")
    _login_as_customer(client, terceiro)
    assert _confirmar(client, codigo).status_code == 400
