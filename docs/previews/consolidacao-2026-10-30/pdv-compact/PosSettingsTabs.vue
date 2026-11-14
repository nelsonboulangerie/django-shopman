<!-- PRÉVIA C (compacto). Cópia literal de origin/codex/shopman-ux-product-review:docs/previews/navigation-2026-10-29/native/PosSettingsTabs.vue (prévia anterior do PDV): abas roláveis com a aba ativa sempre à vista, no lugar do select do celular. -->
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
// Manter a aba atual visível também quando a rota chega por link direto.
const tabStrip = useTemplateRef<HTMLElement>('tabStrip');
async function revealCurrent() {
  await nextTick();
  tabStrip.value?.querySelector('[role="tab"][aria-selected="true"]')?.scrollIntoView({block:'nearest',inline:'nearest'});
}
onMounted(revealCurrent);
watch(current,revealCurrent,{flush:'post'});
</script>

<template>
  <div ref="tabStrip" class="max-w-full min-w-0 overflow-x-auto overflow-y-hidden" data-preview-settings-navigation>
    <NuxtTabs v-model="current" :items="items" :content="false" variant="link"
      class="min-w-max" :ui="{list:'flex-nowrap',trigger:'shrink-0 whitespace-nowrap'}"
      aria-label="Ajustes do PDV" data-pos-settings-tabs />
  </div>
</template>
