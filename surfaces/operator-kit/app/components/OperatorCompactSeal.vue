<script setup lang="ts">
// O selo da linha do chão (modelo de navegação, 31/10/2026): o app (pequeno) e o lugar
// (grande), com o chip da conexão no canto do ícone. Um toque abre o trocador (seções
// deste app, outros apps, a Central, quem opera). No app sem trocador (a Central, cujo
// shell é `home`: trocar de app não passa por ela, é ela), o toque abre a gaveta, a mesma
// que o ☰ abria antes de a linha do chão tomar o cabeçalho do celular: Início, Bloquear,
// os Avisos e o menu de quem opera.
// Cada estado da conexão tem forma e glifo próprios; o estado completo vai no nome
// acessível. `tone` ausente = sem chip (tela sem leitura viva).
import { computed } from "vue";

import { OPERATOR_APPS } from "../../appIdentity";

const props = defineProps<{ tone?: "live" | "calm" | "late" | "off"; time?: string; place?: string }>();
const config = useRuntimeConfig().public as {
  operatorPwa?: { identity?: { label: string; icon: string; iconSrc?: string; color: string } };
};
const identity = config.operatorPwa?.identity;
const switcherEnabled = useState<boolean>("suite-switcher-enabled", () => false);
const switcherOpen = useState<boolean>("suite-switcher-open", () => false);
const drawerOpen = useState<boolean>("suite-drawer-open", () => false);
const expanded = computed(() => (switcherEnabled.value ? switcherOpen.value : drawerOpen.value));
function onClick() {
  if (switcherEnabled.value) switcherOpen.value = true;
  else drawerOpen.value = true;
}
const STATE = {
  live: { icon: "i-lucide-check", cls: "bg-success text-inverted", word: "ao vivo" },
  calm: { icon: "i-lucide-refresh-cw", cls: "bg-elevated text-highlighted ring-1 ring-(--ui-border-accented)", word: "atualização periódica" },
  late: { icon: "i-lucide-clock", cls: "bg-warning text-inverted", word: "leitura atrasada" },
  off: { icon: "i-lucide-x", cls: "bg-error text-inverted", word: "sem conexão" },
} as const;
const state = computed(() => (props.tone ? STATE[props.tone] : null));
const appLabel = computed(() => {
  const app = Object.values(OPERATOR_APPS).find((candidate) => candidate.label === identity?.label);
  return app?.shortLabel || identity?.label || "Aplicativo";
});
const spoken = computed(() => {
  const where = props.place ? `${appLabel.value}, ${props.place}` : appLabel.value;
  const conn = state.value ? ` Conexão: ${state.value.word}${props.time ? `, última leitura ${props.time}` : ""}.` : "";
  const opens = switcherEnabled.value ? "trocar de seção ou de app" : "abrir o menu";
  return `${where}: ${opens}.${conn}`;
});
const iconName = computed(() => {
  const icon = identity?.icon || "layout-grid";
  return icon.includes(":") ? icon : `lucide:${icon}`;
});
</script>

<template>
  <NuxtButton
    color="neutral"
    variant="ghost"
    class="relative min-h-11 min-w-0 shrink justify-start gap-2 px-1"
    :class="place ? 'flex-1' : 'size-11 shrink-0 justify-center p-0'"
    :aria-label="spoken"
    :title="spoken"
    aria-haspopup="dialog"
    :aria-expanded="expanded"
    data-compact-seal
    :data-conn="tone"
    @click="onClick"
  >
    <span class="relative shrink-0">
      <NuxtAvatar
        :src="identity?.iconSrc || undefined"
        :icon="iconName"
        alt=""
        class="size-9"
        :style="{ background: identity?.color || 'var(--ui-primary)' }"
      />
      <span
        v-if="state"
        aria-hidden="true"
        data-conn-chip
        class="absolute -bottom-0.5 -right-0.5 grid size-4 place-items-center rounded-full ring-2 ring-(--ui-bg)"
        :class="state.cls"
      >
        <NuxtIcon :name="state.icon" class="size-2.5" />
      </span>
    </span>
    <span v-if="place" class="flex min-w-0 flex-col text-left leading-tight">
      <span class="truncate text-xs text-muted">{{ appLabel }}</span>
      <span class="flex min-w-0 items-center gap-0.5 font-semibold text-highlighted">
        <span class="truncate" data-compact-place>{{ place }}</span>
        <NuxtIcon name="i-lucide-chevron-down" class="size-3.5 shrink-0 text-muted" />
      </span>
    </span>
  </NuxtButton>
</template>
