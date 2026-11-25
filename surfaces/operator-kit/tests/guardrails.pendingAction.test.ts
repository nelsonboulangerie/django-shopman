import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { OPERATOR_KIT_SURFACES } from "./support/surfaceRegistry";

// Clique nunca inerte: trava estática da layer e dos apps de operador.
//
// Contrato na seção "Clique nunca inerte" do README. Irmã de
// `surfaces/storefront-nuxt/tests/pendingActionGuardrails.test.ts`.
//
// Botão com `@click` numa função `async` do próprio componente precisa declarar o
// pendente no MESMO elemento (`:loading`, `:aria-busy` ou `:disabled`), ou passar
// pela `usePendingAction` (que não é `async function`, então sai da varredura). O que
// já existia sem isso está em `KNOWN_INERT`, que só encolhe: consertou, tira da lista
// (a entrada que sobrou reprova); entrada nova reprova com o arquivo e a função.
//
// Desde DEV-2026-094 o `NuxtButton` (e o `OperatorButton`, que o embrulha) nasce com o
// `loadingAuto` ligado (`app/plugins/buttonPendingByDefault.ts`): o clique que DEVOLVE
// a promessa (`@click="save"`, `@click="save(x)"`) já gira e trava sozinho, e sai da
// varredura. O que ainda pode ficar mudo é:
//   - o `<button>` nativo, que não tem o automático (a regra de sempre);
//   - o botão da suíte cujo handler DESCARTA a promessa (`@click="a(); save()"`,
//     `@click="() => { save() }"`): o automático não a enxerga. Isso reprova sem lista;
//   - o `:loading-auto="false"`, que desliga o automático: só com motivo, na lista.
//
// É heurística de propósito: não vê handler inline (`@click="x = await …"`) nem ação
// async importada de composable. Pega o caso comum, o botão que chama a função async
// declarada ao lado, e não deixa ele crescer.
//
// ⚠️ Lê os ARQUIVOS, não a branch: num worktree, verde só vale para o que está ali.

const kitDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const surfacesDir = resolve(kitDir, "..");

function vueFiles(dir: string): string[] {
  if (!existsSync(dir)) return [];
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory())
      return entry.name === "node_modules" ? [] : vueFiles(path);
    return entry.name.endsWith(".vue") ? [path] : [];
  });
}

// Abre cada tag do template respeitando aspas (handler com `=>` e classe com `>`).
function openingTags(template: string): string[] {
  const tags: string[] = [];
  let i = 0;
  while ((i = template.indexOf("<", i)) !== -1) {
    if (!/[A-Za-z]/.test(template[i + 1] ?? "")) {
      i += 1;
      continue;
    }
    let quote = "";
    let j = i + 1;
    for (; j < template.length; j++) {
      const ch = template[j];
      if (quote) {
        if (ch === quote) quote = "";
      } else if (ch === '"' || ch === "'") quote = ch;
      else if (ch === ">") break;
    }
    tags.push(template.slice(i, j + 1));
    i = j + 1;
  }
  return tags;
}

// Separa os blocos <script> do resto do SFC por índice, sem regex de tag
// (o CodeQL trata regex de <script> como filtro de HTML; aqui só lemos fonte nossa).
function splitScripts(source: string): { script: string; template: string } {
  const lower = source.toLowerCase();
  const scripts: string[] = [];
  let template = "";
  let at = 0;
  while (true) {
    const open = lower.indexOf("<script", at);
    if (open === -1) break;
    const bodyStart = lower.indexOf(">", open) + 1;
    const close = lower.indexOf("</script", bodyStart);
    if (bodyStart === 0 || close === -1) break;
    template += source.slice(at, open);
    scripts.push(source.slice(bodyStart, close));
    const end = lower.indexOf(">", close);
    at = end === -1 ? source.length : end + 1;
  }
  template += source.slice(at);
  return { script: scripts.join("\n"), template };
}

