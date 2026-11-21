import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { OPERATOR_KIT_SURFACES } from "./support/surfaceRegistry";

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
//   - **marketing-nuxt** — de fora de forma PERMANENTE, e por AUDIÊNCIA. Não é
//     "porque é Marketing": é porque o Marketing é o único app que tem as duas
//     audiências DENTRO DELE, e por isso a linha passa por dentro do app em vez
//     de em volta.
//
//     A regra, que é a mesma da loja aplicada com o critério certo: **quem lê é
//     quem manda na palavra.** Texto que o CLIENTE lê mantém "fornada" — a
//     hashtag sugerida de um post, o corpo de um anúncio, o modelo de mensagem,
//     a fila do sino da loja. Texto que o OPERADOR lê virou "lote" — rótulo de
//     campo, título, ajuda do cockpit, mensagem de erro, rótulo de gatilho.
//
//     A prova de que a linha não é por app: `placeholder="#padaria #fornada"` é
//     sugestão de hashtag de Instagram. `#lote` ali não é hashtag de padaria, é
//     vocabulário de chão de fábrica num canal onde a casa fala com cliente.
//
//     ⚠️ E a trava NÃO consegue varrer só o chrome: as duas audiências moram no
//     MESMO arquivo — `AnnouncementCard.vue` tem o rótulo que o gestor lê e o
//     placeholder que vira post. Separar por diretório daria falso positivo em
//     cima de conteúdo legítimo. Então o app inteiro fica exento, e isto está
//     escrito aqui em vez de fingir cobertura: no Marketing, a palavra se
//     escolhe lendo quem é o leitor da linha, e não há regex que faça isso.
//
//     ⚠️ E há um resto que a exenção esconde, então ele fica dito: o harness
//     visual (`tests/visual/mock_backend.py`) ainda tem TRÊS strings de
//     operador com a palavra velha — `schedule_label`, `rejected_reason` e o
//     `title` da revisão. Elas deviam dizer "lote" pela regra de cima, e não
//     dizem por motivo mecânico: mexer ali regera os retratos em PNG, e
//     baseline só se regera na sessão que tem o browser da CI. Isto é dívida
//     com nome, não decisão — some quando os retratos forem regerados.
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

// O registro canônico decide o escopo. Superfícies de cliente têm voz própria;
// enumerar uma exceção por nome faria cada nova superfície pública quebrar uma
// regra que nunca se aplicou a ela.
const OPERATOR_SCOPE = new Set([...OPERATOR_KIT_SURFACES, "operator-kit", "operator-router"]);

