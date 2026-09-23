import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

// ╔══════════════════════════════════════════════════════════════════════════╗
// ║  TODA FALHA DO PDV TEM SAÍDA — §2, o resto do PDV, pela FONTE            ║
// ╚══════════════════════════════════════════════════════════════════════════╝
//
// O PDV é a superfície onde o erro custa mais caro — tem cliente esperando no
// balcão — e era a que menos dizia o que fazer. Medido em 22/09/2026, contando
// as mensagens que começavam com "Falha …" e quantas continham algum gesto:
//
//     pos-nuxt          33 falhas →  1 com saída
//     orders-nuxt       19        →  5
//     production-nuxt    4        →  2
//     kds-nuxt           3        →  2
//
// A única com saída era `saveTab`: *"Os itens seguem na tela; confira a conexão
// e tente de novo."* Ela é o formato, e o formato tem três partes:
//
//     o que aconteceu  +  o que sobrevive  +  o que fazer agora
//
// "Falha ao registrar movimento." tem a primeira e mente por omissão nas outras
// duas: o operador não sabe se o dinheiro saiu da gaveta, e é exatamente o que
// ele precisa saber antes de decidir se toca o botão de novo.
//
// ## Por que a saída mora FORA do `httpErrorMessage`
//
// `httpErrorMessage(erro, fallback)` devolve o `detail` do servidor quando ele
// manda um, e SÓ cai no fallback quando não manda. Gesto escrito dentro do
// fallback, portanto, desaparece justamente quando o servidor explica a causa —
// e o backend manda `detail` em quase toda recusa de negócio. Por isso o padrão
// é `` `${httpErrorMessage(erro, causa)} ${saida}` ``: a causa é do servidor
// quando ele a tem, a saída é sempre nossa.
//
// ## Por que a trava tem duas metades
//
// Esta varredura não enxerga indireção: em `usePosCashSession` a saída viaja como
// ARGUMENTO até um `run()` compartilhado, e a linha do `toast.error` não contém
// gesto nenhum — o gesto está nos nove chamadores. Ler aquele arquivo com regex
// daria verde falso ou vermelho falso. Por isso o arquivo do dinheiro é travado
// pelo COMPORTAMENTO, em `tests/composables/falhaComSaida.caixa.test.ts`: a
// mutação roda contra um servidor que recusa, e a trava lê o toast que o
// operador leria.

/** O que conta como saída: um verbo que o operador pode executar agora. */
const GESTO =
  /\b(tente|tenta|confira|confirme|avise|chame|peça|refaça|digite|atualize|reabra|feche|corrija|cancele|siga|repetir|repita|identifique|configure|reinicie|escolha|informe|aguarde|volte|busque|selecione|copie|mande|reimprima)\b/i;

// ───────────────────────────────────────────────────────────────────────────
// A varredura
// ───────────────────────────────────────────────────────────────────────────

const appDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "app");

/**
 * Exceções NOMINAIS. Lista curta de propósito: a lista que cresce sem ninguém
 * olhar é como a regra morre. Cada entrada diz por que a saída está em OUTRO
 * lugar — nunca por que ela não existe.
 */
const EXCECOES: Array<{ arquivo: string; trecho: string; porque: string }> = [
  {
    arquivo: "composables/usePosCashSession.ts",
    trecho: "message: httpErrorMessage(error, causa)",
    porque: "o diálogo de PIN é a saída; coberto pelo §1",
  },
  {
    arquivo: "composables/usePosCashSession.ts",
    trecho: "toast.error(`${httpErrorMessage(error, causa)} ${saida}`)",
    porque: "a saída chega por argumento dos nove chamadores; coberto pelo §1",
  },
  {
    arquivo: "composables/usePosCashSession.ts",
    trecho: 'detail: httpErrorMessage(error, "o servidor não montou o comprovante")',
    porque: "fragmento: entra em 'O comprovante não saiu: …', cuja saída é a ação 'Tentar de novo' do toast",
  },
  {
    arquivo: "composables/useDrawerLock.ts",
    trecho: 'const causa = httpErrorMessage(error, "A gaveta não foi liberada.")',
    porque: "a causa é reusada pelos dois ramos; a saída do ramo de toast está na linha do toast",
  },
  {
    arquivo: "pages/index.vue",
    trecho: "O recibo saiu pelo diálogo do navegador.",
    porque: "não há gesto a pedir: o recibo JÁ saiu pelo outro caminho (window.print)",
  },
  {
    arquivo: "composables/useDrawerLock.ts",
    trecho: "O sensor da gaveta parou de responder. O gerente foi avisado.",
    porque: "aviso de estado, não recusa: quem age é o gerente, já acionado",
  },
  {
    arquivo: "pages/index.vue",
    trecho: 'danfeFallbackToast(orderRef, httpErrorMessage(error, "o servidor não montou a DANFE"))',
    porque: "fragmento: o danfeFallbackToast traz 'Ver a nota na tela' ou 'Reimprima nas últimas vendas'",
  },
];

const EXTENSOES = [".ts", ".vue"];

