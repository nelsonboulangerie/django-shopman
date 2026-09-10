<script setup lang="ts">
// Comparar (/recipes/compare?a=ref@n&b=ref@n) — duas versões lado a lado, da mesma
// receita ou de receitas diferentes. Dois seletores (receita + número da versão)
// e a tabela de deltas por ingrediente e por métrica; o tom vem do servidor por
// sinal (o que subiu, o que desceu), calmo por padrão.
import { compareQuery, parseVersionRef, toneClass } from "~/presentation/recipeBook";

useHead({ title: "Comparar receitas · Produção" });

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

function onEntryChange(side: "a" | "b", event: Event) {
  const entryRef = (event.target as HTMLSelectElement).value;
  const count = versionCount(entryRef);
  setSide(side, entryRef, count > 0 ? count : 1);
}

function onNumberChange(side: "a" | "b", event: Event) {
  const current = side === "a" ? sideA.value : sideB.value;
  if (!current) return;
  const number = Math.max(1, Number((event.target as HTMLInputElement).value) || 1);
  setSide(side, current.ref, number);
}

const { ready, compare, rows, metrics, pending, error, refresh } = useRecipeCompare(a, b);
</script>

<template>
  <main class="flex min-h-screen flex-col">
    <RecipeHeader title="Comparar" :back="sideA ? `/recipes/${sideA.ref}` : '/recipes'" :pending="pending" @refresh="refresh()" />

    <section class="min-h-0 flex-1 overflow-auto p-3 md:p-4">
      <div class="mb-4 grid gap-3 sm:grid-cols-2">
        <div v-for="side in (['a', 'b'] as const)" :key="side" class="grid gap-2 rounded-lg border bg-card p-3">
          <p class="text-xs font-medium uppercase tracking-wider text-muted-foreground">{{ side === "a" ? "Lado A" : "Lado B" }}</p>
          <div class="flex flex-wrap items-end gap-2">
            <label class="grid min-w-0 flex-1 gap-1 text-xs font-medium text-muted-foreground">
              Receita
              <select
                :value="(side === 'a' ? sideA : sideB)?.ref ?? ''"
                class="h-9 w-full rounded-md border bg-background px-2 text-sm text-foreground"
                :disabled="bookPending && !entries.length"
                @change="onEntryChange(side, $event)"
              >
                <option value="">Escolha…</option>
                <option v-for="entry in entries" :key="entry.ref" :value="entry.ref">
                  {{ entry.name }}{{ entry.output_sku ? ` · ${entry.output_sku}` : "" }}
                </option>
              </select>
            </label>
            <label class="grid gap-1 text-xs font-medium text-muted-foreground">
              Versão
              <input
                type="number"
                min="1"
                :max="versionCount((side === 'a' ? sideA : sideB)?.ref ?? '') || undefined"
                :value="(side === 'a' ? sideA : sideB)?.number ?? ''"
                :disabled="!(side === 'a' ? sideA : sideB)"
                class="h-9 w-20 rounded-md border bg-background px-2 text-sm tabular-nums text-foreground"
                @change="onNumberChange(side, $event)"
              />
            </label>
          </div>
        </div>
      </div>

      <div
        v-if="!ready"
        class="grid place-items-center gap-2 rounded-lg border border-dashed py-16 text-center text-muted-foreground"
      >
        <Icon name="lucide:git-compare" class="size-8" />
        <p class="text-base font-medium">Escolha as duas versões para comparar.</p>
        <p class="text-sm">Pode ser a mesma receita em dois momentos ou duas receitas diferentes.</p>
      </div>

      <p v-else-if="pending && !compare" class="text-sm text-muted-foreground">Comparando…</p>

      <div
        v-else-if="error && !compare"
        class="grid place-items-center gap-2 rounded-lg border border-dashed border-destructive/30 py-16 text-center text-muted-foreground"
      >
        <Icon name="lucide:cloud-off" class="size-8 text-destructive/70" />
        <p class="text-base font-medium text-foreground">Não foi possível comparar.</p>
        <p class="text-sm">Confira se as duas versões existem.</p>
        <button
          type="button"
          class="mt-1 inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium transition hover:bg-accent"
          @click="refresh()"
        >
          <Icon name="lucide:refresh-cw" class="size-4" /> Tentar de novo
        </button>
      </div>

      <template v-else-if="compare">
        <div class="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
          <span><span class="text-muted-foreground">A</span> <b>{{ compare.a_title }}</b></span>
          <span><span class="text-muted-foreground">B</span> <b>{{ compare.b_title }}</b></span>
        </div>

        <div class="overflow-x-auto rounded-lg border">
          <table class="w-full min-w-[36rem] text-sm">
            <thead class="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th class="px-3 py-2 font-semibold">Ingrediente</th>
                <th class="hidden px-3 py-2 font-semibold sm:table-cell">Papel</th>
                <th class="px-3 py-2 text-right font-semibold">A</th>
                <th class="px-3 py-2 text-right font-semibold">B</th>
                <th class="px-3 py-2 text-right font-semibold">Diferença</th>
                <th class="px-3 py-2 text-right font-semibold">%</th>
              </tr>
            </thead>
            <tbody class="divide-y">
              <tr v-if="!rows.length">
                <td colspan="6" class="px-3 py-4 text-center text-muted-foreground">Nenhum ingrediente para comparar.</td>
              </tr>
              <tr v-for="(row, index) in rows" :key="`${row.sku || row.name}-${index}`" class="hover:bg-muted/30">
                <td class="px-3 py-2">
                  <p class="font-medium">{{ row.name || row.sku }}</p>
                  <p v-if="row.sku" class="font-mono text-xs text-muted-foreground">{{ row.sku }}</p>
                </td>
                <td class="hidden px-3 py-2 text-muted-foreground sm:table-cell">{{ row.role_label }}</td>
                <td class="px-3 py-2 text-right tabular-nums">{{ row.a_display || "—" }}</td>
                <td class="px-3 py-2 text-right tabular-nums">{{ row.b_display || "—" }}</td>
                <td class="px-3 py-2 text-right tabular-nums font-semibold" :class="toneClass(row.tone)">{{ row.delta_display || "—" }}</td>
                <td class="px-3 py-2 text-right tabular-nums" :class="toneClass(row.tone)">{{ row.delta_pct_display || "—" }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="metrics.length" class="mt-4 max-w-2xl overflow-hidden rounded-lg border">
          <p class="border-b bg-muted/40 px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Métricas</p>
          <table class="w-full text-sm">
            <tbody class="divide-y">
              <tr v-for="metric in metrics" :key="metric.label">
                <td class="px-3 py-2 font-medium">{{ metric.label }}</td>
                <td class="px-3 py-2 text-right tabular-nums">{{ metric.a_display || "—" }}</td>
                <td class="px-3 py-2 text-right tabular-nums">{{ metric.b_display || "—" }}</td>
                <td class="px-3 py-2 text-right tabular-nums font-semibold" :class="toneClass(metric.tone)">{{ metric.delta_display || "—" }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </section>
  </main>
</template>
