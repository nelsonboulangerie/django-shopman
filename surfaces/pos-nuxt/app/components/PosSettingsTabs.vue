<script setup lang="ts">
// O andar Ajustes do PDV (prévia v4 `salao-mesas4.html` pino 1): Terminal,
// Impressoras, Maquininhas, Salão, Envio à cozinha e Atalhos de venda. Cada aba lê e
// edita o cadastro que já existe (`services/pos_settings.py`, o Salão em
// `services/seating.py`); a configuração rara continua no Admin.
//
// Sub-seção da suíte (WP-FASE2 §5): mora na toolbar do cabeçalho (`#filters-primary`),
// e uma sub-seção muda a URL. Do `sm` para cima, as abas (`NuxtTabs`, variante `link`);
// no celular, com mais de 3 opções, a lista de escolha (`NuxtSelect`). As duas vão no
// HTML do servidor e o CSS mostra a certa (a régua do kit responde "mesa" até montar).
import { POS_SETTINGS_TABS } from "~/presentation/settingsTabs";

const route = useRoute();
const items = POS_SETTINGS_TABS.map((tab) => ({ label: tab.label, value: tab.to }));
const current = computed({
  get: () => POS_SETTINGS_TABS.find((tab) => route.path.startsWith(tab.to))?.to ?? POS_SETTINGS_TABS[0].to,
  set: (to: string) => {
    if (to && to !== route.path) void navigateTo(to);
  },
});
</script>

<template>
  <NuxtTabs
    v-model="current"
    :items="items"
    :content="false"
    variant="link"
    class="max-sm:hidden"
    aria-label="Ajustes do PDV"
    data-pos-settings-tabs
  />
  <NuxtSelect
    v-model="current"
    :items="items"
    class="w-56 sm:hidden"
    aria-label="Ajustes do PDV"
    data-pos-settings-select
  />
</template>
