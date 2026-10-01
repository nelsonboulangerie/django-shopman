"""Onde moram os arquivos de USUÁRIO (``STORAGES["default"]``).

Por que existe: o contêiner da DigitalOcean não tem disco persistente. Com o
``FileSystemStorage`` de sempre, o arquivo salvo em ``media/`` vive até o próximo
deploy e some; a foto que o ``/recipes/new`` manda evapora. O dono decidiu
(D6, 01/10/2026) guardar esses arquivos no Cloudflare R2, que fala a API do S3.

A troca fica atrás de uma env que nasce DESLIGADA:

- ``SHOPMAN_MEDIA_STORAGE`` vazio ou ``local`` (padrão): nada muda, o default
  segue ``django.core.files.storage.FileSystemStorage``.
- ``SHOPMAN_MEDIA_STORAGE=r2``: o default vira ``storages.backends.s3.S3Storage``
  apontado para ``https://<R2_ACCOUNT_ID>.r2.cloudflarestorage.com``, região
  ``auto``, com ``R2_BUCKET``, ``R2_ACCESS_KEY_ID`` e ``R2_SECRET_ACCESS_KEY``.

Ligada sem credencial, o boot CAI com ``ImproperlyConfigured`` listando o que
falta. Cair em silêncio no disco local seria o pior caso: a casa acreditaria que
os arquivos estão guardados e eles sumiriam no deploy seguinte. Valor
desconhecido na env (``R2``, ``s3``, erro de digitação) também cai.

Bucket PRIVADO com URL assinada, por padrão:

- o R2 não tem ACL por objeto, então ``default_acl`` fica ``None`` (mandar
  ``public-read`` não tornaria nada público e só convida erro);
- ``querystring_auth=True``: cada ``.url`` sai assinada e vence em
  ``R2_URL_EXPIRE_SECONDS`` (padrão 3600). Arquivo de usuário pode ter dado
  pessoal (foto, comprovante); quem não tem o link assinado não lê. Tornar o
  bucket público por domínio próprio é decisão separada, não padrão;
- ``file_overwrite=False``: dois uploads com o mesmo nome não se apagam, o
  segundo ganha sufixo.

O ``client_config`` liga ``when_required`` nos checksums: o boto3 1.36+ manda
CRC32 em todo upload, o R2 passou a aceitar, e o modo ``when_required`` mantém o
upload funcionando mesmo que essa compatibilidade oscile.

O estático (``STORAGES["staticfiles"]``) não passa por aqui: segue no WhiteNoise.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from django.core.exceptions import ImproperlyConfigured

LOCAL_BACKEND = "django.core.files.storage.FileSystemStorage"
R2_BACKEND = "storages.backends.s3.S3Storage"

FLAG_ENV = "SHOPMAN_MEDIA_STORAGE"
R2_REQUIRED_ENVS = ("R2_ACCOUNT_ID", "R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")
R2_EXPIRE_ENV = "R2_URL_EXPIRE_SECONDS"
DEFAULT_URL_EXPIRE_SECONDS = 3600


def media_storage(environ: Mapping[str, str] | None = None) -> dict:
    """Devolve a entrada ``STORAGES["default"]`` conforme o ambiente."""
    env = os.environ if environ is None else environ
    mode = (env.get(FLAG_ENV) or "").strip().lower()

    if mode in ("", "local"):
        return {"BACKEND": LOCAL_BACKEND}
    if mode != "r2":
        raise ImproperlyConfigured(
            f"{FLAG_ENV}={env.get(FLAG_ENV)!r} não é um valor conhecido. Use 'local' (padrão) ou 'r2'."
        )

    values = {name: (env.get(name) or "").strip() for name in R2_REQUIRED_ENVS}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ImproperlyConfigured(
            f"{FLAG_ENV}=r2 sem credencial do Cloudflare R2. Faltam: {', '.join(missing)}. "
            "Sem elas o arquivo iria para o disco do contêiner e sumiria no próximo deploy."
        )

    raw_expire = (env.get(R2_EXPIRE_ENV) or "").strip()
    try:
        expire = int(raw_expire) if raw_expire else DEFAULT_URL_EXPIRE_SECONDS
    except ValueError:
        expire = 0
    if expire <= 0:
        raise ImproperlyConfigured(f"{R2_EXPIRE_ENV}={raw_expire!r} precisa ser um inteiro positivo de segundos.")

    from botocore.config import Config

    return {
        "BACKEND": R2_BACKEND,
        "OPTIONS": {
            "endpoint_url": f"https://{values['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
            "region_name": "auto",
            "bucket_name": values["R2_BUCKET"],
            "access_key": values["R2_ACCESS_KEY_ID"],
            "secret_key": values["R2_SECRET_ACCESS_KEY"],
            "default_acl": None,
            "querystring_auth": True,
            "querystring_expire": expire,
            "file_overwrite": False,
            "client_config": Config(
                signature_version="s3v4",
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        },
    }