function arquivosDeFonte(dir: string, achados: string[] = []): string[] {
  for (const entrada of readdirSync(dir)) {
    const caminho = join(dir, entrada);
    if (statSync(caminho).isDirectory()) arquivosDeFonte(caminho, achados);
    else if (EXTENSOES.some((ext) => entrada.endsWith(ext))) achados.push(caminho);
  }
  return achados;
}

/**
 * Tira comentário de linha cheia. A prosa desta casa explica a regra CITANDO a
 * frase ("Sem saída acrescentada: …tente de novo…"), e comentário contando como
 * gesto daria verde para código que não diz nada ao operador.
 */
function semComentarios(fonte: string): string {
  return fonte
    .split("\n")
    .map((linha) => {
      const limpa = linha.trim();
      return limpa.startsWith("//") || limpa.startsWith("*") || limpa.startsWith("/*") ? "" : linha;
    })
    .join("\n");
}

/**
 * Quebra o arquivo em INSTRUÇÕES, entendendo aspas, crases e `${…}`.
 *
 * A versão ingênua disto — recuar até o `{` anterior e avançar até o `;` —
 * recuava para dentro do `${` de um template literal, saía de fase com as
 * crases e devolvia 600 caracteres a partir do meio de uma string. Instrução
 * mal recortada erra nas duas direções: engole o gesto da linha vizinha (verde
 * falso) e acusa quem tem saída (vermelho falso).
 */
function instrucoes(fonte: string): string[] {
  const achadas: string[] = [];
  const pilhaTemplate: number[] = [];
  let inicio = 0;
  let profundidade = 0;
  let aspas: string | null = null;

  const fechar = (fim: number) => {
    const texto = fonte.slice(inicio, fim + 1);
    if (texto.trim()) achadas.push(texto);
    inicio = fim + 1;
  };

  for (let i = 0; i < fonte.length; i += 1) {
    const c = fonte[i];
    if (aspas) {
      if (c === "\\") { i += 1; continue; }
      if (c === aspas) { aspas = null; continue; }
      // `${` devolve o lexer ao modo código, um nível mais fundo.
      if (aspas === "`" && c === "$" && fonte[i + 1] === "{") {
        pilhaTemplate.push(profundidade);
        profundidade += 1;
        aspas = null;
        i += 1;
      }
      continue;
    }
    if (c === "'" || c === '"' || c === "`") { aspas = c; continue; }
    if (c === "(" || c === "[" || c === "{") { profundidade += 1; continue; }
    if (c === ")" || c === "]" || c === "}") {
      profundidade -= 1;
      // Fechou o `}` de um `${…}`: volta para dentro da crase.
      if (pilhaTemplate.length && profundidade === pilhaTemplate[pilhaTemplate.length - 1]) {
        pilhaTemplate.pop();
        aspas = "`";
      }
      continue;
    }
    // O `;` encerra SEMPRE, e não só na profundidade 0: dentro de um corpo de
    // função a profundidade nunca volta a zero, e exigir isso fazia o arquivo
    // inteiro virar uma instrução só — com algum gesto solto em algum ponto,
    // portanto verde para todo mundo. Foi assim que esta trava passou por uma
    // regressão injetada de propósito, antes de valer a pena confiar nela.
    // Chave também encerra (bloco ou objeto, as duas servem de fronteira) —
    // menos a que fecha um `${…}`, que partiria a frase do operador ao meio.
    if (c === ";" || ((c === "{" || c === "}") && !pilhaTemplate.length)) fechar(i);
    else if (c === "\n" && profundidade === 0 && !pilhaTemplate.length) fechar(i);
  }
  fechar(fonte.length - 1);
  return achadas;
}

const GATILHOS = [/httpErrorMessage\(/, /toast\.error\(\s*"/, /toast\.warning\(\s*"/];

describe("toda mensagem de falha do PDV diz o que fazer agora", () => {
  const arquivos = arquivosDeFonte(appDir);

  it("a varredura encontra a superfície inteira (a trava que não lê nada passa sempre)", () => {
    expect(arquivos.length).toBeGreaterThan(50);
  });

  it("nenhuma falha termina sem gesto", () => {
    const semSaida: string[] = [];

    for (const caminho of arquivos) {
      const relativo = relative(appDir, caminho).split("\\").join("/");
      const fonte = semComentarios(readFileSync(caminho, "utf8"));

      for (const instrucao of instrucoes(fonte)) {
        if (!GATILHOS.some((gatilho) => gatilho.test(instrucao))) continue;
        if (GESTO.test(instrucao)) continue;
        const dispensada = EXCECOES.some(
          (e) => e.arquivo === relativo && instrucao.includes(e.trecho),
        );
        if (dispensada) continue;
        semSaida.push(`${relativo}: ${instrucao.trim().replace(/\s+/g, " ").slice(0, 200)}`);
      }
    }

    expect(semSaida, `falha(s) sem saída:\n${semSaida.join("\n")}`).toEqual([]);
  });

  it("toda exceção listada ainda existe (lista que envelhece deixa de ser exceção)", () => {
    for (const excecao of EXCECOES) {
      const fonte = readFileSync(join(appDir, excecao.arquivo), "utf8");
      expect(fonte, `exceção obsoleta: ${excecao.arquivo} / ${excecao.porque}`).toContain(
        excecao.trecho,
      );
    }
  });
});
