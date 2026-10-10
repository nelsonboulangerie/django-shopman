<script setup lang="ts">
// QUANDO a casa cumpre o pedido: o dia, a janela e a prontidão.
//
// Uma peça só para os dois lugares do PDV que perguntam isso: abrir a venda
// (`PosScheduleModal`) e reagendar a encomenda (`PosPreorderRescheduleDialog`).
// Eram duas cópias linha a linha, e já tinham divergido: o reagendar não punha o
// limite de dias da casa e não avisava a janela que ficou impossível. Cada cópia
// era um defeito esperando.
//
// Nasce SEM moldura: é o conteúdo, e cada consumidor põe a moldura que quer
// (diálogo, passo de assistente). Quem busca as janelas continua sendo o
// consumidor; a peça não decide o que a casa pode prometer, só mostra o que o
// servidor resolveu e diz o porquê.
import {
  readinessNote,
  selectedWindowConflict,
  type ScheduleWindow,
} from "~/presentation/schedule";

const props = withDefaults(defineProps<{
  /** O hoje da LOJA. Vazio enquanto a primeira resposta não chegou. */
  today: string;
  /** O dia escolhido (vazio: nenhum ainda). */
  date: string;
  /** A janela escolhida (vazio: a combinar). */
  timeSlot: string;
  /** Datas em que a casa realmente opera, já sem os dias fechados. */
  availableDates: string[];
  /** Última data que a casa aceita encomendar (`lastBookableDate`). */
  maxDate?: string;
  /** Janelas do dia escolhido, anotadas para estes itens. */
  windows: ScheduleWindow[];
  /** O item que segura o pedido, e a que horas ele libera. */
  bottleneckName: string;
  readyAt: string;
  /** A resposta ainda está a caminho: não é o mesmo que "não há janela". */
  pending: boolean;
  /** A busca FALHOU: terceiro estado, e ele não pode se disfarçar de pendência. */
  failed?: boolean;
  /** Nome do grupo de dias para leitor de tela. */
  dayLabel?: string;
}>(), { maxDate: "", failed: false, dayLabel: "Dia" });

const emit = defineEmits<{
  "update:date": [string];
  "update:timeSlot": [string];
}>();

const note = computed(() => readinessNote(props.bottleneckName, props.readyAt));
const conflict = computed(() => selectedWindowConflict(props.windows, props.timeSlot));

// Três estados, três frases. "Sem janela neste dia" é um FATO; "ainda não sei" é
// outra coisa; e "não consegui perguntar" é uma terceira.
const emptyMessage = computed(() => {
  if (props.pending) return "Carregando os horários…";
  if (props.failed) return "Não deu para carregar os horários. Tente de novo.";
  return "Não há horário combinável neste dia.";
});

function pickDate(iso: string) {
  if (iso === props.date) return;
  emit("update:date", iso);
  // A janela escolhida pertencia ao dia ANTERIOR. Mantê-la faria o operador
  // levar "10:00 às 10:30" de quinta para um sábado que fecha às 11h, e a
  // promessa sairia errada sem ninguém ter tocado no horário.
  emit("update:timeSlot", "");
}
</script>

<template>
  <div class="grid gap-4" data-schedule-picker>
    <div class="grid gap-2">
      <span class="text-sm font-medium">Dia</span>
      <!-- A "Escolha rápida de dia" do kit (Tipo 1): Hoje, Amanhã, a próxima data
           em que a casa abre e Outra data. Dia fechado aparece apagado com o
           motivo, e nada passa do limite de dias da casa. -->
      <OperatorDayPicker
        v-if="today"
        :model-value="date"
        :today="today"
        :min="today"
        :max="maxDate || undefined"
        :available-dates="availableDates"
        :label="dayLabel"
        @update:model-value="pickDate"
      />
      <p v-else class="rounded-md border border-dashed px-3 py-4 text-center text-sm text-muted-foreground">
        {{ failed ? "Não deu para carregar os dias. Tente de novo." : "Carregando os dias…" }}
      </p>
    </div>

    <!-- O motivo dito UMA vez, no topo, em vez de repetido em dez janelas
         apagadas. É a frase que o operador repete ao cliente. -->
    <p v-if="note" class="rounded-md border border-warning/40 bg-warning/5 px-3 py-2 text-xs" data-schedule-readiness>
      {{ note }}
    </p>

    <div class="grid gap-2">
      <div class="flex items-baseline justify-between gap-2">
        <span class="text-sm font-medium">Horário</span>
        <NuxtButton
          v-if="timeSlot"
          color="neutral"
          variant="ghost"
          class="px-1 text-xs font-medium text-muted-foreground underline underline-offset-2 hover:text-foreground"
          @click="emit('update:timeSlot', '')"
        >
          A combinar
        </NuxtButton>
      </div>

      <!-- A janela impossível APARECE, desabilitada, com o motivo. Sumir com ela
           deixa o operador sem resposta para "e às 9h não dá?", e ele acaba
           prometendo por fora do sistema. -->
      <div v-if="windows.length" class="grid gap-1.5 sm:grid-cols-2">
        <NuxtButton
          v-for="option in windows"
          :key="option.ref"
          color="neutral"
          variant="ghost"
          class="rounded-md border px-3 py-2 text-left text-sm transition flex-col items-start gap-0 font-normal"
          :class="[
            option.enabled === false ? 'cursor-not-allowed border-dashed opacity-50' : 'hover:bg-accent',
            timeSlot === option.ref ? 'border-primary bg-primary/5 font-semibold' : 'border-border',
          ]"
          :disabled="option.enabled === false"
          :title="option.reason || ''"
          :data-schedule-slot="option.ref"
          @click="emit('update:timeSlot', option.ref)"
        >
          <span class="block tabular-nums">{{ option.label }}</span>
          <span v-if="option.enabled === false && option.reason" class="block text-xs opacity-80">
            {{ option.reason }}
          </span>
        </NuxtButton>
      </div>
      <p v-else class="rounded-md border border-dashed px-3 py-4 text-center text-sm text-muted-foreground">
        {{ emptyMessage }}
      </p>

      <!-- A escolha que virou impossível SOZINHA: na venda, o operador marcou
           09:00 e só depois lançou a baguete; no reagendar, a janela combinada
           não cabe mais no preparo destes itens. Descobrir isso no confirmar é
           tarde: o cliente já ouviu o horário. -->
      <p v-if="conflict" class="text-xs font-medium text-destructive" data-schedule-conflict>{{ conflict }}</p>
    </div>
  </div>
</template>