const SOURCES = sourceFiles(surfacesDir).filter((file) => {
  const path = relative(surfacesDir, file);
  const surface = path.split("/")[0];
  return OPERATOR_SCOPE.has(surface) && !MAY_QUOTE.has(path);
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
    expect([...apps].sort()).toEqual([...OPERATOR_KIT_SURFACES, "operator-kit", "operator-router"].sort());
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

// ─────────────────────────────────────────────────────────────────────────────
// Guardrail de VOCABULÁRIO, terceira regra: a unidade do modo de fazer de uma
// receita chama-se **etapa**. Decisão do dono em 01/10/2026, diante da colisão
// que estava no ar: o modelo e o Admin diziam "Etapas" (`Recipe.steps`, o campo
// do Admin do Craftsman) e as telas de receita do app de Produção diziam
// "Passos", "Passos lidos" e "Passos (um por linha)". A mesma coisa com dois
// nomes, a depender da porta.
//
// ## Por que o escopo é o app de Produção, e não as superfícies todas
//
// "Passo" é palavra certa para outra coisa: o passo do login, o passo a passo da
// instalação (`OperatorInstallSteps.vue`), os dois passos do dropdown do
// `FilterBar`. Nada disso é etapa de receita. Recusar a palavra em todas as
// superfícies obrigaria a reescrever frases que dizem a verdade. Etapa de receita
// e de produção só aparece ao operador no `production-nuxt` (receitas, grade da
// produção, leitura automática da ficha), então a trava mora ali, no app inteiro,
// para que a próxima tela de receita nasça coberta sem ninguém lembrar dela.
//
// Comentário é descontado, como na regra do "lote": "plan + finish num passo"
// (`useQcKiosk.ts`) fala de um gesto, não de uma etapa. O que chega ao operador
// (template, atributo, literal, nome de teste) é o que conta. A irmã em Python é
// `shopman/backstage/tests/test_vocabulario_etapa_da_receita.py`.
/** A unidade do modo de fazer é "etapa" (feminino: "uma por linha"). */
const BANNED_STEP = /\bpassos?\b/i;

const STEP_SOURCES = SOURCES.filter((file) =>
  relative(surfacesDir, file).startsWith("production-nuxt/"),
);

describe("a unidade do modo de fazer de uma receita chama-se etapa", () => {
  it("nenhum texto do app de Produção diz 'passo'", () => {
    const leaks = STEP_SOURCES.flatMap((file) => offenders(file, BANNED_STEP, stripComments));

    expect(
      leaks,
      "A unidade do modo de fazer é 'etapa' (decisão do dono, 01/10/2026), o mesmo\n" +
        "nome do modelo e do Admin. A trava não escreve a substituição porque o gênero\n" +
        "muda: 'Passos (um por linha)' vira 'Etapas (uma por linha)', 'Passos lidos'\n" +
        "vira 'Etapas lidas'. Leia a linha.\n" +
        `Onde:\n  ${leaks.join("\n  ")}`,
    ).toEqual([]);
  }, 30_000);

  it("a varredura enxerga as telas de receita", () => {
    const paths = STEP_SOURCES.map((file) => relative(surfacesDir, file));
    expect(paths).toContain("production-nuxt/app/pages/recipes/[ref]/edit.vue");
    expect(paths).toContain("production-nuxt/app/pages/recipes/new.vue");
    expect(STEP_SOURCES.length).toBeGreaterThan(40);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Guardrail de VOCABULÁRIO, quarta regra: na tela, a navegação lateral se chama
// **barra lateral** (dono, 08/10/2026, PR #1544). "Rail" é jargão de quem desenha:
// o botão dizia "Compactar o rail" e o menu do operador dizia "Ocultar a barra" para a
// mesma peça. No código, `rail` continua sendo o nome (`SUITE_RAIL_*`,
// `data-suite-rail`, a variante `rail:` do CSS), por isso a trava não recusa a
// palavra solta: recusa a palavra como texto (depois de artigo, preposição ou verbo
// de gesto, ou abrindo um literal com maiúscula). Comentário é descontado; teste
// também, porque nome de teste não chega ao operador.
const BANNED_RAIL =
  /(["'`>]\s*Rail\b|\b(?:o|do|no|ao|pelo|um|Mostrar|Ocultar|Compactar|Expandir|Recolher) rail\b)/;

const APP_SOURCES = SOURCES.filter((file) => /^[^/]+\/app\//.test(relative(surfacesDir, file)));

describe("na tela, a navegação lateral se chama barra lateral", () => {
  it("nenhum texto de operador diz 'rail'", () => {
    const leaks = APP_SOURCES.flatMap((file) => offenders(file, BANNED_RAIL, stripComments));

    expect(
      leaks,
      "Na tela é 'barra lateral' (decisão do dono, 08/10/2026): 'Compactar a barra\n" +
        "lateral', 'Ocultar a barra lateral', 'Mostrar a barra lateral'. O nome no\n" +
        "código pode continuar `rail`.\n" +
        `Onde:\n  ${leaks.join("\n  ")}`,
    ).toEqual([]);
  }, 30_000);

  it("a varredura enxerga o kit e os apps", () => {
    const paths = APP_SOURCES.map((file) => relative(surfacesDir, file));
    expect(paths).toContain("operator-kit/app/presentation/suiteChrome.ts");
    expect(paths).toContain("operator-kit/app/components/OperatorMenuItems.vue");
    expect(APP_SOURCES.length).toBeGreaterThan(400);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Guardrail de VOCABULÁRIO, quinta regra: quando a produção termina, o lote, o
// produto e as unidades **ficam prontos**. Decisão do dono em 16/11/2026: a casa
// diz "ficar pronto", nunca "sair do forno". Vale para todo tempo do verbo: "sai
// do forno", "saiu do forno", "saíram do forno", "saindo do forno", "acabou de
// sair do forno", "saída do forno".
//
// Esta trava nasceu depois da varredura (o PR #2800 e o que fecha a #2798), e não
// antes, pelo mesmo motivo das outras: a instância consertada sem trava volta. O
// B.I. dizia "Saíram do forno" na série do gráfico e na exportação, o Marketing
// dizia "Produto saiu do forno" na lista de avisos e "24 un saíram às 10h01" no
// cartão do lote, e quem escreveu cada uma leu as vizinhas.
//
// ## O que ela recusa, e o que não
//
// Recusa o verbo "sair" seguido de "do forno" (com até duas palavras no meio:
// "saiu agora do forno", "saíram quentinhos do forno"). NÃO recusa o forno: a
// casa tem forno, e "Retirou do forno", "Tempo de forno" e "Timer do forno"
// continuam certos. Também não recusa "sair" sozinho: "Saiu para entrega" é o
// pedido saindo com o entregador, e "saiu às 14h20" é a maquininha. O "sair" sem
// "do forno" que fala do lote ("quando o lote sair") nenhum regex separa do resto
// sem ler a frase; esse só olho pega, e está dito aqui em vez de fingir cobertura.
//
// Comentário é descontado, como na regra do "lote": a regra é sobre o que chega a
// alguém (template, atributo, literal de string, nome de teste). A leitura é do
// texto inteiro, não linha a linha, porque frase de template quebra no meio.
//
// ## Quem fica de fora, e por quê (exceção declarada, nunca calada)
//
//   - **storefront-nuxt** — fora do escopo desta trava inteira (ver o topo do
//     arquivo). A loja segue a mesma regra do dono, com a trava DELA: a voz do
//     cliente não é o vocabulário do operador.
//   - **marketing-nuxt/tests/** — as fixtures e o mock visual do Marketing levam
//     CORPO DE ANÚNCIO ("Croissant saiu do forno"), que é o texto que a casa
//     escreve PARA o cliente, não texto de operador. É a mesma linha de audiência
//     que deixa "fornada" no Marketing. O `app/` do Marketing NÃO está exento: os
//     exemplos do formulário de modelo e o fato do lote já dizem "ficar pronto".
//     E o mock visual tem um motivo mecânico a mais: mexer no corpo do anúncio
//     dele muda os retratos, e baseline só se regera no navegador da CI.
//
// A irmã em Python é `shopman/backstage/tests/test_vocabulario_de_tela.py`.
const OUT_OF_OVEN_VERB =
  "(?:sai|saiu|sair|saem|sa[ií]ram|saindo|sairá|sairão|saía|saíam|saída|saídas|saído|saídos)";

/** "sair … do forno", em qualquer tempo, com até duas palavras no meio. */
const BANNED_OUT_OF_OVEN = new RegExp(
  `(?<![\\p{L}\\d])${OUT_OF_OVEN_VERB}(?:\\s+[\\p{L}\\d]+){0,2}?\\s+dos?\\s+fornos?(?![\\p{L}\\d])`,
  "giu",
);

function saysOutOfOven(text: string): boolean {
  BANNED_OUT_OF_OVEN.lastIndex = 0;
  return BANNED_OUT_OF_OVEN.test(text);
}

/** Texto para o cliente dentro de app de operador: corpo de anúncio em fixture e mock. */
const EXEMPT_FROM_OUT_OF_OVEN = ["marketing-nuxt/tests/"];

const isOutOfOvenExempt = (file: string) =>
  EXEMPT_FROM_OUT_OF_OVEN.some((prefix) => relative(surfacesDir, file).startsWith(prefix));

/** Lê o texto inteiro (a frase pode quebrar de linha) e devolve `arquivo:linha: trecho`. */
function outOfOvenOffenders(file: string): string[] {
  const text = stripComments(readFileSync(file, "utf8"));
  return Array.from(text.matchAll(BANNED_OUT_OF_OVEN), (match) => {
    const line = text.slice(0, match.index).split("\n").length;
    return `${relative(surfacesDir, file)}:${line}: ${match[0].replace(/\s+/g, " ")}`;
  });
}

describe("a casa diz ficar pronto, nunca sair do forno", () => {
  it("o detector conhece os tempos do verbo", () => {
    for (const text of [
      "Saíram do forno",
      "Unidades que não saíram do forno",
      "Produto saiu do forno",
      "O pão acabou de sair do forno!",
      "o lote sai do forno já classificado",
      "tem coisa boa saindo do forno",
      "Saiu agora do forno",
      "Saíram quentinhos do forno",
      "Aviso na saída do forno",
      "unidades que saíram\n          do forno",
    ]) {
      expect(saysOutOfOven(text), text).toBe(true);
    }
  });

  it("o detector deixa em paz o forno e o que sai sem ser dele", () => {
    for (const text of [
      "Retirou do forno",
      "Tempo de forno medido",
      "Timer do forno de Baguete",
      "Só é possível retirar do forno um lote aberto.",
      "Saiu para entrega",
      "Pedido A47 · Maria · saiu às 14h20",
      "Ficaram prontas",
      "O preparo abre quando o lote ficar pronto.",
      "24 un ficaram prontas às 10h01",
    ]) {
      expect(saysOutOfOven(text), text).toBe(false);
    }
  });

  it("nenhum texto de operador diz que algo sai do forno", () => {
    const leaks = SOURCES.filter((file) => !isOutOfOvenExempt(file)).flatMap(outOfOvenOffenders);

    expect(
      leaks,
      "A casa diz 'ficar pronto', nunca 'sair do forno' (decisão do dono, 16/11/2026).\n" +
        "A trava não escreve a substituição porque o verbo concorda com o que ficou\n" +
        "pronto: 'Saíram do forno' sobre unidades vira 'Ficaram prontas', 'o lote sai\n" +
        "do forno' vira 'o lote fica pronto'. Leia a linha. Se o texto é corpo de\n" +
        "anúncio ou aviso que a casa escreve PARA o cliente, ele não é texto de\n" +
        "operador: declare a exceção em EXEMPT_FROM_OUT_OF_OVEN, com o motivo.\n" +
        `Onde:\n  ${leaks.join("\n  ")}`,
    ).toEqual([]);
  }, 30_000);

  // Exceção sem prazo vira permanente. Esta é travada pelo CONTEÚDO da lista e pela
  // prova de que ainda esconde alguma coisa: no dia em que as fixtures do Marketing
  // não disserem mais a frase, este teste reprova e a exceção sai junto.
  it("a única exceção é o corpo de anúncio nas fixtures do Marketing, e ela ainda esconde algo", () => {
    expect(EXEMPT_FROM_OUT_OF_OVEN).toEqual(["marketing-nuxt/tests/"]);
    const hidden = SOURCES.filter(isOutOfOvenExempt).flatMap(outOfOvenOffenders);
    expect(hidden.length).toBeGreaterThan(0);
  }, 30_000);

  it("a varredura enxerga o B.I., o Marketing e a Produção", () => {
    const paths = SOURCES.filter((file) => !isOutOfOvenExempt(file)).map((file) =>
      relative(surfacesDir, file),
    );
    expect(paths).toContain("bi-nuxt/app/presentation/production.ts");
    expect(paths).toContain("bi-nuxt/app/components/ProductionLots.vue");
    expect(paths).toContain("marketing-nuxt/app/components/AnnouncementTemplateForm.vue");
    expect(paths).toContain("marketing-nuxt/app/presentation/decisions.ts");
    expect(paths).toContain("production-nuxt/app/pages/close.vue");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Guardrail de VOCABULÁRIO, a regra do serviço de entrega (M1b-b3, #3139): a tela
// do operador diz o nome do serviço da corrida COMO O CADASTRO DIZ, nunca "TaOn"
// escrito no código. A casa entrega por mais de um serviço (DEV-2026-030: a TaOn,
// os entregadores da casa, outra central amanhã), e o nome chega pronto do servidor
// (`service_name` no bloco do entregador e na corrida das Entregas; `ride_plan` no
// sheet de chamar). A frase monta com `deliveryServiceName` (presentation/
// deliveryService.ts), que diz "central" quando o servidor não disse.
//
// Só o código das telas (`app/`, `server/`): o teste e o mock usam "TaOn" como DADO
// do cadastro, que é exatamente o que a tela recebe. Comentário é descontado: dizer
// que a TaOn faz isto ou aquilo continua sendo verdade sobre a TaOn.

const BANNED_SERVICE = /\bTaOn\b/;

// O B.I. de entregas fica de fora até decidir o que o custo soma com mais de um
// serviço (#3144): lá não é troca de nome, é o que o número significa. A issue fecha
// esta exceção; o teste abaixo dela trava a lista pelo conteúdo.
const EXEMPT_FROM_SERVICE = ["bi-nuxt/app/pages/delivery.vue", "bi-nuxt/app/presentation/delivery.ts"];

const SCREEN_SOURCES = SOURCES.filter((file) => {
  const path = relative(surfacesDir, file);
  return /\/(app|server)\//.test(path) && !EXEMPT_FROM_SERVICE.includes(path);
});

describe("o nome do serviço de entrega vem do cadastro", () => {
  it("nenhum texto de operador diz 'TaOn' fixo", () => {
    const leaks = SCREEN_SOURCES.flatMap((file) => offenders(file, BANNED_SERVICE, stripComments));

    expect(
      leaks,
      "O nome do serviço da corrida vem do cadastro (service_name), não do código.\n" +
        "Use deliveryServiceName(<o service_name do bloco ou da corrida>) na frase.\n" +
        `Onde:\n  ${leaks.join("\n  ")}`,
    ).toEqual([]);
  }, 30_000);

  it("a varredura enxerga as telas, não um recorte", () => {
    const apps = new Set(SCREEN_SOURCES.map((file) => relative(surfacesDir, file).split("/")[0]));
    expect([...apps]).toEqual(expect.arrayContaining(["orders-nuxt", "pos-nuxt", "operator-kit"]));
  });

  it("a exceção do B.I. é só a do #3144, e não cresce", () => {
    expect(EXEMPT_FROM_SERVICE).toEqual(["bi-nuxt/app/pages/delivery.vue", "bi-nuxt/app/presentation/delivery.ts"]);
  });
});
