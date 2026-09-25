#!/usr/bin/env python
"""Cria um app de operador novo em `surfaces/` e o registra em todos os lugares.

## Por que existe

Superfície nova entra em mais de dez arquivos, e faltar em um não acusa nada no
dia: o `purchase-nuxt` ficou fora do Dependabot desde que nasceu. A trava
(`scripts/check_surface_registry.py`) acusa o que falta; este gerador faz a
superfície já nascer inteira, e termina rodando a própria trava.

## O que ele faz

1. Registra o app em `surfaces/registry.json` (porta = a maior + 1).
2. Gera `surfaces/<id>-nuxt/` a partir do molde: casca de operador que estende
   `../operator-kit` (BFF canônico, `/health/*`, login/PIN, rail, PWA), com as
   dependências e o lock do `hub-nuxt` (o conjunto base, sem extra nenhum) e um
   teste de contrato da casca.
3. Escreve o app em cada lugar que enumera superfícies: Dependabot, as duas
   matrizes do `surfaces-gate.yml`, `SURFACES` do Makefile, `groups.json`,
   `Dockerfile.operator-group`, os dois specs de `.do/` (ingress, `OPERATOR_HOSTS`,
   env da URL), `CSRF_TRUSTED_ORIGINS` de dev, a env e o tile do Shopman Apps no
   Django, `app-identity.json`, o perfil do gate de PWA e a árvore do
   `CLAUDE.md`/`README.md`.
4. Gera os ícones PWA se o `operator-kit` tiver `node_modules`; senão, diz o comando.

## O que ele NÃO decide

- **O subdomínio** é argumento obrigatório: hostname é DNS e é do dono. O
  gerador escreve no spec o que foi pedido; o registro de DNS continua manual.
- **A permissão.** O app nasce trancado na permissão pedida em `perm=`, que
  precisa existir no Django, e o tile do Shopman Apps nasce visível só para
  superusuário (falha fechada) até alguém trocar pelo predicado certo.
- **A copy.** O rótulo vem do argumento; descrição e convite de instalação saem
  num formato neutro, e o vocabulário fechado (`docs/reference/suite-vocabulary.md`)
  é quem decide a versão final.
- **Superfície de cliente.** Existe uma, a loja, e ela tem voz própria.

## Uso

    make new-surface name=loyalty label="Fidelidade" subdomain=fidelidade \\
        group=operator-office perm=backstage.view_loyalty \\
        color="#5B6B2E" symbol=lucide:heart-handshake

    python scripts/new_surface.py --name loyalty ... --dry-run   # só diz o que faria
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOLD_DEPENDENCIES = "hub-nuxt"
NAME_RE = re.compile(r"^[a-z][a-z0-9]{1,19}$")
COLOR_RE = re.compile(r"^#[0-9A-F]{6}$")


class SurfaceError(Exception):
    pass


# ── edição de texto com âncora ──────────────────────────────────────────────


class Repo:
    """Escritas no repositório com âncora obrigatória: âncora que sumiu é erro, nunca chute."""

    def __init__(self, root: Path, dry_run: bool = False):
        self.root = root
        self.dry_run = dry_run
        self.touched: list[str] = []

    def read(self, rel: str) -> str:
        return (self.root / rel).read_text(encoding="utf-8")

    def write(self, rel: str, content: str) -> None:
        self.touched.append(rel)
        if self.dry_run:
            return
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def insert_after_last(
        self, rel: str, pattern: str, new_lines: str, *, within: tuple[str, str] | None = None
    ) -> None:
        """Insere `new_lines` depois da ÚLTIMA linha que casa `pattern` (opcionalmente dentro de um trecho)."""
        source = self.read(rel)
        lines = source.splitlines(keepends=True)
        start, end = 0, len(lines)
        if within:
            start = _index(lines, within[0], rel)
            end = next((i for i in range(start + 1, len(lines)) if re.search(within[1], lines[i])), len(lines))
        matches = [i for i in range(start, end) if re.search(pattern, lines[i])]
        if not matches:
            raise SurfaceError(f"{rel}: não achei a âncora {pattern!r}")
        at = matches[-1] + 1
        lines[at:at] = [new_lines if new_lines.endswith("\n") else new_lines + "\n"]
        self.write(rel, "".join(lines))

    def replace_once(self, rel: str, old: str, new: str) -> None:
        source = self.read(rel)
        if source.count(old) != 1:
            raise SurfaceError(f"{rel}: esperava a âncora exatamente uma vez: {old!r}")
        self.write(rel, source.replace(old, new))


def _index(lines: list[str], pattern: str, rel: str) -> int:
    for i, line in enumerate(lines):
        if re.search(pattern, line):
            return i
    raise SurfaceError(f"{rel}: não achei {pattern!r}")


# ── o registro ──────────────────────────────────────────────────────────────


def load_registry(root: Path) -> dict:
    return json.loads((root / "surfaces/registry.json").read_text(encoding="utf-8"))


def dump_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def dump_groups(groups: dict) -> str:
    """O formato à mão do `groups.json`: um app por linha."""
    out = ["{"]
    for g, (name, group) in enumerate(groups.items()):
        out.append(f'  "{name}": {{')
        out.append(f'    "description": {json.dumps(group["description"], ensure_ascii=False)},')
        out.append('    "apps": [')
        for a, app in enumerate(group["apps"]):
            body = ", ".join(f'"{k}": {json.dumps(v, ensure_ascii=False)}' for k, v in app.items())
            out.append(f"      {{ {body} }}{',' if a < len(group['apps']) - 1 else ''}")
        out.append("    ]")
        out.append(f"  }}{',' if g < len(groups) - 1 else ''}")
    out.append("}")
    return "\n".join(out) + "\n"


# ── o app ───────────────────────────────────────────────────────────────────


def nuxt_config(app_id: str) -> str:
    return f"""import tailwindcss from "@tailwindcss/vite";
