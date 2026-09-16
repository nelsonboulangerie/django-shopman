<script setup lang="ts">
// Painel de timers da bancada — abre do cabeçalho em qualquer tela de Produção.
// Vários ao mesmo tempo; nome e SKU opcionais; nenhum processo, nenhuma etapa.
// Espelha a UX do timer do forno (numpad de minutos, +1/+5/+10, ``Visto`` só
// silencia, sem pausa — o processo físico não pausa). O que toca aqui é
// lembrete: não conclui fornada, não fecha QC, não trava Continuar.
import type { FloorTimerEntry } from "~/composables/useFloorTimers";
import {
  hasOpenDialogOutside,
  isEditableKeyboardTarget,
  isNativeActionTarget,
  productionContextKeysBlocked,
  resolveQuantityKeyboardShortcut,
} from "~/presentation/keyboard";

const open = defineModel<boolean>("open", { default: false });

const timers = useFloorTimers();

const creating = ref(false);
const minutes = ref("0");
const fresh = ref(true);
const name = ref("");

function resetForm() {
  minutes.value = String(timers.lastMinutes.value ?? 0);
  fresh.value = true;
  name.value = "";
}

// Sem nenhum timer, abrir já é criar: um toque a menos no rush.
watch(open, (value) => {
  if (!value) return;
  resetForm();
  creating.value = timers.entries.value.length === 0;
});

function digit(value: string) {
  const next = fresh.value ? value : `${minutes.value}${value}`;
  minutes.value = String(Math.min(999, Number(next) || 0));
  fresh.value = false;
}
function backspace() {
  minutes.value =
    minutes.value.length <= 1 ? "0" : minutes.value.slice(0, -1);
}
function clearMinutes() {
  minutes.value = "0";
  fresh.value = true;
}
function add(extra: number) {
  minutes.value = String((parseInt(minutes.value, 10) || 0) + extra);
  fresh.value = true;
}
const minutesValid = computed(() => parseInt(minutes.value, 10) >= 1);

function startNew() {
  const value = parseInt(minutes.value, 10);
  if (!(value >= 1)) return;
  timers.create(value, { label: name.value });
  creating.value = false;
}

function modeLabel(entry: FloorTimerEntry): string {
  if (entry.mode === "ringing") return "Tempo esgotado";
  if (entry.mode === "seen") return "Visto";
  return timers.remainingLabel(entry.key);
}

// O teclado físico alimenta o mesmo numpad; só enquanto ESTE diálogo cria um
// timer, e nunca por baixo do lock do operador nem de um campo em edição.
function onKeydown(event: KeyboardEvent) {
  if (
    !open.value ||
    !creating.value ||
    event.repeat ||
    event.isComposing ||
    productionContextKeysBlocked() ||
    hasOpenDialogOutside("[data-production-timer-dialog]") ||
    isEditableKeyboardTarget(event.target)
  ) {
    return;
  }
  const shortcut = resolveQuantityKeyboardShortcut(event);
  if (!shortcut) return;
  if (
    shortcut.kind === "confirm" &&
    event.code !== "NumpadEnter" &&
    isNativeActionTarget(event.target)
  ) {
    return;
  }
  event.preventDefault();
  if (shortcut.kind === "digit") digit(shortcut.digit);
  else if (shortcut.kind === "backspace") backspace();
  else if (shortcut.kind === "clear") clearMinutes();
  else startNew();
}
onMounted(() => window.addEventListener("keydown", onKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));

const PAD_KEY =
  "rounded-md border bg-card py-2.5 text-lg font-semibold tabular-nums transition hover:bg-accent active:translate-y-px";
const PAD_ADD =
  "rounded-md border border-dashed bg-card py-2.5 text-base font-semibold tabular-nums text-muted-foreground transition hover:bg-accent hover:text-foreground active:translate-y-px";
</script>

