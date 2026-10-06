import { existsSync, readFileSync, readdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  DEPLOYED_OPERATOR_SURFACES,
  OPERATOR_SURFACES,
} from "./support/surfaceRegistry";

// Todo ícone dos apps de operador sai do BUNDLE do cliente, nunca da rede no meio do
// gesto. Irmã de `surfaces/storefront-nuxt/tests/iconCollections.test.ts` (#1311).
//
// O `@nuxt/icon` (`clientBundle.scan`) só embute no bundle os ícones de coleções
// INSTALADAS (`@iconify-json/<prefixo>`). Ícone de coleção ausente é buscado em
// `/api/_nuxt_icon/<prefixo>.json` na primeira vez que aparece. O spinner dos botões
// (`line-md:loading-loop`) era assim, e o toque em "Atualizar" do aviso de versão nova
// o faz aparecer no mesmo instante em que o Chromium desliga o worker antigo para
// ativar o novo. Requisição durante esse desligamento religa o worker antigo
// (`ServiceWorkerVersion::OnStoppedInternal`), e a ativação passa a esperar 30 s de
// ociosidade ou o timer de 5 min: o botão gira e a versão nova não entra. Foi provado
// no storefront (#1311); os apps de operador têm o mesmo plugin, o mesmo
// `updateServiceWorker(true)` e o mesmo spinner. Sem rede, o ícone simplesmente não
// aparecia.
//
// ## Onde a coleção mora
//
// Na LAYER (`operator-kit/package.json`), e vale para os nove apps: o `@nuxt/icon`
// 2.5 resolve coleções a partir do `rootDir` do app E do diretório de cada layer
// (`getResolvePaths`), tanto na descoberta (`serverBundle: "local"`) quanto no
// `clientBundle`. Medido no build do hub-nuxt, que não declara `line-md` e só o usa
// pela layer (`OperatorLogin.vue`): antes, "client bundle consist of 63 icons" e o
// nome `line-md:loading-loop` sem corpo no JS; depois, 64 ícones com o SVG embutido.
// Por isso coleção usada pela LAYER tem de estar instalada na layer: instalada só num
// app, os outros oito buscariam pela rede. A coleção usada só por um app pode morar no
// app ou na layer.
//
// ⚠️ Ela lê os ARQUIVOS, não a branch: num worktree, verde só vale para o que está ali.

const kitDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const surfacesDir = resolve(kitDir, "..");
const require = createRequire(import.meta.url);
const iconifyPrefixes = new Set(
  Object.keys(require("@iconify/collections/collections.json")),
);

const ICON_LITERAL =
  /["'`]([a-z0-9]+(?:-[a-z0-9]+)*):([a-z0-9]+(?:-[a-z0-9]+)*)["'`]/g;

function installedCollections(dir: string): Set<string> {
  const pkg = JSON.parse(readFileSync(join(dir, "package.json"), "utf8"));
  return new Set(
    Object.keys({ ...pkg.dependencies, ...pkg.devDependencies })
      .filter((name) => name.startsWith("@iconify-json/"))
      .map((name) => name.slice("@iconify-json/".length)),
  );
}

function sourceFiles(root: string, dir: string): string[] {
  if (!existsSync(join(root, dir))) return [];
  return readdirSync(join(root, dir), { withFileTypes: true }).flatMap(
    (entry) => {
      const path = `${dir}/${entry.name}`;
      if (entry.isDirectory()) return sourceFiles(root, path);
      return /\.(vue|ts)$/.test(entry.name) ? [path] : [];
    },
  );
}

/** Ícones citados no código que vai para o navegador, por prefixo de coleção. */
function iconNames(root: string, dirs: string[]): Map<string, string[]> {
  const byPrefix = new Map<string, string[]>();
  for (const file of dirs.flatMap((dir) => sourceFiles(root, dir))) {
    const source = readFileSync(join(root, file), "utf8");
    for (const [, prefix, name] of source.matchAll(ICON_LITERAL)) {
      if (!prefix || !iconifyPrefixes.has(prefix)) continue;
      const list = byPrefix.get(prefix) ?? [];
      list.push(`${prefix}:${name} (${file})`);
      byPrefix.set(prefix, list);
    }
  }
  return byPrefix;
}

function missing(
  used: Map<string, string[]>,
  installed: Set<string>,
): string[] {
  return [...used]
    .filter(([prefix]) => !installed.has(prefix))
    .map(
      ([prefix, icons]) =>
        `@iconify-json/${prefix}: ${icons.slice(0, 3).join(", ")}`,
    );
}

const kitInstalled = installedCollections(kitDir);
const kitIcons = iconNames(kitDir, ["app", "runtime"]);

describe("coleções de ícones dos apps de operador", () => {
  it("acha os ícones da layer e de cada app (a varredura não está cega)", () => {
    expect(kitIcons.get("lucide")?.length).toBeGreaterThan(20);
    expect(
      kitIcons
        .get("line-md")
        ?.some((icon) => icon.startsWith("line-md:loading-loop")),
    ).toBe(true);
    expect(OPERATOR_SURFACES.length).toBeGreaterThanOrEqual(8);
    for (const app of DEPLOYED_OPERATOR_SURFACES) {
      expect(
        iconNames(join(surfacesDir, app), ["app"]).get("lucide")?.length,
        app,
      ).toBeGreaterThan(0);
    }
  });

  it("todo prefixo usado pela layer tem a coleção instalada NA layer (vale para os nove apps)", () => {
    expect(missing(kitIcons, kitInstalled)).toEqual([]);
  });

  it.each(OPERATOR_SURFACES)(
    "%s: todo prefixo usado tem a coleção instalada no app ou na layer",
    (app) => {
      const appDir = join(surfacesDir, app);
      const installed = new Set([
        ...kitInstalled,
        ...installedCollections(appDir),
      ]);
      expect(missing(iconNames(appDir, ["app"]), installed)).toEqual([]);
    },
  );
});
