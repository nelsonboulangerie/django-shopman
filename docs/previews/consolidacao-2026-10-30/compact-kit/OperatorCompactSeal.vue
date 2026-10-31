<script setup lang="ts">
// PRÉVIA (modo compacto). O selo do app com a mesma anatomia do OperatorAppSeal (avatar
// de 36px na cor do app, alvo de 44px; leva à Central) e o chip de conexão no canto
// inferior direito. Cada estado tem forma e glifo próprios (✓ ao vivo, ↻ periódico,
// relógio atrasado, × sem conexão): a cor nunca fala sozinha, e o estado completo vai no
// nome acessível. `tone` ausente = sem chip (tela sem leitura viva).
const props = defineProps<{ tone?: 'live' | 'calm' | 'late' | 'off'; time?: string; to?: string }>();
const config = useRuntimeConfig().public as { operatorHubUrl?: string; operatorPwa?: { identity?: { label: string; icon: string; iconSrc?: string; color: string } } };
const identity = config.operatorPwa?.identity;
const hub = computed(() => props.to ?? config.operatorHubUrl ?? '');
const STATE = {
  live: { icon: 'i-lucide-check', cls: 'bg-success text-inverted', word: 'ao vivo' },
  calm: { icon: 'i-lucide-refresh-cw', cls: 'bg-elevated text-highlighted ring-1 ring-(--ui-border-accented)', word: 'atualização periódica' },
  late: { icon: 'i-lucide-clock', cls: 'bg-warning text-inverted', word: 'leitura atrasada' },
  off: { icon: 'i-lucide-x', cls: 'bg-error text-inverted', word: 'sem conexão' },
} as const;
const state = computed(() => (props.tone ? STATE[props.tone] : null));
const spoken = computed(() => {
  const app = identity?.label || 'Aplicativo';
  const conn = state.value ? ` Conexão: ${state.value.word}${props.time ? `, última leitura ${props.time}` : ''}.` : '';
  return `${app}: abrir a Central.${conn}`;
});
const iconName = computed(() => { const i = identity?.icon || 'layout-grid'; return i.includes(':') ? i : `lucide:${i}`; });
const { attrsFor } = useOperatorAppLink();
const link = computed(() => attrsFor(hub.value));
</script>
<template>
  <NuxtButton :to="hub || undefined" :target="hub ? link.target : undefined" :rel="hub ? link.rel : undefined"
    color="neutral" variant="ghost" square class="relative size-11 shrink-0 justify-center p-0"
    :aria-label="spoken" :title="spoken" data-compact-seal :data-conn="tone">
    <NuxtAvatar :src="identity?.iconSrc || undefined" :icon="iconName" alt="" class="size-9" :style="{ background: identity?.color || 'var(--ui-primary)' }" />
    <span v-if="state" aria-hidden="true" data-conn-chip
      class="absolute bottom-0.5 right-0.5 grid size-4 place-items-center rounded-full ring-2 ring-(--ui-bg)" :class="state.cls">
      <NuxtIcon :name="state.icon" class="size-2.5" />
    </span>
  </NuxtButton>
</template>
