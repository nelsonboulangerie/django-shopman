<script setup lang="ts">
// Reagendar uma encomenda: a nova data e, se quiser, a nova janela. As datas e
// as janelas são as que o servidor diz combináveis para ESTES itens (a mesma
// `/pos/schedule/` da venda — dia fechado e feriado já ficam de fora, e a janela
// que o preparo não alcança aparece apagada com o motivo). Quem valida e move o
// resto (despertador, lembrete, estoque, produção) é o orquestrador; aqui só se
// escolhe e se confirma.
import { rescheduleChanged, rescheduleConfirmLabel } from "~/presentation/preorderActions";
import { dateLabel, readinessNote, scheduleLabel, windowLabel, type ScheduleWindow } from "~/presentation/schedule";
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
    if (mine === seq) schedule.value = response;
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
  // A janela escolhida era do dia anterior: no dia novo ela precisa ser
  // escolhida de novo (ou fica "a combinar").
  slot.value = "";
  void load();
}

const today = computed(() => schedule.value?.today || "");
const quickDates = computed(() => (schedule.value?.available_dates ?? []).slice(0, 7));
const windows = computed<ScheduleWindow[]>(() => schedule.value?.windows ?? []);
const note = computed(() => readinessNote(schedule.value?.bottleneck_name || "", schedule.value?.ready_at || ""));
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
        <div class="grid gap-2">
          <span class="text-sm font-medium">Dia</span>
          <div class="flex flex-wrap gap-2">
            <UiButton
              v-for="iso in quickDates"
              :key="iso"
              type="button"
              variant="outline"
              size="sm"
              :class="date === iso ? 'border-primary bg-primary/5 font-semibold' : ''"
              :data-reschedule-date="iso"
              @click="pickDate(iso)"
            >
              {{ dateLabel(iso, today) }}
            </UiButton>
          </div>
          <label class="grid gap-1 text-sm">
            <span class="text-xs text-muted-foreground">Outra data</span>
            <UiInput
              :model-value="date"
              type="date"
              :min="today"
              @update:model-value="pickDate(String($event || ''))"
            />
          </label>
        </div>

        <p v-if="note" class="rounded-md border border-warning/40 bg-warning/5 px-3 py-2 text-xs">{{ note }}</p>

        <div class="grid gap-2">
          <div class="flex items-baseline justify-between gap-2">
            <span class="text-sm font-medium">Horário</span>
            <button
              v-if="slot"
              type="button"
              class="text-xs font-medium text-muted-foreground underline underline-offset-2 hover:text-foreground"
              @click="slot = ''"
            >
              A combinar
            </button>
          </div>
          <div v-if="windows.length" class="grid gap-1.5 sm:grid-cols-2">
            <button
              v-for="window in windows"
              :key="window.ref"
              type="button"
              class="rounded-md border px-3 py-2 text-left text-sm transition"
              :class="[
                window.enabled === false ? 'cursor-not-allowed border-dashed opacity-50' : 'hover:bg-accent',
                slot === window.ref ? 'border-primary bg-primary/5 font-semibold' : 'border-border',
              ]"
              :disabled="window.enabled === false"
              :data-reschedule-slot="window.ref"
              @click="slot = window.ref"
            >
              <span class="block tabular-nums">{{ window.label }}</span>
              <span v-if="window.enabled === false && window.reason" class="block text-xs opacity-80">{{ window.reason }}</span>
            </button>
          </div>
          <p v-else class="rounded-md border border-dashed px-3 py-4 text-center text-sm text-muted-foreground">
            {{ loading ? "Carregando os horários…" : failed ? "Não deu para carregar os horários. Tente de novo." : "Não há horário combinável neste dia." }}
          </p>
        </div>

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
