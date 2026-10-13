#!/usr/bin/env python
"""Ferramentas do ENSAIO GERAL da virada: tudo fora do app vivo.

O roteiro é ``docs/runbooks/ensaio-geral-da-virada.md``. Três subcomandos, todos
só de arquivo (nenhum ``doctl``, nenhuma rede, nenhum ``apps update``):

``depois``
    Lê o spec guardado na abertura (``antes``) e escreve o spec como ele ficaria
    depois de o dono colar o delta do dia D (a tabela ``DELTA`` de
    ``scripts/golive_spec_delta.py``). Com ele o ensaio roda o delta, o
    ``production-readiness`` em modo alvo e o ``doctl apps propose`` (validação
    da DO, sem aplicar) contra o estado do dia D, sem o dia D ter acontecido.
    Segredo que o dia D troca vira marcador em texto (``ENSAIO-NAO-APLICAR-…``,
    tipo ``SECRET``); a chave publicável do Stripe vira ``pk_live_ENSAIO…``.

``reapontar``
    Escreve o spec com uma linha trocada: o ``cluster_name`` do banco do app
    (componente ``postgres``) apontando para o cluster restaurado. É o arquivo
    do passo "Reapontar" do rollback de dado (cutover §0b); o ensaio prova que o
    diff é de uma linha e que os ``EV[...]`` ficam intactos.

``env``
    Escreve um arquivo ``export CHAVE='valor'`` com o env efetivo de um
    componente Django do spec (o do app, com o do componente por cima), para
    rodar ``manage.py check --deploy`` (SHOPMAN_E026/E027 inclusive) e o app
    localmente contra o banco restaurado. Segredo do spec nunca é lido: vira
    valor SINTÉTICO (não autentica em provedor nenhum) ou sai da lista, e as
    referências ``${...}`` do App Platform viram as URLs do ensaio.

Nenhum arquivo destes pode ser aplicado no app vivo. Os três se recusam a
escrever dentro do repositório: o ``antes`` tem segredos cifrados e o ``env``
tem valores sintéticos que não têm o que fazer num commit.

Saída: 0 escreveu; 2 entrada inválida (spec ilegível, caminho dentro do
repositório, componente inexistente, falta de argumento).
"""

from __future__ import annotations

import argparse
import copy
import re
import secrets
import shlex
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    import yaml
except ImportError as exc:  # pragma: no cover - o .venv da raiz tem PyYAML
    print("PyYAML ausente: rode com .venv/bin/python", file=sys.stderr)
    raise SystemExit(2) from exc

from scripts import golive_spec_delta as delta  # noqa: E402

#: Prefixo de todo valor que este script inventa. Quem achar isto num painel
#: sabe de onde veio e que não é credencial.
MARK = "ENSAIO-NAO-APLICAR"
HEADER = (
    "# ENSAIO GERAL DA VIRADA: gerado por scripts/golive_ensaio.py.\n"
    "# NUNCA aplicar no app vivo (doctl apps update / painel). Ver\n"
    "# docs/runbooks/ensaio-geral-da-virada.md.\n"
)

_REF = re.compile(r"\$\{[^}]+\}")

#: Segredos que o ``env`` não sintetiza: formato estruturado (certificado,
#: chave VAPID, DSN) ou efeito que o ensaio não quer (Sentry, SMTP). Sem eles o
#: ``check --deploy`` só avisa (W019 do VAPID) ou não olha.
_DROP_SECRETS = (
    "EFI_CERTIFICATE_PEM_BASE64",
    "EFI_CERTIFICATE_BASE64",
    "EFI_CERTIFICATE_PEM",
    "PURCHASE_NFE_CERTIFICATE_PFX_BASE64",
    "PURCHASE_NFE_CERTIFICATE_PASSWORD",
    "VAPID_PRIVATE_KEY",
    "VAPID_PUBLIC_KEY",
    "VAPID_CLAIMS_EMAIL",
    "SENTRY_DSN",
    "EMAIL_HOST_PASSWORD",
)

