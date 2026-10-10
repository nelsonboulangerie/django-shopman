import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// A pergunta antes de descartar é o diálogo da casa (`useConfirm`), nunca o
// `window.confirm` do navegador. Contrato na seção "Pergunta antes de descartar
// (`useConfirm`)" do README.
//
// Motivo medido (03/10/2026): o Gestor de pedidos perguntava em dez pontos pela caixa
// nativa: fonte do sistema, "OK"/"Cancelar" que não dizem o ato, e no app instalado uma
// caixa estranha sobre a tela. Todos os dez passaram para o `useConfirm`; esta trava
// impede o próximo.
//
// Varre `app/` de TODA superfície Nuxt (`surfaces/*-nuxt`, a loja inclusive) e da
// layer. Reprova `window.confirm(`, `globalThis.confirm(`, `self.confirm(` e o
// `confirm(` solto num arquivo que não declara um `confirm` próprio (o PDV e o Gestor
// têm funções chamadas `confirm`, e elas não são a caixa do navegador).
//
// O `beforeunload` (fechar a aba, recarregar) fica de fora: ali o navegador não deixa
// a página desenhar a caixa, e o `event.preventDefault()` é o único gesto possível.
//
// ⚠️ Lê os ARQUIVOS, não a branch: num worktree, verde só vale para o que está ali.

const kitDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const surfacesDir = resolve(kitDir, "..");

function sourceFiles(dir: string): string[] {
  if (!existsSync(dir)) return [];
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return entry.name === "node_modules" ? [] : sourceFiles(path);
    return /\.(vue|ts|js|mjs)$/.test(entry.name) ? [path] : [];
  });
}

// Comentário fala da caixa nativa para explicar por que ela saiu; isso não é uso.
// O comentário de template sai por índice, sem regex de `<!--` (o CodeQL lê regex de
// comentário HTML como filtro de HTML; aqui só lemos fonte nossa).
function withoutTemplateComments(source: string): string {
  let out = "";
  let at = 0;
  while (true) {
    const open = source.indexOf("<!--", at);
    if (open === -1) return out + source.slice(at);
    const close = source.indexOf("-->", open + 4);
    out += source.slice(at, open);
    if (close === -1) return out;
    at = close + 3;
  }
}

function withoutComments(source: string): string {
  return withoutTemplateComments(source)
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:"'`\\])\/\/.*$/gm, "$1");
}

function nativeConfirmCalls(source: string): number {
  const code = withoutComments(source);
  const global = code.match(/\b(?:window|globalThis|self)\s*\.\s*confirm\s*\(/g)?.length ?? 0;
  const declaresOwn =
    /\b(?:function|const|let|var)\s+confirm\b/.test(code) || /[{,]\s*confirm\s*[,}]/.test(code);
  const bare = declaresOwn ? 0 : (code.match(/(?<![\w$.])confirm\s*\(/g)?.length ?? 0);
  return global + bare;
}

function surfaceDirs(): string[] {
  return readdirSync(surfacesDir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && (entry.name.endsWith("-nuxt") || entry.name === "operator-kit"))
    .map((entry) => entry.name)
    .sort();
}

// O que existia em 03/10/2026 fora do Gestor, com o motivo. Só encolhe: migrou, tira
// daqui (a entrada que sobrou reprova); entrada nova não entra sem motivo escrito.
// A Produção migrou na UX-P1 (qualidade em lote): o descarte da contagem usa o
// useConfirm e a confirmação da qualidade é o próprio gesto, com a consequência
// escrita antes. A lista ficou vazia e assim deve ficar.
const DECLARED: Record<string, { calls: number; reason: string }> = {};

describe("pergunta antes de descartar: o diálogo da casa, nunca a caixa do navegador", () => {
  it("nenhuma superfície chama o confirm nativo fora do que está declarado com motivo", () => {
    const found: Record<string, number> = {};
    for (const dir of surfaceDirs()) {
      for (const file of sourceFiles(join(surfacesDir, dir, "app"))) {
        const calls = nativeConfirmCalls(readFileSync(file, "utf8"));
        if (calls) found[relative(surfacesDir, file)] = calls;
      }
    }
    const declared = Object.fromEntries(Object.entries(DECLARED).map(([file, entry]) => [file, entry.calls]));
    expect(found).toEqual(declared);
  });

  it("toda exceção declarada diz o motivo", () => {
    for (const entry of Object.values(DECLARED)) expect(entry.reason.trim().length).toBeGreaterThan(20);
  });

  it("a varredura acusa a caixa nativa e deixa passar a função própria e o comentário", () => {
    expect(nativeConfirmCalls('if (!window.confirm("Descartar?")) return;')).toBe(1);
    expect(nativeConfirmCalls('const ok = globalThis.confirm("x");')).toBe(1);
    expect(nativeConfirmCalls('if (!confirm("Descartar?")) return;')).toBe(1);
    expect(nativeConfirmCalls("function confirm() {}\nconfirm();")).toBe(0);
    expect(nativeConfirmCalls("const { confirm } = useThing();\nawait confirm();")).toBe(0);
    expect(nativeConfirmCalls("await decisionCommand.confirm(value);")).toBe(0);
    expect(nativeConfirmCalls("// antes: if (!window.confirm(x)) return\nconst a = 1;")).toBe(0);
    expect(nativeConfirmCalls("<!-- não `window.confirm(...)` -->")).toBe(0);
  });

  it("o diálogo da casa está montado na peça que todo app de operador monta", () => {
    const runtime = readFileSync(join(kitDir, "app/components/OperatorPwaRuntime.vue"), "utf8");
    expect(runtime).toContain("<OperatorConfirmDialog />");
  });
});
