<script setup lang="ts">
// QUANDO — "é para hoje ou para outro dia, e a que horas?".
//
// Terceira caixa da barra de contexto, irmã de Cliente e Recebimento. Estas três
// perguntas são fatos do PEDIDO: decididas na abertura do atendimento, revistas
// de relance depois.
//
// A data morava dentro do formulário de ENTREGA, e o custo disso era grande e
// silencioso: a retirada agendada não existia. A casa recebe encomenda por
// telefone ("pode separar dois croissants para quinta às 10h?") e o balcão não
// tinha onde escrever isso — o commit apagava a data porque retirada não é
// entrega, e o pedido nascia para hoje.
//
// A tela NÃO decide o que a casa pode prometer. As datas ofertadas já pulam dia
// fechado e feriado; as janelas já vêm anotadas com a prontidão do carrinho. Ela
// mostra o que o servidor resolveu, e diz o porquê.
import type { ScheduleWindow } from "~/presentation/schedule";

const props = defineProps<{
  salesMode?: "counter" | "order";
  open: boolean;
  /** O hoje da LOJA (um tablet com fuso errado agendaria para ontem). */
  today: string;
  deliveryDate?: string;
  fulfillmentType?: "pickup" | "delivery";
  /** A data que vale — a escolhida, ou o hoje que o servidor devolveu. */
  deliveryDateEffective: string;
  deliveryTimeSlot: string;
  /** Datas em que a casa realmente opera, já sem os dias fechados. */
  availableDates: string[];
  /** Janelas do dia escolhido, anotadas para este carrinho. */
  windows: ScheduleWindow[];
  /** O item que segura o pedido, e a que horas ele libera. */
  bottleneckName: string;
  readyAt: string;
  /** Última data que a casa aceita encomendar (Admin: `max_preorder_days`). */
  maxDate: string;
  /** A resposta ainda está a caminho — não é o mesmo que "não há janela". */
  pending: boolean;
  /** A busca FALHOU — terceiro estado, e ele não pode se disfarçar de pendência. */
  failed?: boolean;
}>();

const emit = defineEmits<{
  "update:open": [boolean];
  "update:deliveryDate": [string];
  "update:deliveryTimeSlot": [string];
}>();

const isOpen = computed({
  get: () => props.open,
  set: (value: boolean) => emit("update:open", value),
});

// Na encomenda o dia é explícito (nada marcado até o operador escolher); no
// balcão vale o hoje que o servidor devolveu. O dia, a janela, a prontidão e o
// aviso de horário impossível são o `PosSchedulePicker`, o mesmo do reagendar.
const chosenDate = computed(() => (props.salesMode === "order" ? props.deliveryDate ?? "" : props.deliveryDateEffective));

/**
 * No balcão, "sem agendamento" é UM gesto, não "apagar a data e depois apagar a
 * hora". Na encomenda não existe: ela exige um dia, e o "Hoje" é o primeiro botão.
 */
function backToToday() {
  emit("update:deliveryDate", "");
  emit("update:deliveryTimeSlot", "");
}
</script>

<template>
  <UiDialog v-model:open="isOpen">
    <UiDialogContent class="max-h-[85vh] overflow-y-auto sm:max-w-lg">
      <UiDialogHeader>
        <UiDialogTitle>Quando</UiDialogTitle>
        <UiDialogDescription>{{ fulfillmentType === "delivery" ? "Entrega" : fulfillmentType === "pickup" ? "Retirada" : "Pedido" }}: combine o dia e o horário. Agendamento exige cliente identificado.</UiDialogDescription>
      </UiDialogHeader>

      <!-- HOJE é o padrão, e ele é uma AFIRMAÇÃO: a esmagadora maioria das
           vendas é para agora, e a caixa não pode parecer que falta preencher
           alguma coisa. -->
      <PosSchedulePicker
        :today="today"
        :date="chosenDate"
        :time-slot="deliveryTimeSlot"
        :available-dates="availableDates"
        :max-date="maxDate"
        :windows="windows"
        :bottleneck-name="bottleneckName"
        :ready-at="readyAt"
        :pending="pending"
        :failed="failed"
        day-label="Dia do pedido"
        @update:date="$emit('update:deliveryDate', $event)"
        @update:time-slot="$emit('update:deliveryTimeSlot', $event)"
      />

      <UiDialogFooter class="gap-2 sm:justify-between">
        <UiButton v-if="fulfillmentType !== 'delivery' && salesMode !== 'order'" variant="outline" @click="backToToday">Sem agendamento · levar agora</UiButton>
        <UiButton class="sm:ml-auto" :disabled="salesMode === 'order' && !deliveryDate" @click="isOpen = false">Confirmar dia e horário</UiButton>
      </UiDialogFooter>
    </UiDialogContent>
  </UiDialog>
</template>
