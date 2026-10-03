<script setup lang="ts">
// Reagendar uma encomenda: a nova data e, se quiser, a nova janela. As datas e
// as janelas são as que o servidor diz combináveis para ESTES itens (a mesma
// `/pos/schedule/` da venda — dia fechado e feriado já ficam de fora, e a janela
// que o preparo não alcança aparece apagada com o motivo). Quem valida e move o
// resto (despertador, lembrete, estoque, produção) é o orquestrador; aqui só se
// escolhe e se confirma.
import { rescheduleChanged, rescheduleConfirmLabel } from "~/presentation/preorderActions";
import { lastBookableDate, scheduleLabel, windowLabel, type ScheduleWindow } from "~/presentation/schedule";
import type { POSScheduleResponse } from "~/types/pos";

const props = defineProps<{
  open: boolean;
  customerName: string;
  /** A data e a janela combinadas hoje. */
  currentDate: string;
  currentSlot: string;
  /** Os itens da encomenda: a janela oferecível depende deles. */
  skus: string[];
  busy?: boolean;
}>();

const emit = defineEmits<{
  "update:open": [boolean];
  confirm: [{ date: string; slot: string; reason: string }];
}>();

const apiPath = useApiPath();
const date = ref(props.currentDate);
const slot = ref(props.currentSlot);
const reason = ref("");
const schedule = ref<POSScheduleResponse | null>(null);
const loading = ref(false);
const failed = ref(false);
const storeToday = ref("");
let seq = 0;

async function load() {
  const mine = ++seq;
  loading.value = true;
  failed.value = false;
  try {
    const query = new URLSearchParams();
    if (date.value) query.set("date", date.value);
    if (props.skus.length) query.set("skus", props.skus.join(","));
    const response = await $fetch<POSScheduleResponse>(apiPath(`/api/v1/backstage/pos/schedule/?${query.toString()}`), {
      method: "GET", credentials: "include",
    });
    if (mine === seq) {
      schedule.value = response;
      if (response.today) storeToday.value = response.today;
    }
  } catch {
    if (mine === seq) {
      schedule.value = null;
      failed.value = true;
    }
  } finally {
    if (mine === seq) loading.value = false;
  }
}

watch(() => props.open, (open) => {
  if (!open) return;
  date.value = props.currentDate;
  slot.value = props.currentSlot;
  reason.value = "";
  void load();
});

function pickDate(iso: string) {
  if (!iso || iso === date.value) return;
  date.value = iso;
  // A janela do dia anterior já foi limpa pelo `PosSchedulePicker`: no dia novo
  // ela precisa ser escolhida de novo (ou fica "a combinar").
  void load();
}

// O hoje da loja sobrevive a uma busca que falhou: os dias continuam escolhíveis.
const today = computed(() => schedule.value?.today || storeToday.value);
const availableDates = computed(() => schedule.value?.available_dates ?? []);
// O limite de dias da casa sai da MESMA resposta que a venda lê: a última data
// ofertada. Sem ele, o operador escolhia um dia além do limite e só descobria
// no confirmar, quando o servidor recusava.
const maxDate = computed(() => lastBookableDate(availableDates.value));
const windows = computed<ScheduleWindow[]>(() => schedule.value?.windows ?? []);
const changed = computed(() => rescheduleChanged({ date: props.currentDate, slot: props.currentSlot }, { date: date.value, slot: slot.value }));
const target = computed(() => (changed.value ? scheduleLabel(date.value, windowLabel(windows.value, slot.value), today.value) : ""));
const currentLabel = computed(() => scheduleLabel(props.currentDate, windowLabel([], props.currentSlot), today.value));

function confirm() {
  if (props.busy || !changed.value) return;
  emit("confirm", { date: date.value, slot: slot.value, reason: reason.value.trim() });
}
</script>

<template>
  <UiDialog :open="open" @update:open="(value) => emit('update:open', value)">
    <UiDialogContent class="max-h-[85vh] overflow-y-auto sm:max-w-lg" data-preorder-reschedule-dialog>
      <UiDialogHeader>
        <UiDialogTitle>Reagendar a encomenda de {{ customerName }}</UiDialogTitle>
        <UiDialogDescription>Combinado hoje: {{ currentLabel }}. Escolha o novo dia e, se quiser, o horário.</UiDialogDescription>
      </UiDialogHeader>

      <form class="grid gap-4" @submit.prevent="confirm">
        <!-- O mesmo seletor da venda: o limite de dias da casa, a janela
             impossível apagada com o motivo e o aviso quando a janela combinada
             não cabe mais no preparo destes itens. -->
        <PosSchedulePicker
          :today="today"
          :date="date"
          :time-slot="slot"
          :available-dates="availableDates"
          :max-date="maxDate"
          :windows="windows"
          :bottleneck-name="schedule?.bottleneck_name || ''"
          :ready-at="schedule?.ready_at || ''"
          :pending="loading"
          :failed="failed"
          day-label="Novo dia da encomenda"
          @update:date="pickDate"
          @update:time-slot="slot = $event"
        />

        <label class="grid gap-1.5">
          <span class="text-sm font-medium">Motivo (opcional)</span>
          <UiInput v-model="reason" autocomplete="off" class="h-11 text-base" :maxlength="500" data-preorder-reschedule-reason />
        </label>

        <UiDialogFooter>
          <UiButton type="button" variant="outline" @click="emit('update:open', false)">Voltar</UiButton>
          <UiButton type="submit" :disabled="busy || !changed" :loading="busy" data-preorder-reschedule-confirm>
            {{ rescheduleConfirmLabel(target) }}
          </UiButton>
        </UiDialogFooter>
      </form>
    </UiDialogContent>
  </UiDialog>
</template>
