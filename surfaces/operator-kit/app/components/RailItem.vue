<script setup lang="ts">
// Item do rail — a unidade do `OperatorRail`, consistente nos 3 estados: só ícone
// (compacto/colapsado, com tooltip nativo) ou ícone + rótulo (estendido). Vira <a> quando
// recebe `href` (ex.: voltar ao Shopman Apps) ou <button> que emite `activate` (ex.: travar).
// Não conhece o estado do rail — lê `useRailState().showLabels` (verdade compartilhada).
import { computed } from "vue";

const props = defineProps<{
  /** Ícone Lucide, com ou sem o prefixo `lucide:`. */
  icon: string;
  label: string;
  /** Realce de item ativo (nav) — vira `aria-current="page"`. */
  active?: boolean;
  /** Item-link (navega em vez de emitir) — ex.: Shopman Apps. */
  href?: string;
  /** Rótulo acessível quando difere do visível (ex.: "admin — travar"). */
  ariaLabel?: string;
  /** Ação em andamento — gira o ícone e desabilita (ex.: atualizar). */
  busy?: boolean;
  /** Cue de atenção — anel no ícone mesmo no compacto (ex.: abrir caixa). */
  attention?: boolean;
  /**
   * Selo com uma contagem curta (ex.: encomendas de hoje por entregar). Some quando
   * vazio — zero não é selo. No compacto vira pastilha no canto do ícone; no
   * estendido, pílula no fim da linha. O número é visual: quem monta o item diz o
   * que ele conta no `ariaLabel`, porque "3" solto não é frase para leitor de tela.
   */
  badge?: string;
}>();

const emit = defineEmits<{ activate: [] }>();

const { showLabels } = useRailState();
const iconName = computed(() => (props.icon.startsWith("lucide:") ? props.icon : `lucide:${props.icon}`));
const a11yLabel = computed(() => props.ariaLabel || props.label);

function onClick() {
  if (!props.href && !props.busy) emit("activate");
}
</script>

<template>
  <component
    :is="href ? 'a' : 'button'"
    :href="href"
    :type="href ? undefined : 'button'"
    :disabled="href ? undefined : busy"
    :aria-label="a11yLabel"
    :aria-current="active ? 'page' : undefined"
    :title="showLabels ? undefined : a11yLabel"
    class="flex h-11 items-center rounded-md transition disabled:opacity-60"
    :class="[
      showLabels ? 'w-full gap-3 px-2.5' : 'w-11 justify-center',
      active
        ? 'bg-rail-foreground/15 text-rail-foreground'
        : 'text-rail-foreground/80 hover:bg-rail-foreground/10 hover:text-rail-foreground',
    ]"
    @click="onClick"
  >
    <!-- Anel de atenção quando `attention` (e não ativo): sobrevive ao estado compacto. -->
    <span
      v-if="attention && !active"
      class="grid size-7 shrink-0 place-items-center rounded-md ring-2 ring-rail-foreground/45"
    >
      <Icon :name="iconName" class="size-5" />
    </span>
    <span v-else class="relative grid shrink-0 place-items-center">
      <Icon :name="iconName" class="size-5 shrink-0" :class="busy ? 'animate-spin' : ''" />
      <span
        v-if="badge && !showLabels"
        aria-hidden="true"
        class="absolute -top-2 -right-2.5 min-w-4 rounded-full bg-rail-foreground px-1 text-center text-[0.625rem] leading-4 font-semibold tabular-nums text-rail"
        data-rail-badge
      >{{ badge }}</span>
    </span>
    <span v-if="showLabels" class="min-w-0 flex-1 truncate text-left text-sm">{{ label }}</span>
    <span
      v-if="badge && showLabels"
      aria-hidden="true"
      class="shrink-0 rounded-full bg-rail-foreground px-1.5 text-xs leading-5 font-semibold tabular-nums text-rail"
      data-rail-badge
    >{{ badge }}</span>
  </component>
</template>
