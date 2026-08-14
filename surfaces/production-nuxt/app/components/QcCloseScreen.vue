<script setup lang="ts">
// Tela 2 do quiosque de QC (QC-FORNADA §5). Regras de layout medidas no
// protótipo e honradas aqui:
//   · o numpad é ÂNCORA: da barra do topo até o ⌫ nada muda de altura em
//     nenhum estado (os cartões de motivo têm altura fixa e o sheet cobre por
//     cima, não empurra);
//   · dois campos lado a lado, o da direita apagado até um grau com desconto;
//   · a escala é coluna à direita do numpad, faixa de cor contínua na borda
//     esquerda, vão maior entre numpad e coluna do que entre teclas;
//   · Confirmar sempre ativo: se falta motivo, pergunta um de cada vez no
//     bottom sheet e fecha na resposta.
import type { QCDefectProjection, QCGradeProjection } from "~/types/production";
import {
  applyDiscountGrade,
  buildPartition,
  canSubmit,
  discountGrades,
  finishedTotal,
  fullPriceGrades,
  gradeBandClass,
  initialState,
  lossQty,
  ovenAnchor,
  pendingQuestions,
  typeBackspace,
  typeDigit,
  defaultGradeRef,
  type QcEntryState,
  type QcPartitionGroup,
  type QcQuestion,
} from "~/presentation/qc";

const props = defineProps<{
  title: string;
  subtitle: string;
  planned: number | null;
  /** A fornada real que entrou no forno (declarada no start); null sem start. */
  started: number | null;
  grades: QCGradeProjection[];
  defects: QCDefectProjection[];
  submitting: boolean;
}>();

const emit = defineEmits<{
  back: [];
  confirm: [payload: { quantity: string; partition: QcPartitionGroup[] }];
}>();

// A âncora da aritmética: o que ENTROU no forno (started), com o previsto
// como referência quando divergem — ver `ovenAnchor` (QC-FORNADA §1/§4).
const anchor = ovenAnchor(props.planned, props.started);

const state = ref<QcEntryState>(initialState(anchor.anchor, defaultGradeRef(props.grades)));

const topGrades = computed(() => fullPriceGrades(props.grades));
const lowGrades = computed(() => discountGrades(props.grades));
const activeDefects = computed(() => props.defects);

// ── Campo ativo e entrada tipo calculadora ──────────────────────────────────
const activeField = ref<"full" | "discount">("full");
const fresh = ref(true);
const discountEnabled = computed(() => state.value.discountGradeRef !== "");

function focusField(field: "full" | "discount") {
  if (field === "discount" && !discountEnabled.value) return;
  activeField.value = field;
  fresh.value = true;
}

function onDigit(digit: string) {
  const s = { ...state.value };
  if (activeField.value === "full") {
    s.fullQty = typeDigit(s.fullQty, digit, fresh.value);
    s.fullTouched = true;
  } else {
    s.discountQty = typeDigit(s.discountQty, digit, fresh.value);
  }
  // Editou quantidade: a confirmação de "saiu mais que o previsto" caduca.
  s.overshootConfirmed = false;
  fresh.value = false;
  state.value = s;
}

function onBackspace() {
  const s = { ...state.value };
  if (activeField.value === "full") {
    s.fullQty = typeBackspace(s.fullQty);
    s.fullTouched = true;
  } else {
    s.discountQty = typeBackspace(s.discountQty);
  }
  s.overshootConfirmed = false;
  state.value = s;
}

function onClear() {
  const s = { ...state.value };
  if (activeField.value === "full") {
    s.fullQty = 0;
    s.fullTouched = true;
  } else {
    s.discountQty = 0;
  }
  s.overshootConfirmed = false;
  fresh.value = true;
  state.value = s;
}

// ── Escala ──────────────────────────────────────────────────────────────────
function pickGrade(grade: QCGradeProjection) {
  if (grade.markdown_percent === 0) {
    state.value = { ...state.value, fullGradeRef: grade.ref };
    return;
  }
  state.value = applyDiscountGrade(state.value, grade.ref);
  activeField.value = "discount";
  fresh.value = true;
}

const loss = computed(() => lossQty(state.value));
const total = computed(() => finishedTotal(state.value));

const defectLabel = (ref: string) => props.defects.find((d) => d.ref === ref)?.label ?? "";
const discountIsVetoed = computed(
  () => !!props.defects.find((d) => d.ref === state.value.discountDefectRef)?.forces_discard,
);

// ── Confirmar sempre ativo + sheet de motivos ───────────────────────────────
const sheetQuestion = ref<QcQuestion | null>(null);
const submitAfterAnswer = ref(false);

const sheetTitle = computed(() =>
  sheetQuestion.value === "overshoot"
    ? `Saíram ${total.value} de ${state.value.planned} ${props.started !== null ? "no forno" : "previstas"}?`
    : sheetQuestion.value === "loss_reason"
      ? `O que houve com as ${loss.value} que não saíram?`
      : `O que houve com as ${state.value.discountQty} do sublote?`,
);

function openQuestion(question: QcQuestion, thenSubmit: boolean) {
  sheetQuestion.value = question;
  submitAfterAnswer.value = thenSubmit;
}