// Corpo de `async function <nome>(…) {…}` por contagem de chaves (fonte nossa,
// sem chave solta em string nos casos medidos). Vazio se não achar.
function asyncFunctionBody(script: string, name: string): string {
  const start = script.search(new RegExp(`async\\s+function\\s+${name}\\b`));
  if (start === -1) return "";
  const paramsEnd = script.indexOf(")", start);
  const open = script.indexOf("{", paramsEnd);
  if (paramsEnd === -1 || open === -1) return "";
  let depth = 0;
  for (let i = open; i < script.length; i++) {
    if (script[i] === "{") depth += 1;
    else if (script[i] === "}" && --depth === 0)
      return script.slice(open + 1, i);
  }
  return "";
}

// Função async que só espera a PERGUNTA da casa (`useConfirm`, direto ou por outra
// função que também só espera por ela) não é clique inerte: o toque abre o diálogo
// no mesmo instante. Ela sai da varredura; a que espera rede continua nela.
function confirmOnlyNames(
  script: string,
  asyncNames: Set<string>,
): Set<string> {
  const askers = new Set(
    [...script.matchAll(/(?:const|let)\s+(\w+)\s*=\s*useConfirm\(\)/g)].map(
      (m) => m[1]!,
    ),
  );
  if (!askers.size) return new Set();
  const confirmOnly = new Set<string>();
  let grew = true;
  while (grew) {
    grew = false;
    for (const name of asyncNames) {
      if (confirmOnly.has(name)) continue;
      const awaited = [
        ...asyncFunctionBody(script, name).matchAll(
          /\bawait\b\s*\(?\s*([\w$.]*)/g,
        ),
      ].map((m) => m[1]!);
      if (
        awaited.length &&
        awaited.every((callee) => askers.has(callee) || confirmOnly.has(callee))
      ) {
        confirmOnly.add(name);
        grew = true;
      }
    }
  }
  return confirmOnly;
}

// Botões da suíte com o pendente automático (o `loadingAuto` ligado no plugin).
const AUTO_PENDING_TAGS = /^<(?:NuxtButton|OperatorButton)\b/;
// Handler que devolve o que a função devolveu: o nome solto ou UMA chamada.
const RETURNS_RESULT = /^(?:\w+|\w+\([^;]*\))$/;

function asyncNamesOf(script: string): Set<string> {
  const declaredAsync = new Set([
    ...[...script.matchAll(/async\s+function\s+(\w+)/g)].map((m) => m[1]!),
    ...[...script.matchAll(/(?:const|let)\s+(\w+)\s*=\s*async\b/g)].map(
      (m) => m[1]!,
    ),
  ]);
  const confirmOnly = confirmOnlyNames(script, declaredAsync);
  return new Set([...declaredAsync].filter((name) => !confirmOnly.has(name)));
}

// Botão da suíte cujo handler chama uma função async e joga a promessa fora: o
// pendente automático não a vê, e o botão fica mudo.
function discardedAsyncClicks(source: string): string[] {
  const { script, template } = splitScripts(source);
  const asyncNames = asyncNamesOf(script);
  const found = new Set<string>();
  for (const tag of openingTags(template)) {
    if (!AUTO_PENDING_TAGS.test(tag)) continue;
    const click = tag.match(/@click(?:\.\w+)*="([^"]*)"/);
    if (!click) continue;
    const handler = click[1]!.trim();
    if (RETURNS_RESULT.test(handler)) continue;
    if (/\s:(?:loading|aria-busy)=/.test(tag)) continue;
    for (const call of handler.matchAll(/\b(\w+)\s*\(/g)) {
      if (asyncNames.has(call[1]!)) found.add(call[1]!);
    }
  }
  return [...found].sort();
}

function inertAsyncClicks(source: string): string[] {
  const { script, template } = splitScripts(source);
  const declaredAsync = new Set([
    ...[...script.matchAll(/async\s+function\s+(\w+)/g)].map((m) => m[1]!),
    ...[...script.matchAll(/(?:const|let)\s+(\w+)\s*=\s*async\b/g)].map(
      (m) => m[1]!,
    ),
  ]);
  const confirmOnly = confirmOnlyNames(script, declaredAsync);
  const asyncNames = new Set(
    [...declaredAsync].filter((name) => !confirmOnly.has(name)),
  );
  const inert = new Set<string>();
  for (const tag of openingTags(template)) {
    const click = tag.match(
      /@click(?:\.\w+)*="(void\s+)?(\w+)(?:\([^"]*\))?"/,
    );
    if (!click || !asyncNames.has(click[2]!)) continue;
    // O botão da suíte gira sozinho quando o handler devolve a promessa.
    if (AUTO_PENDING_TAGS.test(tag) && !click[1]) continue;
    if (/\s:(?:loading|aria-busy|disabled)=/.test(tag)) continue;
    inert.add(click[2]!);
  }
  return [...inert].sort();
}