<template>
  <UiDialog :open="open" @update:open="(v: boolean) => (open = v)">
    <UiDialogContent class="sm:max-w-md" data-production-timer-dialog>
      <UiDialogHeader>
        <UiDialogTitle
          >Timers<template v-if="timers.activeCount.value">
            · {{ timers.activeCount.value }}
            {{ timers.activeCount.value === 1 ? "ativo" : "ativos" }}</template
          ></UiDialogTitle
        >
        <UiDialogDescription
          >Lembretes deste aparelho — fermentação, descanso, o que for. Não
          travam nada.</UiDialogDescription
        >
      </UiDialogHeader>

      <!-- Novo timer: minutos no numpad, nome opcional. Sem tipo de processo. -->
      <div v-if="creating" class="flex flex-col gap-3">
        <div class="grid h-20 place-items-center rounded-md border bg-background">
          <p class="text-4xl font-bold tabular-nums">
            {{ minutes
            }}<span class="ml-1 text-base font-medium text-muted-foreground"
              >min</span
            >
          </p>
        </div>
        <div
          class="grid grid-cols-4 gap-1.5"
          role="group"
          aria-label="Minutos do timer"
        >
          <template
            v-for="row in [
              { digits: [1, 2, 3], add: 1 },
              { digits: [4, 5, 6], add: 5 },
              { digits: [7, 8, 9], add: 10 },
            ]"
            :key="row.add"
          >
            <button
              v-for="value in row.digits"
              :key="value"
              type="button"
              :class="PAD_KEY"
              :aria-label="`Dígito ${value}`"
              @click="digit(String(value))"
            >
              {{ value }}
            </button>
            <button
              type="button"
              :class="PAD_ADD"
              :aria-label="`Somar ${row.add} minutos`"
              @click="add(row.add)"
            >
              +{{ row.add }}
            </button>
          </template>
          <button
            type="button"
            class="rounded-md border bg-card py-2.5 text-sm font-medium transition hover:bg-accent active:translate-y-px"
            aria-label="Limpar minutos"
            aria-keyshortcuts="C Delete"
            @click="clearMinutes()"
          >
            C
          </button>
          <button
            type="button"
            :class="PAD_KEY"
            aria-label="Dígito 0"
            @click="digit('0')"
          >
            0
          </button>
          <button
            type="button"
            class="grid place-items-center rounded-md border bg-card py-2.5 transition hover:bg-accent active:translate-y-px"
            aria-label="Apagar último dígito"
            @click="backspace()"
          >
            <Icon name="lucide:delete" class="size-5" />
          </button>
          <button
            type="button"
            :disabled="!minutesValid"
            aria-keyshortcuts="Enter"
            class="rounded-md border border-transparent bg-primary py-2.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 active:translate-y-px disabled:opacity-50"
            @click="startNew()"
          >
            Iniciar
          </button>
        </div>
        <UiInput
          v-model="name"
          type="text"
          placeholder="Nome (opcional) — ex.: Croissant"
          aria-label="Nome do timer"
          class="min-h-11"
          @keydown.enter.prevent="startNew()"
        />
        <UiButton
          v-if="timers.entries.value.length"
          type="button"
          variant="outline"
          class="min-h-11"
          @click="creating = false"
        >
          Voltar aos timers
        </UiButton>
      </div>

      <!-- Ativos: quem toca fica no topo, oscilando; +N ao vivo; Visto só silencia. -->
      <div v-else class="flex flex-col gap-2">
        <ul class="flex max-h-[55vh] flex-col gap-2 overflow-y-auto">
          <li
            v-for="entry in timers.entries.value"
            :key="entry.key"
            class="flex flex-col gap-2 rounded-md border p-2.5"
            :class="{
              'floor-timer-ringing border-destructive/50': entry.mode === 'ringing',
            }"
          >
            <div class="flex items-center justify-between gap-3">
              <div class="min-w-0">
                <p class="truncate font-semibold">{{ entry.title }}</p>
                <p class="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <span v-if="entry.sku" class="truncate">{{ entry.sku }}</span>
                  <span v-if="entry.kind === 'oven'">Forno</span>
                  <span>{{ entry.minutes }} min</span>
                </p>
              </div>
              <p
                class="shrink-0 text-2xl font-bold tabular-nums"
                :class="
                  entry.mode === 'ringing'
                    ? 'animate-pulse text-destructive motion-reduce:animate-none'
                    : entry.mode === 'seen'
                      ? 'text-muted-foreground'
                      : 'text-foreground'
                "
                role="timer"
                :aria-label="`${entry.title}: ${modeLabel(entry)}`"
              >
                {{ modeLabel(entry) }}
              </p>
            </div>
            <div class="grid grid-cols-4 gap-1.5">
              <button
                v-for="extra in [1, 5]"
                :key="`add-${extra}`"
                type="button"
                class="min-h-11 rounded-md border bg-card text-base font-semibold tabular-nums transition hover:bg-accent active:translate-y-px"
                :aria-label="`Somar ${extra} minutos a ${entry.title}`"
                @click="timers.extend(entry.key, extra)"
              >
                +{{ extra }}
              </button>
              <button
                v-if="entry.mode === 'ringing'"
                type="button"
                class="min-h-11 rounded-md border border-transparent bg-primary text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 active:translate-y-px"
                :aria-label="`Visto: ${entry.title}`"
                @click="timers.seen(entry.key)"
              >
                Visto
              </button>
              <span v-else aria-hidden="true" />
              <button
                type="button"
                class="min-h-11 rounded-md border bg-card text-sm font-medium text-muted-foreground transition hover:bg-accent hover:text-foreground active:translate-y-px"
                :aria-label="`Encerrar ${entry.title}`"
                @click="timers.clear(entry.key)"
              >
                Encerrar
              </button>
            </div>
          </li>
        </ul>
        <UiButton
          type="button"
          class="min-h-11"
          @click="
            resetForm();
            creating = true;
          "
        >
          <Icon name="lucide:plus" class="size-4" /> Novo timer
        </UiButton>
      </div>
    </UiDialogContent>
  </UiDialog>
</template>

<style scoped>
/* A linha inteira oscila em danger quando o alarme toca: visível de longe,
   sem depender de ler o texto (mesma linguagem do card do forno). */
@keyframes floor-timer-ring {
  0%,
  100% {
    background-color: var(--card);
  }
  50% {
    background-color: color-mix(in oklab, var(--destructive) 16%, var(--card));
  }
}
.floor-timer-ringing {
  animation: floor-timer-ring 1.1s ease-in-out infinite;
}
@media (prefers-reduced-motion: reduce) {
  .floor-timer-ringing {
    animation: none;
    box-shadow: inset 0 0 0 3px
      color-mix(in oklab, var(--destructive) 55%, transparent);
  }
}
</style>
