<script setup lang="ts">
// Ajustes da Cozinha (item do pé do rail e da barra do polegar, prévia v4). Mora aqui
// o que é da BANCADA e não do toque de quem passa: a densidade da grade (lembrada
// neste dispositivo) e, num quadro de estação, a data de consulta (o KDS é de hoje;
// outra data é prévia, só leitura e sem som).
import { KDS_DENSITIES } from "~/composables/useKdsDensity";

const open = useKdsSettingsOpen();
const { density, setDensity } = useKdsDensity();
const board = useKdsBoardState();
const route = useRoute();
const router = useRouter();

const onStation = computed(() => board.value.onBoard && board.value.availableDates.length > 0);

function dateLabel(value: string): string {
  const today = board.value.today;
  if (value === today) return "Hoje";
  const base = new Date(`${today}T12:00:00`);
  const date = new Date(`${value}T12:00:00`);
  if (date.getTime() - base.getTime() === 86_400_000) return "Amanhã";
  return date.toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit" });
}

// Trocar a data é só trocar o endereço (o quadro relê pela rota): nada a esperar.
function pickDate(value: string) {
  const query = { ...route.query };
  if (value === board.value.today) delete query.date;
  else query.date = value;
  void router.replace({ path: route.path, query });
  open.value = false;
}
</script>

<template>
  <UiDialog :open="open" @update:open="open = Boolean($event)">
    <UiDialogContent class="flex max-h-[85vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-md" data-kds-settings data-suite="v3">
      <UiDialogTitle class="border-b px-5 py-4 op-title">Ajustes da Cozinha</UiDialogTitle>
      <UiDialogDescription class="sr-only">
        Densidade da grade neste dispositivo e a data operacional da estação.
      </UiDialogDescription>
      <div class="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto p-5">
        <section class="flex flex-col gap-2">
          <h3 class="op-eyebrow text-muted-foreground">Tamanho do ticket</h3>
          <div class="grid grid-cols-3 gap-2" role="radiogroup" aria-label="Tamanho do ticket neste dispositivo">
            <button
              v-for="option in KDS_DENSITIES"
              :key="option.key"
              type="button"
              role="radio"
              :aria-checked="density === option.key"
              class="flex min-h-14 flex-col items-center justify-center gap-1 rounded-lg border px-2 py-2 op-label transition"
              :class="density === option.key ? 'border-primary bg-primary/10 font-semibold' : 'bg-card hover:bg-accent'"
              :data-density="option.key"
              @click="setDensity(option.key)"
            >
              <Icon :name="option.icon" class="size-5" aria-hidden="true" />
              {{ option.label }}
            </button>
          </div>
          <p class="op-micro text-muted-foreground">Lembrado neste dispositivo.</p>
        </section>

        <section v-if="onStation" class="flex flex-col gap-2">
          <h3 class="op-eyebrow text-muted-foreground">Data da estação</h3>
          <div class="flex flex-wrap gap-2">
            <UiFilterChip
              v-for="date in board.availableDates"
              :key="date"
              :active="date === board.serviceDate"
              :aria-pressed="date === board.serviceDate"
              @click="pickDate(date)"
            >
              {{ dateLabel(date) }}
            </UiFilterChip>
          </div>
          <p class="op-micro text-muted-foreground">
            Outra data é só consulta: nada pode ser iniciado ou finalizado, e o som fica desligado.
          </p>
        </section>
      </div>
    </UiDialogContent>
  </UiDialog>
</template>