#: Segredos com formato fixo que o settings parseia.
_FIXED_SECRETS = {"SHOPMAN_PRIVACY_RECEIPT_HMAC_PREVIOUS_KEYS": "{}"}


class EnsaioError(RuntimeError):
    pass


# ── Escrita ──────────────────────────────────────────────────────────────────


class _SpecDumper(yaml.SafeDumper):
    pass


def _represent_str(dumper: yaml.SafeDumper, value: str):
    """Aspas em todo texto que outro leitor de YAML leria como número ou booleano.

    Medido em 13/10/2026: o PyYAML escreve ``02119381000158`` (o CNPJ do spec)
    sem aspas, porque para ele não é octal válido, e a DO (Go) lê como número e
    recusa o spec inteiro ("cannot unmarshal number into ... envs.value").
    """
    try:
        loaded = yaml.safe_load(value) if value else value
    except yaml.YAMLError:
        loaded = None
    numeric_like = bool(re.fullmatch(r"[-+]?[0-9][0-9_.eE+-]*", value))
    style = "'" if (numeric_like or not isinstance(loaded, str)) and value != "" else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_SpecDumper.add_representer(str, _represent_str)


def dump_spec(spec: dict) -> str:
    return HEADER + yaml.dump(spec, Dumper=_SpecDumper, sort_keys=False, allow_unicode=True)


