"""Um autenticador WebAuthn de software, nosso, para os testes de passkey.

⚠️ **Por que é nosso e não de biblioteca.** A primeira versão usava `soft-webauthn`, e isso
custou caro: ele arrasta `fido2>=1.0,<2.0` (faixa larguíssima), enquanto o `webauthn` de runtime
pede `cryptography>=46` e `cbor2>=5.6.5`. Duas bibliotecas de WebAuthn disputando as mesmas
transitivas fizeram o pip explorar o produto cartesiano e desistir:

    error: resolution-too-deep

E não quebrou só o meu teste: quebrou o `pip install` do repositório, ou seja o CI de **todas**
as frentes abertas, incluindo a de leitor de crachá do PDV, que não tem nada a ver com passkey.
Outra sessão apagou o incêndio pinando `fido2`; isto aqui remove a causa — uma biblioteca de
WebAuthn, não duas.

O que este arquivo faz é o que um celular faz: guarda uma chave privada, monta o
`authenticator data` e assina. São ~70 linhas de `cryptography` + `cbor2`, as duas já exigidas
pelo `webauthn` — nenhuma dependência nova.

⚠️ E ele marca **user verified** (flag `0x04`), que era o motivo de eu já ter subclassado o
`soft-webauthn` antes: o dublê de lá só ligava "usuário presente". "Presente" é alguém tocando o
aparelho; "verificado" é rosto, digital ou PIN — e é isso que o nosso serviço exige. A tentação
era baixar `require_user_verification` para o teste passar, o que trocaria a segurança de
produção pela conveniência do dublê.
"""

from __future__ import annotations

import json
import os
from base64 import urlsafe_b64encode
from hashlib import sha256
from struct import pack

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

#: Flags do authenticator data (WebAuthn §6.1).
USER_PRESENT = 0x01
USER_VERIFIED = 0x04
ATTESTED_CREDENTIAL_DATA = 0x40

#: AAGUID zerado = autenticador que não se identifica. É o que uma passkey de plataforma faz.
AAGUID = b"\x00" * 16

#: ES256 (ECDSA com P-256 e SHA-256) — o algoritmo que todo autenticador real suporta.
COSE_ALG_ES256 = -7


class VerifyingDevice:
    """Um autenticador de plataforma que exige e reporta verificação de usuário."""

    def __init__(self) -> None:
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(32)
        self.sign_count = 0
        self.rp_id = ""
        self.user_handle = b""

    # ── Cadastrar ────────────────────────────────────────────────────

    def create(self, options: dict, origin: str) -> dict:
        """O que `navigator.credentials.create()` devolveria."""
        public_key = options["publicKey"]
        self.rp_id = public_key["rp"]["id"]
        self.user_handle = public_key["user"]["id"]

        client_data = self._client_data("webauthn.create", public_key["challenge"], origin)
        auth_data = self._authenticator_data(attested=True)

        # `fmt: none` — atestação anônima, que é o que passkey de plataforma usa na prática.
        attestation_object = cbor2.dumps({
            "fmt": "none",
            "attStmt": {},
            "authData": auth_data,
        })
        return {
            "id": urlsafe_b64encode(self.credential_id),
            "rawId": self.credential_id,
            "type": "public-key",
            "response": {
                "clientDataJSON": client_data,
                "attestationObject": attestation_object,
            },
        }

    # ── Entrar ───────────────────────────────────────────────────────

    def get(self, options: dict, origin: str) -> dict:
        """O que `navigator.credentials.get()` devolveria."""
        public_key = options["publicKey"]
        if self.rp_id and self.rp_id != public_key["rpId"]:
            raise ValueError("rpId pedido não é o da credencial")

        self.sign_count += 1
        client_data = self._client_data("webauthn.get", public_key["challenge"], origin)
        auth_data = self._authenticator_data(attested=False)

        # ⚠️ A assinatura cobre `authData + hash(clientData)`, nesta ordem. É por isso que a
        # flag de verificação entra ANTES de assinar: remendar os bytes depois inutilizaria a
        # assinatura, e o erro apareceria como "não reconhecemos esta chave".
        signature = self.private_key.sign(
            auth_data + sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()),
        )
        return {
            "id": urlsafe_b64encode(self.credential_id),
            "rawId": self.credential_id,
            "type": "public-key",
            "response": {
                "clientDataJSON": client_data,
                "authenticatorData": auth_data,
                "signature": signature,
                "userHandle": self.user_handle,
            },
        }

    # ── As peças do protocolo ────────────────────────────────────────

    def _client_data(self, ceremony: str, challenge: bytes, origin: str) -> bytes:
        """O `clientDataJSON`: quem pediu, o que, e de qual ORIGEM.

        A origem entra aqui, e é o que dá a imunidade a phishing: um site clonado assina para
        a origem dele, e a verificação recusa.
        """
        return json.dumps({
            "type": ceremony,
            "challenge": urlsafe_b64encode(challenge).decode("ascii").rstrip("="),
            "origin": origin,
        }).encode("utf-8")

    def _authenticator_data(self, *, attested: bool) -> bytes:
        flags = USER_PRESENT | USER_VERIFIED
        if attested:
            flags |= ATTESTED_CREDENTIAL_DATA

        data = sha256(self.rp_id.encode("ascii")).digest()
        data += bytes([flags])
        data += pack(">I", self.sign_count)
        if attested:
            data += AAGUID
            data += pack(">H", len(self.credential_id))
            data += self.credential_id
            data += self._cose_public_key()
        return data

    def _cose_public_key(self) -> bytes:
        """A chave pública em COSE_Key — o formato que o WebAuthn transporta."""
        numbers = self.private_key.public_key().public_numbers()
        return cbor2.dumps({
            1: 2,                 # kty: EC2
            3: COSE_ALG_ES256,    # alg
            -1: 1,                # crv: P-256
            -2: numbers.x.to_bytes(32, "big"),
            -3: numbers.y.to_bytes(32, "big"),
        })

    def cred_init(self, rp_id: str, user_handle: bytes) -> None:
        """Preparar uma credencial sem cadastrá-la — usado para simular um intruso."""
        self.rp_id = rp_id
        self.user_handle = user_handle
