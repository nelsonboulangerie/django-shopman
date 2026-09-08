#!/usr/bin/env python
"""Espera a DigitalOcean terminar de trocar os contêineres — perguntando.

"Deploy Images terminou" NÃO é "está no ar": o workflow empurra as imagens e a
App Platform só então puxa e troca. Medido em 05/09/2026: imagens às 14:01Z,
deployment ACTIVE às 14:06Z. Perguntar ao vivo antes disso mede a versão
ANTERIOR — um verde que atesta o que não subiu.

Aqui havia `sleep 420` dentro do workflow, e o número era o defeito nos dois
sentidos. Curto demais, o smoke atesta a versão anterior. Longo demais, estoura
o teto do job — que foi o que aconteceu de 06 a 08/09/2026: `timeout-minutes: 5`
contra sete minutos de espera, dezesseis runs cancelados, asserção nenhuma. E
run cancelado não fica vermelho, então ninguém soube.

Espera cega não tem número certo. Este script pergunta: a DigitalOcean sabe
quando o deployment ficou ACTIVE, e o `workflow_run` diz a que instante o deploy
terminou.

⚠️ Mora em `scripts/` e não embutido no YAML de propósito. A primeira versão era
Python dentro de shell dentro de um bloco YAML, e morreu com `syntax error near
unexpected token '('` antes de esperar coisa alguma. Três níveis de citação é um
a mais do que cabe numa cabeça.

Saídas:
  0  deployment novo ficou ACTIVE — ou não havia deployment a esperar
  1  deployment terminou ERROR/CANCELED, ou não ficou pronto no teto
  2  erro de uso/credencial
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

API = "https://api.digitalocean.com/v2"

#: Fases terminais de fracasso: o que o Deploy Images publicou NÃO chegou ao
#: alpha. Seguir para as asserções aqui seria medir a versão anterior e ficar
#: verde — o modo de falhar que o smoke inteiro existe para impedir.
FAILED_PHASES = {"ERROR", "CANCELED"}

#: O relógio da DO e o do Actions não são o mesmo, e o deployment nasce quando
#: ela VÊ a tag nova. Folga para trás, para não perder o deployment por segundos.
CLOCK_SKEW_SECONDS = 120


def _get(path: str, token: str) -> dict:
    request = urllib.request.Request(
        f"{API}{path}", headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def _epoch(value: str | None) -> int:
    if not value:
        return 0
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return 0
    return int(parsed.astimezone(UTC).timestamp())


def find_app_id(apps: list[dict], name: str) -> str | None:
    for app in apps:
        if (app.get("spec") or {}).get("name") == name:
            return app.get("id")
    return None


def newest_since(deployments: list[dict], since: int) -> dict | None:
    """Deployment mais recente criado a partir de `since`, ou None."""
    fresh = [d for d in deployments if _epoch(d.get("created_at")) >= since]
    if not fresh:
        return None
    return max(fresh, key=lambda d: _epoch(d.get("created_at")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-name", default=os.environ.get("DO_APP_NAME", ""))
    parser.add_argument(
        "--since",
        default=os.environ.get("DEPLOY_FINISHED_AT", ""),
        help="instante ISO em que o Deploy Images terminou; vazio aceita o "
        "deployment ACTIVE corrente (é assim que o probe exercita o caminho).",
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

    since = _epoch(args.since)
    if since:
        since -= CLOCK_SKEW_SECONDS
        print(f"Deploy Images terminou em {args.since}")
    else:
        print("sem instante de referência: aceitando o deployment ACTIVE corrente")

    deadline = time.monotonic() + args.max_seconds
    while True:
        payload = _get(f"/apps/{app_id}/deployments?per_page=20", token)
        top = newest_since(payload.get("deployments") or [], since)
        phase = (top or {}).get("phase", "NONE")
        dep_id = (top or {}).get("id", "none")
        print(f"{datetime.now(UTC):%H:%M:%SZ}  deployment={dep_id} phase={phase}")

        if phase == "ACTIVE":
            print(f"deployment {dep_id} ACTIVE — o alpha está com o que subiu.")
            return 0
        if phase in FAILED_PHASES:
            print(
                f"::error::deployment {dep_id} terminou {phase} — o que o Deploy "
                "Images publicou NÃO chegou ao alpha. As asserções abaixo "
                "mediriam a versão anterior e ficariam verdes.",
                file=sys.stderr,
            )
            return 1

        if time.monotonic() >= deadline:
            if phase == "NONE":
                # Deploy Images roda a cada push no main, mas só rebuilda o que o
                # push tocou: um merge que só mexeu em `docs/` não publica imagem
                # nenhuma e a DO não cria deployment. Não é falha, e as asserções
                # contra o que está no ar seguem valendo.
                print(
                    f"::notice::Nenhum deployment novo em {args.max_seconds}s. "
                    "Provavelmente o push não tocou componente publicável. "
                    "Seguindo com as asserções contra o que está no ar."
                )
                return 0
            print(
                f"::error::deployment {dep_id} ainda em {phase} depois de "
                f"{args.max_seconds}s.",
                file=sys.stderr,
            )
            return 1
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
