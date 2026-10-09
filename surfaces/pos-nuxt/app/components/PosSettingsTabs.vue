<script setup lang="ts">
// O andar Ajustes do PDV (prévia v4 `salao-mesas4.html` pino 1): Terminal,
// Impressoras, Maquininhas, Salão, Envio à cozinha e Atalhos de venda. Cada aba lê e
// edita o cadastro que já existe (`services/pos_settings.py`, o Salão em
// `services/seating.py`); a configuração rara continua no Admin.
import { POS_SETTINGS_TABS } from "~/presentation/settingsTabs";

const route = useRoute();
</script>

<template>
  <nav class="-mb-px flex items-end gap-1 overflow-x-auto px-4 no-scrollbar" aria-label="Ajustes do PDV" data-pos-settings-tabs>
    <NuxtLink
      v-for="tab in POS_SETTINGS_TABS"
      :key="tab.to"
      :to="tab.to"
      class="inline-flex h-8 shrink-0 items-center rounded-t-md px-3 op-label whitespace-nowrap transition"
      :class="route.path === tab.to
        ? 'bg-secondary font-semibold shadow-[inset_0_-2px_0_var(--primary)]'
        : 'text-muted-foreground hover:bg-accent hover:text-foreground'"
      :aria-current="route.path === tab.to ? 'page' : undefined"
      :data-pos-settings-tab="tab.key"
    >{{ tab.label }}</NuxtLink>
  </nav>
</template>
