<script setup lang="ts">
// Recusar ou cancelar um pedido no Gestor. O diálogo é o `OperatorReasonDialog` do
// operator-kit, o mesmo do cancelar no PDV; aqui mora só o que é do Gestor:
//   - Marketplace (iFood): o seletor de códigos da lista viva do pedido. O iFood EXIGE
//     um dos códigos dele; a descrição escolhida vira o motivo que o cliente lê.
//   - Outros canais: os motivos prontos da casa (Admin/Unfold), agrupados, mais
//     "Outros" e o texto livre.
// Recusar exige motivo (o cliente é avisado com ele); cancelar pode sair em branco,
// com o texto genérico que a página aplica.
import type { ReasonChoice } from "../../../operator-kit/app/types/reason";
import type { CancellationPresetGroupProjection, CancellationReason } from "~/types/orders";

const props = defineProps<{
  open: boolean;
  mode: "reject" | "cancel";
  loading: boolean;
  reasons: CancellationReason[];
  presets: CancellationPresetGroupProjection[];
  busy: boolean;
  marketplace: boolean;
  error?: string;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  "dirty-change": [value: boolean];
  retry: [];
  confirm: [payload: { reason: string; cancellationCode: string }];
}>();

const title = computed(() => (props.mode === "reject" ? "Recusar pedido" : "Cancelar pedido"));
const description = computed(() =>
  props.marketplace
    ? "Escolha o motivo que o iFood exige. Ele é enviado ao iFood."
    : props.mode === "reject"
      ? "Informe o motivo. O cliente recebe o aviso com ele."
      : "O motivo é enviado ao cliente na notificação de cancelamento.",
);
</script>

<template>
  <OperatorReasonDialog
    :open="open"
    :title="title"
    :description="description"
    :confirm-label="mode === 'reject' ? 'Recusar pedido' : 'Confirmar'"
    :required="mode === 'reject'"
    :presets="presets"
    :coded="marketplace"
    :coded-reasons="reasons"
    coded-label="Motivo exigido pelo iFood"
    coded-empty-text="O iFood não oferece motivos de cancelamento neste momento."
    :loading="loading"
    loading-text="Carregando motivos do iFood…"
    :error="error"
    :busy="busy"
    :placeholder="mode === 'reject' ? 'Motivo da recusa…' : 'Motivo do cancelamento (opcional)…'"
    @update:open="(value: boolean) => emit('update:open', value)"
    @dirty-change="(value: boolean) => emit('dirty-change', value)"
    @retry="emit('retry')"
    @confirm="(choice: ReasonChoice) => emit('confirm', { reason: choice.reason, cancellationCode: choice.code })"
  />
</template>
