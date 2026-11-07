// PRÉVIA (modelo de navegação aprovado em 31/10/2026), aplicada ao Gestor. Roda numa
// CÓPIA temporária de surfaces/, DEPOIS de `gestor-compact/apply-conn-sim.mjs` e
// `gestor-compact/apply-compact.mjs` (a linha do chão de 30/10). Nunca escreve em surfaces/.
// Âncoras exatas: se o código do main mudar, falha alto.
//
// O que muda (só navegação; a fila, o cartão e o detalhe do pedido ficam como no main):
//   1. O selo abre o trocador (seções deste app por forma, outros apps, quem opera).
//   2. Sem ☰ no celular e no tablet: o selo está sempre na barra.
//   3. Forma chão (Pedidos, Saída, o pedido, Rotinas): sem barra de seções embaixo.
//      Forma escritório (Histórico, Catálogo, Clientes, Canais, Postos): a barra de baixo
//      mostra as seções do escritório; "Mais" abre o trocador.
//   4. A linha do chão ganha o lugar no selo ("Gestor · Saída") e a busca vira ícone.
// Uso: node apply-modelo.mjs <cópia>/surfaces/orders-nuxt
import { copyFile, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";

const root = process.argv[2];
if (!root) throw Error("Informe a cópia temporária do orders-nuxt.");
const kit = join(root, "../operator-kit");
const here = (name) => new URL(name, import.meta.url);

async function patch(file, pairs) {
  let s = await readFile(file, "utf8");
  if (s.includes("PRÉVIA modelo")) return console.log(`já aplicado: ${file}`);
  for (const [from, to] of pairs) {
    const n = s.split(from).length - 1;
    if (n !== 1) throw Error(`${file}: âncora achada ${n}x:\n${from.slice(0, 160)}`);
    s = s.replace(from, to);
  }
  await writeFile(file, s);
  console.log(`ok: ${file.replace(root + "/", "").replace(kit + "/", "kit/")}`);
}

// ── Kit ─────────────────────────────────────────────────────────────────────
await copyFile(here("OperatorSwitcher.vue"), join(kit, "app/components/OperatorSwitcher.vue"));
await copyFile(here("OperatorCompactSeal.vue"), join(kit, "app/components/OperatorCompactSeal.vue"));

await patch(join(kit, "app/presentation/appBar.ts"), [[
  "  divider?: boolean;\n}",
  `  divider?: boolean;
  /** PRÉVIA modelo: a forma da tela (chão, escritório, parede). Ausente = escritório. */
  form?: "floor" | "office" | "wall";
}`,
]]);

// O selo do topo (celular, tablet em pé) e o do topo da barra lateral: abrem o trocador.
await writeFile(join(kit, "app/components/OperatorAppSeal.vue"), `<script setup lang="ts">
// PRÉVIA modelo (31/10/2026): o selo abre o trocador (seções, outros apps, quem opera).
// Na própria Central (\`home\`), continua só identidade.
const props = withDefaults(defineProps<{ home?: boolean; placement?: "header" | "rail" }>(), { home: false, placement: "header" });
interface SealIdentity { label: string; icon: string; iconSrc: string; color: string }
const config = useRuntimeConfig().public as { operatorPwa?: { identity?: SealIdentity } };
const identity = config.operatorPwa?.identity;
const open = useState<boolean>("suite-switcher-open", () => false);
const broken = ref(false);
const iconName = computed(() => { const icon = identity?.icon || "layout-grid"; return icon.includes(":") ? icon : \`lucide:\${icon}\`; });
</script>
<template>
  <NuxtButton color="neutral" variant="ghost" square
    :class="placement === 'header' ? '-mx-1 my-1.5 rail:hidden' : ''"
    :aria-label="home ? identity?.label : \`\${identity?.label || 'App'}: trocar de seção ou de app\`"
    :aria-haspopup="home ? undefined : 'dialog'" data-page-header-app
    @click="home ? undefined : (open = true)">
    <NuxtAvatar :src="identity?.iconSrc && !broken ? identity.iconSrc : undefined" :icon="iconName" alt=""
      :style="{ background: identity?.color || 'var(--primary)' }" @error="broken = true" />
  </NuxtButton>
</template>
`);
console.log("ok: kit/app/components/OperatorAppSeal.vue");

await patch(join(kit, "app/components/OperatorSuiteShell.vue"), [
  [
    "  home?: boolean;\n}>();",
    `  home?: boolean;
  /** PRÉVIA modelo: todas as seções do app, com a forma de cada uma (o trocador). */
  switcherSections?: readonly OperatorSection[];
  /** PRÉVIA modelo: a forma de uma tela que não é seção (o item aberto). */
  defaultForm?: "floor" | "office" | "wall";
}>();`,
  ],
  [
    `const quickSections = computed(() =>
  props.sections.filter((section) => section.where !== "rail"),
);`,
    `const quickSections = computed(() =>
  props.sections.filter((section) => section.where !== "rail"),
);
// PRÉVIA modelo: a forma da tela decide a barra de baixo. Chão: nenhuma (o posto define o
// lugar; trocar é pelo selo). Escritório: as seções do escritório, "Mais" abre o trocador.
const pool = computed(() => props.switcherSections ?? props.sections);
function exactKey(path: string): string | undefined {
  const clean = (path || "/").split("?")[0]!.replace(/(.)\\/$/, "$1");
  let best: { key: string; len: number } | undefined;
  for (const section of pool.value) {
    for (const cand of [section.to, ...(section.match || [])]) {
      if (!cand) continue;
      const c = cand.split("?")[0]!.replace(/(.)\\/$/, "$1");
      const hit = c === "/" ? clean === "/" : clean === c || clean.startsWith(c + "/");
      if (hit && (!best || c.length > best.len)) best = { key: section.key, len: c.length };
    }
  }
  return best?.key;
}
const switcherCurrent = computed(() => props.current ?? exactKey(route.path));
const form = computed(
  () => pool.value.find((s) => s.key === switcherCurrent.value)?.form ?? props.defaultForm ?? "office",
);
const switcherOpen = useState<boolean>("suite-switcher-open", () => false);
const officeQuick = computed(() =>
  props.switcherSections
    ? props.switcherSections.filter((s) => (s.form ?? "office") === "office").map((s) => ({ ...s, quick: undefined }))
    : quickSections.value,
);`,
  ],
  [
    `        <OperatorQuickBar
          :sections="quickSections"
          :current="active"
          :label="label"
          @select="emit('select', $event)"
          @more="drawerOpen = true"
        />`,
    `        <OperatorQuickBar
          v-if="form === 'office'"
          :sections="officeQuick"
          :current="switcherCurrent"
          :label="label"
          @select="emit('select', $event)"
          @more="switcherOpen = true"
        />`,
  ],
  [
    "  <ClientOnly><OperatorUrgentAlert /></ClientOnly>",
    `  <ClientOnly><OperatorUrgentAlert /></ClientOnly>
  <ClientOnly><OperatorSwitcher v-if="!home" :sections="pool" :current="switcherCurrent" :operator-name="operatorName" @lock="emit('lock')" /></ClientOnly>`,
  ],
]);

await patch(join(kit, "app/components/OperatorPageHeader.vue"), [
  [`      :toggle="Boolean(suiteRail)"`, `      :toggle="false"`],
  [
    `const sealClass = computed(() => (suiteRail ? "max-sm:hidden" : ""));`,
    `// PRÉVIA modelo: sem ☰, o selo é a porta do trocador em toda largura.
const sealClass = computed(() => "");`,
  ],
]);

// A linha do chão (prévia de 30/10): o selo diz o lugar; a busca vira ícone, e o termo
// ativo segue na faixa de baixo.
await patch(join(kit, "app/components/OperatorCompactBar.vue"), [
  [
    `<slot name="lead"><OperatorCompactSeal :tone="tone" :time="time" :to="to" /></slot>`,
    `<!-- PRÉVIA modelo: o selo leva o lugar. -->
      <slot name="lead"><OperatorCompactSeal :tone="tone" :time="time" :to="to" :place="title" /></slot>`,
  ],
  [`:class="$slots.identity ? 'shrink-0' : 'flex-1'" role="group"`, `:class="'shrink-0'" role="group"`],
  [
    `:class="$slots.identity ? 'w-11 flex-none justify-center px-0' : ''"`,
    `:class="'w-11 flex-none justify-center px-0'"`,
  ],
  [`<span v-if="!$slots.identity" class="min-w-0 truncate text-left"`, `<span v-if="false" class="min-w-0 truncate text-left"`],
]);

// ── Gestor ──────────────────────────────────────────────────────────────────
await patch(join(root, "app/app.vue"), [
  [
    "const { sections, current } = useGestorSections();",
    `const { sections, settings, current } = useGestorSections();
// PRÉVIA modelo: o trocador lista tudo, pela forma. Chão: Pedidos, Saída e Rotinas
// (andando pela loja, dono 31/10). Escritório: o que hoje mora em Ajustes.
const FLOOR = new Set(["orders", "exit", "checklists"]);
const switcherSections = computed(() => {
  const seen = new Set<string>();
  return [...sections.value.filter((s) => s.key !== "settings"), ...settings.value]
    .filter((s) => (seen.has(s.key) ? false : (seen.add(s.key), true)))
    .map((s) => ({ ...s, form: FLOOR.has(s.key) ? ("floor" as const) : ("office" as const) }));
});`,
  ],
  [
    `        :current="current"
        label="Seções do Gestor"`,
    `        :current="current"
        :switcher-sections="switcherSections"
        default-form="floor"
        label="Seções do Gestor"`,
  ],
]);

// ── Simulador: a projeção da Central, para "Outros apps" (dados fictícios) ──
const C = process.env.PREVIEW_CENTRAL || "";
const tiles = [
  ["pos", "PDV", "shopping-basket", process.env.PREVIEW_POS || C, "1 encomenda na próxima hora", "Caixa aberto"],
  ["kds", "Cozinha", "chef-hat", process.env.PREVIEW_KDS || C, "1 atrasado", "3 em preparo"],
  ["gestor", "Gestor de pedidos", "square-kanban", "", "", ""],
  ["production", "Produção", "croissant", C, "", "5 lotes hoje"],
  ["purchase", "Compras", "package", process.env.PREVIEW_PURCHASE || C, "2 entregas para receber", ""],
  ["marketing", "Marketing", "megaphone", C, "1 anúncio para decidir", ""],
  ["bi", "B.I.", "chart-no-axes-combined", C, "", "Vendas de ontem"],
].map(([ref, label, icon, url, attention, summary]) => ({
  ref, label, icon, url, kind: "launch", description: "", status_attention: attention,
  status_summary: summary, status_positive: "", next_item: null,
}));
await patch(join(root, "tests/visual/mockBackend.mjs"), [[
  `  if (path === "/api/v1/backstage/orders/rail-counts/") {`,
  `  // PRÉVIA modelo: a projeção da Central (dados fictícios), para o trocador.
  if (path === "/api/v1/backstage/hub/") { send(res, 200, { hub: { tiles: ${JSON.stringify(tiles)} } }); return; }
  if (path === "/api/v1/backstage/orders/rail-counts/") {`,
]]);
console.log("apply-modelo: kit, Gestor e simulador aplicados");
