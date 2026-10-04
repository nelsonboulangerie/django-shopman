<script setup lang="ts">
// O cabeçalho de toda tela do Marketing (camada visual da suíte, V4-MKT): o
// `OperatorPageHeader` do kit com o que é comum às telas deste app.
//
// - celular e tablet em pé (barra de 56px, prévia `marketing-decisoes4.html`): as ações
//   de polegar da tela; os Avisos (as decisões e a caixa pessoal) são do kit, e o menu
//   do operador mora no "Mais" da barra do polegar (V6-KIT);
// - em toda tela de Ajustes, a segunda linha com Campanhas, Modelos, Ofertas e cupons
//   e Plataformas (`MarketingSettingsNav`), na linha de recortes do cabeçalho.
//
// Os slots são os do kit (`status`, `search`, `actions`, `lead`, `filters`,
// `phone-actions`, `below`) e passam direto.
const props = defineProps<{
  title: string;
  eyebrow?: string;
  /**
   * A tela já pôs no `#phone-actions` o equivalente de polegar dos controles (ex.:
   * Atualizar como ícone): no celular o `#actions` não monta, e a linha extra que ele
   * abriria embaixo do título não existe.
   */
  phoneHidesActions?: boolean;
}>();

const isPhone = useMediaQuery("(max-width: 767.98px)");
// A largura só existe no navegador. Até montar, a tela segue o que o servidor
// desenhou (sem `#actions` quando ele some no celular), e a hidratação não descasa.
const mounted = ref(false);
onMounted(() => {
  mounted.value = true;
});
const showActions = computed(
  () => !props.phoneHidesActions || (mounted.value && !isPhone.value),
);
const { activeSection } = useMarketingSections();
const onSettings = computed(() => activeSection.value === "settings");
</script>

<template>
  <OperatorPageHeader :title="title" :eyebrow="eyebrow">
    <template v-if="$slots.lead" #lead><slot name="lead" /></template>
    <template v-if="$slots.status" #status><slot name="status" /></template>
    <template v-if="$slots.search" #search><slot name="search" /></template>
    <template v-if="$slots.actions && showActions" #actions><slot name="actions" /></template>
    <template v-if="$slots['phone-actions']" #phone-actions><slot name="phone-actions" /></template>
    <template v-if="onSettings || $slots.filters" #filters>
      <MarketingSettingsNav v-if="onSettings" />
      <slot name="filters" />
    </template>
    <template v-if="$slots.below" #below><slot name="below" /></template>
  </OperatorPageHeader>
</template>
