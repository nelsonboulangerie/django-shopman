<script setup lang="ts">
// Comparar (/recipes/compare?a=ref@n&b=ref@n) — duas versões lado a lado, da mesma
// receita ou de receitas diferentes. Dois seletores (receita + número da versão)
// e a tabela de deltas por ingrediente e por métrica; o tom vem do servidor por
// sinal (o que subiu, o que desceu), calmo por padrão.
import { compareQuery, parseVersionRef, toneClass } from "~/presentation/recipeBook";

useHead({ title: "Comparar receitas" });

const route = useRoute();
const router = useRouter();

function fromQuery(key: "a" | "b"): string {
  const value = route.query[key];
  return typeof value === "string" ? value : "";
}
const a = ref(fromQuery("a"));
const b = ref(fromQuery("b"));
watch(
  () => [route.query.a, route.query.b],
  () => {
    a.value = fromQuery("a");
    b.value = fromQuery("b");
  },
);

// Os seletores: a lista do inventário dá as receitas e quantas versões cada uma tem.
const { entries, pending: bookPending } = useRecipeBook(ref(""), ref(""), ref(false));

const sideA = computed(() => parseVersionRef(a.value));
const sideB = computed(() => parseVersionRef(b.value));

function versionCount(entryRef: string): number {
  return entries.value.find((entry) => entry.ref === entryRef)?.version_count ?? 0;
}

function setSide(side: "a" | "b", entryRef: string, number: number) {
  const other = side === "a" ? sideB.value : sideA.value;
  const next =
    side === "a"
      ? compareQuery(entryRef, number, other?.ref ?? "", other?.number ?? 0)
      : compareQuery(other?.ref ?? "", other?.number ?? 0, entryRef, number);
  const query: Record<string, string> = {};
  if (entryRef && number > 0) query[side] = next[side];
  if (other) query[side === "a" ? "b" : "a"] = next[side === "a" ? "b" : "a"];
  router.replace({ query });
}

function onEntryChange(side: "a" | "b", entryRef: string) {
  const count = versionCount(entryRef);
  setSide(side, entryRef, count > 0 ? count : 1);
}

function onNumberChange(side: "a" | "b", value: number | string | null | undefined) {
  const current = side === "a" ? sideA.value : sideB.value;
  if (!current) return;
  const number = Math.max(1, Number(value) || 1);
  setSide(side, current.ref, number);
}

// A lista do inventário cresce: `NuxtSelectMenu` com busca (por nome e SKU).
const entryItems = computed(() =>
  entries.value.map((entry) => ({
    value: entry.ref,
    label: entry.output_sku ? `${entry.name} · ${entry.output_sku}` : entry.name,
  })),
);
const touch = useTouchPointer();

// A tabela da suíte: o ingrediente fica (fixado); o papel é coluna de apoio.
const NUM = { class: { th: "text-right", td: "text-right tabular-nums whitespace-nowrap" } };
const rowColumns = [
  { id: "ingredient", header: "Ingrediente", enableHiding: false },
  { accessorKey: "role_label", header: "Papel", meta: { supporting: true } },
  { id: "a", header: "A", meta: NUM },
  { id: "b", header: "B", meta: NUM },
  { id: "delta", header: "Diferença", meta: NUM },
  { id: "pct", header: "%", meta: NUM },
];
const metricColumns = [
  { accessorKey: "label", header: "Métrica", enableHiding: false },
  { id: "a", header: "A", meta: NUM },
  { id: "b", header: "B", meta: NUM },
  { id: "delta", header: "Diferença", meta: NUM },
];

const { ready, compare, rows, metrics, pending, error, refresh } = useRecipeCompare(a, b);
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <RecipeHeader title="Comparar" :back="sideA ? `/recipes/${sideA.ref}` : '/recipes'" :pending="pending" @refresh="refresh()" />

    <section class="min-h-0 flex-1 overflow-auto p-3 md:p-4">
      <div class="mb-4 grid gap-3 sm:grid-cols-2">
        <NuxtCard v-for="side in (['a', 'b'] as const)" :key="side">
          <div class="flex flex-wrap items-end gap-2">
            <NuxtFormField :label="side === 'a' ? 'Receita A' : 'Receita B'" class="min-w-0 flex-1">
              <NuxtSelectMenu
                :model-value="(side === 'a' ? sideA : sideB)?.ref"
                :items="entryItems"
                value-key="value"
                placeholder="Escolha a receita"
                class="w-full"
                :disabled="bookPending && !entries.length"
                :search-input="{ autofocus: !touch, placeholder: 'Buscar receita' }"
                @update:model-value="(value: string) => onEntryChange(side, value)"
              />
            </NuxtFormField>
            <NuxtFormField label="Versão">
              <NuxtInputNumber
                :model-value="(side === 'a' ? sideA : sideB)?.number ?? null"
                :min="1"
                :max="versionCount((side === 'a' ? sideA : sideB)?.ref ?? '') || undefined"
                :disabled="!(side === 'a' ? sideA : sideB)"
                class="w-28"
                @update:model-value="(value: number | null) => onNumberChange(side, value)"
              />
            </NuxtFormField>
          </div>
        </NuxtCard>
      </div>

      <NuxtEmpty
        v-if="!ready"
        icon="i-lucide-git-compare"
        title="Escolha as duas versões para comparar."
        description="Pode ser a mesma receita em dois momentos ou duas receitas diferentes."
        variant="outline"
      />

      <OperatorScreenState v-else-if="error && !compare" state="error" what="a comparação" description="Confira se as duas versões existem." @retry="refresh()" />
      <OperatorScreenState v-else-if="pending && !compare" state="loading" what="a comparação" />

      <template v-else-if="compare">
        <div class="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
          <span><span class="text-muted-foreground">A</span> <b>{{ compare.a_title }}</b></span>
          <span><span class="text-muted-foreground">B</span> <b>{{ compare.b_title }}</b></span>
        </div>

        <OperatorTable
          :data="rows"
          :columns="rowColumns"
          :row-key="(row) => row.sku || row.name"
          pinned="ingredient"
          empty-title="Nenhum ingrediente para comparar."
          caption="Ingredientes das duas versões"
        >
          <template #ingredient-cell="{ row }">
            <span class="block font-medium">{{ row.original.name || row.original.sku }}</span>
            <span v-if="row.original.sku" class="block font-mono text-xs text-muted-foreground">{{ row.original.sku }}</span>
          </template>
          <template #a-cell="{ row }">{{ row.original.a_display || "—" }}</template>
          <template #b-cell="{ row }">{{ row.original.b_display || "—" }}</template>
          <template #delta-cell="{ row }">
            <span class="font-semibold" :class="toneClass(row.original.tone)">{{ row.original.delta_display || "—" }}</span>
          </template>
          <template #pct-cell="{ row }">
            <span :class="toneClass(row.original.tone)">{{ row.original.delta_pct_display || "—" }}</span>
          </template>
        </OperatorTable>

        <div v-if="metrics.length" class="mt-4 max-w-2xl">
          <OperatorTable
            :data="metrics"
            :columns="metricColumns"
            :row-key="(metric) => metric.label"
            caption="Métricas das duas versões"
          >
            <template #a-cell="{ row }">{{ row.original.a_display || "—" }}</template>
            <template #b-cell="{ row }">{{ row.original.b_display || "—" }}</template>
            <template #delta-cell="{ row }">
              <span class="font-semibold" :class="toneClass(row.original.tone)">{{ row.original.delta_display || "—" }}</span>
            </template>
          </OperatorTable>
        </div>
      </template>
    </section>
  </main>
</template>
