"""Passkey: entrar com o rosto, e o que NUNCA pode acontecer.

Exercitado com um autenticador de software (`soft-webauthn`), que é o único jeito honesto de
testar WebAuthn sem aparelho na mão. Sem ele, o fluxo mais sensível do login ficaria com teste
de fachada — e é justamente aqui que fachada não serve: a verificação é criptográfica, então ou
o teste assina de verdade ou não testa nada.

As três leis que este arquivo guarda, em ordem de importância:

1. **Cadastrar exige identidade FORTE.** Uma sessão que só conhece o número (chegou por link de
   campanha, e mensagem se encaminha) não pode gravar credencial na conta de alguém. Seria
   alguém cadastrando o próprio rosto no acesso de outra pessoa, e para sempre.
2. **Desafio é de uso único.** É ele que impede replay: a assinatura só vale para o desafio que
   acabamos de emitir, naquele navegador.
3. **Entrar por passkey vale como identidade forte.** A credencial só assina para o nosso
   domínio (imune a phishing) e exige rosto/digital. Não há nada a reduzir depois.
"""

from __future__ import annotations

import json

import pytest

from shopman.storefront.identity import IDENTITY_NUMBER, IDENTITY_SESSION_KEY
from shopman.storefront.tests.web._passkey_device import VerifyingDevice

pytestmark = pytest.mark.django_db

REGISTER_OPTIONS = "/api/v1/auth/passkey/register/options/"
REGISTER = "/api/v1/auth/passkey/register/"
LOGIN_OPTIONS = "/api/v1/auth/passkey/login/options/"
LOGIN = "/api/v1/auth/passkey/login/"


@pytest.fixture
def person(db):
    from shopman.guestman.models import Customer

    return Customer.objects.create(
        ref="CLI-PASSKEY", first_name="Ana", last_name="Ferreira", phone="+5543999997777",
    )


def _sign_in(client, person, *, strength: str | None = None):
    from django.contrib.auth import get_user_model
    from shopman.doorman.models import CustomerUser

    User = get_user_model()
    user = User.objects.create_user(username=f"c-{person.ref}", password="x")
    CustomerUser.objects.create(user=user, customer_id=person.uuid)
    client.force_login(user)
    session = client.session
    if strength:
        session[IDENTITY_SESSION_KEY] = strength
    session.save()


