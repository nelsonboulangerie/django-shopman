import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { OPERATOR_SURFACES } from "./support/surfaceRegistry";

// Guardrail de COPY SEM TRAVESSÃO nas superfícies de operador (CLAUDE.md, "Copy sem
// travessão"): nenhum texto visível usa o travessão longo. A frase se reescreve com
// ponto, vírgula, dois-pontos ou parênteses, lendo o sentido.
//
// ## Por que ela nasceu
//
// A regra estava escrita, e a irmã de Python (`shopman/shop/tests/
// test_omotenashi_copy_keys.py`) só olha os defaults da `OmotenashiCopy`. O texto dos
// `.vue` e das `presentation/*.ts` passava por baixo das duas: em 03/10/2026 a captura
// do app rodando mostrou "Peça a quem cuida do sistema para ligá-lo — enquanto isso,
// nenhum dispositivo recebe aviso." no `OperatorPushSettings.vue`, e a varredura achou
// mais de cem linhas assim nos apps de operador.
//
// ## O que ela lê, e o que ela deixa passar
//
// Comentário (bloco, linha e `<!-- -->`) é descontado antes da leitura: travessão em
// prosa de programador é pontuação, não copy. Fica o template inteiro e todo literal de
// script, que é onde mora o que chega à tela.
//
// O travessão SOZINHO ("—" como literal inteiro, ou `>—<` como conteúdo inteiro de um
// elemento) passa: é o sinal de "sem valor" numa célula de tabela, não pontuação de
// frase. Trocá-lo é outra discussão (o defeito "zero como código secreto" da régua de
// copy), não esta trava.
//
// O meia-risca (–) em intervalo ("20:00–08:00", "0–9", "A–Z") também passa: é o sinal
// de intervalo, não travessão.
//
// ⚠️ Ela lê os ARQUIVOS, não a branch: num worktree, verde só vale para o que está ali.

const surfacesDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");

const ROOTS = [...OPERATOR_SURFACES, "operator-kit", "operator-router"];

const SOURCE_EXT = [".vue", ".ts", ".mjs", ".js", ".json"];

const SKIP_DIRS = new Set([
  "node_modules",
  ".nuxt",
  ".output",
  "dist",
  "coverage",
  "tests",
  "test-results",
  "playwright-report",
  "blob-report",
]);

const SKIP_FILES = new Set(["package.json", "package-lock.json", "tsconfig.json"]);

/**
 * Fora da trava, cada um com o seu motivo. Lista nominal de propósito: a que cresce
 * sem ninguém olhar é como a regra morre.
 */
const EXCEPTIONS: Record<string, string> = {
  // Não é copy: é o parser que RECONHECE separadores no título da janela.
  "operator-kit/app/presentation/windowTitle.ts": "regex que reconhece separadores; não é texto",
  // Dívida com nome, não decisão. O Marketing tem a matriz de retratos (`tests/visual`),
  // aprovada no macOS da CI, e retrato só se regrava na sessão que tem o browser da CI
  // (CLAUDE.md). Mexer na copy aqui reprova a matriz. Some quando os retratos forem
  // regravados pela CI com a copy nova (frente UX-COPY1, seguimento).
  "marketing-nuxt/": "retratos do Marketing só se regravam pela CI",
  // Mesma dívida: o aviso de conexão aparece no retrato `global-error__offline` do
  // Marketing. Sai junto com o seguimento acima.
  "operator-kit/app/components/OfflineBanner.vue": "aparece no retrato global-error__offline do Marketing",
};

function sourceFiles(dir: string, found: string[] = []): string[] {
  let entries: string[];
  try {
    entries = readdirSync(dir);
  } catch {
    return found;
  }
  for (const entry of entries) {
    if (SKIP_DIRS.has(entry) || SKIP_FILES.has(entry)) continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) sourceFiles(full, found);
    else if (SOURCE_EXT.some((extension) => full.endsWith(extension))) found.push(full);
  }
  return found;
}

