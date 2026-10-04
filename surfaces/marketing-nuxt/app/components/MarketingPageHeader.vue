<script setup lang="ts">
// O cabeçalho de toda tela do Marketing (camada visual da suíte, V4-MKT): o
// `OperatorPageHeader` do kit com o que é comum às telas deste app.
//
// - celular (barra de 56px, prévia `marketing-decisoes4.html`): as ações de polegar da
//   tela, o sino (que abre a fila de decisões) e o menu do operador (tema, giro e
//   Bloquear, que do tablet para cima moram no rail). Montados por JS, não só
//   escondidos por CSS: dois sinos no DOM seriam dois "Decisões" para quem procura
//   pelo nome;
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
const shell = useMarketingShell();
const { activeSection } = useMarketingSections();
const onSettings = computed(() => activeSection.value === "settings");
</script>

<template>
  <OperatorPageHeader :title="title" :eyebrow="eyebrow">
    <template v-if="$slots.lead" #lead><slot name="lead" /></template>
    <template v-if="$slots.status" #status><slot name="status" /></template>
    <template v-if="$slots.search" #search><slot name="search" /></template>
    <template v-if="$slots.actions && showActions" #actions><slot name="actions" /></template>
    <template #phone-actions>
      <slot name="phone-actions" />
      <!-- Só no navegador: a largura não existe no SSR, e montar o sino pelo palpite
           do servidor descasava a hidratação no celular. -->
      <ClientOnly>
        <template v-if="isPhone">
          <MarketingNotificationsBell />
          <OperatorPhoneMenu
            :operator-name="shell?.operatorName.value"
            @lock="shell?.lock()"
          />
        </template>
      </ClientOnly>
    </template>
    <template v-if="onSettings || $slots.filters" #filters>
      <MarketingSettingsNav v-if="onSettings" />
      <slot name="filters" />
    </template>
    <template v-if="$slots.below" #below><slot name="below" /></template>
  </OperatorPageHeader>
</template>
