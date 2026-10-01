"""Arquivos de usuário no Cloudflare R2, atrás de flag desligada (config/media_storage.py).

Sem rede: só a configuração resolvida e a instância do storage são inspecionadas.
"""

from __future__ import annotations

import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from config.media_storage import LOCAL_BACKEND, R2_BACKEND, R2_REQUIRED_ENVS, media_storage

R2_ENV = {
    "SHOPMAN_MEDIA_STORAGE": "r2",
    "R2_ACCOUNT_ID": "abc123",
    "R2_BUCKET": "nelson-arquivos",
    "R2_ACCESS_KEY_ID": "test-access-key",
    "R2_SECRET_ACCESS_KEY": "test-secret-key",
}


@pytest.mark.parametrize("environ", [{}, {"SHOPMAN_MEDIA_STORAGE": ""}, {"SHOPMAN_MEDIA_STORAGE": "local"}])
def test_flag_off_keeps_todays_local_disk(environ):
    assert media_storage(environ) == {"BACKEND": LOCAL_BACKEND}


def test_suite_settings_keep_local_disk():
    assert settings.STORAGES["default"] == {"BACKEND": LOCAL_BACKEND}


def test_flag_on_points_s3storage_at_the_r2_bucket():
    config = media_storage(R2_ENV)
    options = config["OPTIONS"]

    assert config["BACKEND"] == R2_BACKEND
    assert options["endpoint_url"] == "https://abc123.r2.cloudflarestorage.com"
    assert options["region_name"] == "auto"
    assert options["bucket_name"] == "nelson-arquivos"
    assert options["access_key"] == "test-access-key"
    assert options["secret_key"] == "test-secret-key"
    assert options["default_acl"] is None
    assert options["querystring_auth"] is True
    assert options["querystring_expire"] == 3600
    assert options["file_overwrite"] is False


def test_flag_on_builds_a_working_s3storage_instance():
    from storages.backends.s3 import S3Storage

    storage = S3Storage(**media_storage(R2_ENV)["OPTIONS"])

    assert storage.bucket_name == "nelson-arquivos"
    assert storage.endpoint_url == "https://abc123.r2.cloudflarestorage.com"
    assert storage.region_name == "auto"
    assert storage.default_acl is None
    assert storage.file_overwrite is False
    # A URL sai assinada e com o endpoint do R2, sem tocar a rede.
    url = storage.url("receitas/foto.jpg")
    assert url.startswith("https://")
    assert "r2.cloudflarestorage.com" in url
    assert "X-Amz-Signature=" in url


@pytest.mark.parametrize("missing", R2_REQUIRED_ENVS)
def test_flag_on_without_one_credential_fails_loud(missing):
    environ = {**R2_ENV, missing: "  "}
    with pytest.raises(ImproperlyConfigured, match=missing):
        media_storage(environ)


def test_flag_on_without_any_credential_lists_all_of_them():
    with pytest.raises(ImproperlyConfigured) as excinfo:
        media_storage({"SHOPMAN_MEDIA_STORAGE": "r2"})
    for name in R2_REQUIRED_ENVS:
        assert name in str(excinfo.value)


@pytest.mark.parametrize("value", ["R3", "s3", "true", "1"])
def test_unknown_flag_value_fails_loud(value):
    with pytest.raises(ImproperlyConfigured, match="SHOPMAN_MEDIA_STORAGE"):
        media_storage({"SHOPMAN_MEDIA_STORAGE": value})


def test_flag_value_is_case_insensitive():
    assert media_storage({**R2_ENV, "SHOPMAN_MEDIA_STORAGE": "R2"})["BACKEND"] == R2_BACKEND


@pytest.mark.parametrize("value", ["0", "-5", "uma hora"])
def test_invalid_url_expiry_fails_loud(value):
    with pytest.raises(ImproperlyConfigured, match="R2_URL_EXPIRE_SECONDS"):
        media_storage({**R2_ENV, "R2_URL_EXPIRE_SECONDS": value})


def test_url_expiry_is_configurable():
    assert media_storage({**R2_ENV, "R2_URL_EXPIRE_SECONDS": "600"})["OPTIONS"]["querystring_expire"] == 600
