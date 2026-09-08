"""Espera o deployment DESTE run ficar ACTIVE — correlacionando por digest.

"Deploy Images terminou" não é "está no ar": o workflow empurra as imagens e a
App Platform só então puxa e troca. Perguntar ao vivo antes disso mede a versão
ANTERIOR — um verde que atesta o que não subiu.

## Duas gerações de defeito, e por que a terceira não usa relógio

**1ª — espera cega.** `sleep 420` dentro de um job com `timeout-minutes: 5`.
Dezesseis runs cancelados aos 5 min, asserções `skipped`, e nada vermelho porque
run cancelado não fica vermelho.

**2ª — espera por relógio.** A versão seguinte perguntava à DigitalOcean, mas
escolhia o deployment por `created_at >= fim_do_deploy - 120s`. Duas falhas:

- a folga de 120s deixava entrar o deployment do merge ANTERIOR. Se ele ficasse
  ACTIVE antes de o atual nascer, o smoke aprovava a versão errada;
- quando nenhum deployment aparecia no teto, o script **presumia** que o push não
  tocara componente publicável e retornava sucesso. Se a DigitalOcean falhasse em
  criar um deployment de uma publicação real, o silêncio virava verde.

**3ª — correlação por digest.** O `cause_details.docr_push.image_digest` de cada
deployment diz exatamente qual imagem o disparou, e o Deploy Images publica o
digest de cada componente que construiu (artefato `published-components`). Um
deployment do merge anterior tem outro digest, por construção — não há janela de
relógio para acertar ou errar. E "nada foi publicado" deixa de ser presunção: é
uma lista vazia no manifesto, decidida por quem construiu.

⚠️ O spec do App Platform aponta para a tag MÓVEL (`web`, `pos`), então o
deployment não carrega o SHA. Por isso a correlação é pelo digest e não pela tag.

Saídas:
  0  um deployment deste run ficou ACTIVE — ou o run não publicou nada
  1  deployment esperado não apareceu, não ficou pronto, ou falhou
  2  erro de uso/credencial/manifesto
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

API = "https://api.digitalocean.com/v2"

#: Fases terminais de fracasso: o que o Deploy Images publicou NÃO chegou ao
#: alpha. Seguir para as asserções aqui seria medir a versão anterior e ficar
#: verde — o modo de falhar que o smoke inteiro existe para impedir.
FAILED_PHASES = {"ERROR", "CANCELED"}


def _get(path: str, token: str) -> dict:
    request = urllib.request.Request(
        f"{API}{path}", headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def find_app_id(apps: list[dict], name: str) -> str | None:
    for app in apps:
        if (app.get("spec") or {}).get("name") == name:
            return app.get("id")
    return None


def deployment_digest(deployment: dict) -> str | None:
    """Digest da imagem que disparou o deployment, se houver.

    É o único campo que amarra um deployment a um build específico: o spec usa
    tag móvel e o `created_at` só sabe dizer "depois de", que foi exatamente o
    que deixava o merge anterior passar.
    """
    push = (deployment.get("cause_details") or {}).get("docr_push") or {}
    return push.get("image_digest") or None


def classify(deployments: list[dict], digests: set[str]) -> tuple[str, dict | None]:
    """('ACTIVE'|'FAILED'|'EM_CURSO'|'AUSENTE', deployment)."""
    nossos = [d for d in deployments if deployment_digest(d) in digests]
    if not nossos:
        return "AUSENTE", None
    for d in nossos:
        if d.get("phase") == "ACTIVE":
            return "ACTIVE", d
    em_curso = [d for d in nossos if d.get("phase") not in FAILED_PHASES]
    if em_curso:
        return "EM_CURSO", em_curso[0]
    return "FAILED", nossos[0]


def load_manifest(path: Path) -> list[dict]:
    """Componentes publicados por este run. Manifesto ilegível é ERRO, não zero.

    Tratar ausência como "nada publicado" reintroduziria a presunção que a 2ª
    geração deste script tinha: um upload que falhou passaria por push
    documental, e o smoke aprovaria sem esperar o que subiu.
    """
    dados = json.loads(path.read_text(encoding="utf-8"))
    componentes = dados.get("components")
    if not isinstance(componentes, list):
        raise ValueError("manifesto sem lista `components`")
    for c in componentes:
        if not c.get("digest"):
            raise ValueError(f"componente sem digest: {c.get('tag') or c}")
    return componentes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-name", default=os.environ.get("DO_APP_NAME", ""))
    parser.add_argument(
        "--manifest",
        default=os.environ.get("PUBLISHED_MANIFEST", ""),
        help="published.json do Deploy Images que disparou este run.",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Só exercita credencial, API e parsing, fora de um deploy. Não "
        "afirma nada sobre deployment — é o que pega erro de sintaxe e de "
        "token antes do merge, sem inventar um verde.",
    )
    parser.add_argument(
        "--max-seconds",
        type=int,
        default=int(os.environ.get("DEPLOY_WAIT_MAX_SECONDS", "900")),
    )
    parser.add_argument("--interval", type=int, default=20)
    args = parser.parse_args(argv)

    token = os.environ.get("DO_TOKEN") or ""
    if not token:
        print(
            "::error::DIGITALOCEAN_ACCESS_TOKEN ausente — sem ele não dá para "
            "saber se o deploy chegou ao alpha, e um smoke que não sabe o que "
            "está medindo é pior que smoke nenhum.",
            file=sys.stderr,
        )
        return 2
    if not args.app_name:
        print("::error::--app-name obrigatório", file=sys.stderr)
        return 2

    try:
        apps = _get("/apps?per_page=200", token).get("apps") or []
    except urllib.error.HTTPError as exc:
        print(f"::error::API da DigitalOcean recusou: {exc}", file=sys.stderr)
        return 2
    app_id = find_app_id(apps, args.app_name)
    if not app_id:
        print(f"::error::App '{args.app_name}' não existe na conta.", file=sys.stderr)
        return 2
    print(f"app: {args.app_name} ({app_id})")

    if args.probe:
        deployments = _get(f"/apps/{app_id}/deployments?per_page=5", token)
        for d in (deployments.get("deployments") or [])[:3]:
            print(f"  {d.get('id', '?')[:8]} {d.get('phase')} digest={deployment_digest(d)}")
        print("probe: credencial, API e parsing OK. Nada afirmado sobre deploy.")
        return 0

    if not args.manifest:
        print(
            "::error::--manifest obrigatório fora do probe. Sem ele o script "
            "voltaria a adivinhar o que este run publicou.",
            file=sys.stderr,
        )
        return 2
    try:
        componentes = load_manifest(Path(args.manifest))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(
            f"::error::manifesto de publicação ilegível ({exc}). Não dá para "
            "distinguir 'nada foi publicado' de 'o registro se perdeu', e as "
            "duas coisas não podem terminar iguais.",
            file=sys.stderr,
        )
        return 2

    if not componentes:
        print(
            "::notice::O Deploy Images não publicou componente nenhum neste "
            "push — não há deployment a esperar. Seguindo direto para as "
            "asserções contra o que está no ar."
        )
        return 0

    digests = {c["digest"] for c in componentes}
    print(f"publicados por este run: {', '.join(sorted(c['tag'] for c in componentes))}")

    deadline = time.monotonic() + args.max_seconds
    while True:
        payload = _get(f"/apps/{app_id}/deployments?per_page=20", token)
        estado, dep = classify(payload.get("deployments") or [], digests)
        agora = f"{datetime.now(UTC):%H:%M:%SZ}"
        dep_id = (dep or {}).get("id", "nenhum")[:8]
        print(f"{agora}  {estado}  deployment={dep_id} phase={(dep or {}).get('phase', '-')}")

        if estado == "ACTIVE":
            print(f"deployment {dep_id} ACTIVE com a imagem deste run.")
            return 0
        if estado == "FAILED":
            print(
                f"::error::o deployment {dep_id} deste run terminou "
                f"{dep.get('phase')} — o que o Deploy Images publicou NÃO chegou "
                "ao alpha. As asserções abaixo mediriam a versão anterior e "
                "ficariam verdes.",
                file=sys.stderr,
            )
            return 1

        if time.monotonic() >= deadline:
            print(
                f"::error::este run publicou {len(componentes)} componente(s) e "
                f"nenhum deployment com a imagem deles ficou ACTIVE em "
                f"{args.max_seconds}s (estado: {estado}). O alpha NÃO está com o "
                "que subiu.",
                file=sys.stderr,
            )
            return 1
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
