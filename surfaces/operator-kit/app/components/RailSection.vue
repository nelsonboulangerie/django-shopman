<script setup lang="ts">
// Item do rail da suíte (`OperatorSuiteRail`): ícone em cima, nome embaixo, selo de
// contagem e ponto de atenção. É o `.rail-item` das prévias v3 (`_shared.css`): 64px de
// largura, ícone de 22px, rótulo de 11px, o item ativo acende com o fundo na cor do
// texto do rail. O fundo ativo fica em 68px dentro do rail de 84px, com 8px de
// respiro em cada lado. Altura ≥ 44px (alvo de toque da casa).
//
// Serve às seções do app (link, `to`) e às funções do pé (botão, emite `activate`):
// Avisos, Atalhos, Bloquear. O item inativo fica com o texto cheio, e não a 80% como
// o `.rail-item` da v4: a 80% o rótulo de 10-11px dava 3,8:1 no rail da Produção
// (axe, AA pede 4,5). O ativo acende.
import { computed, resolveComponent } from "vue";

const props = defineProps<{
  icon: string;
  label: string;
  /** Rota (seção do app). Sem ela, o item é um botão e emite `activate`. */
  to?: string;
  active?: boolean;
  /** Contagem no selo; vazia/ausente = sem selo. */
  badge?: string;
  /** Aviso curto ("1 desligado"): vira um ponto no ícone e entra no nome acessível. */
  attention?: string;
  /** Nome acessível quando difere do visível. */
  ariaLabel?: string;
  /** Tecla que leva ao item (anunciada; impressa só com `printShortcut`). */
  shortcut?: string;
  /**
   * Imprime a tecla sob o nome ("Alt1"), como o rail da Produção na prévia v4
   * (`plano-porque4.html`, `.rail-item kbd`). Só com ponteiro fino: no toque não há
   * teclado, e a tecla impressa seria ruído.
   */
  printShortcut?: boolean;
  /** Rótulo de 10px com tracking apertado (`.rail-item.sm` da v4): nomes longos, como "Planejamento". */
  dense?: boolean;
  /**
   * No toque (tablet deitado), o rail é compacto (K4): `shortLabel` no lugar do nome
   * ("Plano" por "Planejamento", `producao-qualidade4.html`); `touchLabel="none"` deixa
   * só o ícone (o PDV no tablet, v3 `depois-pdv-venda-tablet`). O nome cheio continua
   * no nome acessível e no desktop.
   */
  shortLabel?: string;
  touchLabel?: "short" | "none";
}>();

const emit = defineEmits<{ activate: [] }>();

const NuxtLink = resolveComponent("NuxtLink");
const iconName = computed(() => (props.icon.includes(":") ? props.icon : `lucide:${props.icon}`));
const printedShortcut = computed(() => (props.printShortcut && props.shortcut ? props.shortcut.replace(/\+/g, "") : ""));
const a11yLabel = computed(() => {
  const base = props.ariaLabel || props.label;
  return props.attention ? `${base}: ${props.attention}` : base;
});
</script>

<template>
  <component
    :is="to ? NuxtLink : 'button'"
    :to="to"
    :type="to ? undefined : 'button'"
    :aria-current="active ? 'page' : undefined"
    :aria-label="a11yLabel"
    :aria-keyshortcuts="shortcut"
    :title="attention ? `${label}: ${attention}` : undefined"
    :data-active="active || undefined"
    data-rail-section
    class="relative flex w-[68px] flex-col items-center gap-[3px] rounded-[10px] pt-[7px] pb-1.5 text-center leading-[13px] font-semibold whitespace-normal transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rail-foreground"
    :class="[dense ? 'px-0.5 text-[10px] tracking-[-0.3px]' : 'px-1 text-[11px]', active
      ? 'bg-rail-foreground text-rail shadow-[0_1px_2px_rgb(0_0_0/.18)] dark:text-background'
      : 'text-rail-foreground hover:bg-rail-foreground/10']"
    @click="to ? undefined : emit('activate')"
  >
    <slot name="icon">
      <Icon :name="iconName" class="size-[22px]" aria-hidden="true" />
    </slot>
    <!-- Sem quebra no meio da palavra (prévia `.rail-item`): "Encomendas" passa 4px dos
         64px e fica centrada, em vez de virar "Encomenda / s". -->
    <template v-if="touchLabel === 'none'">
      <span class="pointer-coarse:sr-only" :class="dense ? 'whitespace-nowrap' : ''">{{ label }}</span>
    </template>
    <template v-else-if="shortLabel && shortLabel !== label">
      <span class="hidden pointer-coarse:inline" aria-hidden="true" data-rail-short>{{ shortLabel }}</span>
      <span class="pointer-coarse:hidden" :class="dense ? 'whitespace-nowrap' : ''">{{ label }}</span>
    </template>
    <span v-else :class="dense ? 'whitespace-nowrap' : ''">{{ label }}</span>
    <kbd
      v-if="printedShortcut"
      class="hidden font-mono text-[9.5px] leading-none font-semibold tracking-normal pointer-fine:block"
      aria-hidden="true"
      data-rail-shortcut
    >{{ printedShortcut }}</kbd>
    <span
      v-if="badge"
      aria-hidden="true"
      class="absolute top-0.5 right-1.5 h-[18px] min-w-[18px] rounded-full bg-suite-badge px-[5px] text-[11px] leading-[18px] font-bold tabular-nums text-suite-badge-foreground"
      data-rail-badge
    >{{ badge }}</span>
    <span
      v-else-if="attention"
      aria-hidden="true"
      class="absolute top-1.5 right-[17px] size-[9px] rounded-full bg-suite-badge ring-2 ring-rail"
      data-rail-attention
    />
  </component>
</template>
