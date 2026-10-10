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
      <NuxtButton
        label="Gravar atalhos"
        :loading="settings.saving.value === 'shortcuts'"
        :disabled="!changed || settings.saving.value === 'shortcuts'"
        data-settings-shortcuts-save
        @click="save"
      />
    </template>
    <OperatorScreenState v-if="settings.error.value && !settings.data.value" state="error" what="os atalhos" @retry="settings.refresh()" />
    <OperatorScreenState v-else-if="!settings.data.value" state="loading" what="os atalhos" />
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
            <NuxtButton icon="i-lucide-arrow-up" color="neutral" variant="ghost" square :disabled="index === 0" :aria-label="`Subir ${nameOf(ref)}`" @click="move(index, -1)" />
            <NuxtButton icon="i-lucide-arrow-down" color="neutral" variant="ghost" square :disabled="index === chosen.length - 1" :aria-label="`Descer ${nameOf(ref)}`" @click="move(index, 1)" />
            <NuxtButton icon="i-lucide-x" color="neutral" variant="ghost" square :aria-label="`Tirar ${nameOf(ref)}`" @click="toggle(ref)" />
          </li>
        </ol>
      </section>
      <section class="grid gap-2">
        <h2 class="op-label text-muted-foreground">Coleções</h2>
        <div class="flex flex-wrap gap-2">
          <NuxtButton
            v-for="collection in collections"
            :key="collection.ref"
            color="neutral"
            variant="outline"
            active-color="primary"
            active-variant="solid"
            :active="chosen.includes(collection.ref)"
            :aria-pressed="chosen.includes(collection.ref)"
            :leading-icon="chosen.includes(collection.ref) ? 'i-lucide-check' : undefined"
            :label="collection.name"
            @click="toggle(collection.ref)"
          />
        </div>
      </section>
    </template>
  </PosSettingsShell>
</template>
