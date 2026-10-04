<script setup lang="ts">
// A segunda linha de Ajustes: Campanhas, Modelos, Ofertas e cupons e Plataformas.
//
// Decisão do dono (03/10/2026, SUITE-UX §6): Ajustes entra por um item só (no pé do
// rail, ou na barra do polegar) e tem as próprias seções aqui, na linha de recortes do
// cabeçalho da tela (`MarketingPageHeader` a monta em toda tela de Ajustes). O desenho
// é o do chip da suíte (`UiFilterChip` sob `data-suite`, `orders-board3.html`): pílula
// de 44px, a ativa com a borda e o fundo claro da cor primária.
//
// ⚠️ A aba ativa vem para dentro da área visível: numa tela estreita a linha rola, e a
// seção em que o operador está não pode ficar escondida fora dela (o defeito foi
// medido aqui antes de virar regra do `OperatorAppBar`).
const { activeSettings, settingsSections } = useMarketingSections();
const nav = ref<HTMLElement | null>(null);

function revealActive() {
  const active = nav.value?.querySelector<HTMLElement>("[aria-current='page']");
  active?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
}
onMounted(revealActive);
watch(activeSettings, () => nextTick(revealActive));
</script>

<template>
  <nav
    ref="nav"
    class="flex gap-1.5 *:shrink-0"
    aria-label="Seções de Ajustes"
    data-marketing-settings-nav
  >
    <NuxtLink
      v-for="section in settingsSections"
      :key="section.key"
      :to="section.to"
      :aria-current="activeSettings === section.key ? 'page' : undefined"
      class="inline-flex min-h-control items-center gap-2 rounded-full border px-3 text-[13px] transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      :class="
        activeSettings === section.key
          ? 'border-primary bg-primary/10 font-semibold text-foreground'
          : 'border-border bg-card font-medium text-foreground hover:bg-accent'
      "
    >
      <Icon :name="section.icon" class="size-4" aria-hidden="true" />
      {{ section.label }}
    </NuxtLink>
  </nav>
</template>
