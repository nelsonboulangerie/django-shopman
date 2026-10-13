<script setup lang="ts">
// Recusar ou cancelar um pedido no Gestor. O diálogo é o `OperatorReasonDialog` do
// operator-kit, o mesmo do cancelar no PDV; aqui mora só o que é do Gestor:
//   - Marketplace (iFood): o seletor de códigos da lista viva do pedido. O iFood EXIGE
//     um dos códigos dele; a descrição escolhida vira o motivo que o cliente lê.
//   - Cancelar nos outros canais: a lista única de motivos do backend
//     (`cancel_reasons` da projeção). Escolher é obrigatório; o cliente lê a frase
//     revisada do motivo, e o texto livre é a observação interna.
//   - Recusar nos outros canais: os motivos prontos da casa (Admin/Unfold),
//     agrupados, mais "Outros" e o texto livre, que o cliente lê.
import type { ReasonChoice } from "../../../operator-kit/app/types/reason";
import type {
  CancelReasonProjection,
  CancellationPresetGroupProjection,
  CancellationReason,
} from "~/types/orders";

const props = defineProps<{
  open: boolean;
  mode: "reject" | "cancel";
  loading: boolean;
  reasons: CancellationReason[];
  presets: CancellationPresetGroupProjection[];
  cancelReasons: CancelReasonProjection[];
  busy: boolean;
  marketplace: boolean;
  error?: string;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  "dirty-change": [value: boolean];
  retry: [];
  confirm: [payload: { reason: string; cancellationCode: string; reasonKey: string }];
}>();

const keyed = computed(() => props.mode === "cancel" && !props.marketplace);

const title = computed(() =>
  props.mode === "reject" ? "Recusar pedido" : "Cancelar pedido",
);
const description = computed(() =>
  props.marketplace
    ? "Escolha o motivo que o iFood exige. Ele é enviado ao iFood."
    : props.mode === "reject"
      ? "Informe o motivo. O cliente recebe o aviso com ele."
      : "Escolha o motivo. O cliente recebe o aviso com a frase dele.",
);
</script>

<template>
  <OperatorReasonDialog
    :open="open"
    :title="title"
    :description="description"
    :confirm-label="mode === 'reject' ? 'Recusar pedido' : 'Confirmar'"
    :required="mode === 'reject'"
    :presets="keyed ? [] : presets"
    :keyed-reasons="keyed ? cancelReasons : []"
    :coded="marketplace"
    :coded-reasons="reasons"
    coded-label="Motivo exigido pelo iFood"
    coded-empty-text="O iFood não oferece motivos de cancelamento neste momento."
    :loading="loading"
    loading-text="Carregando motivos do iFood…"
    :error="error"
    :busy="busy"
    placeholder="Motivo da recusa…"
    @update:open="(value: boolean) => emit('update:open', value)"
    @dirty-change="(value: boolean) => emit('dirty-change', value)"
    @retry="emit('retry')"
    @confirm="
      (choice: ReasonChoice) =>
        emit('confirm', {
          reason: choice.reason,
          cancellationCode: choice.code,
          reasonKey: choice.key,
        })
    "
  />
</template>