import {{ definePwaCapability }} from "../operator-kit/pwa.config";

export default defineNuxtConfig({{
  extends: ["../operator-kit"],
  ssr: false,

  compatibilityDate: "2026-05-16",
  devtools: {{ enabled: false }},

  runtimeConfig: {{
    djangoBaseUrl: process.env.NUXT_DJANGO_BASE_URL || "http://127.0.0.1:8000",
    public: {{
      // O NOME da chave é o contrato com a env: o Nuxt deriva
      // public.djangoBaseUrl <- NUXT_PUBLIC_DJANGO_BASE_URL.
      djangoBaseUrl:
        process.env.NUXT_PUBLIC_DJANGO_BASE_URL || process.env.NUXT_DJANGO_BASE_URL || "http://127.0.0.1:8000",
    }},
  }},

  modules: [
    definePwaCapability({{
      app: "{app_id}",
      display: "standalone",
      wakeLock: false,
      kiosk: false,
    }}),
    "@nuxtjs/color-mode",
    "motion-v/nuxt",
    "@vueuse/nuxt",
    "@nuxt/icon",
    "@nuxt/fonts",
    "@nuxt/eslint",
    "vue-sonner/nuxt",
  ],

  fonts: {{
    families: [
      {{ name: "Instrument Sans", provider: "google", weights: [400, 500, 600, 700], styles: ["normal"] }},
    ],
  }},

  imports: {{
    imports: [
      {{ from: "tailwind-variants", name: "tv" }},
      {{ from: "tailwind-variants", name: "VariantProps", type: true }},
      {{ from: "vue-sonner", name: "toast", as: "useSonner" }},
    ],
  }},

  colorMode: {{
    preference: "light",
    fallback: "light",
    storageKey: "{app_id}-nuxt-color-mode",
    classSuffix: "",
  }},

  icon: {{
    clientBundle: {{ scan: true, sizeLimitKb: 0 }},
    mode: "svg",
    class: "shrink-0",
    fetchTimeout: 2000,
    serverBundle: "local",
  }},

  css: ["~/assets/css/tailwind.css"],

  app: {{
    baseURL: process.env.NUXT_APP_BASE_URL || "/",
    head: {{
      htmlAttrs: {{ lang: "pt-BR" }},
      // `title` e `theme-color` saem da capability PWA (surfaces/operator-kit/app-identity.json).
      meta: [
        {{ name: "viewport", content: "width=device-width, initial-scale=1, viewport-fit=cover" }},
        {{ name: "robots", content: "noindex, nofollow" }},
      ],
    }},
  }},

  vite: {{
    plugins: [tailwindcss()],
    server: {{
      allowedHosts: [".ngrok-free.app", ".trycloudflare.com"],
    }},
  }},
}});
"""


def app_vue(perm: str, label: str, article: str) -> str:
    return f"""<script setup lang="ts">
