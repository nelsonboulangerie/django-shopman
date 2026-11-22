<script setup lang="ts">
// A confirmação de "Cancelar corrida", igual na seção Entregas e no Painel do
// pedido (prévia 6 da revisão das Entregas, aprovada em 16/11/2026).
//
// O primeiro toque (fora daqui) só ARMA esta confirmação; nada vai à TaOn antes
// do segundo. As frases vêm do servidor (`Action.confirmation`):
//  - antes do aceite: a pergunta e um botão que confirma (a central só aceita
//    um motivo nessa fase, então não há o que escolher);
//  - depois do aceite: o motivo é o próprio botão. Cada um já é o `reason_id`
//    que a central recebe.
import type { Action } from "~/generated/ordersContract";
import { cancelConfirmation } from "../../../operator-kit/app/presentation/courierCancel";

const props = defineProps<{ action: Action; busy?: boolean }>();
const emit = defineEmits<{ confirm: [reasonId?: number]; keep: [] }>();

const copy = computed(() => cancelConfirmation(props.action));
const off = computed(() => props.busy || !props.action.enabled);
</script>

<template>
  <div class="flex w-full flex-col gap-2" data-courier-cancel-confirm>
    <template v-if="copy.reasons.length">
      <NuxtAlert
        color="error"
        variant="subtle"
        icon="i-lucide-ban"
        :title="copy.reasonQuestion"
        :description="copy.consequence"
      />
      <NuxtButton
        v-for="reason in copy.reasons"
        :key="reason.id"
        block
        type="button"
        color="error"
        variant="outline"
        :icon="reason.icon"
        :label="reason.label"
        :disabled="off"
        :data-courier-cancel-reason="reason.id"
        @click="emit('confirm', reason.id)"
      />
      <NuxtSeparator />
      <NuxtButton
        block
        type="button"
        color="neutral"
        variant="ghost"
        label="Manter a corrida"
        data-courier-cancel-keep
        @click="emit('keep')"
      />
    </template>
    <NuxtAlert
      v-else
      color="error"
      variant="subtle"
      icon="i-lucide-ban"
      :title="copy.question"
    >
      <template #actions>
        <NuxtButton
          type="button"
          color="error"
          variant="solid"
          :label="copy.confirmLabel"
          :disabled="off"
          :loading="busy"
          data-courier-cancel-go
          @click="emit('confirm')"
        />
        <NuxtButton
          type="button"
          color="error"
          variant="outline"
          label="Manter a corrida"
          data-courier-cancel-keep
          @click="emit('keep')"
        />
      </template>
    </NuxtAlert>
  </div>
</template>