/**
 * Apaga comentário preservando as quebras de linha, para que o número reportado seja o
 * da linha real. O `//` só conta como comentário quando não vem logo depois de `:`
 * (senão `https://` comeria o resto da linha).
 */
function stripComments(text: string): string {
  const blank = (chunk: string) => chunk.replace(/[^\n]/g, " ");
  return text
    .replace(/\/\*[\s\S]*?\*\//g, blank)
    .replace(/<!--[\s\S]*?-->/g, blank)
    .replace(/(^|[^:])\/\/[^\n]*/g, (match, prefix: string) => prefix + blank(match.slice(prefix.length)));
}

/** O travessão sozinho é sinal de "sem valor", não pontuação (ver acima). */
function dropPlaceholders(text: string): string {
  return text.replace(/(["'`])—\1/g, "$1$1").replace(/>(\s*)—(\s*)</g, ">$1$2<");
}

export function emDashLines(source: string, isJson = false): Array<{ line: number; text: string }> {
  const readable = dropPlaceholders(isJson ? source : stripComments(source));
  const found: Array<{ line: number; text: string }> = [];
  readable.split("\n").forEach((text, index) => {
    if (text.includes("—")) found.push({ line: index + 1, text: text.trim() });
  });
  return found;
}

const SOURCES = ROOTS.flatMap((root) => sourceFiles(join(surfacesDir, root)));

function exceptionFor(path: string): string | undefined {
  return Object.keys(EXCEPTIONS).find((key) => (key.endsWith("/") ? path.startsWith(key) : path === key));
}

describe("copy de operador sem travessão", () => {
  it("a regra pega a frase e deixa passar comentário, célula vazia e intervalo", () => {
    const sample = [
      "<template>",
      "  <!-- aviso — comentário de quem escreve -->",
      "  <p>Peça para ligá-lo — enquanto isso, nada chega.</p>",
      "  <td>{{ row.qty || \"—\" }}</td>",
      "  <template v-else>—</template>",
      "  <span>20:00–08:00</span>",
      "</template>",
      "<script setup lang=\"ts\">",
      "// comentário — livre",
      "const label = `${name} — avise a estação`;",
      "</script>",
    ].join("\n");
    expect(emDashLines(sample)).toEqual([
      { line: 3, text: "<p>Peça para ligá-lo — enquanto isso, nada chega.</p>" },
      { line: 10, text: "const label = `${name} — avise a estação`;" },
    ]);
  });

  it("a varredura lê os apps de operador, o kit e o roteador", () => {
    const roots = new Set(SOURCES.map((file) => relative(surfacesDir, file).split("/")[0]));
    for (const root of ROOTS) expect(roots, root).toContain(root);
    expect(SOURCES.length).toBeGreaterThan(500);
  });

  it("cada exceção declarada ainda existe (exceção órfã é lista que cresce sem olhar)", () => {
    for (const key of Object.keys(EXCEPTIONS)) {
      expect(
        SOURCES.some((file) => {
          const path = relative(surfacesDir, file);
          return key.endsWith("/") ? path.startsWith(key) : path === key;
        }),
        key,
      ).toBe(true);
    }
  });

  it("nenhum texto de operador usa travessão", () => {
    const offenders: string[] = [];
    for (const file of SOURCES) {
      const path = relative(surfacesDir, file);
      if (exceptionFor(path)) continue;
      for (const hit of emDashLines(readFileSync(file, "utf8"), file.endsWith(".json"))) {
        offenders.push(`${path}:${hit.line}: ${hit.text}`);
      }
    }
    expect(
      offenders,
      [
        "Copy de operador não usa travessão (CLAUDE.md, \"Copy sem travessão\").",
        "Reescreva lendo a frase: ponto, vírgula, dois-pontos ou parênteses.",
        ...offenders,
      ].join("\n"),
    ).toEqual([]);
  });
});