// O que já existia sem pendente declarado em 01/10/2026. Só encolhe. Zerou em
// 25/11/2026 (DEV-2026-094): os dez itens eram `NuxtButton`, e o pendente automático
// os cobriu. Fica vazio; item novo reprova.
const KNOWN_INERT: Record<string, string[]> = {};

describe("clique nunca inerte (layer + apps de operador)", () => {
  it("botão com ação async declara o pendente; a lista do que falta só encolhe", () => {
    const found: Record<string, string[]> = {};
    for (const dir of ["operator-kit", ...OPERATOR_KIT_SURFACES]) {
      for (const file of vueFiles(join(surfacesDir, dir, "app"))) {
        const inert = inertAsyncClicks(readFileSync(file, "utf8"));
        if (inert.length) found[relative(surfacesDir, file)] = inert;
      }
    }
    expect(found).toEqual(KNOWN_INERT);
  });

  it("a varredura reconhece o botão mudo e o que declara pendente", () => {
    const mute =
      '<script setup>async function save() {}</script><template><button @click="save">Salvar</button></template>';
    const declared =
      '<script setup>async function save() {}</script><template><button :aria-busy="saving || undefined" @click="save">Salvar</button></template>';
    const viaCapability =
      '<script setup>const { run: save, pending } = usePendingAction(() => $fetch("/x"));</script><template><button :disabled="pending" @click="save" /></template>';
    expect(inertAsyncClicks(mute)).toEqual(["save"]);
    expect(inertAsyncClicks(declared)).toEqual([]);
    expect(inertAsyncClicks(viaCapability)).toEqual([]);
  });

  it("a ação que só espera a pergunta da casa não é inerte; a que espera rede depois dela é", () => {
    const asksOnly =
      '<script setup>const confirmDiscard = useConfirm();\nasync function close() { if (!(await confirmDiscard({ title: "x", description: "y" }))) return; open.value = false; }\nasync function pick() { if (!(await close())) return; }</script><template><button @click="close">Cancelar</button><button @click="pick()">Todas</button></template>';
    const asksThenSaves =
      '<script setup>const confirmDiscard = useConfirm();\nasync function swap() { if (!(await confirmDiscard({ title: "x", description: "y" }))) return; await $fetch("/x"); }</script><template><button @click="swap">Trocar</button></template>';
    expect(inertAsyncClicks(asksOnly)).toEqual([]);
    expect(inertAsyncClicks(asksThenSaves)).toEqual(["swap"]);
  });

  it("o lote do Gestor de pedidos passa pela capability", () => {
    const board = readFileSync(
      join(surfacesDir, "orders-nuxt/app/pages/index.vue"),
      "utf8",
    );
    expect(board).toMatch(/usePendingAction\(\s*async \(\) => \{/);
    // O lote mora na barra de seleção da suíte: o estado da ação vai como dado, e a
    // peça marca `aria-busy` no botão.
    expect(board).toContain("loading: bulkConfirming.value");
    expect(board).toContain("loading: bulkAdvancing.value");
    const bar = readFileSync(join(surfacesDir, "operator-kit/app/components/OperatorBulkBar.vue"), "utf8");
    expect(bar.match(/:aria-busy="[^"]*loading \|\| undefined"/g)?.length).toBe(3);
  });
  it("botão da suíte nunca joga fora a promessa da ação (o automático não a veria)", () => {
    const found: Record<string, string[]> = {};
    for (const dir of ["operator-kit", ...OPERATOR_KIT_SURFACES]) {
      for (const file of vueFiles(join(surfacesDir, dir, "app"))) {
        const discarded = discardedAsyncClicks(readFileSync(file, "utf8"));
        if (discarded.length) found[relative(surfacesDir, file)] = discarded;
      }
    }
    expect(found).toEqual({});
  });

  it("a varredura do descarte reconhece o handler que joga a promessa fora", () => {
    const script = "<script setup>async function save() {}\nconst open = ref(false)</script>";
    const returns = `${script}<template><NuxtButton @click="save(1)" /></template>`;
    const discards = `${script}<template><NuxtButton @click="open = false; save()" /></template>`;
    const block = `${script}<template><OperatorButton label="x" @click="() => { save() }" /></template>`;
    const declared = `${script}<template><NuxtButton :loading="busy" @click="open = false; save()" /></template>`;
    expect(discardedAsyncClicks(returns)).toEqual([]);
    expect(discardedAsyncClicks(discards)).toEqual(["save"]);
    expect(discardedAsyncClicks(block)).toEqual(["save"]);
    expect(discardedAsyncClicks(declared)).toEqual([]);
    // E o botão da suíte que devolve a promessa não é mais "inerte".
    expect(inertAsyncClicks(returns)).toEqual([]);
    expect(inertAsyncClicks(`${script}<template><button @click="save">x</button></template>`)).toEqual(["save"]);
  });

  it("desligar o automático (`:loading-auto=\"false\"`) só com motivo escrito aqui", () => {
    // Hoje ninguém desliga. Quem precisar, entra nesta lista com o porquê.
    const ALLOWED_OPT_OUT: Record<string, string> = {};
    const found: string[] = [];
    for (const dir of ["operator-kit", ...OPERATOR_KIT_SURFACES]) {
      for (const file of vueFiles(join(surfacesDir, dir, "app"))) {
        if (/:loading-auto="false"|:loadingAuto="false"/.test(readFileSync(file, "utf8")))
          found.push(relative(surfacesDir, file));
      }
    }
    expect(found.sort()).toEqual(Object.keys(ALLOWED_OPT_OUT).sort());
  });

  it("a raiz está ligada: botão pendente por padrão, barra de rota e link marcado", () => {
    const plugin = readFileSync(join(kitDir, "app/plugins/buttonPendingByDefault.ts"), "utf8");
    expect(plugin).toContain("option.default = true");
    const root = readFileSync(join(kitDir, "app/components/OperatorAppRoot.vue"), "utf8");
    expect(root).toMatch(/<NuxtLoadingIndicator[^>]*:throttle="0"/);
    expect(root).toContain("<OperatorLoadingFeedback />");
    const feedback = readFileSync(join(kitDir, "app/components/OperatorLoadingFeedback.vue"), "utf8");
    expect(feedback).toContain('"page:loading:start"');
    expect(feedback).toContain("data-navigation-pending");
    const css = readFileSync(join(kitDir, "app/assets/css/operator-base.css"), "utf8");
    expect(css).toContain("a[data-navigation-pending]");
    // Todo app da suíte monta o OperatorAppRoot: é por ele que a barra chega.
    for (const dir of OPERATOR_KIT_SURFACES) {
      const app = join(surfacesDir, dir, "app/app.vue");
      if (existsSync(app)) expect(readFileSync(app, "utf8"), dir).toContain("<OperatorAppRoot");
    }
  });
});
