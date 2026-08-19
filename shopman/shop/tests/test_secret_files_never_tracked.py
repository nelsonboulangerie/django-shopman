"""Nenhum arquivo de credencial pode estar versionado. O repo é PÚBLICO.

Segredo que entra no histórico não sai de graça: o conserto é rotacionar a
credencial, não apagar o commit. O push protection do GitHub cobre padrão de
PROVEDOR reconhecível (chave Stripe, token GitHub) — ele NÃO reconhece
certificado, que é binário opaco. O certificado da Efí é exatamente isso.

Então a regra vira teste, no espírito da casa: guarda que grita, não prosa que
se esquece. O `.gitignore` impede o descuido; este teste impede o `-f`.
"""

from __future__ import annotations

import pathlib
import re
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[3]

# Extensões de material criptográfico. Casadas no NOME, não no conteúdo — o
# ponto é nunca precisar abrir o arquivo para saber que ele não devia estar aqui.
SECRET_SUFFIXES = re.compile(r"\.(pem|p12|pfx|key|jks|keystore|crt|cer)$", re.I)

# `.env` de ambiente. O `.env.example` é exceção deliberada: existe para
# documentar as chaves, sempre sem valor.
ENV_FILE = re.compile(r"(^|/)\.env(\.|$)", re.I)
ENV_ALLOWED = {".env.example"}


def _tracked() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    )
    return out.stdout.splitlines()


@pytest.fixture(scope="module")
def tracked():
    return _tracked()


def test_no_certificate_or_key_is_tracked(tracked):
    offenders = [p for p in tracked if SECRET_SUFFIXES.search(p)]
    assert not offenders, (
        "material criptográfico versionado num repo PÚBLICO:\n  "
        + "\n  ".join(sorted(offenders))
        + "\n\nRotacione a credencial — apagar o commit não basta."
    )


def test_no_environment_file_is_tracked(tracked):
    offenders = [p for p in tracked if ENV_FILE.search(p) and p not in ENV_ALLOWED]
    assert not offenders, (
        "arquivo de ambiente versionado (só `.env.example` é permitido):\n  "
        + "\n  ".join(sorted(offenders))
    )


def test_gitignore_still_blocks_the_patterns():
    """O teste acima pega o que já entrou; este pega o `.gitignore` sendo afrouxado."""
    probes = [
        "efi-producao.p12", "cert.pem", "server.key", "keystore.jks", ".env.production",
    ]
    not_ignored = [
        p for p in probes
        if subprocess.run(
            ["git", "check-ignore", "-q", p], cwd=REPO
        ).returncode != 0
    ]
    assert not not_ignored, (
        "o .gitignore deixou de bloquear:\n  " + "\n  ".join(not_ignored)
    )


def test_the_example_env_is_still_allowed():
    """A exceção precisa continuar existindo: ela documenta as chaves."""
    assert subprocess.run(
        ["git", "check-ignore", "-q", ".env.example"], cwd=REPO
    ).returncode != 0, ".env.example virou ignorado — a documentação das chaves se perde"
