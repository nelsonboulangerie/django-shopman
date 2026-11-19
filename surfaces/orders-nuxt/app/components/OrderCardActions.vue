<script setup lang="ts">
// O rodapé do cartão do pedido: o próximo gesto (ou o Desfazer da saída tocada), os
// secundários e o ⋮. Um componente só para o cartão inteiro (celular, Fila) e para o
// compacto do Painel (D, dono 13/11/2026): os gestos não mudam com o desenho.
//
// Botão travado (WP-G06): o secundário respeita o `disabled` do servidor como o
// principal, e o porquê vai ESCRITO sob os botões. O `title` não existe no toque, e o
// tablet do balcão não tem ponteiro para pairar.
import { computed } from "vue";

import type { OrderCardProjection } from "~/types/orders";
import type { Affordance, AffordanceRef, UndoLine } from "~/presentation/board";
import { blockedReasonLines, cardFooter } from "~/presentation/cardBlocks";
import OrderCardMenu from "./OrderCardMenu.vue";

const props = defineProps<{
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

// O avanço travado que só repetiria a pílula do bloqueio não vira botão morto. Sem
// botão nenhum, o lugar deles recebe as pílulas de aviso do cartão (`#lone`): o ⋮ não
// fica sozinho numa linha (#2710).
const footer = computed(() =>
  cardFooter({
    primary: props.primary,
    primaryLabel: props.primaryLabel,
    secondary: props.secondary,
    blockLabel: props.card.advance_block_label,
    blockAnnounced: Boolean(props.card.advance_block_reason),
    handoff: Boolean(props.handoff),
    waitingFor: props.waitingFor,
  }),
);
const shownPrimary = computed(() => footer.value.primary);

const blockedReasons = computed(() =>
  props.handoff
    ? []
    : blockedReasonLines({
        primary: shownPrimary.value,
        primaryLabel: props.primaryLabel,
        secondary: props.secondary,
        blockAnnounced: Boolean(props.card.advance_block_reason),
      }),
);

function nuxtIcon(icon: string): string {
  return icon.startsWith("lucide:")
    ? `i-lucide-${icon.slice("lucide:".length)}`
    : icon;
}
</script>

<template>
  <div class="@container flex flex-col gap-1.5">
    <div class="flex items-end gap-2">
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
        v-else-if="!handoff && !footer.empty"
        class="grid min-w-0 flex-1 gap-2"
        :class="
          shownPrimary && secondary.length === 1
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
          :disabled="busy || aff.disabled"
          :loading="busy"
          :color="aff.priority === 'danger' ? 'error' : 'neutral'"
          variant="outline"
          :icon="aff.disabled ? 'i-lucide-lock' : nuxtIcon(aff.icon)"
          :title="aff.reason || undefined"
          :data-card-secondary="aff.ref"
          @click="!aff.disabled && emit('action', aff.ref)"
        >
          <span class="min-w-0 text-center leading-tight">{{
            aff.label
          }}</span>
        </NuxtButton>
        <NuxtButton
          v-if="shownPrimary"
          block
          class="min-w-0"
          :class="secondary.length > 1 ? '@[20rem]:col-span-2' : undefined"
          :disabled="busy || shownPrimary.disabled"
          :loading="busy"
          :title="
            shownPrimary.reason ||
            (primaryLabel !== shownPrimary.label ? shownPrimary.label : undefined)
          "
          :color="shownPrimary.disabled ? 'neutral' : 'primary'"
          :variant="shownPrimary.disabled ? 'outline' : 'solid'"
          :icon="shownPrimary.disabled ? 'i-lucide-lock' : nuxtIcon(shownPrimary.icon)"
          data-card-primary
          @click="!shownPrimary.disabled && emit('action', shownPrimary.ref)"
        >
          <span class="min-w-0 text-center leading-tight">{{
            primaryLabel
          }}</span>
        </NuxtButton>
        <NuxtAlert
          v-else-if="!primary && waitingFor"
          class="min-w-0"
          color="info"
          variant="subtle"
          icon="i-lucide-chef-hat"
          :title="`Aguardando ${waitingFor}`"
          data-card-waiting
        />
      </div>
      <div v-else class="min-w-0 flex-1" data-card-lone>
        <slot name="lone" />
      </div>

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
    <!-- Por que o botão está travado, escrito: uma linha por motivo. -->
    <p
      v-for="line in blockedReasons"
      :key="line"
      class="text-xs text-muted"
      data-card-blocked-reason
    >
      {{ line }}
    </p>
  </div>
</template>
