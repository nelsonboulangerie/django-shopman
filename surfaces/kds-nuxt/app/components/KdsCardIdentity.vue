<script setup lang="ts">
// A identidade do card, igual nas estações e na expedição: uma linha de chamada
// discreta (canal + entrega/retirada), o CÓDIGO herói na sua própria linha, e o
// contexto (cliente, adicional, comanda antiga) embaixo dele. À direita, UM
// elemento — o relógio no preparo, o selo de despacho na expedição.
import { lucideIcon } from "~/presentation/board";

defineProps<{
  code: string;
  /** Classe de tamanho do código (escala de densidade). */
  codeClass: string;
  channelIcon?: string;
  overline: string;
}>();
</script>

<template>
  <div class="flex items-start justify-between gap-2.5">
    <div class="min-w-0 flex-1">
      <div
        class="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground"
      >
        <Icon
          v-if="channelIcon"
          :name="`lucide:${lucideIcon(channelIcon)}`"
          class="size-3.5 shrink-0"
        />
        <span class="truncate">{{ overline }}</span>
      </div>
      <p
        class="whitespace-nowrap font-extrabold leading-none tracking-tight tabular-nums"
        :class="codeClass"
      >
        {{ code }}
      </p>
      <slot />
    </div>
    <slot name="aside" />
  </div>
</template>
