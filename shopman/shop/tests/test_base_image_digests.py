"""Imagens base fixadas por digest, e a CI construindo com o MESMO digest.

O tag (``python:3.12-slim``) anda sozinho: o build de hoje e o de amanhã podem sair
de bases diferentes sem nenhum commit. O digest ``@sha256`` fixa a imagem exata. A
CI troca só o REGISTRO (espelho no GHCR, ``ci-image-mirror.yml``), nunca a imagem:
se o build-arg da CI carregar outro digest, a CI prova uma base que o deploy não usa.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]
DOCKERFILES = ("Dockerfile", "surfaces/Dockerfile.surface", "surfaces/Dockerfile.operator-group")
WORKFLOWS = ("runtime-gate.yml", "surfaces-gate.yml", "operator-groups-gate.yml")
_DIGEST = r"@sha256:[0-9a-f]{64}$"


def _pinned_bases() -> dict[str, str]:
    """``nome:tag`` → ``nome:tag@sha256:...`` de cada base dos Dockerfiles."""
    pinned: dict[str, str] = {}
    for name in DOCKERFILES:
        source = (ROOT / name).read_text()
        syntax = re.search(r"^# syntax=(\S+)$", source, re.M)
        assert syntax and re.search(_DIGEST, syntax.group(1)), f"{name}: frontend sem digest"
        refs = [syntax.group(1).removeprefix("docker/")]
        for arg in re.findall(r"^ARG (?:PYTHON|NODE)_IMAGE=(\S+)$", source, re.M):
            assert re.search(_DIGEST, arg), f"{name}: base {arg} sem digest"
            refs.append(arg)
        for ref in refs:
            base = ref.split("@", 1)[0]
            assert pinned.setdefault(base, ref) == ref, f"{base} com digests diferentes entre Dockerfiles"
    return pinned


def test_dockerfile_bases_are_pinned_by_digest():
    assert set(_pinned_bases()) == {"dockerfile:1", "python:3.12-slim", "node:22-alpine"}


def test_ci_mirror_build_args_carry_the_same_digest():
    pinned = _pinned_bases()
    seen = 0
    for workflow in WORKFLOWS:
        source = (ROOT / ".github" / "workflows" / workflow).read_text()
        for ref in re.findall(r"(?:IMAGE|SYNTAX)=ghcr\.io/nelsonboulangerie/ci-mirror/(\S+)", source):
            base = ref.split("@", 1)[0]
            assert base in pinned, f"{workflow}: {base} não é base de Dockerfile"
            assert ref == pinned[base], f"{workflow}: {ref} diverge do Dockerfile ({pinned[base]})"
            seen += 1
    assert seen >= 6
