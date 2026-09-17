import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// VARREDURA: todo link de um app de operador para OUTRO app tem que passar pela regra
// do kit (`crossAppLinkAttrs`). Um `<a :href="hubUrl">` sem `:target` navega a própria
// janela para outra origem — e é isso que produz a tarja de "saiu do app" com o título
// e a cor do app de origem. O caso foi encontrado em dois lugares de uma vez (o rail e
// a tela de "sem acesso" do Marketing); é o tipo de coisa que volta pela porta dos
// fundos num app novo, então quem lembra é o CI.
const surfacesDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const OPERATOR_APPS = [
  "pos-nuxt",
  "kds-nuxt",
  "orders-nuxt",
  "production-nuxt",
  "hub-nuxt",
  "marketing-nuxt",
  "purchase-nuxt",
  "bi-nuxt",
] as const;

/** Href que sai da própria origem: a URL de outro app de operador. */
const CROSS_APP_HREF = /:href="(hubUrl|centralUrl|tile\.url)"/;

function vueFiles(dir: string): string[] {
  const out: string[] = [];
  let entries: string[];
  try {
    entries = readdirSync(dir);
  } catch {
    return out;
  }
  for (const entry of entries) {
    if (entry === "node_modules" || entry.startsWith(".")) continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...vueFiles(full));
    else if (entry.endsWith(".vue")) out.push(full);
  }
  return out;
}

/** O texto da tag que contém o índice dado (do `<` anterior até o `>` seguinte). */
function enclosingTag(source: string, index: number): string {
  const start = source.lastIndexOf("<", index);
  const end = source.indexOf(">", index);
  return source.slice(start, end + 1);
}

describe("link para outro app de operador", () => {
  it("nunca navega a própria janela: todo href cross-app declara :target", () => {
    const offenders: string[] = [];
    let scanned = 0;
    for (const app of OPERATOR_APPS) {
      for (const file of vueFiles(join(surfacesDir, app, "app"))) {
        const source = readFileSync(file, "utf8");
        for (const match of source.matchAll(new RegExp(CROSS_APP_HREF, "g"))) {
          scanned += 1;
          const tag = enclosingTag(source, match.index ?? 0);
          if (!tag.includes(":target=")) offenders.push(`${app}: ${file.slice(surfacesDir.length + 1)}`);
        }
      }
    }
    expect(offenders, "use useOperatorAppLink().attrsFor(href) e ligue :target/:rel").toEqual([]);
    // Varredura que não acha nada não prova nada: se o padrão do href mudar (ou os
    // links saírem do lugar), este teste passaria a ser decorativo sem ninguém notar.
    // Hoje são os tiles da Central e o "Voltar à Central" da tela sem acesso do Marketing.
    expect(scanned, "a varredura parou de encontrar os links cross-app").toBeGreaterThanOrEqual(2);
  });

  it("o próprio rail do kit — a origem do padrão — está em dia", () => {
    const rail = readFileSync(join(surfacesDir, "operator-kit", "app", "components", "OperatorRail.vue"), "utf8");
    expect(rail).toContain("useOperatorAppLink()");
    expect(rail).toContain(":target=\"centralUrl ? centralLink.target : undefined\"");
  });
});
