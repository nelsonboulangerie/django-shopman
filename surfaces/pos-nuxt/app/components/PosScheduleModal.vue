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
import {
  dateLabel,
  readinessNote,
  selectedWindowConflict,
  type ScheduleWindow,
} from "~/presentation/schedule";

const props = defineProps<{
  open: boolean;
  /** O hoje da LOJA (um tablet com fuso errado agendaria para ontem). */
  today: string;
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

// Os próximos dias viram atalho; o resto fica no seletor de data. Cinco cobre a
// semana de encomenda sem virar uma parede de botões no balcão.
const quickDates = computed(() => props.availableDates.slice(0, 5));

const isToday = computed(() => !props.deliveryDateEffective || props.deliveryDateEffective === props.today);

const note = computed(() => readinessNote(props.bottleneckName, props.readyAt));
const conflict = computed(() => selectedWindowConflict(props.windows, props.deliveryTimeSlot));

// Três estados, três frases. "Sem janela neste dia" é um FATO; "ainda não sei" é
// outra coisa; e "não consegui perguntar" é uma terceira, que estava se passando
// por "carregando" para sempre quando o endpoint errava.
const emptyMessage = computed(() => {
  if (props.pending) return "Carregando os horários…";
  if (props.failed) return "Não deu para carregar os horários. Tente de novo.";
  return "Não há horário combinável neste dia.";
});

/** Voltar para hoje é UM gesto, não "apagar a data e depois apagar a hora". */
function backToToday() {
  emit("update:deliveryDate", "");
  emit("update:deliveryTimeSlot", "");
}

function pickDate(iso: string) {
  emit("update:deliveryDate", iso);
  // A janela escolhida pertencia ao dia ANTERIOR. Mantê-la faria o operador
  // levar "10:00 às 10:30" de quinta para um sábado que fecha às 11h, e a
  // promessa sairia errada sem ninguém ter tocado no horário.
  emit("update:deliveryTimeSlot", "");
}
</script>

<template>
  <UiDialog v-model:open="isOpen">
    <UiDialogContent class="max-h-[85vh] overflow-y-auto sm:max-w-lg">
      <UiDialogHeader>
        <UiDialogTitle>Quando</UiDialogTitle>
        <UiDialogDescription>Para quando o cliente quer o pedido.</UiDialogDescription>
      </UiDialogHeader>

      <div class="grid gap-4">
        <!-- HOJE é o padrão, e ele é uma AFIRMAÇÃO: a esmagadora maioria das
             vendas é para agora, e a caixa não pode parecer que falta preencher
             alguma coisa. -->
        <div class="grid gap-2">
          <span class="text-sm font-medium text-muted-foreground">Dia</span>
          <div class="flex flex-wrap gap-2">
            <UiButton
              v-for="iso in quickDates"
              :key="iso"
              type="button"
              variant="outline"
              size="sm"
              class="h-9 px-3"
              :class="deliveryDateEffective === iso ? 'border-primary bg-primary/5 font-semibold' : ''"
              @click="iso === today ? backToToday() : pickDate(iso)"
            >
              {{ dateLabel(iso, today) }}
            </UiButton>
          </div>
          <label class="grid gap-1 text-sm">
            <span class="text-xs text-muted-foreground">Outra data</span>
            <UiInput
              :model-value="deliveryDateEffective"
              type="date"
              :min="today"
              :max="maxDate"
              @update:model-value="pickDate(String($event || ''))"
            />
          </label>
        </div>

        <!-- O motivo dito UMA vez, no topo, em vez de repetido em dez janelas
             apagadas. É a frase que o operador repete ao cliente. -->
        <p v-if="note" class="rounded-md border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-xs">
          {{ note }}
        </p>

        <div class="grid gap-2">
          <div class="flex items-baseline justify-between gap-2">
            <span class="text-sm font-medium text-muted-foreground">Horário</span>
            <button
              v-if="deliveryTimeSlot"
              type="button"
              class="text-xs font-medium text-muted-foreground underline underline-offset-2 hover:text-foreground"
              @click="$emit('update:deliveryTimeSlot', '')"
            >
              A combinar
            </button>
          </div>

          <!-- A janela impossível APARECE, desabilitada, com o motivo. Sumir com
               ela deixa o operador sem resposta para "e às 9h não dá?", e ele
               acaba prometendo por fora do sistema. -->
          <div v-if="windows.length" class="grid gap-1.5 sm:grid-cols-2">
            <button
              v-for="slot in windows"
              :key="slot.ref"
              type="button"
              class="rounded-md border px-3 py-2 text-left text-sm transition"
              :class="[
                slot.enabled === false
                  ? 'cursor-not-allowed border-dashed opacity-50'
                  : 'hover:bg-accent',
                deliveryTimeSlot === slot.ref ? 'border-primary bg-primary/5 font-semibold' : 'border-border',
              ]"
              :disabled="slot.enabled === false"
              :title="slot.reason || ''"
              @click="$emit('update:deliveryTimeSlot', slot.ref)"
            >
              <span class="block tabular-nums">{{ slot.label }}</span>
              <span v-if="slot.enabled === false && slot.reason" class="block text-xs opacity-80">
                {{ slot.reason }}
              </span>
            </button>
          </div>
          <p v-else class="rounded-md border border-dashed px-3 py-4 text-center text-sm text-muted-foreground">
            {{ emptyMessage }}
          </p>

          <!-- A escolha que virou impossível SOZINHA: o operador marcou 09:00 e
               só depois lançou a baguete. Descobrir isso na tela de pagamento é
               tarde — o cliente já ouviu o horário. -->
          <p v-if="conflict" class="text-xs font-medium text-destructive">{{ conflict }}</p>
        </div>
      </div>

      <UiDialogFooter class="gap-2 sm:justify-between">
        <UiButton v-if="!isToday" variant="outline" @click="backToToday">Voltar para hoje</UiButton>
        <UiButton class="sm:ml-auto" @click="isOpen = false">Concluir</UiButton>
      </UiDialogFooter>
    </UiDialogContent>
  </UiDialog>
</template>
