<script setup lang="ts">
// Novo timer — o caminho do que a fileira de etiquetas não previu: numpad de
// minutos, nome opcional e, se o operador quiser, GUARDAR o que acabou de
// digitar como etiqueta nova. Guardar é uma escolha explícita e a tela diz o
// que ela significa: a etiqueta fica para todo o fournil, não para este tablet.
//
// O numpad é o mesmo gesto do timer do forno (Expedição) e do PDV, e o teclado
// físico alimenta ele — o painel de parede tem teclado numérico e não tem dedo
// sobrando. O atributo ``data-production-timer-dialog`` mantém a exclusão mútua
// com o numpad do forno (ver presentation/keyboard.ts).
import {
  hasOpenDialogOutside,
  isEditableKeyboardTarget,
  isNativeActionTarget,
  productionContextKeysBlocked,
  resolveQuantityKeyboardShortcut,
} from "~/presentation/keyboard";
import { findTagByLabel, normalizeTagLabel } from "~/presentation/timers";
import type { TimerTagProjection } from "~/composables/useTimerTags";

const open = defineModel<boolean>("open", { default: false });
const props = defineProps<{
  /** Sugestão de minutos: o último tempo que este dispositivo disparou. */
  lastMinutes: number | null;
  tags: TimerTagProjection[];
  savingTag: boolean;
}>();
const emit = defineEmits<{
  start: [{ minutes: number; label: string; saveAsTag: boolean }];
}>();

const minutes = ref("0");
const fresh = ref(true);
const name = ref("");
const saveAsTag = ref(false);

watch(open, (value) => {
  if (!value) return;
  minutes.value = String(props.lastMinutes ?? 0);
  fresh.value = true;
  name.value = "";
  saveAsTag.value = false;
});

function digit(value: string) {
  const next = fresh.value ? value : `${minutes.value}${value}`;
  minutes.value = String(Math.min(999, Number(next) || 0));
  fresh.value = false;
}
function backspace() {
  minutes.value = minutes.value.length <= 1 ? "0" : minutes.value.slice(0, -1);
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
const namedValid = computed(() => normalizeTagLabel(name.value).length > 0);
/** Sem nome não há o que guardar: a etiqueta É o nome. */
const canSaveAsTag = computed(() => namedValid.value);
const twin = computed(() =>
  namedValid.value ? findTagByLabel(props.tags, name.value) : null,
);

function start() {
  if (!minutesValid.value) return;
  emit("start", {
    minutes: parseInt(minutes.value, 10),
    label: name.value.trim(),
    saveAsTag: saveAsTag.value && canSaveAsTag.value,
  });
}

function onKeydown(event: KeyboardEvent) {
  if (
    !open.value ||
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
  else start();
}
onMounted(() => window.addEventListener("keydown", onKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));

const PAD_KEY =
  "rounded-md border bg-card py-3 text-xl font-semibold tabular-nums transition hover:bg-accent active:translate-y-px";
const PAD_ADD =
  "rounded-md border border-dashed bg-card py-3 text-base font-semibold tabular-nums text-muted-foreground transition hover:bg-accent hover:text-foreground active:translate-y-px";
</script>

<template>
  <UiDialog :open="open" @update:open="(v: boolean) => (open = v)">
    <UiDialogContent class="sm:max-w-md" data-production-timer-dialog>
      <UiDialogHeader>
        <UiDialogTitle>Novo timer</UiDialogTitle>
        <UiDialogDescription
          >Lembrete deste dispositivo. Não trava fornada, QC nem
          Continuar.</UiDialogDescription
        >
      </UiDialogHeader>

      <div class="flex flex-col gap-3">
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
            class="rounded-md border bg-card py-3 text-sm font-medium transition hover:bg-accent active:translate-y-px"
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
            class="grid place-items-center rounded-md border bg-card py-3 transition hover:bg-accent active:translate-y-px"
            aria-label="Apagar último dígito"
            @click="backspace()"
          >
            <Icon name="lucide:delete" class="size-5" />
          </button>
          <button
            type="button"
            :disabled="!minutesValid"
            aria-keyshortcuts="Enter"
            class="rounded-md border border-transparent bg-primary py-3 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 active:translate-y-px disabled:opacity-50"
            @click="start()"
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
          @keydown.enter.prevent="start()"
        />

        <!-- Guardar como etiqueta: escolha explícita, com a consequência escrita.
             Sem nome não há etiqueta, e nome que já existe não vira irmã. -->
        <div v-if="canSaveAsTag" class="rounded-md border border-dashed p-3">
          <label
            v-if="!twin"
            class="flex min-h-11 items-start gap-2.5 text-sm font-medium"
          >
            <input
              v-model="saveAsTag"
              type="checkbox"
              class="mt-0.5 size-5 shrink-0 accent-primary"
            />
            <span>
              Guardar “{{ name.trim() }}” como etiqueta
              <span class="block text-xs font-normal text-muted-foreground">
                Fica na fileira de disparo rápido para todo o fournil, com
                {{ minutes }} min. O gestor pode ajustar depois.
              </span>
            </span>
          </label>
          <p v-else class="text-sm text-muted-foreground">
            Já existe a etiqueta <strong class="text-foreground">{{ twin.label }}</strong>
            na fileira, com {{ twin.minutes }} min. Este timer vai correr com os
            {{ minutes }} min que você digitou.
          </p>
        </div>

        <p v-if="savingTag" class="text-xs text-muted-foreground">
          Guardando a etiqueta…
        </p>
      </div>
    </UiDialogContent>
  </UiDialog>
</template>
