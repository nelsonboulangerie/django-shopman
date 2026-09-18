import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Guardrail de VOCABULÁRIO: a palavra da casa para o objeto que o operador segura é
// **dispositivo**; a do cartão é **maquininha**. "Aparelho" não é nenhuma das duas. É o
// `WP-COPY-VUE-SWEEP` da §5.5 de `docs/reference/omotenashi-copy.md`.
//
// ## Por que a irmã de Python não bastava
//
// `shopman/backstage/tests/test_vocabulario_de_tela.py` varre os `.py` desde 17/09.
// String de `.vue` e de `.ts` passava por baixo dela, e "por baixo dela" é onde moram
// as nove superfícies — metade do sistema. Uma regra que vale em metade do sistema,
// como já está escrito no CLAUDE.md sobre URLs, não é convenção, é lembrança.
//
// A prova de que lembrança não segura: o commit `ab50a503d` (17/09/2026) é uma
// varredura manual `aparelho` → `dispositivo`, deliberada, com o critério na mensagem
// e 17 arquivos tocados — e deixou `navigator.platform || "Aparelho"` de pé no
// `useWebPush.ts`, que é o arquivo que ela mesma editou, na linha que vira o NOME DO
// DISPOSITIVO na tela quando o navegador não diz qual é.
//
// ## Por que ela varre o arquivo inteiro, e não só o texto de tela
//
// A trava de Python nasceu recusando a palavra só em literal de string: comentário e
// docstring ficavam livres, porque a regra era "sobre a palavra na tela". Em
// 18/09/2026 o dono ampliou: *"não usamos o termo aparelho"*. Então o canal deixou de
// importar — template, string, comentário e nome de teste contam igual. O que mudou não
// foi o rigor, foi o sujeito da regra: era a tela, virou a palavra. É também o que
// dispensa a inversão do `stripNoise` de `guardrails.identifiers.test.ts`: lá é preciso
// separar código de prosa porque a regra do identificador só vale para um dos dois.
// Aqui vale para os dois.
//
// ## Por que o Storefront fica de fora — e isto é decisão, não buraco
//
// A loja diz **aparelho** ao cliente, com autorização do dono, reafirmada por ele na
// mesma conversa de 18/09 que fechou a regra aqui: *"pode manter assim só lá:
// aparelho"*. Superfície de cliente final tem voz própria, e quem escreve para o
// cliente não herda o vocabulário de quem escreve para o balcão. A exenção é da
// SUPERFÍCIE inteira, de propósito: meia superfície com duas palavras é pior do que
// qualquer uma das duas — é o defeito D7c, e ele já existe lá dentro
// (`conta/seguranca.vue` diz as duas). Consertar isso é da frente que aplica o
// relatório de copy do Storefront, não desta trava.
//
// ⚠️ Ela lê os ARQUIVOS, não a branch: num worktree, verde só vale para o que está ali.

const surfacesDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");

/** A palavra proibida, nas duas caixas e no plural. */
const BANNED = /aparelh/i;

// `.mjs` entra pelo `operator-router`, que é superfície e não é Nuxt; `.py` entra pelo
// harness visual do Marketing, que serve as respostas do servidor para o retrato.
const SOURCE_EXT = [".ts", ".vue", ".mjs", ".py"];

/** Voz do cliente final, por decisão do dono (ver acima). Não é dívida a pagar. */
const EXEMPT_SURFACES = ["storefront-nuxt/"];

const SKIP_DIRS = new Set([
  "node_modules",
  ".nuxt",
  ".output",
  "dist",
  "coverage",
  "test-results",
  "playwright-report",
  "blob-report",
]);

// Os dois arquivos que PRECISAM escrever a palavra, porque é o que eles recusam.
// Allowlist curta e nominal de propósito: a lista que cresce sem ninguém olhar é como
// a regra morre. Terceiro nome aqui é sinal de que alguém está contornando a trava.
const MAY_QUOTE = new Set([
  "operator-kit/tests/guardrails.vocabulary.test.ts",
  "marketing-nuxt/tests/operatorLanguage.test.ts",
]);

function sourceFiles(dir: string, found: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    if (SKIP_DIRS.has(entry)) continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) sourceFiles(full, found);
    else if (SOURCE_EXT.some((extension) => full.endsWith(extension))) found.push(full);
  }
  return found;
}

const SOURCES = sourceFiles(surfacesDir).filter((file) => {
  const path = relative(surfacesDir, file);
  return (
    !MAY_QUOTE.has(path) && !EXEMPT_SURFACES.some((prefix) => path.startsWith(prefix))
  );
});

function offenders(file: string): string[] {
  return readFileSync(file, "utf8")
    .split("\n")
    .flatMap((line, index) =>
      BANNED.test(line)
        ? [`${relative(surfacesDir, file)}:${index + 1}: ${line.trim()}`]
        : [],
    );
}

describe("a palavra da casa é dispositivo — e a do cartão é maquininha", () => {
  it("nenhum arquivo das superfícies diz 'aparelho'", () => {
    const leaks = SOURCES.flatMap(offenders);

    expect(
      leaks,
      "A palavra da casa é 'dispositivo' — ou 'maquininha', quando o objeto é a\n" +
        "maquininha de cartão. A trava não escreve a substituição: leia a linha e\n" +
        "escolha, porque trocar mecanicamente já produziu 'aparelho (maquininha)'.\n" +
        `Onde:\n  ${leaks.join("\n  ")}`,
    ).toEqual([]);
    // Varredura de 1.553 arquivos em disco, com os outros projetos rodando ao lado:
    // o limite padrão de 5 s é relógio de máquina, não sinal de regra quebrada.
  }, 30_000);

  // Varredura que não varre nada passa sempre. Oito apps de operador + a layer + o
  // router: o piso existe para que a próxima superfície nasça coberta sem ninguém
  // lembrar de incluí-la, e a lista fechada obriga quem exentar uma a dizer aqui.
  it("a varredura enxerga as superfícies de operador inteiras, não um recorte", () => {
    expect(SOURCES.length).toBeGreaterThan(400);

    const apps = new Set(SOURCES.map((file) => relative(surfacesDir, file).split("/")[0]));
    expect([...apps].sort()).toEqual([
      "bi-nuxt",
      "hub-nuxt",
      "kds-nuxt",
      "marketing-nuxt",
      "operator-kit",
      "operator-router",
      "orders-nuxt",
      "pos-nuxt",
      "production-nuxt",
      "purchase-nuxt",
    ]);
  });
});
