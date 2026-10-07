import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { OPERATOR_SURFACES } from "./support/surfaceRegistry";

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
      /@click(?:\.\w+)*="(?:void\s+)?(\w+)(?:\([^"]*\))?"/,
    );
    if (!click || !asyncNames.has(click[1]!)) continue;
    if (/\s:(?:loading|aria-busy|disabled)=/.test(tag)) continue;
    inert.add(click[1]!);
  }
  return [...inert].sort();
}

// O que já existia sem pendente declarado em 01/10/2026. Só encolhe.
const KNOWN_INERT: Record<string, string[]> = {
  "bi-nuxt/app/pages/explore.vue": ["removeLoaded"],
  "marketing-nuxt/app/components/MarketingBoard.vue": ["confirmReject"],
  "marketing-nuxt/app/pages/announcements/[id].vue": [
    "refreshAll",
    "trackDeliveryUntilSettled",
  ],
  "marketing-nuxt/app/pages/platforms.vue": ["onVerifyCatalog"],
  "marketing-nuxt/app/pages/templates.vue": ["confirmRemove"],
  "operator-kit/app/components/OperatorPwaInstallInvite.vue": ["install"],
  "orders-nuxt/app/components/ChannelHealthChecklist.vue": ["copyAddress"],
  "orders-nuxt/app/pages/catalog.vue": ["saveOrderDraft"],
  "pos-nuxt/app/components/PosAddressAutocomplete.vue": ["accept"],
  "pos-nuxt/app/components/PosCustomerModal.vue": ["cancelDecision"],
  "pos-nuxt/app/components/PosPaymentResult.vue": ["copyCode", "copyLink"],
  "pos-nuxt/app/pages/session/closing.vue": [
    "goToCashReport",
    "goToCashSession",
  ],
  "pos-nuxt/app/pages/session/report.vue": ["goToCashSession"],
  "production-nuxt/app/components/ProductionStageGrid.vue": ["confirmVoid"],
  "production-nuxt/app/pages/board.vue": ["toggleFullscreen"],
  "purchase-nuxt/app/pages/index.vue": [
    "addAndOpenReceiptLine",
    "toggleScannerTorch",
  ],
};

describe("clique nunca inerte (layer + apps de operador)", () => {
  it("botão com ação async declara o pendente; a lista do que falta só encolhe", () => {
    const found: Record<string, string[]> = {};
    for (const dir of ["operator-kit", ...OPERATOR_SURFACES]) {
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
    expect(board).toContain(':aria-busy="bulkConfirming || undefined"');
    expect(board).toContain(':aria-busy="bulkAdvancing || undefined"');
  });
});
