from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID


def synthetic_certificate(*, pfx=False, start=-1, end=1, password=b"", include_private_key=True):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "local-test.invalid")])
    now = datetime.now(UTC)
    certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now + timedelta(days=start)).not_valid_after(now + timedelta(days=end))
        .sign(key, hashes.SHA256()))
    if pfx:
        encryption = serialization.BestAvailableEncryption(password) if password else serialization.NoEncryption()
        return pkcs12.serialize_key_and_certificates(
            b"test",
            key if include_private_key else None,
            certificate,
            None,
            encryption,
        )
    certificate_pem = certificate.public_bytes(serialization.Encoding.PEM)
    if not include_private_key:
        return certificate_pem
    private_key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    return certificate_pem + private_key_pem
