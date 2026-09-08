"""Domínio morto não volta pelo arquivo, e host declarado tem rota.

Duas coisas que o spec versionado deixou passar, medidas em 08/09/2026 contra o
app vivo:

- `.do/app.alpha-subdomains.yaml` ainda trazia `alpha.nelsonboulangerie.com.br`
  como **PRIMARY**. Esse domínio está morto desde o corte de 01/09 e um
  `apps update` o teria ressuscitado — que é exatamente o acidente de 01/09,
  quando uma sessão aplicou um snapshot velho e devolveu os `staging.*` que
  outra tinha acabado de remover.
- `backup.boulangerie.com.br` estava **no ar e fora do arquivo**. O update
  apaga domínio com o mesmo silêncio com que apaga env, e o atalho do cofre
  teria sumido — apesar de o arquivo declarar `SHOPMAN_BACKUP_SHEET_HOST`
  apontando para ele.

O drift-check (`scripts/check_do_spec_drift.py`) pega os dois, mas só na frente
do app vivo, com credencial da DigitalOcean. Estes testes são a metade que roda
na CI: eles não sabem o que está no ar, e não precisam — sabem o que o próprio
arquivo promete e o que a casa já decidiu que está morto.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[3]
DEPLOY_SPECS = (
    ROOT / ".do" / "app.subdomains.yaml",
    ROOT / ".do" / "app.alpha-subdomains.yaml",
)

#: Hosts cortados em 01/09/2026 por decisão do dono, sem alias e para sempre.
#: A loja é `menu.nelsonboulangerie.com.br`.
DEAD_HOSTS = (
    "alpha.nelsonboulangerie.com.br",
    "staging.nelsonboulangerie.com.br",
    "api.staging.nelsonboulangerie.com.br",
    "admin.staging.nelsonboulangerie.com.br",
)


def _spec(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _domains(spec: dict) -> dict[str, str]:
    return {
        entry["domain"]: (entry.get("type") or "ALIAS")
        for entry in spec.get("domains") or []
        if entry.get("domain")
    }


def _authorities(spec: dict) -> set[str]:
    """Hosts com regra de ingress explícita. O catch-all fica de fora."""
    out = set()
    for rule in (spec.get("ingress") or {}).get("rules") or []:
        authority = (rule.get("match") or {}).get("authority") or {}
        host = authority.get("exact") or authority.get("prefix")
        if host:
            out.add(host)
    return out


def _has_catch_all(spec: dict) -> bool:
    return any(
        not ((rule.get("match") or {}).get("authority") or {})
        for rule in (spec.get("ingress") or {}).get("rules") or []
    )


def _env_values(spec: dict) -> dict[str, str]:
    return {
        entry["key"]: str(entry.get("value") or "")
        for entry in spec.get("envs") or []
        if entry.get("key")
    }


@pytest.mark.parametrize("path", DEPLOY_SPECS, ids=lambda p: p.name)
def test_deploy_spec_never_resurrects_a_dead_host(path: pathlib.Path):
    """Comentário pode citar o morto; configuração, não.

    A varredura é sobre **valores** — domínio, autoridade de ingress e valor de
    env. O aviso em prosa que explica por que o host está morto é justamente o
    que se quer manter no arquivo.
    """
    spec = _spec(path)
    configured = set(_domains(spec)) | _authorities(spec)
    for value in _env_values(spec).values():
        configured.update(part.strip() for part in value.replace("https://", "").split(","))

    offenders = sorted(host for host in DEAD_HOSTS if host in configured)
    assert not offenders, (
        f"{path.name} reintroduz host cortado em 01/09: {', '.join(offenders)}. "
        "A loja é menu.nelsonboulangerie.com.br."
    )


@pytest.mark.parametrize("path", DEPLOY_SPECS, ids=lambda p: p.name)
def test_every_declared_domain_is_routed(path: pathlib.Path):
    """Domínio sem rota é domínio que responde 404 depois de propagar o DNS."""
    spec = _spec(path)
    authorities = _authorities(spec)
    catch_all = _has_catch_all(spec)

    unrouted = sorted(
        domain
        for domain, kind in _domains(spec).items()
        if domain not in authorities and not (kind == "PRIMARY" and catch_all)
    )
    assert not unrouted, f"{path.name}: domínio declarado sem regra de ingress: {unrouted}"


@pytest.mark.parametrize("path", DEPLOY_SPECS, ids=lambda p: p.name)
def test_backup_sheet_host_is_a_declared_domain(path: pathlib.Path):
    """O atalho do cofre é env + domínio + rota — as três, ou nenhuma.

    Este é o teste que teria pego o buraco: `SHOPMAN_BACKUP_SHEET_HOST` entrou
    nos dois specs no PR #546, e o domínio que ele nomeia não entrou em nenhum.
    """
    spec = _spec(path)
    host = _env_values(spec).get("SHOPMAN_BACKUP_SHEET_HOST")
    if not host:
        pytest.skip("spec não declara o atalho do cofre")
    assert host in _domains(spec), (
        f"{path.name}: SHOPMAN_BACKUP_SHEET_HOST={host} não está na lista de domínios"
    )
    assert host in _authorities(spec), (
        f"{path.name}: SHOPMAN_BACKUP_SHEET_HOST={host} não tem regra de ingress"
    )
