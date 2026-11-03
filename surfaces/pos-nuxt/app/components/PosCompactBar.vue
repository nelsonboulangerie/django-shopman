<script setup lang="ts">
// A linha do chão do PDV no celular (modelo de navegação, 31/10/2026): a
// `OperatorCompactBar` do kit com o ao vivo do PDV no chip do selo. Sem conexão o PDV
// não tem "ao vivo" (`posLiveStatus` devolve nulo): o chip mostra ×, além da faixa do
// `OfflineBanner`. Props, eventos e encaixes (`lead`, `identity`, `filters`) passam
// direto para o kit; a página que a usa se declara `data-compact-page`.
defineOptions({ inheritAttrs: false });
defineProps<{ title: string }>();
const liveStatus = usePosLiveStatus();
</script>

<template>
  <OperatorCompactBar
    v-bind="$attrs"
    :title="title"
    :tone="liveStatus.view.value?.tone ?? 'off'"
    :time="liveStatus.time.value"
    :conn-label="liveStatus.view.value?.label ?? 'Sem conexão'"
  >
    <template v-for="(_, name) in $slots" #[name]="scope">
      <slot :name="name" v-bind="scope ?? {}" />
    </template>
  </OperatorCompactBar>
</template>
