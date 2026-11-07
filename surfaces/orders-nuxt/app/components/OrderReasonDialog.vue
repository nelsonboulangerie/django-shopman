<script setup lang="ts">
// Recusar ou cancelar um pedido no Gestor. O diálogo é o `OperatorReasonDialog` do
// operator-kit, o mesmo do cancelar no PDV; aqui mora só o que é do Gestor:
//   - Marketplace (iFood): o seletor de códigos da lista viva do pedido. O iFood EXIGE
//     um dos códigos dele; a descrição escolhida vira o motivo que o cliente lê.
//   - Recusar e cancelar nos outros canais: a MESMA lista única de motivos do
//     backend (`cancel_reasons` da projeção; beta 06/11, antes a recusa tinha uma
//     lista própria). Escolher é obrigatório; o cliente lê a frase revisada do
//     motivo, e o texto livre é a observação interna.
import type { ReasonChoice } from "../../../operator-kit/app/types/reason";
import type { CancelReasonProjection, CancellationReason } from "~/types/orders";

const props = defineProps<{
  open: boolean;
  mode: "reject" | "cancel";
  loading: boolean;
  reasons: CancellationReason[];
  cancelReasons: CancelReasonProjection[];
  busy: boolean;
  marketplace: boolean;
  error?: string;
  /** Motivo já marcado ao abrir (cancelar o Pix vencido: "Pagamento não confirmado"). */
  initialKey?: string;
  /**
   * O que acontece com o dinheiro ("R$ 5,10 serão estornados no cartão do
   * cliente."), da projeção do pedido. O diálogo falava só do motivo, e o
   * operador cancelava sem saber o destino do dinheiro (beta 06/11, F5).
   */
  moneyEffect?: string;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
  "dirty-change": [value: boolean];
  retry: [];
  confirm: [payload: { reason: string; cancellationCode: string; reasonKey: string }];
}>();

const keyed = computed(() => !props.marketplace && props.cancelReasons.length > 0);

const title = computed(() =>
  props.mode === "reject" ? "Recusar pedido" : "Cancelar pedido",
);
const description = computed(() => {
  const base = props.marketplace
    ? "Escolha o motivo que o iFood exige. Ele é enviado ao iFood."
    : "Escolha o motivo. O cliente recebe o aviso com a frase do motivo.";
  const money = String(props.moneyEffect ?? "").trim();
  return money ? `${money} ${base}` : base;
});
</script>

<template>
  <OperatorReasonDialog
    :open="open"
    :title="title"
    :description="description"
    :confirm-label="mode === 'reject' ? 'Recusar pedido' : 'Cancelar pedido'"
    :required="mode === 'reject' && !keyed"
    :keyed-reasons="keyed ? cancelReasons : []"
    :initial-key="keyed ? (initialKey ?? '') : ''"
    :coded="marketplace"
    :coded-reasons="reasons"
    coded-label="Motivo exigido pelo iFood"
    coded-empty-text="O iFood não oferece motivos de cancelamento neste momento."
    :loading="loading"
    :loading-text="marketplace ? 'Carregando motivos do iFood…' : 'Carregando motivos…'"
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