// Casca do app: gate de operador + rail + outlet. As telas são páginas próprias (pages/).
const OPERATOR_PERM = "{perm}";
const {{ canIdentify, sessionUnavailable, refresh, locked, mustChange, operator, lock }} = useOperatorLock(OPERATOR_PERM);

const hubUrl = useRuntimeConfig().public.operatorHubUrl as string;

useOperatorWindowTitle();
</script>

<template>
  <div class="flex min-h-screen bg-background text-foreground">
    <NuxtRouteAnnouncer />
    <OfflineBanner />
    <div v-if="canIdentify" class="sticky top-0 flex h-screen shrink-0 print:hidden">
      <OperatorRail
        :hub-url="hubUrl"
        :operator-name="operator?.name"
        @lock="lock"
      />
    </div>
    <div class="flex min-w-0 flex-1 flex-col">
      <NuxtPage v-if="canIdentify" />
    </div>
    <!-- Erro de rede NÃO é sessão morta: sem esta guarda, todo redeploy
         subiria a tela de senha com a sessão viva. -->
    <OperatorSessionUnavailable v-if="sessionUnavailable" scope="{article} {label}" @retry="refresh()" />
    <OperatorLogin v-if="!canIdentify && !sessionUnavailable" />
    <OperatorLock v-else-if="locked || mustChange" :perm="OPERATOR_PERM" />
    <OperatorSonner />
    <OperatorPwaRuntime />
  </div>
</template>
"""


def index_vue(label: str) -> str:
    return f"""<template>
  <main class="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-2 p-6">
    <h1 class="text-2xl font-semibold">{label}</h1>
  </main>
</template>
"""


def shell_test(app_id: str, perm: str) -> str:
    return f"""import {{ readFileSync }} from "node:fs";
import {{ describe, expect, it }} from "vitest";

// Contrato da casca: o app só abre para quem tem a permissão dele, e distingue
// erro de rede de sessão morta antes de pedir a senha.
const shell = readFileSync(new URL("../app/app.vue", import.meta.url), "utf8");
const config = readFileSync(new URL("../nuxt.config.ts", import.meta.url), "utf8");

