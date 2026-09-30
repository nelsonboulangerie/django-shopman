#!/usr/bin/env python
"""Confere o spec VERSIONADO contra o app VIVO na DigitalOcean, antes do update.

A armadilha que este script existe para desarmar, medida em 05/09/2026: o
``.do/app.alpha-subdomains.yaml`` tinha 73 envs e o app vivo tinha 95. As 22 de
diferença estavam configuradas só no painel — entre elas TODO o e-mail, a
emissão fiscal inteira e o NF-e de Compras com o certificado e-CNPJ.

``doctl apps update --spec`` não faz merge: o spec que você manda **passa a ser
o spec**. Chave que existe só no vivo é apagada, em silêncio, sem confirmação e
sem linha no log. O deploy sobe verde e o e-mail para de sair.

Este script não conserta nada e não escreve em lugar nenhum — ele **lê os dois
lados e mostra a diferença**, para que a decisão de rodar o update seja tomada
com a lista na frente. É de propósito somente-leitura: um script que
"sincroniza sozinho" seria uma segunda forma de perder configuração.

    python scripts/check_do_spec_drift.py                        # detecta o app pelo nome
    python scripts/check_do_spec_drift.py --app-id <uuid>
    python scripts/check_do_spec_drift.py --spec .do/app.subdomains.yaml
    python scripts/check_do_spec_drift.py --live-spec /tmp/vivo.yaml   # sem doctl
    python scripts/check_do_spec_drift.py --context shopman-spec-update

Compara envs (de app e por serviço), domínios, ingress, bancos anexados
(``databases``, campo a campo) e, por componente, imagem (registry_type,
repository, tag/digest, deploy_on_push) e dimensionamento (instance_count,
instance_size_slug).

⚠️ O token precisa LER databases. Sem o escopo, o App Platform devolve o bloco
só com ``name`` — o formato que derrubou os deploys em 29-30/09/2026 — e o
script recusa a leitura (sai 2) em vez de acusar drift falso.

Saída: chaves só no vivo (**as que sumiriam**), chaves só no versionado (as que
nasceriam), e divergência de valor/escopo/tipo nas que existem dos dois lados.
Sai com 1 quando há qualquer diferença — é gate de conferência manual, não de
CI: a CI não tem (nem deve ter) credencial da DigitalOcean.

⚠️ Valor de segredo nunca é comparado nem impresso. No spec do vivo ele vem
cifrado (``EV[1:...]``) e no versionado não existe por política — comparar
produziria "divergente" sempre, e imprimir seria vazar.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover - o .venv da raiz tem PyYAML
    print("PyYAML ausente — rode com .venv/bin/python", file=sys.stderr)
    raise SystemExit(2) from exc

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Nome do app no App Platform por spec versionado. `doctl apps list` devolve
#: o `spec.name`, que é o campo `name:` do topo do próprio arquivo.
DEFAULT_SPEC = REPO_ROOT / ".do" / "app.alpha-subdomains.yaml"

#: Chaves que existem NO ARQUIVO e não no vivo **de propósito**, com a razão.
#:
#: Sem esta lista o drift nunca fecha: as duas apareceriam como "nasceriam" para
#: sempre, e um relatório que nunca fica limpo deixa de ser lido — a próxima
#: divergência de verdade chega no meio de um ruído que todo mundo já aprendeu a
#: ignorar. Uma diferença deliberada precisa ser *declarada* como deliberada,
#: não tolerada em silêncio.
#:
#: ⚠️ Só vale para o lado "nasceriam". Chave que existe no vivo e não no arquivo
#: **apaga** no update; essa direção tem declaração própria e mais estreita
#: (``EXPECTED_ONLY_LIVE``), e esta lista nunca a cobre.
EXPECTED_ONLY_VERSIONED: dict[str, str] = {
    "FOCUS_NFE_ENVIRONMENT": (
        "declarada explícita no arquivo; o vivo não a tem e cai no default do "
        "settings.py, que é o mesmo `homologacao`. Aplicar não muda comportamento."
    ),
    "SENTRY_DSN": (
        "SECRET sem valor, esperando o opt-in de docs/runbooks/ativar-sentry.md. "
        "Sem DSN o settings.py não inicializa o Sentry."
    ),
}


#: Chaves que existem NOS DOIS LADOS com valores diferentes **de propósito**:
#: chave → ``(valor no vivo, valor no arquivo, razão)``.
#:
#: Os dois valores ficam presos na declaração, não só a chave. Declarar a chave
#: sozinha calaria qualquer valor que ela viesse a ter — e aí a lista viraria um
#: jeito de silenciar drift de verdade. Se um dos lados mudar para um valor que
#: não é o declarado, a divergência volta a acusar.
_PUBLICATION_ARMED_IN_THE_PANEL = (
    "a publicação é ARMADA NO PAINEL pela operação. O template de deploy nunca "
    "pré-arma publicação pública (test_deploy_templates_never_prearm_publication_canary). "
    "O arquivo fica em `false` de propósito; o vivo fica em `true` por decisão de operação."
)
EXPECTED_VALUE_DIVERGENCE: dict[str, tuple[str, str, str]] = {
    "SHOPMAN_MARKETING_INSTAGRAM_PUBLICATION_ENABLED": ("true", "false", _PUBLICATION_ARMED_IN_THE_PANEL),
    "SHOPMAN_MARKETING_FACEBOOK_PUBLICATION_ENABLED": ("true", "false", _PUBLICATION_ARMED_IN_THE_PANEL),
    "SHOPMAN_MARKETING_GOOGLE_PUBLICATION_ENABLED": ("true", "false", _PUBLICATION_ARMED_IN_THE_PANEL),
}

#: Chaves que existem SÓ NO VIVO e cuja remoção pelo ``apps update`` é o
#: resultado QUERIDO, com a razão.
#:
#: ⚠️ É a direção que apaga, então a entrada aqui é afirmação forte: "esta
#: chave pode sumir, e sumir é o que se quer". Serve só para a chave que já
#: saiu do arquivo de propósito e cuja remoção do vivo está pendente. Feita a
#: remoção, a entrada sai daqui — declaração velha esconde a volta da chave.
EXPECTED_ONLY_LIVE: dict[str, str] = {
    "SHOPMAN_REQUIRE_ACTIVE_OPERATOR": (
        "saiu do arquivo em b8df875f4; nenhum código lê esta chave. A remoção do "
        "ambiente vivo está pendente (spec do vivo editado à mão, só esta linha)."
    ),
}


def load_spec(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def doctl(*args: str, context: str | None = None) -> list[str]:
    return ["doctl", *(["--context", context] if context else []), *args]


def app_id_for(name: str, *, context: str | None = None) -> str | None:
    result = subprocess.run(
        doctl("apps", "list", "--format", "ID,Spec.Name", "--no-header", context=context),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == name:
            return parts[0]
    return None


def fetch_live_spec(app_id: str, *, context: str | None = None) -> dict:
    result = subprocess.run(
        doctl("apps", "spec", "get", app_id, context=context),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"doctl apps spec get falhou: {result.stderr.strip()}")
    return yaml.safe_load(result.stdout) or {}


def token_reads_databases(*, context: str | None = None) -> bool:
    """O token enxerga os bancos gerenciados?

    Medido em 30/09/2026: com o token de deploy (sem escopo de database), o
    ``doctl apps spec get`` devolve o bloco ``databases`` só com ``name`` — o
    MESMO formato mutilado que derrubou os deploys por 21 horas. O App
    Platform apaga os campos na leitura em vez de recusar. Com o token certo o
    bloco vem inteiro. Sem esta pergunta, o check acusaria a mutilação num app
    sadio — e, pior, quem salvar essa leitura e mandar de volta num
    ``apps update`` reproduz o incidente.
    """
    result = subprocess.run(
        doctl("databases", "list", "--format", "ID", "--no-header", context=context),
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def env_index(spec: dict) -> dict[str, dict]:
    """Envs de nível de APP, por chave.

    Env de serviço (as ``NUXT_*`` de cada superfície) fica de fora de propósito:
    ela é comparada por serviço, e misturar as duas escalas faria toda chave
    homônima de dois serviços parecer divergente.
    """
    return {entry["key"]: entry for entry in spec.get("envs", []) if "key" in entry}


def service_env_index(spec: dict) -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    for service in spec.get("services", []) or []:
        name = service.get("name") or "?"
        out[name] = {entry["key"]: entry for entry in service.get("envs", []) or [] if "key" in entry}
    return out


def domain_index(spec: dict) -> dict[str, str]:
    """Domínios por hostname → `"<type> zone=<zone>"`.

    Env não é a única coisa que o update apaga. Medido em 08/09/2026: o arquivo
    trazia `alpha.nelsonboulangerie.com.br` como PRIMARY — um domínio **morto**
    desde o corte de 01/09 — e **não** trazia `backup.boulangerie.com.br`, que
    estava no ar. Um update teria ressuscitado o morto e apagado o vivo, e o
    drift-check, que só olhava env, teria dito "OK".
    """
    out: dict[str, str] = {}
    for entry in spec.get("domains", []) or []:
        name = entry.get("domain")
        if name:
            out[name] = f"{entry.get('type') or 'ALIAS'} zone={entry.get('zone') or '-'}"
    return out


def ingress_index(spec: dict) -> dict[str, str]:
    """Regras de ingress por autoridade → componente que a serve.

    Comparado como **conjunto**, não como lista ordenada: o painel acrescenta
    regra no fim e o arquivo agrupa por leitura, então a ordem diverge sem que
    nada de real mude. O que importa é *quem serve cada host* — e se a regra
    catch-all (sem autoridade) existe.
    """
    out: dict[str, str] = {}
    for rule in (spec.get("ingress") or {}).get("rules", []) or []:
        match = rule.get("match") or {}
        authority = match.get("authority") or {}
        host = authority.get("exact") or authority.get("prefix") or "<catch-all>"
        path = (match.get("path") or {}).get("prefix") or "/"
        out[f"{host} {path}"] = (rule.get("component") or {}).get("name") or "?"
    return out


#: Seções de componente do spec. `doctl apps update` troca a lista inteira de
#: cada uma: componente que só existe no vivo é DESLIGADO.
COMPONENT_SECTIONS = ("services", "workers", "jobs", "static_sites", "functions")

#: Campos da imagem que decidem O QUE sobe. `registry` fica de fora: para DOCR
#: o App Platform o preenche sozinho no vivo (`nelsonboulangerie`) e o arquivo
#: não o declara — comparar daria divergência eterna sem mudar nada.
IMAGE_FIELDS = ("registry_type", "repository", "tag", "digest")

#: O essencial do componente que, se sumir, muda o que roda ou quanto roda.
COMPONENT_FIELDS = ("instance_count", "instance_size_slug")


def database_index(spec: dict) -> dict[str, dict]:
    """Bancos anexados por `name` → todos os campos da entrada.

    O caso que ensinou (29/09/2026, deployment ded45b84): um `apps update`
    reduziu as duas entradas a `- name: postgres` / `- name: cache`. Todo deploy
    novo passou a morrer em `Creating database` com InternalError, sem mensagem,
    por 21 horas — só `apps restart` passava, porque clona o deployment
    anterior. Nem toda entrada tem todos os campos (o `cache` Valkey não tem
    `db_name`/`db_user`), então o que conta é o versionado, não uma lista fixa.
    """
    out: dict[str, dict] = {}
    for entry in spec.get("databases", []) or []:
        name = entry.get("name")
        if name:
            out[name] = {key: value for key, value in entry.items() if key != "name"}
    return out


def component_index(spec: dict) -> dict[str, dict]:
    """Componentes por `"<seção>/<nome>"` → imagem e dimensionamento.

    A tag da imagem é o que o `deploy_on_push` assina: tag trocada no vivo
    (ou no arquivo) faz o componente rodar outra imagem sem que ninguém veja.
    """
    out: dict[str, dict] = {}
    for section in COMPONENT_SECTIONS:
        for component in spec.get(section, []) or []:
            fields: dict = {}
            image = component.get("image") or {}
            for field in IMAGE_FIELDS:
                if field in image:
                    fields[f"image.{field}"] = image[field]
            if "deploy_on_push" in image:
                fields["image.deploy_on_push"] = bool((image["deploy_on_push"] or {}).get("enabled"))
            for field in COMPONENT_FIELDS:
                if field in component:
                    fields[field] = component[field]
            out[f"{section}/{component.get('name') or '?'}"] = fields
    return out


def compare_records(
    live: dict[str, dict], versioned: dict[str, dict], *, label: str, unit: str
) -> list[str]:
    """Compara registros com campos (banco → campos, componente → campos).

    Campo presente no arquivo e AUSENTE no vivo é problema, não "nasceria":
    é a forma exata da mutilação de 29/09, em que a entrada existia dos dois
    lados e o vivo tinha perdido tudo menos o `name`.
    """
    problems: list[str] = []

    only_live = sorted(set(live) - set(versioned))
    if only_live:
        problems.append(f"  ⛔ SUMIRIAM no `apps update` — {unit} no vivo e NÃO no arquivo ({label}):")
        problems.extend(f"       {key}" for key in only_live)

    only_versioned = sorted(set(versioned) - set(live))
    if only_versioned:
        problems.append(f"  ➕ nasceriam — {unit} no arquivo e não no vivo ({label}):")
        problems.extend(f"       {key}" for key in only_versioned)

    for key in sorted(set(live) & set(versioned)):
        left, right = live[key], versioned[key]
        missing_live = sorted(set(right) - set(left))
        if missing_live:
            problems.append(
                f"  ⛔ {label} {key}: o VIVO perdeu campos que o arquivo declara — "
                + ", ".join(f"{field}={right[field]!r}" for field in missing_live)
            )
        only_live_fields = sorted(set(left) - set(right))
        if only_live_fields:
            problems.append(
                f"  ⛔ {label} {key}: SUMIRIAM no `apps update` — campos só no vivo: "
                + ", ".join(f"{field}={left[field]!r}" for field in only_live_fields)
            )
        for field in sorted(set(left) & set(right)):
            if left[field] != right[field]:
                problems.append(
                    f"  ⚠️ {label} {key}: `{field}` diverge — vivo={left[field]!r} "
                    f"versionado={right[field]!r}"
                )
    return problems


def mutilated_databases(live: dict[str, dict], versioned: dict[str, dict]) -> list[str]:
    """Entradas de banco que no vivo têm só `name` e no arquivo têm campos."""
    return sorted(name for name, fields in live.items() if not fields and versioned.get(name))


def env_type(entry: dict) -> str:
    """`GENERAL` é o default do App Platform, e o `doctl` OMITE o campo quando
    é ele. Sem esta normalização, toda env comum do vivo apareceria como
    "type diverge — vivo=None versionado='GENERAL'": cinquenta linhas de ruído
    que enterrariam as poucas divergências de verdade.
    """
    return (entry.get("type") or "GENERAL").upper()


def is_secret(entry: dict) -> bool:
    return env_type(entry) == "SECRET"


def compare_plain(
    live: dict[str, str], versioned: dict[str, str], *, label: str, unit: str
) -> list[str]:
    """Compara mapa simples (domínio→tipo, autoridade→componente)."""
    problems: list[str] = []

    only_live = sorted(set(live) - set(versioned))
    if only_live:
        problems.append(f"  ⛔ SUMIRIAM no `apps update` — {unit} no vivo e NÃO no arquivo ({label}):")
        problems.extend(f"       {key} → {live[key]}" for key in only_live)

    only_versioned = sorted(set(versioned) - set(live))
    if only_versioned:
        problems.append(f"  ➕ nasceriam — {unit} no arquivo e não no vivo ({label}):")
        problems.extend(f"       {key} → {versioned[key]}" for key in only_versioned)

    for key in sorted(set(live) & set(versioned)):
        if live[key] != versioned[key]:
            problems.append(
                f"  ⚠️ {key}: diverge — vivo={live[key]!r} versionado={versioned[key]!r}"
            )
    return problems


def compare(
    live: dict[str, dict],
    versioned: dict[str, dict],
    *,
    label: str,
    expected_only_versioned: dict[str, str] | None = None,
    expected_only_live: dict[str, str] | None = None,
    expected_value_divergence: dict[str, tuple[str, str, str]] | None = None,
) -> tuple[list[str], list[str]]:
    """`(problemas, esperado)`. Problemas vazios significa "os dois lados batem"."""
    problems: list[str] = []
    expected: list[str] = []
    declared = expected_only_versioned or {}
    declared_live = expected_only_live or {}
    declared_values = expected_value_divergence or {}

    only_live = sorted(key for key in set(live) - set(versioned) if key not in declared_live)
    for key in sorted(key for key in set(live) - set(versioned) if key in declared_live):
        expected.append(f"  ✅ {key}: só no vivo, sai no update de propósito — {declared_live[key]}")
    only_versioned = sorted(key for key in set(versioned) - set(live) if key not in declared)
    for key in sorted(key for key in set(versioned) - set(live) if key in declared):
        expected.append(f"  ✅ {key}: só no arquivo, de propósito — {declared[key]}")

    if only_live:
        problems.append(
            f"  ⛔ SUMIRIAM no `apps update` — existem no vivo e NÃO no spec versionado ({label}):"
        )
        problems.extend(f"       {key}" for key in only_live)

    if only_versioned:
        problems.append(f"  ➕ nasceriam — existem no spec versionado e não no vivo ({label}):")
        problems.extend(f"       {key}" for key in only_versioned)

    for key in sorted(set(live) & set(versioned)):
        left, right = live[key], versioned[key]
        if is_secret(left) or is_secret(right):
            # Valor de segredo nunca é comparado nem impresso. Só o
            # enquadramento (é segredo dos dois lados?) importa aqui.
            if is_secret(left) != is_secret(right):
                problems.append(
                    f"  ⚠️ {key}: `type` diverge — vivo={env_type(left)} versionado={env_type(right)}"
                )
            continue
        if env_type(left) != env_type(right):
            problems.append(
                f"  ⚠️ {key}: `type` diverge — vivo={env_type(left)} versionado={env_type(right)}"
            )
        declared_value = declared_values.get(key)
        if (
            declared_value
            and left.get("value") != right.get("value")
            and (left.get("value"), right.get("value")) == declared_value[:2]
        ):
            expected.append(
                f"  ✅ {key}: vivo={left.get('value')!r} versionado={right.get('value')!r}, "
                f"de propósito — {declared_value[2]}"
            )
            fields: tuple[str, ...] = ("scope",)
        else:
            fields = ("value", "scope")
        for field in fields:
            if left.get(field) != right.get(field):
                problems.append(
                    f"  ⚠️ {key}: `{field}` diverge — vivo={left.get(field)!r} "
                    f"versionado={right.get(field)!r}"
                )
    return problems, expected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Drift entre o spec versionado e o app vivo")
    parser.add_argument("--spec", default=str(DEFAULT_SPEC), help="spec versionado a conferir")
    parser.add_argument("--app-id", default=None, help="UUID do app (default: acha pelo `name:` do spec)")
    parser.add_argument(
        "--live-spec",
        default=None,
        help="arquivo com o spec do vivo já baixado (pula o doctl)",
    )
    parser.add_argument(
        "--context",
        default=None,
        help="contexto do doctl (o token precisa ler databases; ver o runbook)",
    )
    args = parser.parse_args(argv)

    spec_path = Path(args.spec)
    if not spec_path.is_absolute():
        spec_path = REPO_ROOT / spec_path
    if not spec_path.is_file():
        print(f"spec não encontrado: {spec_path}", file=sys.stderr)
        return 2

    versioned = load_spec(spec_path)

    if args.live_spec:
        live = load_spec(Path(args.live_spec))
        origin = args.live_spec
    else:
        app_id = args.app_id or app_id_for(versioned.get("name", ""), context=args.context)
        if not app_id:
            print(
                f"app '{versioned.get('name')}' não encontrado via doctl.\n"
                "Autentique (`doctl auth init`) ou passe --app-id / --live-spec.",
                file=sys.stderr,
            )
            return 2
        try:
            live = fetch_live_spec(app_id, context=args.context)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        origin = f"app {app_id}"
        if versioned.get("databases") and not token_reads_databases(context=args.context):
            # Leitura cega: o vivo viria sem os campos do banco e o check
            # acusaria a mutilação num app sadio. Recusar é mais honesto que
            # um FAIL falso — e o aviso é o próprio incidente de 29/09.
            print(
                "⛔ leitura cega: o token deste contexto do doctl NÃO lê databases.\n"
                "   Com ele, `apps spec get` devolve `databases` só com `name` — e mandar\n"
                "   essa leitura de volta num `apps update` quebra todo deploy novo\n"
                "   (InternalError em `Creating database`, 29-30/09/2026).\n"
                "   Rode com um contexto que leia databases: --context <ctx> (make: context=<ctx>).",
                file=sys.stderr,
            )
            return 2

    # `relative_to` estoura para caminho fora do repo, e conferir um spec salvo
    # em /tmp é justamente o que se faz ao comparar duas versões do arquivo.
    try:
        shown = spec_path.relative_to(REPO_ROOT)
    except ValueError:
        shown = spec_path
    print(f"Spec versionado : {shown}")
    print(f"App vivo        : {origin}")
    print(
        f"envs de app     : vivo={len(env_index(live))} versionado={len(env_index(versioned))}"
    )
    print(
        f"domínios        : vivo={len(domain_index(live))} versionado={len(domain_index(versioned))}"
    )
    print(
        f"bancos anexados : vivo={len(database_index(live))} "
        f"versionado={len(database_index(versioned))}"
    )
    print(
        f"componentes     : vivo={len(component_index(live))} "
        f"versionado={len(component_index(versioned))}"
    )

    problems, expected = compare(
        env_index(live),
        env_index(versioned),
        label="envs de app",
        expected_only_versioned=EXPECTED_ONLY_VERSIONED,
        expected_only_live=EXPECTED_ONLY_LIVE,
        expected_value_divergence=EXPECTED_VALUE_DIVERGENCE,
    )

    live_services, versioned_services = service_env_index(live), service_env_index(versioned)
    for name in sorted(set(live_services) | set(versioned_services)):
        service_problems, service_expected = compare(
            live_services.get(name, {}),
            versioned_services.get(name, {}),
            label=f"serviço {name}",
        )
        problems.extend(service_problems)
        expected.extend(service_expected)

    problems.extend(
        compare_plain(
            domain_index(live), domain_index(versioned), label="domínios", unit="hostnames"
        )
    )
    problems.extend(
        compare_plain(
            ingress_index(live),
            ingress_index(versioned),
            label="ingress",
            unit="regras de roteamento",
        )
    )

    live_databases, versioned_databases = database_index(live), database_index(versioned)
    mutilated = mutilated_databases(live_databases, versioned_databases)
    if mutilated:
        problems.append(
            "  ⛔ databases MUTILADO no vivo — só `name` em: "
            + ", ".join(mutilated)
            + ". Todo deploy novo morre em `Creating database` (InternalError, sem"
            " mensagem); só `apps restart` passa. Foi o incidente de 29-30/09/2026."
        )
    problems.extend(
        compare_records(
            live_databases, versioned_databases, label="databases", unit="bancos anexados"
        )
    )
    problems.extend(
        compare_records(
            component_index(live), component_index(versioned), label="componente", unit="componentes"
        )
    )

    if expected:
        print("\nDiferenças declaradas como esperadas (não são drift):")
        for line in expected:
            print(line)
        print()

    if not problems:
        print("- [OK] spec_drift: o spec versionado descreve o app vivo inteiro.")
        return 0

    print("- [FAIL] spec_drift: o spec versionado NÃO descreve o app vivo.")
    for line in problems:
        print(line)
    print(
        "\n⛔ NÃO rode `doctl apps update --spec` enquanto houver linha em SUMIRIAM:\n"
        "   o update substitui o spec inteiro, não faz merge. Env, DOMÍNIO, regra\n"
        "   de ingress, banco anexado e componente somem do mesmo jeito. Traga a coisa para o arquivo primeiro\n"
        "   (segredo entra como `type: SECRET` SEM `value` — o valor cifrado que já\n"
        "   está no painel permanece).\n"
        "   Ver docs/runbooks/conferir-spec-digitalocean.md."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
