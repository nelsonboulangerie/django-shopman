<script setup lang="ts">
// PRÉVIA (modelo de navegação, 31/10/2026). O selo da linha do chão: o app (pequeno) e o
// lugar (grande), com o ponto da conexão no canto do ícone. Um toque abre o trocador
// (seções deste app, outros apps, quem opera); ele não leva mais direto à Central.
// Cada estado da conexão tem forma e glifo próprios; o estado completo vai no nome
// acessível. `tone` ausente = sem ponto (tela sem leitura viva).
const props = defineProps<{ tone?: 'live' | 'calm' | 'late' | 'off'; time?: string; to?: string; place?: string }>();
const config = useRuntimeConfig().public as { operatorPwa?: { identity?: { label: string; icon: string; iconSrc?: string; color: string } } };
const identity = config.operatorPwa?.identity;
const switcherOpen = useState<boolean>('suite-switcher-open', () => false);
const STATE = {
  live: { icon: 'i-lucide-check', cls: 'bg-success text-inverted', word: 'ao vivo' },
  calm: { icon: 'i-lucide-refresh-cw', cls: 'bg-elevated text-highlighted ring-1 ring-(--ui-border-accented)', word: 'atualização periódica' },
  late: { icon: 'i-lucide-clock', cls: 'bg-warning text-inverted', word: 'leitura atrasada' },
  off: { icon: 'i-lucide-x', cls: 'bg-error text-inverted', word: 'sem conexão' },
} as const;
const state = computed(() => (props.tone ? STATE[props.tone] : null));
const appLabel = computed(() => identity?.label === 'Gestor de pedidos' ? 'Gestor' : identity?.label || 'Aplicativo');
const spoken = computed(() => {
  const where = props.place ? `${appLabel.value}, ${props.place}` : appLabel.value;
  const conn = state.value ? ` Conexão: ${state.value.word}${props.time ? `, última leitura ${props.time}` : ''}.` : '';
  return `${where}: trocar de seção ou de app.${conn}`;
});
const iconName = computed(() => { const i = identity?.icon || 'layout-grid'; return i.includes(':') ? i : `lucide:${i}`; });
</script>
<template>
  <NuxtButton color="neutral" variant="ghost" class="relative min-h-11 min-w-0 shrink justify-start gap-2 px-1"
    :class="place ? 'flex-1' : 'size-11 shrink-0 justify-center p-0'"
    :aria-label="spoken" :title="spoken" aria-haspopup="dialog" :aria-expanded="switcherOpen"
    data-compact-seal :data-conn="tone" @click="switcherOpen = true">
    <span class="relative shrink-0">
      <NuxtAvatar :src="identity?.iconSrc || undefined" :icon="iconName" alt="" class="size-9" :style="{ background: identity?.color || 'var(--ui-primary)' }" />
      <span v-if="state" aria-hidden="true" data-conn-chip
        class="absolute -bottom-0.5 -right-0.5 grid size-4 place-items-center rounded-full ring-2 ring-(--ui-bg)" :class="state.cls">
        <NuxtIcon :name="state.icon" class="size-2.5" />
      </span>
    </span>
    <span v-if="place" class="flex min-w-0 flex-col text-left leading-tight">
      <span class="truncate text-xs text-muted">{{ appLabel }}</span>
      <span class="flex min-w-0 items-center gap-0.5 font-semibold text-highlighted">
        <span class="truncate">{{ place }}</span>
        <NuxtIcon name="i-lucide-chevron-down" class="size-3.5 shrink-0 text-muted" />
      </span>
    </span>
  </NuxtButton>
</template>