function _advanceQuestions() {
  const remaining = pendingQuestions(state.value);
  if (submitAfterAnswer.value && remaining.length) {
    sheetQuestion.value = remaining[0] ?? null;
    return;
  }
  const shouldSubmit = submitAfterAnswer.value;
  sheetQuestion.value = null;
  submitAfterAnswer.value = false;
  if (shouldSubmit) submit();
}

function answerDefect(defect: QCDefectProjection) {
  const s = { ...state.value };
  if (sheetQuestion.value === "loss_reason") s.lossDefectRef = defect.ref;
  else s.discountDefectRef = defect.ref;
  state.value = s;
  _advanceQuestions();
}

/** "Sim, saíram N": o operador assume o acima-do-previsto conscientemente. */
function confirmOvershoot() {
  state.value = { ...state.value, overshootConfirmed: true };
  _advanceQuestions();
}

/** "Corrigir": volta para o campo com entrada fresca — era typo. */
function fixOvershoot() {
  sheetQuestion.value = null;
  submitAfterAnswer.value = false;
  activeField.value = "full";
  fresh.value = true;
}

function onConfirm() {
  if (!canSubmit(state.value)) {
    useSonner.warning(
      "A fornada não tem grupo vendável. Perda total se registra como estorno, com o gestor.",
    );
    return;
  }
  const questions = pendingQuestions(state.value);
  if (questions.length) {
    openQuestion(questions[0]!, true);
    return;
  }
  submit();
}

function submit() {
  emit("confirm", {
    quantity: String(total.value),
    partition: buildPartition(state.value),
  });
}

// ── Teclado físico (numpad USB funciona sem mudança) ────────────────────────
function onKeydown(event: KeyboardEvent) {
  // Digitação num input real (ex.: busca do cabeçalho) não é entrada do numpad.
  const target = event.target as HTMLElement | null;
  if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) return;
  if (event.key === "Escape") {
    sheetQuestion.value = null;
    submitAfterAnswer.value = false;
    return;
  }
  if (sheetQuestion.value) return;
  if (/^[0-9]$/.test(event.key)) {
    onDigit(event.key);
  } else if (event.key === "Backspace") {
    onBackspace();
  } else if (event.key === "Tab") {
    event.preventDefault();
    focusField(activeField.value === "full" ? "discount" : "full");
  } else if (event.key === "Enter") {
    onConfirm();
  }
}
onMounted(() => window.addEventListener("keydown", onKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));

const fieldCard =
  "flex h-24 flex-col justify-between rounded-lg border bg-card p-3 text-left transition";
</script>

