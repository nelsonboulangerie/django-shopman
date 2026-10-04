<script setup lang="ts">
// PDV › Ajustes › Atalhos de venda (UX-15): as coleções favoritas deste terminal
// (`Terminal.metadata.favorite_collection_refs`). Elas vêm primeiro na fila de chips
// da venda e formam o chip "Favoritos" do toque. A ordem da lista é a dos chips.
useHead({ title: "Atalhos de venda" });

const settings = usePosSettings();
const chosen = ref<string[]>([]);
watch(() => settings.data.value?.shortcuts.favorite_collection_refs, (refs) => {
  chosen.value = [...(refs || [])];
}, { immediate: true });
const collections = computed(() => settings.data.value?.shortcuts.collections || []);
const nameOf = (ref: string) => collections.value.find((c) => c.ref === ref)?.name || ref;
const changed = computed(() => JSON.stringify(chosen.value) !== JSON.stringify(settings.data.value?.shortcuts.favorite_collection_refs || []));
function toggle(ref: string) {
  chosen.value = chosen.value.includes(ref) ? chosen.value.filter((r) => r !== ref) : [...chosen.value, ref];
}
function move(index: number, delta: number) {
  const next = [...chosen.value];
  const target = index + delta;
  if (target < 0 || target >= next.length) return;
  [next[index], next[target]] = [next[target]!, next[index]!];
  chosen.value = next;
}
function save() {
  if (!settings.data.value) return;
  void settings.save(
    "shortcuts",
    { terminal_ref: settings.data.value.terminal_ref, favorite_collection_refs: chosen.value },
    "Atalhos de venda gravados.",
  );
}
</script>

<template>
  <PosSettingsShell title="Atalhos de venda" subtitle="as coleções que abrem a venda">
    <template #actions>
      <UiButton :disabled="!changed || settings.saving.value === 'shortcuts'" data-settings-shortcuts-save @click="save">Gravar atalhos</UiButton>
    </template>
    <div v-if="settings.error.value && !settings.data.value" class="flex flex-wrap items-center gap-3 rounded-xl border border-dashed p-4">
      <p class="min-w-0 flex-1 op-body text-muted-foreground">{{ httpErrorMessage(settings.error.value, "Não deu para ler os atalhos. Confira a conexão e tente de novo.") }}</p>
      <UiButton variant="outline" @click="settings.refresh()">Tentar de novo</UiButton>
    </div>
    <p v-else-if="!settings.data.value" class="op-body text-muted-foreground">Lendo os atalhos…</p>
    <template v-else>
      <p class="op-body text-muted-foreground">
        Valem para <b class="text-foreground">{{ settings.data.value.terminal_label || "este terminal" }}</b>: as favoritas vêm primeiro nos chips da venda e, no tablet, formam o chip "Favoritos".
      </p>
      <section class="grid gap-2 rounded-xl border border-border bg-card p-4">
        <h2 class="op-label font-semibold">Favoritas, na ordem dos chips</h2>
        <p v-if="!chosen.length" class="op-micro text-muted-foreground">Nenhuma ainda. Toque nas coleções abaixo.</p>
        <ol class="grid gap-1.5">
          <li v-for="(ref, index) in chosen" :key="ref" class="flex items-center gap-2 rounded-md bg-secondary px-3 py-1.5" :data-settings-shortcut="ref">
            <Icon name="lucide:star" class="size-4 text-primary" aria-hidden="true" />
            <span class="min-w-0 flex-1 truncate op-label font-semibold">{{ nameOf(ref) }}</span>
            <button type="button" class="grid size-9 place-items-center rounded-md hover:bg-accent disabled:opacity-30" :disabled="index === 0" :aria-label="`Subir ${nameOf(ref)}`" @click="move(index, -1)"><Icon name="lucide:arrow-up" class="size-4" /></button>
            <button type="button" class="grid size-9 place-items-center rounded-md hover:bg-accent disabled:opacity-30" :disabled="index === chosen.length - 1" :aria-label="`Descer ${nameOf(ref)}`" @click="move(index, 1)"><Icon name="lucide:arrow-down" class="size-4" /></button>
            <button type="button" class="grid size-9 place-items-center rounded-md text-muted-foreground hover:bg-accent" :aria-label="`Tirar ${nameOf(ref)}`" @click="toggle(ref)"><Icon name="lucide:x" class="size-4" /></button>
          </li>
        </ol>
      </section>
      <section class="grid gap-2">
        <h2 class="op-label text-muted-foreground">Coleções</h2>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="collection in collections"
            :key="collection.ref"
            type="button"
            class="inline-flex h-11 items-center gap-1.5 rounded-full border px-3.5 op-label transition"
            :class="chosen.includes(collection.ref) ? 'border-primary bg-primary/10 font-semibold' : 'border-border bg-card hover:bg-accent'"
            :aria-pressed="chosen.includes(collection.ref)"
            @click="toggle(collection.ref)"
          >
            <Icon v-if="chosen.includes(collection.ref)" name="lucide:check" class="size-4 text-primary" aria-hidden="true" />
            {{ collection.name }}
          </button>
        </div>
      </section>
    </template>
  </PosSettingsShell>
</template>