describe("casca do {app_id}", () => {{
  it("tranca na permissão do app", () => {{
    expect(shell).toContain('const OPERATOR_PERM = "{perm}"');
    expect(shell).toContain("useOperatorLock(OPERATOR_PERM)");
  }});

  it("não confunde erro de rede com sessão morta", () => {{
    expect(shell).toContain("sessionUnavailable");
    expect(shell).toContain("OperatorLogin");
  }});

  it("estende a layer e declara a identidade PWA certa", () => {{
    expect(config).toContain('extends: ["../operator-kit"]');
    expect(config).toContain('app: "{app_id}"');
  }});
}});
"""


def offline_html(label: str, color: str) -> str:
    return (
        '<!doctype html>\n<html lang="pt-BR"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        f'<meta name="theme-color" content="{color}"><title>{label} sem conexão</title>'
        '<style>:root{font-family:"Instrument Sans",system-ui,sans-serif;color-scheme:light}*{box-sizing:border-box}'
        "body{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px;background:#fafaf9;color:#1f2933}"
        "main{width:min(100%,440px);border:1px solid #e2e8f0;border-radius:10px;background:#fff;padding:24px;text-align:center}"
        "img{width:80px;height:80px;border-radius:18px}h1{margin:20px 0 8px;font-size:1.35rem}p{margin:0;color:#52606d;line-height:1.5}"
        "a{display:grid;place-items:center;margin-top:24px;min-height:44px;border-radius:8px;"
        f"background:{color};color:#fff;font-weight:700;text-decoration:none}}</style></head>"
        f'<body><main><img src="/pwa/pwa-192x192.png" alt=""><h1>{label} ficou sem conexão</h1>'
        "<p>Assim que a rede voltar, tente novamente.</p>"
        '<a href="/">Tentar de novo</a></main></body></html>\n'
    )


def write_app(repo: Repo, app_id: str, port: int, label: str, perm: str, article: str, color: str) -> None:
    d = f"surfaces/{app_id}-nuxt"
    mold = f"surfaces/{MOLD_DEPENDENCIES}"

    package = json.loads(repo.read(f"{mold}/package.json"))
    package["name"] = f"{app_id}-nuxt"
    scripts = package["scripts"]
    scripts["dev"] = f"nuxt dev --host 127.0.0.1 --port {port}"
    scripts["preview"] = f"HOST=127.0.0.1 nuxt preview --port {port}"
    scripts["pwa:assets"] = f"node ../operator-kit/scripts/generate-pwa-assets.mjs --app={app_id} --out=public/pwa"
    scripts.pop("test:e2e", None)
    repo.write(f"{d}/package.json", dump_json(package))

    # O lock do molde vale para o app novo porque as dependências são as MESMAS;
    # só o nome do pacote raiz muda. É o que mantém o app alinhado aos irmãos
    # (check_surface_versions) desde o primeiro commit.
    lock = json.loads(repo.read(f"{mold}/package-lock.json"))
    lock["name"] = f"{app_id}-nuxt"
    lock["packages"][""]["name"] = f"{app_id}-nuxt"
    repo.write(f"{d}/package-lock.json", json.dumps(lock, ensure_ascii=False, indent=2) + "\n")

    for name in (".gitignore", "tsconfig.json", "vitest.config.ts", "app/assets/css/tailwind.css", "public/robots.txt"):
        repo.write(f"{d}/{name}", repo.read(f"{mold}/{name}"))
    repo.write(
        f"{d}/eslint.config.mjs",
        "// Flat config: preset do Nuxt (@nuxt/eslint gera .nuxt/eslint.config.mjs no\n"
        "// `nuxt prepare`) + base compartilhada do operator-kit + Prettier por último.\n"
        'import withNuxt from "./.nuxt/eslint.config.mjs";\n'
        'import operatorKit from "../operator-kit/eslint.config.base.mjs";\n'
        'import prettier from "eslint-config-prettier";\n\n'
        "export default withNuxt(...operatorKit, prettier);\n",
    )
    repo.write(f"{d}/nuxt.config.ts", nuxt_config(app_id))
    repo.write(f"{d}/app/app.vue", app_vue(perm, label, article))
    repo.write(f"{d}/app/pages/index.vue", index_vue(label))
    repo.write(f"{d}/tests/shell.test.ts", shell_test(app_id, perm))
    repo.write(f"{d}/public/offline.html", offline_html(label, color))
    repo.write(
        f"{d}/README.md",
        f"# {label} (`{app_id}-nuxt`)\n\n"
        f"App de operador gerado por `make new-surface`. Estende `../operator-kit` (BFF, health,\n"
        f"login/PIN, rail, PWA) e está registrado em `surfaces/registry.json`.\n\n"
        f"```bash\nnpm ci && npm run dev   # http://127.0.0.1:{port}\n```\n",
    )


# ── os lugares que enumeram superfícies ─────────────────────────────────────


def register_everywhere(repo: Repo, s: dict, sibling: dict, domain_by_spec: dict[str, str], identity: dict) -> None:
    app_id, d, port, group = s["id"], s["dir"], s["dev_port"], s["service"]

    repo.insert_after_last(".github/dependabot.yml", r"^\s+- /surfaces/[a-z]+-nuxt$", f"      - /surfaces/{d}")

    gate = ".github/workflows/surfaces-gate.yml"
    repo.insert_after_last(
        gate, r"^\s{10}- [a-z]+-nuxt$", f"          - {d}", within=(r"^  app-quality:", r"^  [a-z-]+:$")
    )
    repo.insert_after_last(
        gate,
        r"^\s{12}surface: [a-z]+-nuxt$",
        f"          - app: {app_id}\n            surface: {d}",
        within=(r"^  pwa-quality:", r"^  [a-z-]+:$"),
    )

    line = next(ln for ln in repo.read("Makefile").splitlines() if ln.startswith("SURFACES :="))
    repo.replace_once("Makefile", line + "\n", f"{line} {d}\n")

    groups = json.loads(repo.read("surfaces/operator-router/groups.json"))
    groups[group]["apps"].append({"id": app_id, "surface": d})
    repo.write("surfaces/operator-router/groups.json", dump_groups(groups))

    docker = "surfaces/Dockerfile.operator-group"
    repo.replace_once(
        docker,
        "# Base de runtime comum:",
        f"FROM kit AS {app_id}\nCOPY surfaces/{d} ./surfaces/{d}\nRUN cd surfaces/{d} && npm ci && npm run build\n\n# Base de runtime comum:",
    )
    repo.insert_after_last(
        docker,
        r"^COPY --from=",
        f"COPY --from={app_id} /repo/surfaces/{d}/.output ./apps/{d}/.output",
        within=(rf"^FROM runtime AS {group}$", r"^FROM "),
    )

    for spec, domain in domain_by_spec.items():
        register_in_spec(repo, spec, s, sibling, domain)

    settings = "config/settings.py"
    repo.insert_after_last(
        settings,
        r'^\s+"http://127\.0\.0\.1:\d+",$',
        f'        "http://localhost:{port}",\n        "http://127.0.0.1:{port}",',
        within=(r"^\s*CSRF_TRUSTED_ORIGINS \+= \[", r"^\s*\]"),
    )
    env = s["base_url_env"]
    repo.insert_after_last(
        settings,
        r"^SHOPMAN_[A-Z]+_BASE_URL = \(os\.environ\.get\(",
        f"\n# Base URL pública do {s['label']} (surfaces/{d}). Vazio ⇒ o tile/link some, sem rota morta.\n"
        f'{env} = (os.environ.get("{env}") or "").strip().rstrip("/")',
    )
    repo.replace_once(
        settings,
        '        "loja": SHOPMAN_STOREFRONT_BASE_URL,\n',
        f'        "{s["hub_tile"]}": {env},\n        "loja": SHOPMAN_STOREFRONT_BASE_URL,\n',
    )

    hub = "shopman/backstage/projections/hub.py"
    repo.replace_once(
        hub,
        '    "loja": "http://127.0.0.1:3000/",\n',
        f'    "{s["hub_tile"]}": "http://127.0.0.1:{port}/",\n    "loja": "http://127.0.0.1:3000/",\n',
    )
    repo.replace_once(
        hub,
        '    _AppSpec("loja",',
        f'    _AppSpec("{s["hub_tile"]}", "{s["label"]}", "{identity["description"].rstrip(".")}", '
        f'"{identity["fallbackIcon"]}", "launch", is_superuser),\n    _AppSpec("loja",',
    )

    table = json.loads(repo.read("surfaces/operator-kit/app-identity.json"))
    table["apps"][app_id] = identity
    repo.write("surfaces/operator-kit/app-identity.json", dump_json(table))

    repo.insert_after_last(
        "tools/pwa-gate/check.mjs", r"^  [a-z]+: operatorProfile\(", f"  {app_id}: operatorProfile('{app_id}'),"
    )

    repo.insert_after_last(
        "CLAUDE.md",
        r"^├── [a-z]+-nuxt/ ",
        f"├── {d + '/':<18}{s['label']} (:{port}){' ' * 8}→ api./backstage",
        within=(r"^surfaces/\s", r"^└── "),
    )
    repo.insert_after_last("README.md", r"^│   ├── [a-z]+-nuxt/ ", f"│   ├── {d + '/':<24}# {s['label']} (:{port})")


def register_in_spec(repo: Repo, spec: str, s: dict, sibling: dict, domain: str) -> None:
    lines = repo.read(spec).splitlines(keepends=True)
    host, sibling_host = f"{s['subdomain']}.{domain}", f"{sibling['subdomain']}.{domain}"

    # Ingress: duplica a regra do irmão do mesmo grupo, trocando o host.
    at = _index(lines, rf"exact: {re.escape(sibling_host)}\s*$", spec)
    start = next(i for i in range(at, -1, -1) if re.match(r"^\s*- ", lines[i]))
    indent = len(lines[start]) - len(lines[start].lstrip())
    end = next(
        (
            i
            for i in range(start + 1, len(lines))
            if lines[i].strip() and len(lines[i]) - len(lines[i].lstrip()) <= indent
        ),
        len(lines),
    )
    rule = "".join(lines[start:end]).replace(sibling_host, host)
    lines[end:end] = [f"{' ' * indent}# {s['dir']} — host {s['subdomain']}.\n", rule]

    # OPERATOR_HOSTS do grupo e env da URL pública: o valor do irmão diz o formato.
    source = "".join(lines)
    pair = f"{sibling['id']}={sibling_host}"
    if source.count(pair) != 1:
        raise SurfaceError(f"{spec}: esperava `{pair}` uma vez no OPERATOR_HOSTS")
    source = source.replace(pair, f"{pair},{s['id']}={host}")

    env_block = re.search(rf"^(\s*)- key: {sibling['base_url_env']}\n(?:\1  .*\n)+", source, re.M)
    if not env_block:
        raise SurfaceError(f"{spec}: não achei a env {sibling['base_url_env']}")
    block = env_block.group(0).replace(sibling["base_url_env"], s["base_url_env"]).replace(sibling_host, host)
    source = source[: env_block.end()] + block + source[env_block.end() :]
    repo.write(spec, source)


def spec_domain(repo: Repo, spec: str) -> str:
    match = re.search(r"exact: api\.(\S+)", repo.read(spec))
    if not match:
        raise SurfaceError(f"{spec}: sem host `api.` no ingress")
    return match.group(1)


# ── orquestração ────────────────────────────────────────────────────────────


def create(
    root: Path,
    *,
    name: str,
    label: str,
    subdomain: str,
    group: str,
    perm: str,
    color: str,
    symbol: str,
    fallback_icon: str | None = None,
    article: str = "o",
    description: str | None = None,
    dry_run: bool = False,
) -> Repo:
    registry = load_registry(root)
    surfaces = registry["surfaces"]
    color = color.upper()
    if not NAME_RE.match(name):
        raise SurfaceError(f"name={name!r}: use minúsculas e dígitos, começando por letra (vira o prefixo das envs)")
    if name in surfaces or (root / f"surfaces/{name}-nuxt").exists():
        raise SurfaceError(f"{name} já existe")
    if group not in registry["operator_groups"]:
        raise SurfaceError(f"group={group!r}: use um de {sorted(registry['operator_groups'])}")
    if not re.match(r"^[a-z][a-z0-9-]*$", subdomain) or any(s.get("subdomain") == subdomain for s in surfaces.values()):
        raise SurfaceError(f"subdomain={subdomain!r} inválido ou já usado")
    if not re.match(r"^[a-z_]+\.[a-z_]+$", perm):
        raise SurfaceError(f"perm={perm!r}: use `<app_label>.<codename>`")
    if not COLOR_RE.match(color):
        raise SurfaceError(f"color={color!r}: use #RRGGBB")
    if not re.match(r"^(lucide|tabler):[a-z0-9-]+$", symbol):
        raise SurfaceError(f"symbol={symbol!r}: use lucide:<nome> ou tabler:<nome>")

    siblings = [dict(s, id=k) for k, s in surfaces.items() if s.get("service") == group and s.get("base_url_env")]
    if not siblings:
        raise SurfaceError(f"{group} não tem app com URL pública para servir de molde no spec")
    sibling = siblings[-1]

    port = max(s["dev_port"] for s in surfaces.values()) + 1
    entry = {
        "dir": f"{name}-nuxt",
        "kind": "operator",
        "dev_port": port,
        "service": group,
        "subdomain": subdomain,
        "base_url_env": f"SHOPMAN_{name.upper()}_BASE_URL",
        "hub_tile": name,
    }
    icon = fallback_icon or symbol.split(":", 1)[1]
    identity = {
        "label": label,
        "description": description or f"{label} da operação.",
        "symbol": symbol,
        "fallbackIcon": icon,
        "color": color,
        "article": article,
        "install": f"Abra {article} {label} direto da tela inicial deste dispositivo.",
    }

    repo = Repo(root, dry_run=dry_run)
    domains = {spec: spec_domain(repo, spec) for spec in (".do/app.subdomains.yaml", ".do/app.alpha-subdomains.yaml")}

    surfaces[name] = entry
    repo.write("surfaces/registry.json", dump_json(registry))
    write_app(repo, name, port, label, perm, article, color)
    register_everywhere(repo, dict(entry, id=name, label=label), sibling, domains, identity)
    return repo


def generate_icons(root: Path, name: str) -> bool:
    kit = root / "surfaces/operator-kit"
    if not (kit / "node_modules/sharp").exists():
        return False
    app = root / f"surfaces/{name}-nuxt"
    subprocess.run(
        ["node", str(kit / "scripts/generate-pwa-assets.mjs"), f"--app={name}", "--out=public/pwa"],
        cwd=app,
        check=True,
    )
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", required=True, help="id do app (prefixo das envs): loyalty")
    parser.add_argument("--label", required=True, help='rótulo do app: "Fidelidade"')
    parser.add_argument("--subdomain", required=True, help="rótulo do hostname (DNS é do dono): fidelidade")
    parser.add_argument("--group", required=True, help="operator-floor ou operator-office")
    parser.add_argument("--perm", required=True, help="permissão Django que abre o app: backstage.view_loyalty")
    parser.add_argument("--color", required=True, help="cor do ícone e da barra de título: #5B6B2E")
    parser.add_argument("--symbol", required=True, help="ícone Iconify: lucide:heart-handshake")
    parser.add_argument("--fallback-icon", help="nome Lucide do tile quando o PNG não carrega (padrão: o do symbol)")
    parser.add_argument("--article", default="o", help='artigo do rótulo: "o", "a", "as"')
    parser.add_argument("--description", help="frase do manifesto")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--root", default=str(ROOT), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = Path(args.root)

    try:
        repo = create(
            root,
            name=args.name,
            label=args.label,
            subdomain=args.subdomain,
            group=args.group,
            perm=args.perm,
            color=args.color,
            symbol=args.symbol,
            fallback_icon=args.fallback_icon,
            article=args.article,
            description=args.description,
            dry_run=args.dry_run,
        )
    except SurfaceError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2

    print(("[dry-run] escreveria" if args.dry_run else "escrito") + ":")
    for rel in dict.fromkeys(repo.touched):
        print(f"  {rel}")
    if args.dry_run:
        return 0

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import check_surface_registry

    errors = check_surface_registry.run(root)
    for error in errors:
        print(f"✗ {error}", file=sys.stderr)
    icons = generate_icons(root, args.name)
    d = f"surfaces/{args.name}-nuxt"
    print(
        f"""
Próximos passos (fora do alcance do gerador):
  1. {"ícones PWA gerados" if icons else f"ícones PWA: cd {d} && npm run pwa:assets (precisa do npm ci no operator-kit)"}
  2. cd {d} && npm ci && npm run typecheck && npm test && npm run lint
  3. a permissão {args.perm} tem de existir no Django; troque o `is_superuser` do tile em
     shopman/backstage/projections/hub.py pelo predicado dela
  4. a API do app no backstage (shopman/backstage/api/) e a primeira tela de verdade
  5. o registro de DNS de {args.subdomain}. é do dono — o spec já roteia o host
"""
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
