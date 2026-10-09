<script setup lang="ts">
// Moldura das telas compostas da rodada 2: o shell REAL da suíte (`OperatorSuiteShell`:
// barra lateral de três estados na mesa, gaveta e barra inferior abaixo de `lg`) com as
// faixas na ordem das regras de precedência:
//   barra primária → toolbar (ou a barra de seleção, que ocupa o lugar dela) →
//   chips dos recortes (só no celular) → aviso da tela → conteúdo → ação flutuante.
// A ação flutua sobre o conteúdo (abaixo de `lg`) e o conteúdo reserva a altura dela no
// fim: o último item nunca fica coberto. A reserva é medida, não adivinhada.
import { useElementSize } from "@vueuse/core";
import { computed, ref, useSlots } from "vue";

import type { OperatorSection } from "../../../operator-kit/app/presentation/appBar";

defineProps<{
  storageKey: string;
  sections: readonly OperatorSection[];
  label: string;
  current: string;
}>();

const slots = useSlots();
const bar = ref<HTMLElement | null>(null);
const { height } = useElementSize(bar);
// 12 px de folga embaixo + 12 px de respiro acima da barra. Antes de medir (servidor e
// primeiro quadro), a reserva conservadora de 10 rem.
const reserve = computed(() => (slots.base ? (height.value ? `${height.value + 24}px` : "10rem") : undefined));
</script>

<template>
  <OperatorSuiteShell :storage-key="storageKey" :sections="sections" :label="label" :current="current">
    <div class="flex min-h-0 flex-1 flex-col bg-default" data-fase2-screen>
      <header class="shrink-0 border-b border-default bg-card" data-fase2-role="primary">
        <slot name="header" />
      </header>
      <div v-if="$slots.toolbar" class="shrink-0 border-b border-default bg-card" data-fase2-role="secondary">
        <slot name="toolbar" />
      </div>
      <div class="relative flex min-h-0 flex-1 flex-col">
        <div class="min-h-0 flex-1 overflow-y-auto lg:pb-4!" :style="{ paddingBottom: reserve }" data-fase2-scroll>
          <slot />
        </div>
        <div
          v-if="$slots.base"
          ref="bar"
          class="absolute inset-x-3 bottom-3 lg:hidden"
          data-fase2-role="base"
        >
          <slot name="base" />
        </div>
      </div>
    </div>
  </OperatorSuiteShell>
</template>