def _guard_outside_repo(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved == _ROOT or _ROOT in resolved.parents:
        raise EnsaioError(f"{path}: dentro do repositório. Escreva fora dele (ex.: ~/ensaio-virada/).")
    return resolved


def _write(path: str, text: str) -> Path:
    target = _guard_outside_repo(Path(path))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    target.chmod(0o600)
    return target


# ── depois ───────────────────────────────────────────────────────────────────


def _env_lists(spec: dict) -> list[list[dict]]:
    """A lista de env do app e a de cada componente Django (onde o delta olha)."""
    lists = [spec.setdefault("envs", [])]
    lists.extend(component.setdefault("envs", []) for component in delta.django_components(spec).values())
    return lists


def _set_everywhere(spec: dict, key: str, value: str, *, secret: bool = False) -> None:
    """Escreve ``key`` no env do app e por cima de todo override de componente."""
    touched = False
    for envs in _env_lists(spec):
        for entry in envs:
            if entry.get("key") == key:
                entry["value"] = value
                entry["type"] = "SECRET" if secret else "GENERAL"
                touched = True
    if not touched:
        entry = {"key": key, "scope": "RUN_AND_BUILD_TIME", "value": value}
        if secret:
            entry["type"] = "SECRET"
        spec["envs"].append(entry)


def _remove_everywhere(spec: dict, key: str) -> None:
    for envs in _env_lists(spec):
        envs[:] = [entry for entry in envs if entry.get("key") != key]


def apply_delta(antes: dict) -> tuple[dict, list[str]]:
    """O spec como fica depois da gravação única do dia D, e o que mudou."""
    if not delta.django_components(antes):
        raise EnsaioError("o spec não tem componente Django (run_command com manage.py/config.asgi)")
    depois = copy.deepcopy(antes)
    changes: list[str] = []
    findings = {f.row.key: f for f in delta.evaluate(antes, etapa="dia-d")}
    for row in delta.DELTA:
        rule = row.dia_d
        finding = findings[row.key]
        if rule.kind == "rotated":
            _set_everywhere(depois, row.key, f"{MARK}-{row.key}", secret=True)
            changes.append(f"{row.key}: segredo novo (marcador)")
            continue
        if finding.status == "ok":
            continue
        if rule.kind in {"equals", "equals_or_absent"}:
            _set_everywhere(depois, row.key, rule.value)
            changes.append(f"{row.key} = {rule.value}")
        elif rule.kind == "true":
            _set_everywhere(depois, row.key, "true")
            changes.append(f"{row.key} = true")
        elif rule.kind in {"off", "absent"}:
            _remove_everywhere(depois, row.key)
            changes.append(f"apagar {row.key}")
        elif rule.kind == "prefix":
            _set_everywhere(depois, row.key, f"{rule.value}{MARK.replace('-', '_')}")
            changes.append(f"{row.key} = {rule.value}… (marcador)")
        else:
            # ``present`` faltando: o dia D não inventa valor. Fica [VIRAR] no
            # delta do depois, que é o achado do ensaio.
            changes.append(f"{row.key}: FALTA no spec (o ensaio não inventa)")
    return depois, changes


# ── reapontar ────────────────────────────────────────────────────────────────


def repoint(antes: dict, *, cluster: str, database: str = "postgres") -> tuple[dict, str]:
    """Troca SÓ o ``cluster_name`` do banco ``database``. Devolve o spec e o nome antigo."""
    if not cluster.strip():
        raise EnsaioError("--cluster vazio")
    novo = copy.deepcopy(antes)
    for entry in novo.get("databases") or []:
        if entry.get("name") == database:
            old = str(entry.get("cluster_name") or "")
            if not old:
                raise EnsaioError(f"o banco {database!r} do spec não tem cluster_name (não é cluster gerenciado)")
            if old == cluster:
                raise EnsaioError(f"o banco {database!r} já aponta para {cluster!r}")
            entry["cluster_name"] = cluster
            return novo, old
    raise EnsaioError(f"o spec não tem banco chamado {database!r} no bloco databases")


# ── env ──────────────────────────────────────────────────────────────────────


def _synthetic(key: str, envs: dict[str, dict]) -> str:
    if key in _FIXED_SECRETS:
        return _FIXED_SECRETS[key]
    token = secrets.token_hex(24)
    if key == "STRIPE_SECRET_KEY":
        publishable = str((envs.get("STRIPE_PUBLISHABLE_KEY") or {}).get("value", ""))
        mode = "live" if publishable.startswith("pk_live_") else "test"
        return f"sk_{mode}_ensaio_{token}"
    if key == "STRIPE_WEBHOOK_SECRET":
        return f"whsec_ensaio_{token}"
    return f"ensaio-sintetico-{token}"


def build_env(
    spec: dict,
    *,
    component: str,
    database_url: str,
    redis_url: str,
    efi_cert_path: str = "",
    extra_hosts: tuple[str, ...] = (),
) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Env do processo ``component`` para rodar local; e o relato (só nomes)."""
    components = delta.django_components(spec)
    if component not in components:
        raise EnsaioError(f"componente Django {component!r} não está no spec (há: {', '.join(sorted(components))})")
    effective = delta.effective_envs(spec, components[component])
    out: dict[str, str] = {}
    report: dict[str, list[str]] = {"sintetico": [], "fora": [], "referencia": []}
    for key, entry in effective.items():
        value = str(entry.get("value", ""))
        if delta._is_secret(entry):
            if key in _DROP_SECRETS:
                report["fora"].append(key)
                continue
            out[key] = _synthetic(key, effective)
            report["sintetico"].append(key)
            continue
        if _REF.search(value):
            if key == "DATABASE_URL":
                out[key] = database_url
            elif key == "REDIS_URL":
                out[key] = redis_url
            else:
                report["fora"].append(key)
                continue
            report["referencia"].append(key)
            continue
        out[key] = value
    if any(key.startswith("EFI_CERTIFICATE") for key in effective):
        if not efi_cert_path:
            raise EnsaioError(
                "o spec tem certificado da Efí: passe --efi-cert-path com um PEM sintético "
                "(receita no runbook do ensaio, passo do check --deploy)"
            )
        out["EFI_CERTIFICATE_PATH"] = efi_cert_path
        report["sintetico"].append("EFI_CERTIFICATE_PATH")
    if extra_hosts:
        hosts = [h for h in out.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]
        out["DJANGO_ALLOWED_HOSTS"] = ",".join([*hosts, *extra_hosts])
    for key in ("DATABASE_URL", "REDIS_URL"):
        if key not in out:
            out[key] = database_url if key == "DATABASE_URL" else redis_url
            report["referencia"].append(key)
    return out, report


def render_env(values: dict[str, str], report: dict[str, list[str]], *, component: str) -> str:
    lines = [
        HEADER.rstrip("\n"),
        f"# Env efetivo do componente {component!r}. Segredos: SINTÉTICOS, nenhum vale em provedor.",
        f"# sintéticos: {', '.join(sorted(report['sintetico'])) or '-'}",
        f"# fora (formato estruturado ou efeito indesejado no ensaio): {', '.join(sorted(report['fora'])) or '-'}",
        f"# referências do App Platform trocadas pelas do ensaio: {', '.join(sorted(report['referencia'])) or '-'}",
    ]
    lines.extend(f"export {key}={shlex.quote(value)}" for key, value in sorted(values.items()))
    return "\n".join(lines) + "\n"


# ── CLI ──────────────────────────────────────────────────────────────────────


def _load(path: str) -> dict:
    try:
        data = yaml.safe_load(Path(path).expanduser().read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise EnsaioError(f"não consegui ler {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise EnsaioError(f"{path} não é um spec do App Platform")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_depois = sub.add_parser("depois", help="spec do dia D, a partir do spec guardado (só arquivo)")
    p_depois.add_argument("--antes", required=True, help="spec guardado na abertura (doctl apps spec get)")
    p_depois.add_argument("--saida", required=True, help="arquivo a escrever, FORA do repositório")

    p_rep = sub.add_parser("reapontar", help="spec com o banco do app apontando para o cluster restaurado")
    p_rep.add_argument("--antes", required=True)
    p_rep.add_argument("--cluster", required=True, help="nome do cluster restaurado (doctl databases list)")
    p_rep.add_argument("--banco", default="postgres", help="nome do banco no bloco databases (default: postgres)")
    p_rep.add_argument("--saida", required=True)

    p_env = sub.add_parser("env", help="env de um componente, com segredos sintéticos, para rodar local")
    p_env.add_argument("--spec", required=True)
    p_env.add_argument("--componente", default="release")
    p_env.add_argument("--database-url", required=True, help="banco restaurado (local, porta do ensaio)")
    p_env.add_argument("--redis-url", required=True)
    p_env.add_argument("--efi-cert-path", default="", help="PEM sintético (openssl req -x509 …)")
    p_env.add_argument("--host-extra", action="append", default=[], help="host a somar ao DJANGO_ALLOWED_HOSTS")
    p_env.add_argument("--saida", required=True)

    args = parser.parse_args(argv)
    try:
        if args.cmd == "depois":
            depois, changes = apply_delta(_load(args.antes))
            target = _write(args.saida, dump_spec(depois))
            print(f"escrevi {target} ({len(changes)} mudança(s) do dia D):")
            print("\n".join(f"  - {line}" for line in changes))
        elif args.cmd == "reapontar":
            novo, old = repoint(_load(args.antes), cluster=args.cluster, database=args.banco)
            target = _write(args.saida, dump_spec(novo))
            print(f"escrevi {target}: databases[{args.banco}].cluster_name {old} → {args.cluster} (só esta linha)")
        else:
            values, report = build_env(
                _load(args.spec),
                component=args.componente,
                database_url=args.database_url,
                redis_url=args.redis_url,
                efi_cert_path=args.efi_cert_path,
                extra_hosts=tuple(args.host_extra),
            )
            target = _write(args.saida, render_env(values, report, component=args.componente))
            print(
                f"escrevi {target}: {len(values)} variáveis, {len(report['sintetico'])} sintéticas, "
                f"{len(report['fora'])} fora"
            )
    except EnsaioError as exc:
        print(f"golive-ensaio: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
