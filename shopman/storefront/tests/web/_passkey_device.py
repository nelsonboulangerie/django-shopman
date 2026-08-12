"""Um autenticador de software que marca "usuário verificado".

⚠️ Existe porque o `soft-webauthn` fixa as flags do authenticator data em `0x41`
(dado atestado + usuário presente) e **não** liga o bit de **user verified** (`0x04`) — nem
tem parâmetro para isso. "Presente" é só "alguém tocou o aparelho"; "verificado" é rosto,
digital ou PIN.

A tentação era baixar `require_user_verification` para `False` no serviço e fazer o teste
passar. Isso trocaria a segurança de PRODUÇÃO pela conveniência do dublê: um aparelho
destravado na mão de outra pessoa passaria a entrar. Então o que se estende é o dublê.

Só os dois métodos precisam de sobrescrita, e eles duplicam a montagem do `soft-webauthn`
porque a flag entra ANTES da assinatura: em `get`, a assinatura cobre o authenticator data, e
remendar os bytes depois de assinar inutilizaria a assinatura.
"""

from __future__ import annotations

import json
from base64 import urlsafe_b64encode
from hashlib import sha256
from struct import pack

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from soft_webauthn import SoftWebauthnDevice

#: Flags do authenticator data. `0x04` é o bit que diz "o usuário foi VERIFICADO" — é o que a
#: nossa verificação exige, e é o que separa "tocou" de "provou que é você".
USER_PRESENT = 0x01
USER_VERIFIED = 0x04
ATTESTED_CREDENTIAL_DATA = 0x40


class VerifyingDevice(SoftWebauthnDevice):
    """Autenticador que exige e reporta verificação de usuário, como um celular real."""

    def create(self, options, origin):
        attestation = super().create(options, origin)

        # `fmt: none` (o que o `soft-webauthn` usa) não assina o authenticator data, então
        # ligar a flag depois é seguro aqui — e é o único ponto onde isso vale.
        import cbor2

        att_obj = cbor2.loads(attestation["response"]["attestationObject"])
        auth_data = bytearray(att_obj["authData"])
        auth_data[32] |= USER_VERIFIED
        att_obj["authData"] = bytes(auth_data)
        attestation["response"]["attestationObject"] = cbor2.dumps(att_obj)
        return attestation

    def get(self, options, origin):
        """Assertion com a flag de verificação — montada do zero porque a flag é assinada."""
        if self.rp_id != options["publicKey"]["rpId"]:
            raise ValueError("Requested rpID does not match current credential")

        self.sign_count += 1

        client_data = json.dumps({
            "type": "webauthn.get",
            "challenge": urlsafe_b64encode(
                options["publicKey"]["challenge"]
            ).decode("ascii").rstrip("="),
            "origin": origin,
        }).encode("utf-8")
        client_data_hash = sha256(client_data).digest()

        rp_id_hash = sha256(self.rp_id.encode("ascii")).digest()
        flags = bytes([USER_PRESENT | USER_VERIFIED])
        authenticator_data = rp_id_hash + flags + pack(">I", self.sign_count)

        signature = self.private_key.sign(
            authenticator_data + client_data_hash, ec.ECDSA(hashes.SHA256()),
        )
        return {
            "id": urlsafe_b64encode(self.credential_id),
            "rawId": self.credential_id,
            "response": {
                "authenticatorData": authenticator_data,
                "clientDataJSON": client_data,
                "signature": signature,
                "userHandle": self.user_handle,
            },
            "type": "public-key",
        }
