import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { OPERATOR_KIT_SURFACES } from "./support/surfaceRegistry";

// Guardrail da AUTORIZAÇÃO DE GERENTE: uma estrutura só na suíte inteira.
//
// Em 28/10/2026 o dono achou, cancelando venda de teste no Gestor, o diálogo de
// gerente pedindo o nome DIGITADO ("erro crasso, já tínhamos resolvido"). Já
// tinha sido resolvido em 21/09 (`cfb10c14a`, a lista de gerentes no Gestor), e
// voltou porque a peça de identificação guardava um campo de nome livre como
// "porta de saída" da lista vazia. No alpha a lista é vazia sempre que a Joyce
// opera (é a única gerente com PIN, e a lista tira quem opera).
//
// E havia uma segunda moldura em volta da mesma peça: o `PosCancelSaleDialog`
// montava o próprio diálogo com o `OperatorIdentify`, repetindo a decisão do
// campo livre. Cada moldura própria é um lugar a mais onde a regra pode voltar.
//
// A regra que esta trava segura:
//   1. `OperatorIdentify` só é usado pelo `OperatorLock` (destrave) e pelo
//      `OperatorManagerAuth` (autorização). Toda autorização de gerente passa
//      pelo `OperatorManagerAuth`; contexto do ato vai no slot `context`.
//   2. Ninguém reintroduz o campo de nome digitado.

const surfacesDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const SCOPE = [...OPERATOR_KIT_SURFACES, "operator-kit"];
const SKIP = new Set(["node_modules", ".nuxt", ".output", "dist", "tests", "coverage"]);

function sourceFiles(dir: string, found: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    if (SKIP.has(entry)) continue;
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) sourceFiles(path, found);
    else if (/\.(vue|ts)$/.test(entry)) found.push(path);
  }
  return found;
}

const files = SCOPE.flatMap((app) => sourceFiles(join(surfacesDir, app, "app")));
const rel = (path: string) => relative(surfacesDir, path);

describe("autorização de gerente: uma estrutura só", () => {
  it("varre os apps do kit", () => {
    expect(files.length).toBeGreaterThan(100);
  });

  it("OperatorIdentify só mora no destrave e na autorização do kit", () => {
    const users = files
      .filter((path) => /<OperatorIdentify\b/.test(readFileSync(path, "utf8")))
      .map(rel)
      .sort();
    expect(users).toEqual([
      "operator-kit/app/components/OperatorLock.vue",
      "operator-kit/app/components/OperatorManagerAuth.vue",
    ]);
  });

  it("nenhuma tela pede o nome do gerente digitado", () => {
    const offenders = files
      .filter((path) =>
        /allow-typed-name|allowTypedName|typedName|Nome do gerente/.test(readFileSync(path, "utf8")),
      )
      .map(rel);
    expect(offenders).toEqual([]);
  });
});
