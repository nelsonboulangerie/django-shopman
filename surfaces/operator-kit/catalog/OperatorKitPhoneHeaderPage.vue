<script setup lang="ts">
// Bancada da regra do celular (README "Barra do topo no celular" e "Toolbar no
// celular"): uma tela no shell da suíte com MAIS ações e controles do que cabem a
// 320 px, para a trava `tests/catalog/phone-header.spec.ts` medir que o kit decide o
// transbordo (nada se sobrepõe, nada some). Só existe no harness do catálogo.
import { computed, ref } from "vue";

import { periodOfDay, todayIso } from "../app/presentation/dates";
import type { OperatorSection } from "../app/presentation/appBar";
import type { OperatorHeaderAction } from "../app/presentation/pageHeader";

const ROUTE = "/__operator_kit_catalog/phone-header";
const sections: OperatorSection[] = [
  { key: "reading", label: "Leitura", icon: "i-lucide-chart-line", to: ROUTE },
  { key: "history", label: "Histórico", icon: "i-lucide-history", to: `${ROUTE}?s=history` },
  { key: "settings", label: "Ajustes", icon: "i-lucide-settings", to: `${ROUTE}?s=settings` },
];

const chosen = ref<string[]>([]);
function did(label: string) {
  chosen.value = [...chosen.value, label];
}
const actions: OperatorHeaderAction[] = [
  { label: "Copiar link desta leitura", icon: "i-lucide-link", onSelect: () => did("copiar") },
  { label: "Compartilhar esta leitura", icon: "i-lucide-share-2", onSelect: () => did("compartilhar") },
  { label: "Exportar CSV", icon: "i-lucide-download", onSelect: () => did("exportar") },
  { label: "Imprimir", icon: "i-lucide-printer", onSelect: () => did("imprimir") },
  { label: "Trocar o tema", icon: "i-lucide-sun-moon", onSelect: () => did("tema") },
];

const today = todayIso();
const period = ref(periodOfDay("day", today, today));
const channel = ref("all");
const compare = ref("previous");
const CHANNELS = [
  { value: "all", label: "Todos os canais" },
  { value: "shop", label: "Loja online" },
  { value: "counter", label: "Balcão" },
  { value: "ifood", label: "iFood" },
];
const activeFilters = computed(() =>
  channel.value === "all"
    ? []
    : [{
        key: "channel",
        label: `Canal: ${CHANNELS.find((item) => item.value === channel.value)?.label}`,
        remove: () => (channel.value = "all"),
      }],
);
</script>

<template>
  <OperatorAppRoot>
    <OperatorSuiteShell
      storage-key="kit-phone-header"
      :sections="sections"
      label="Seções da bancada"
    >
      <main class="flex min-h-0 flex-1 flex-col" data-phone-header-bench :data-chosen="chosen.join(',')">
        <OperatorPageHeader
          title="Quem compra no balcão?"
          eyebrow="Auditoria do Dono"
          :actions="actions"
          :active-filters="activeFilters"
        >
          <template #status>
            <OperatorLiveStatus tone="live" time="10:00" label="Ao vivo" />
          </template>
          <template #actions>
            <NuxtButton label="Exportar CSV" icon="i-lucide-download" color="neutral" variant="outline" />
            <NuxtButton label="Imprimir" icon="i-lucide-printer" color="neutral" variant="outline" />
          </template>
          <template #filters-primary>
            <OperatorPeriodPicker v-model="period" compact :today="today" :max="today" label="Dia da leitura" />
          </template>
          <template #filters>
            <NuxtFormField label="Comparar com" orientation="horizontal">
              <NuxtSelect v-model="compare" :items="[{ value: 'previous', label: 'Período anterior' }, { value: 'year', label: 'Ano anterior' }]" />
            </NuxtFormField>
            <NuxtFormField label="Canal" orientation="horizontal">
              <NuxtSelect v-model="channel" :items="CHANNELS" data-bench-channel />
            </NuxtFormField>
          </template>
          <template #filters-end>
            <span class="text-xs text-muted-foreground" data-bench-freshness>Última leitura útil: 10:00:00 · há 3 s</span>
          </template>
        </OperatorPageHeader>
        <section class="p-4 text-sm">Conteúdo da leitura.</section>
      </main>
    </OperatorSuiteShell>
  </OperatorAppRoot>
</template>

<style>
@import "./catalog.css";
</style>
