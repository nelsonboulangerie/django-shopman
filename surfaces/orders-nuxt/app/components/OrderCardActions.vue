<script setup lang="ts">
// O rodapé do cartão do pedido: o próximo gesto (ou o Desfazer da saída tocada), os
// secundários e o ⋮. Um componente só para o cartão inteiro (celular, Fila) e para o
// compacto do Quadro (D, dono 13/11/2026): os gestos não mudam com o desenho.
import type { OrderCardProjection } from "~/types/orders";
import type { Affordance, AffordanceRef, UndoLine } from "~/presentation/board";
import OrderCardMenu from "./OrderCardMenu.vue";

defineProps<{
  card: OrderCardProjection;
  busy?: boolean;
  handoff: UndoLine | null;
  primary: Affordance | null;
  secondary: Affordance[];
  primaryLabel: string;
  waitingFor: string;
  canOpen?: boolean;
  selecting?: boolean;
  selected?: boolean;
}>();
const emit = defineEmits<{
  (e: "action", ref: AffordanceRef): void;
  (e: "toggle-select" | "toggle-assign" | "select-mode"): void;
  (e: "station-recall" | "volumes", value: number): void;
}>();

function nuxtIcon(icon: string): string {
  return icon.startsWith("lucide:")
    ? `i-lucide-${icon.slice("lucide:".length)}`
    : icon;
}
</script>

<template>
  <div class="@container flex items-end gap-2">
    <!-- O Desfazer é o MESMO botão da saída tocada (dono, 09/10/2026): o primário
         sólido, no mesmo lugar e tamanho; muda só o texto, e o fundo esvazia atrás. -->
    <OperatorTimedButton
      v-if="handoff && handoff.canUndo"
      :until="handoff.untilIso"
      :since="handoff.sinceIso || undefined"
      :server-now="card.server_now_iso || undefined"
      label="Desfazer"
      block
      class="min-w-0 flex-1"
      color="primary"
      variant="solid"
      icon="i-lucide-undo-2"
      :disabled="busy"
      :loading="busy"
      data-undo-button
      @click="emit('action', handoff.action)"
    />
    <div
      v-else-if="!handoff"
      class="grid min-w-0 flex-1 gap-2"
      :class="
        primary && secondary.length === 1
          ? '@[22rem]:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]'
          : secondary.length > 1
            ? 'grid-cols-1 @[20rem]:grid-cols-2'
            : 'grid-cols-1'
      "
    >
      <NuxtButton
        v-for="aff in secondary"
        :key="aff.ref"
        block
        class="h-full min-w-0"
        :disabled="busy"
        :loading="busy"
        :color="aff.priority === 'danger' ? 'error' : 'neutral'"
        variant="outline"
        :icon="nuxtIcon(aff.icon)"
        :title="aff.reason || undefined"
        @click="emit('action', aff.ref)"
      >
        <span class="min-w-0 text-center leading-tight">{{
          aff.label
        }}</span>
      </NuxtButton>
      <NuxtButton
        v-if="primary"
        block
        class="min-w-0"
        :class="secondary.length > 1 ? '@[20rem]:col-span-2' : undefined"
        :disabled="busy || primary.disabled"
        :loading="busy"
        :title="
          primary.reason ||
          (primaryLabel !== primary.label ? primary.label : undefined)
        "
        :color="primary.disabled ? 'neutral' : 'primary'"
        :variant="primary.disabled ? 'outline' : 'solid'"
        :icon="primary.disabled ? 'i-lucide-lock' : nuxtIcon(primary.icon)"
        data-card-primary
        @click="!primary.disabled && emit('action', primary.ref)"
      >
        <span class="min-w-0 text-center leading-tight">{{
          primaryLabel
        }}</span>
      </NuxtButton>
      <NuxtAlert
        v-else-if="waitingFor"
        class="min-w-0"
        color="info"
        variant="subtle"
        icon="i-lucide-chef-hat"
        :title="`Aguardando ${waitingFor}`"
        data-card-waiting
      />
    </div>
    <div v-else class="flex-1" />

    <!-- ⋯ do cartão: atender, seleção em lote, voltar à estação, abrir. -->
    <OrderCardMenu
      class="shrink-0"
      :card="card"
      :busy="busy"
      :can-open="canOpen"
      :selecting="selecting"
      :selected="selected"
      @toggle-assign="emit('toggle-assign')"
      @toggle-select="emit('toggle-select')"
      @select-mode="emit('select-mode')"
      @volumes="(count) => emit('volumes', count)"
      @station-recall="(pk) => emit('station-recall', pk)"
    />
  </div>
</template>
