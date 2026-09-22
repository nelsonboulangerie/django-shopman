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

// ─────────────────────────────────────────────────────────────────────────────
// Guardrail de VOCABULÁRIO, segunda regra: o objeto que a Produção planeja,
// inicia e fecha chama-se **lote**. Decisão do dono em 22/09/2026, diante dos
// três nomes que a mesma coisa tinha na tela ("lote" × "fornada" × "ordem de
// produção"): *"lote, genérico mesmo"*. A razão é de fato, não de gosto —
// *fornada* só serve para o que vai ao forno, e a casa produz coisa que não vai
// ao forno.
//
// Não há ambiguidade nova com o `Batch` do stockman, que já é "Lote" em
// português: pela ADR-017 uma fornada PRODUZ um lote — são o mesmo objeto visto
// de dois lados, e adotar "lote" na tela alinha a palavra ao modelo. Onde a
// frase precisava dizer os dois ("Esta fornada não possui lotes identificáveis"),
// ela foi reescrita à mão para falar de rastreabilidade, não para empilhar a
// mesma palavra duas vezes.
//
// ## Por que esta regra NÃO varre o arquivo inteiro, e a do "aparelho" varre
//
// São regras com sujeitos diferentes, e a diferença é a razão de cada uma:
//
//   - "aparelho" é uma palavra que a casa NÃO usa. Em 18/09/2026 o dono disse
//     *"não usamos o termo aparelho"*, e aí o canal deixou de importar:
//     comentário e nome de teste contam igual.
//   - "fornada" é uma palavra CERTA — para o evento do forno. O que mudou foi o
//     NOME DO OBJETO NA TELA, não a legitimidade da palavra. Um comentário que
//     explica que o timer "arma na enfornada", ou que cita a seção §4 da nota de
//     QC, continua dizendo a verdade. Bani-lo obrigaria a mentir sobre o forno
//     para satisfazer uma regra que é sobre o rótulo do botão.
//
// Por isso aqui o comentário é descontado antes da leitura, e só o que chega ao
// operador — template, atributo, literal de string, nome de teste — é recusado.
// É a mesma separação do `stripNoise` de `guardrails.identifiers.test.ts`, com a
// metade oposta preservada: lá se joga fora a prosa e se lê o código; aqui se
// joga fora o comentário e se lê o texto.
//
// ⚠️ `enfornada` NÃO é recusada: a borda de palavra do regex não abre no meio
// dela, e é assim de propósito — enfornar é o que se faz com o lote no forno.
//
// ## Quem fica de fora
//
//   - **storefront-nuxt** — a loja continua dizendo "fornada" ao cliente, pelo
//     mesmo motivo que a mantém dizendo "aparelho": superfície de cliente final
//     tem voz própria, e "fornada" é palavra de marca de padaria. Trocar ali
//     rebaixaria a voz da casa para o vocabulário do balcão. Decisão, não dívida.
//   - **marketing-nuxt** — de fora por motivo MECÂNICO e TEMPORÁRIO, não
//     semântico: a matriz visual do Marketing tem baselines em PNG e havia duas
//     levas na fila mexendo neles (#978 e #979) quando esta regra nasceu. Uma
//     terceira frente no mesmo diretório travaria as três. A troca do Marketing
//     vive no PR de seguimento #984; quando ele entrar, esta linha
//     sai daqui, e não há nada a decidir de novo.
/** O nome do objeto na tela é "lote" — "fornada" nomeia o evento do forno. */
const BANNED_BATCH = /\bfornadas?\b/i;

/**
 * Apaga comentário (bloco, linha e `<!-- -->`) preservando as quebras de linha,
 * para que o número da linha reportado continue sendo o número da linha real.
 * O `//` só conta como comentário quando não vem logo depois de `:` — senão
 * `https://` comeria o resto da linha e a trava ficaria cega ali.
 */
function stripComments(text: string): string {
  const blank = (chunk: string) => chunk.replace(/[^\n]/g, " ");
  return text
    .replace(/\/\*[\s\S]*?\*\//g, blank)
    .replace(/<!--[\s\S]*?-->/g, blank)
    .replace(/(^|[^:])\/\/[^\n]*/g, (match, prefix: string) => prefix + blank(match.slice(prefix.length)));
}

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

/**
 * Fora da regra do "lote", cada um pelo seu motivo (ver o bloco acima):
 * o Storefront por decisão de voz, o Marketing por bloqueio de baseline.
 */
const EXEMPT_FROM_BATCH = ["marketing-nuxt/"];

const BATCH_SOURCES = SOURCES.filter(
  (file) =>
    !EXEMPT_FROM_BATCH.some((prefix) => relative(surfacesDir, file).startsWith(prefix)),
);

function offenders(
  file: string,
  banned: RegExp,
  prepare: (text: string) => string = (text) => text,
): string[] {
  const raw = readFileSync(file, "utf8").split("\n");
  return prepare(readFileSync(file, "utf8"))
    .split("\n")
    .flatMap((line, index) =>
      banned.test(line)
        ? [`${relative(surfacesDir, file)}:${index + 1}: ${raw[index]?.trim() ?? line.trim()}`]
        : [],
    );
}

describe("a palavra da casa é dispositivo — e a do cartão é maquininha", () => {
  it("nenhum arquivo das superfícies diz 'aparelho'", () => {
    const leaks = SOURCES.flatMap((file) => offenders(file, BANNED));

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

describe("o objeto que a Produção planeja e fecha chama-se lote", () => {
  it("nenhum texto de operador diz 'fornada'", () => {
    const leaks = BATCH_SOURCES.flatMap((file) =>
      offenders(file, BANNED_BATCH, stripComments),
    );

    expect(
      leaks,
      "O nome do objeto na tela é 'lote' (decisão do dono, 22/09/2026): 'fornada'\n" +
        "só serve para o que vai ao forno, e a casa produz coisa que não vai.\n" +
        "A trava não escreve a substituição porque a troca mecânica erra a\n" +
        "concordância — 'a fornada' vira 'o lote', e 'fornadas planejadas' vira\n" +
        "'lotes planejados'. Leia a linha. Se a frase precisar falar do lote de\n" +
        "rastreabilidade (o Batch) na mesma sentença, reescreva-a: empilhar a\n" +
        "palavra duas vezes é pior do que qualquer um dos dois nomes.\n" +
        "Comentário é descontado de propósito: falar de 'enfornada' e da nota de\n" +
        `QC continua certo.\nOnde:\n  ${leaks.join("\n  ")}`,
    ).toEqual([]);
  }, 30_000);

  // A exenção do Marketing é temporária e tem dono; a do Storefront é decisão.
  // Este teste existe para que a temporária não vire permanente por esquecimento:
  // ele trava a lista pelo CONTEÚDO, então o PR de seguimento não tem como apagar
  // a exenção sem passar por aqui — e o que ele faz é apagar as duas coisas
  // juntas, a linha do `EXEMPT_FROM_BATCH` e este `it`. Exenção sem prazo é
  // exenção permanente; exenção que quebra o teste ao sair tem data.
  it("só o Marketing está exento por bloqueio, e a lista é nominal", () => {
    expect(EXEMPT_FROM_BATCH).toEqual(["marketing-nuxt/"]);
    expect(SOURCES.length - BATCH_SOURCES.length).toBeGreaterThan(0);
  });
});
