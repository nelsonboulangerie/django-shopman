// PRÉVIA (31/10/2026): três alternativas para o aviso de pedido, o som bloqueado e a linha
// de cima do chão no celular. O dono escolheu b em 31/10: é o padrão sem parâmetro.
// Roda DEPOIS de apply-modelo.mjs. `?v=a|b|c` escolhe; a escolha vale na navegação até
// recarregar sem o parâmetro.
//   a: como a prévia do modelo (faixa no topo, grupo com moldura).
//   b: aviso numa pílula no polegar (Ver, Visto); som pela tela "Toque para começar";
//      linha de cima sem moldura, Filtros dentro do ⋮.
//   c: sem aviso separado: a aba Entrada acende com "novo" e o som para quando você abre
//      a Entrada (muda a regra do Visto: pede o sim do dono); som e linha como em b.
// O aviso toca para o pedido que acabou de ter algo a fazer, em qualquer zona (não só o
// novo da Entrada). Em b a pílula diz qual pedido e o que ele pede, e Ver leva à zona dele;
// na Saída ela fica acima do "Entregar", que é a ação do momento ali.
// Uso: node apply-alternativas.mjs <cópia>/surfaces/orders-nuxt
import { readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";

const root = process.argv[2];
if (!root) throw Error("Informe a cópia temporária do orders-nuxt.");

async function patch(file, pairs) {
  let s = await readFile(file, "utf8");
  if (s.includes("PRÉVIA alternativas")) return console.log(`já aplicado: ${file}`);
  for (const [from, to] of pairs) {
    const n = s.split(from).length - 1;
    if (n !== 1) throw Error(`${file}: âncora achada ${n}x:\n${from.slice(0, 160)}`);
    s = s.replace(from, to);
  }
  await writeFile(file, s);
  console.log(`ok: ${file}`);
}

await patch(join(root, "../operator-kit/app/components/OperatorCompactBar.vue"), [
  [
    "options?: Array<any>; avisos?: 'own' | 'options' | 'none'; to?: string;",
    "options?: Array<any>; avisos?: 'own' | 'options' | 'none'; to?: string;\n  /** PRÉVIA alternativas: sem moldura; Filtros entra no ⋮. */ plain?: boolean;",
  ],
  [
    "  ...(props.avisos === 'options' ? [[{ label: 'Avisos', icon: 'i-lucide-bell', onSelect: openInbox }]] : []),",
    "  ...(props.avisos === 'options' ? [[{ label: 'Avisos', icon: 'i-lucide-bell', onSelect: openInbox }]] : []),\n  ...(props.plain && slots.filters ? [[{ label: props.filterActive ? 'Filtros: ' + props.filterLabel : 'Filtros', icon: 'i-lucide-list-filter', onSelect: () => (filtersOpen.value = true) }]] : []),",
  ],
  ["const filtersOpen = ref(false);", "const filtersOpen = ref(false);\nconst slots = useSlots();"],
  [`:class="'shrink-0'" role="group"`, `:class="plain ? 'shrink-0 border-0 bg-transparent' : 'shrink-0'" role="group"`],
  [`<NuxtButton v-if="$slots.filters" icon="i-lucide-list-filter"`, `<NuxtButton v-if="$slots.filters && !plain" icon="i-lucide-list-filter"`],
  [
    `:class="search || $slots.filters ? 'border-l border-default' : ''"`,
    `:class="!plain && (search || $slots.filters) ? 'border-l border-default' : ''"`,
  ],
]);

await patch(join(root, "app/composables/useOrdersBoard.ts"), [
  [
    "  const attentionPending = ref(false);",
    `  const attentionPending = ref(false);
  // PRÉVIA alternativas: o pedido que fez o aviso tocar, para a pílula dizer qual é.
  const attentionRef = ref("");`,
  ],
  [
    `      attentionPending.value = pendingAttentionRefs.size > 0;
      announceTreatableOrder(decision.firstUnseen);`,
    `      attentionPending.value = pendingAttentionRefs.size > 0;
      attentionRef.value = decision.firstUnseen;
      announceTreatableOrder(decision.firstUnseen);`,
  ],
  ["\n    attentionPending,\n", "\n    attentionPending,\n    attentionRef,\n"],
]);

await patch(join(root, "app/pages/index.vue"), [
  ["\n  attentionPending,\n", "\n  attentionPending,\n  attentionRef,\n"],
  [
    `  queueScopeCounts,
  type QueueScope,`,
    `  queueCode,
  queueScopeCounts,
  type QueueScope,`,
  ],
  [
    "const compactOptions = computed(",
    `// PRÉVIA alternativas: ?v=a (faixa no topo), b (pílula no polegar), c (a aba Entrada acende).
const pv = useState<"a" | "b" | "c">("preview-v", () =>
  ["a", "b", "c"].includes(String(route.query.v)) ? (route.query.v as "a" | "b" | "c") : "b",
);
watch(() => route.query.v, (v) => { if (v === "a" || v === "b" || v === "c") pv.value = v; });
// O aviso não é só de pedido novo: toca para o pedido que acabou de ter algo a fazer, em
// qualquer zona. A pílula diz qual é, com o mesmo status que o cartão mostra (a zona
// mentia: um pedido já na rua aparecia como "pronto para sair"), e Ver leva à zona dele.
const attention = computed(() => {
  const zone = zones.value.find((z) => z.cards.some((c) => c.ref === attentionRef.value));
  const card = zone?.cards.find((c) => c.ref === attentionRef.value);
  return {
    zone: zone?.key ?? "intake",
    code: card ? queueCode(card) : "",
    what: card?.status_label || "Pedido para tratar",
  };
});
const startDismissed = ref(false);
function startTap() { startDismissed.value = true; handleSoundAction(); }
// Ver: abre a zona do pedido. Na Saída, fica nela se o pedido é da Saída ou do preparo;
// senão sai do posto e abre Pedidos (o selo muda junto).
function seeAttention() {
  const zone = attention.value.zone;
  if (phoneExitMode.value && zone !== "expedition" && zone !== "prep") phoneExitMode.value = false;
  pickPhoneZone(zone);
}
// c: abrir a Entrada é ver o pedido novo; o som para ali.
watch([phoneZone, attentionPending, pv], ([zone, pending, variant]) => {
  if (variant === "c" && pending && zone === "intake" && pickedZone.value === "intake") acknowledgeAttention();
});
const compactOptions = computed(`,
  ],
  [
    `    count: triaged(tab.zone).length,
  })),`,
    `    count: triaged(tab.zone).length,
    fresh: pv.value === "c" && tab.key === "intake" && attentionPending.value,
  })),`,
  ],
  [
    `<template #trailing="{ item }"><OperatorCountChip :count="item.count" /></template>`,
    `<template #trailing="{ item }"><OperatorCountChip :count="item.count" /><NuxtBadge v-if="item.fresh" label="novo" color="warning" variant="solid" size="sm" class="ms-1 animate-pulse" data-alt-fresh /></template>`,
  ],
  [
    `      v-if="(attentionPending && !exitPostView) || (soundOn && soundBlocked)"`,
    `      v-if="pv === 'a' && ((attentionPending && !exitPostView) || (soundOn && soundBlocked))"`,
  ],
  [`      :avisos="previewAvisos"`, `      :avisos="previewAvisos"\n      :plain="pv !== 'a'"`],
  [
    `    <OperatorPageHeader
      :title="exitPostView ? 'Saída' : 'Pedidos'"`,
    `    <!-- PRÉVIA alternativas b: o aviso no polegar, sem empurrar a fila. Na Saída, acima do
         "Entregar", que é a ação do momento ali e não pode ficar coberta. -->
    <div v-if="pv === 'b' && attentionPending && !exitPostView" :class="phoneExitMode ? 'bottom-24' : 'bottom-4'" class="fixed inset-x-3 z-40 md:hidden" role="status" data-alt-pill>
      <div class="flex items-center gap-2 rounded-2xl bg-inverted py-1.5 pl-4 pr-1.5 text-inverted shadow-lg">
        <NuxtIcon name="i-lucide-bell-ring" class="size-5 shrink-0" />
        <p class="min-w-0 flex-1 leading-tight"><strong class="block truncate">{{ attention.code || attention.what }}</strong><span v-if="attention.code" class="block truncate text-xs opacity-80">{{ attention.what }}</span></p>
        <NuxtButton label="Ver" color="neutral" variant="ghost" class="min-h-11 text-inverted" data-alt-pill-see @click="seeAttention" />
        <NuxtButton icon="i-lucide-check" label="Visto" color="neutral" variant="outline" class="min-h-11" data-alt-pill-seen @click="acknowledgeAttention" />
      </div>
    </div>
    <!-- PRÉVIA alternativas b e c: o som pede um toque do navegador uma vez; a tela pede. -->
    <button v-if="pv !== 'a' && soundOn && soundBlocked && !startDismissed" type="button" class="fixed inset-0 z-50 grid place-items-center bg-default/95 p-6 text-center md:hidden" data-alt-start @click="startTap">
      <span><span class="block text-2xl font-semibold text-highlighted">Toque para começar</span><span class="mt-2 block text-muted">O som dos pedidos novos liga junto.</span></span>
    </button>
    <OperatorPageHeader
      :title="exitPostView ? 'Saída' : 'Pedidos'"`,
  ],
]);
console.log("apply-alternativas: a, b, c aplicadas");