<template>
  <div class="mx-auto flex w-full max-w-2xl flex-col px-4 pb-6">
    <!-- Barra do topo: âncora superior, altura fixa. -->
    <header class="flex h-14 shrink-0 items-center justify-between gap-3">
      <button
        type="button"
        class="flex items-center gap-1 rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent"
        @click="emit('back')"
      >
        <Icon name="lucide:chevron-left" class="size-4" />
        Voltar
      </button>
      <div class="min-w-0 text-center">
        <p class="truncate text-base font-semibold">{{ title }}</p>
        <p class="truncate text-xs text-muted-foreground">{{ subtitle }}</p>
      </div>
      <div class="rounded-md border bg-muted/40 px-3 py-2 text-sm tabular-nums">
        <template v-if="started !== null"
          >{{ started }} no forno<template v-if="anchor.planned !== null">
            · {{ anchor.planned }} previstos</template
          ></template
        >
        <template v-else-if="planned !== null">{{ planned }} previstos</template>
        <template v-else>Sem previsto</template>
      </div>
    </header>

    <!-- Dois campos lado a lado, sempre visíveis. -->
    <div class="mt-2 grid shrink-0 grid-cols-2 gap-3">
      <button
        type="button"
        :class="[fieldCard, activeField === 'full' ? 'border-primary ring-2 ring-primary/30' : 'hover:bg-accent']"
        @click="focusField('full')"
      >
        <span class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Qualidade OK</span>
        <span class="text-4xl font-semibold tabular-nums">{{ state.fullQty }}</span>
      </button>
      <button
        type="button"
        :disabled="!discountEnabled"
        :class="[
          fieldCard,
          !discountEnabled
            ? 'opacity-40'
            : activeField === 'discount'
              ? 'border-primary ring-2 ring-primary/30'
              : 'hover:bg-accent',
        ]"
        @click="focusField('discount')"
      >
        <span class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Quantas divergentes</span>
        <span class="text-4xl font-semibold tabular-nums">{{ discountEnabled ? state.discountQty : "" }}</span>
      </button>
    </div>

    <!-- Legenda do numpad: diz em qual campo se está. Altura fixa. -->
    <p class="flex h-8 shrink-0 items-center text-sm text-muted-foreground">
      Digitando em: {{ activeField === "full" ? "qualidade OK" : "quantas divergentes" }}
    </p>

    <!-- Numpad âncora + escala em coluna, vão maior entre os dois blocos. -->
    <div class="grid shrink-0 grid-cols-[minmax(0,1fr)_11rem] gap-8">
      <OperatorNumpad subject="quantidade" @digit="onDigit" @backspace="onBackspace" @clear="onClear" />
      <div class="flex flex-col gap-2" role="group" aria-label="Escala de qualidade">
        <button
          v-for="grade in [...topGrades, ...lowGrades]"
          :key="grade.ref"
          type="button"
          class="relative flex flex-1 items-center justify-between overflow-hidden rounded-md border py-2 pl-4 pr-3 text-left transition hover:bg-accent"
          :class="{
            'border-primary bg-accent ring-2 ring-primary/30':
              grade.ref === state.fullGradeRef || grade.ref === state.discountGradeRef,
          }"
          @click="pickGrade(grade)"
        >
          <span class="absolute inset-y-0 left-0 w-1.5" :class="gradeBandClass(grade, grades)" />
          <span class="font-medium">{{ grade.label }}</span>
          <span v-if="grade.markdown_percent" class="text-xs tabular-nums text-muted-foreground">
            &minus;{{ grade.markdown_percent }}%
          </span>
        </button>
      </div>
    </div>

    <!-- Cartões de motivo: uma linha cada, ABAIXO do numpad (nada o empurra).
         Esquerda: a fornada e o que se perdeu dela. Direita: o sublote.
         Fornada limpa não paga a linha: o Confirmar encosta no numpad. -->
    <div
      v-if="loss > 0 || (discountEnabled && state.discountQty > 0)"
      class="mt-4 grid h-14 shrink-0 grid-cols-2 gap-3"
    >
      <button
        v-if="loss > 0"
        type="button"
        class="flex items-center justify-between rounded-md border border-dashed px-3 text-sm transition hover:bg-accent"
        @click="openQuestion('loss_reason', false)"
      >
        <span class="text-muted-foreground">Perda: <b class="tabular-nums text-foreground">{{ loss }}</b></span>
        <span :class="state.lossDefectRef ? 'font-medium' : 'text-muted-foreground'">
          {{ state.lossDefectRef ? defectLabel(state.lossDefectRef) : "Toque para o motivo" }}
        </span>
      </button>
      <span v-else aria-hidden="true" />
      <button
        v-if="discountEnabled && state.discountQty > 0"
        type="button"
        class="flex items-center justify-between rounded-md border border-dashed px-3 text-sm transition hover:bg-accent"
        @click="openQuestion('discount_reason', false)"
      >
        <span class="text-muted-foreground">Sublote: <b class="tabular-nums text-foreground">{{ state.discountQty }}</b></span>
        <span :class="state.discountDefectRef ? 'font-medium' : 'text-muted-foreground'">
          <template v-if="state.discountDefectRef">
            {{ defectLabel(state.discountDefectRef) }}<template v-if="discountIsVetoed"> · vira descarte</template>
          </template>
          <template v-else>Toque para o motivo</template>
        </span>
      </button>
      <span v-else aria-hidden="true" />
    </div>

    <!-- Confirmar sempre ativo: significa "fechar a fornada". -->
    <button
      type="button"
      class="mt-4 h-14 shrink-0 rounded-lg bg-primary text-lg font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-60"
      :disabled="submitting"
      @click="onConfirm"
    >
      {{ submitting ? "Fechando a fornada…" : "Confirmar" }}
    </button>

    <!-- Motivos em bottom sheet: custam zero espaço até serem necessários. -->
    <UiSheet :open="sheetQuestion !== null" @update:open="(v: boolean) => { if (!v) { sheetQuestion = null; submitAfterAnswer = false; } }">
      <UiSheetContent side="bottom" :title="sheetTitle">
        <template #content>
          <!-- Plausibilidade: acima do previsto pede confirmação consciente —
               o typo (222 no lugar de 22) morre num toque de Corrigir. -->
          <div
            v-if="sheetQuestion === 'overshoot'"
            class="grid grid-cols-2 gap-2 px-4 pb-6"
          >
            <button
              type="button"
              class="rounded-md border px-3 py-4 text-base font-medium transition hover:bg-accent active:translate-y-px"
              @click="fixOvershoot()"
            >
              Corrigir
            </button>
            <button
              type="button"
              class="rounded-md border border-transparent bg-primary px-3 py-4 text-base font-semibold text-primary-foreground transition hover:bg-primary/90 active:translate-y-px"
              @click="confirmOvershoot()"
            >
              Sim, saíram {{ total }}
            </button>
          </div>
          <div v-else class="grid grid-cols-2 gap-2 px-4 pb-6 sm:grid-cols-3">
            <button
              v-for="defect in activeDefects"
              :key="defect.ref"
              type="button"
              class="flex flex-col items-start gap-0.5 rounded-md border bg-card px-3 py-2.5 text-left transition hover:bg-accent"
              @click="answerDefect(defect)"
            >
              <span class="font-medium">{{ defect.label }}</span>
              <span class="text-xs text-muted-foreground">{{ defect.hint }}</span>
            </button>
          </div>
        </template>
      </UiSheetContent>
    </UiSheet>
  </div>
</template>