def _b64url(raw: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    import base64

    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _as_device_options(options: dict) -> dict:
    """As opções em BYTES, como o navegador entrega ao autenticador.

    ⚠️ O servidor responde JSON (base64url, porque JSON não tem bytes) e o autenticador espera
    bytes. Quem faz essa tradução no mundo real é o JS do navegador — aqui o teste faz o mesmo
    papel. Sem isto, o autenticador recebe string onde espera bytes e o erro (`a bytes-like
    object is required`) não diz nada sobre o que está errado no protocolo.
    """
    native = dict(options)
    if "challenge" in native:
        native["challenge"] = _unb64(native["challenge"])
    if isinstance(native.get("user"), dict):
        user = dict(native["user"])
        user["id"] = _unb64(user["id"])
        native["user"] = user
    for key in ("excludeCredentials", "allowCredentials"):
        if native.get(key):
            native[key] = [{**cred, "id": _unb64(cred["id"])} for cred in native[key]]
    return native


def _as_json_credential(attestation: dict) -> dict:
    """O que o navegador manda: os campos binários em base64url.

    O `soft-webauthn` devolve bytes crus (é um autenticador, não um navegador), então esta
    função faz o papel do JS do lado do cliente.
    """
    return {
        "id": _b64url(attestation["rawId"]),
        "rawId": _b64url(attestation["rawId"]),
        "type": attestation["type"],
        "response": {
            key: _b64url(value)
            for key, value in attestation["response"].items()
            if isinstance(value, bytes)
        },
    }


def _enroll(client, person, *, device: VerifyingDevice | None = None, origin="http://testserver"):
    """Cadastra uma passkey de verdade e devolve o aparelho de software."""
    device = device or VerifyingDevice()

    options = client.post(REGISTER_OPTIONS, content_type="application/json")
    assert options.status_code == 200, options.content

    attestation = device.create({"publicKey": _as_device_options(options.json())}, origin)
    response = client.post(
        REGISTER,
        data=json.dumps({"credential": _as_json_credential(attestation), "label": "iPhone da Ana"}),
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    return device


# ── Cadastrar ────────────────────────────────────────────────────────


def test_a_visitor_cannot_enroll(client):
    assert client.post(REGISTER_OPTIONS, content_type="application/json").status_code == 401


def test_enrolling_needs_a_strong_identity(client, person):
    """⚠️ A lei mais importante daqui.

    Quem chegou por link de campanha sabe o número, não as mãos. Deixar essa sessão gravar
    credencial seria alguém cadastrando o PRÓPRIO rosto no acesso de outra pessoa — e passkey
    não expira, então o estrago seria permanente.
    """
    _sign_in(client, person, strength=IDENTITY_NUMBER)

    response = client.post(REGISTER_OPTIONS, content_type="application/json")

    assert response.status_code == 403
    assert response.json()["error_code"] == "identity_confirmation_required"
    # E a copy oferece o caminho, em vez de só barrar.
    assert "Confirme que é você" in response.json()["detail"]


def test_the_write_route_is_gated_too(client, person):
    """Barrar só as opções deixaria a porta dos fundos aberta: quem tem um desafio de antes
    poderia gravar depois de virar sessão fraca."""
    _sign_in(client, person, strength=IDENTITY_NUMBER)

    response = client.post(
        REGISTER, data=json.dumps({"credential": {"id": "x"}}), content_type="application/json",
    )

    assert response.status_code == 403


def test_a_known_device_enrolls_and_the_key_is_stored(client, person):
    from shopman.doorman.models import Passkey

    _sign_in(client, person)  # sem marca ⇒ identidade forte

    _enroll(client, person)

    passkey = Passkey.objects.get()
    assert str(passkey.customer_id) == str(person.uuid)
    assert passkey.label == "iPhone da Ana"
    assert passkey.public_key, "a chave PÚBLICA fica guardada"
    # A privada nunca sai do aparelho — não há campo para ela, e é isso que faz vazar esta
    # tabela não permitir entrar como ninguém.
    assert not hasattr(passkey, "private_key")


def test_the_registration_challenge_is_single_use(client, person):
    """Desafio reaproveitado é replay. Ele sai da sessão na primeira leitura."""
    _sign_in(client, person)
    device = VerifyingDevice()

    options = client.post(REGISTER_OPTIONS, content_type="application/json").json()
    attestation = device.create({"publicKey": _as_device_options(options)}, "http://testserver")
    payload = json.dumps({"credential": _as_json_credential(attestation)})

    first = client.post(REGISTER, data=payload, content_type="application/json")
    assert first.status_code == 200

    again = client.post(REGISTER, data=payload, content_type="application/json")
    assert again.status_code == 400
    assert "expirou" in again.json()["detail"]


# ── Entrar ───────────────────────────────────────────────────────────


def test_signing_in_with_a_passkey_needs_no_phone_and_no_code(client, person):
    """O ponto todo: sem digitar telefone, sem código, sem senha."""
    _sign_in(client, person)
    device = _enroll(client, person)
    client.logout()

    options = client.post(LOGIN_OPTIONS, content_type="application/json")
    assert options.status_code == 200, options.content
    # Sem `allowCredentials`: o navegador oferece o que ELE tem para o nosso domínio.
    assert not options.json().get("allowCredentials")

    assertion = device.get({"publicKey": _as_device_options(options.json())}, "http://testserver")
    response = client.post(
        LOGIN,
        data=json.dumps({"credential": _as_json_credential(assertion)}),
        content_type="application/json",
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["is_authenticated"] is True
    assert body["customer_ref"] == person.ref


def test_a_passkey_session_is_strong_identity(client, person):
    """Nada reduzido, nada a confirmar: é a credencial mais forte que temos."""
    from shopman.storefront.identity import IDENTITY_DEVICE

    _sign_in(client, person)
    device = _enroll(client, person)
    client.logout()

    options = client.post(LOGIN_OPTIONS, content_type="application/json").json()
    assertion = device.get({"publicKey": _as_device_options(options)}, "http://testserver")
    client.post(
        LOGIN,
        data=json.dumps({"credential": _as_json_credential(assertion)}),
        content_type="application/json",
    )

    assert client.session[IDENTITY_SESSION_KEY] == IDENTITY_DEVICE


def test_the_cart_survives_the_passkey_login(client, person):
    """Sacola anônima sobrevive à troca de sessão, como em todo login daqui."""
    _sign_in(client, person)
    device = _enroll(client, person)
    client.logout()

    session = client.session
    session["cart_session_key"] = "sacola-passkey"
    session.save()

    options = client.post(LOGIN_OPTIONS, content_type="application/json").json()
    assertion = device.get({"publicKey": _as_device_options(options)}, "http://testserver")
    client.post(
        LOGIN,
        data=json.dumps({"credential": _as_json_credential(assertion)}),
        content_type="application/json",
    )

    assert client.session["cart_session_key"] == "sacola-passkey"


# ── O que nunca pode passar ──────────────────────────────────────────


def test_a_credential_we_never_saw_is_refused(client, person):
    """Aparelho de outra pessoa (ou de outro site) não entra."""
    _sign_in(client, person)
    _enroll(client, person)
    client.logout()

    intruso = VerifyingDevice()
    options = client.post(LOGIN_OPTIONS, content_type="application/json").json()
    # O intruso precisa de uma credencial sua para assinar; ela não está na nossa base.
    intruso.cred_init(options["rpId"], b"outro-usuario")
    assertion = intruso.get({"publicKey": _as_device_options(options)}, "http://testserver")

    response = client.post(
        LOGIN,
        data=json.dumps({"credential": _as_json_credential(assertion)}),
        content_type="application/json",
    )

    assert response.status_code == 400
    # Mensagem única: distinguir "não existe" de "não confere" contaria a quem tenta se
    # aquela credencial existe na nossa base.
    assert response.json()["detail"] == "Não reconhecemos esta chave. Entre pelo WhatsApp."


def test_a_replayed_assertion_is_refused(client, person):
    """⚠️ A mesma assinatura duas vezes é replay — e é o ataque óbvio contra desafio-resposta."""
    _sign_in(client, person)
    device = _enroll(client, person)
    client.logout()

    options = client.post(LOGIN_OPTIONS, content_type="application/json").json()
    assertion = device.get({"publicKey": _as_device_options(options)}, "http://testserver")
    payload = json.dumps({"credential": _as_json_credential(assertion)})

    assert client.post(LOGIN, data=payload, content_type="application/json").status_code == 200
    client.logout()

    replay = client.post(LOGIN, data=payload, content_type="application/json")
    assert replay.status_code == 400


def test_an_assertion_for_another_origin_is_refused(client, person):
    """A imunidade a phishing, exercitada: site clonado assina para o domínio DELE."""
    _sign_in(client, person)
    device = _enroll(client, person)
    client.logout()

    options = client.post(LOGIN_OPTIONS, content_type="application/json").json()
    assertion = device.get({"publicKey": _as_device_options(options)}, "https://site-clonado.example")

    response = client.post(
        LOGIN,
        data=json.dumps({"credential": _as_json_credential(assertion)}),
        content_type="application/json",
    )

    assert response.status_code == 400


def test_an_orphan_credential_never_opens_a_session(client, person):
    """Cliente apagado e chave sobrando: recusa, e deixa rastro no log."""
    from shopman.doorman.models import Passkey

    _sign_in(client, person)
    device = _enroll(client, person)
    client.logout()

    Passkey.objects.update(customer_id="00000000-0000-0000-0000-000000000000")

    options = client.post(LOGIN_OPTIONS, content_type="application/json").json()
    assertion = device.get({"publicKey": _as_device_options(options)}, "http://testserver")
    response = client.post(
        LOGIN,
        data=json.dumps({"credential": _as_json_credential(assertion)}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Não reconhecemos esta chave. Entre pelo WhatsApp."


# ── A lista que a pessoa vê e revoga ─────────────────────────────────


LIST_URL = "/api/v1/account/passkeys/"


def test_the_list_shows_the_nickname_and_never_the_key(client, person):
    """Sem apelido, revogar seria escolher entre dois identificadores base64 — não é escolha.

    E a chave pública não desce: ela não tem uso na tela, e o que não é preciso mandar não se
    manda.
    """
    _sign_in(client, person)
    _enroll(client, person)

    response = client.get(LIST_URL)

    assert response.status_code == 200, response.content
    rows = response.json()["passkeys"]
    assert len(rows) == 1
    assert rows[0]["label"] == "iPhone da Ana"
    body = json.dumps(response.json())
    assert "public_key" not in body


def test_revoking_removes_the_credential(client, person):
    from shopman.doorman.models import Passkey

    _sign_in(client, person)
    _enroll(client, person)
    credential_id = Passkey.objects.get().credential_id

    response = client.delete(f"{LIST_URL}{credential_id}/")

    assert response.status_code == 200, response.content
    assert not Passkey.objects.exists()


def test_nobody_revokes_a_credential_of_someone_else(client, person, db):
    """⚠️ Escopado ao cliente, e o id de terceiro responde igual ao inexistente.

    Distinguir 404 de 403 aqui contaria a quem tenta quais credenciais existem na base.
    """
    from shopman.doorman.models import Passkey
    from shopman.guestman.models import Customer

    outra = Customer.objects.create(ref="CLI-OUTRA", first_name="Bia", phone="+5543999995555")
    alheia = Passkey.objects.create(
        customer_id=outra.uuid, credential_id="credencial-da-bia", public_key="x",
    )

    _sign_in(client, person)
    response = client.delete(f"{LIST_URL}{alheia.credential_id}/")

    assert response.status_code == 404
    assert Passkey.objects.filter(credential_id=alheia.credential_id).exists()

    inexistente = client.delete(f"{LIST_URL}nao-existe/")
    assert inexistente.status_code == 404


def test_a_weak_session_can_neither_see_nor_revoke(client, person):
    """Quem chegou por link não mexe no acesso rápido: seria empurrar a dona de volta para o
    caminho lento sem ela ter pedido."""
    _sign_in(client, person, strength=IDENTITY_NUMBER)

    listed = client.get(LIST_URL)
    assert listed.status_code == 403
    assert listed.json()["error_code"] == "identity_confirmation_required"

    revoked = client.delete(f"{LIST_URL}qualquer/")
    assert revoked.status_code == 403
