<script setup lang="ts">
// Fechamento de uma única fornada. Os quatro botões são buckets de qualidade
// disjuntos; o grau padrão recebe automaticamente o saldo que não foi lançado
// nos demais graus nem em Perda.
import type { QCDefectProjection, QCGradeProjection } from "~/types/production";
import {
  defaultGradeRef,
  gradeBandClass,
  isLowerQualityGrade,
  ovenAnchor,
  typeBackspace,
  typeDigit,
  type QcPartitionGroup,
} from "~/presentation/qc";

const props = withDefaults(
  defineProps<{
    title: string;
    subtitle: string;
    planned: number | null;
    /** A fornada real que entrou no forno (declarada no start); null sem start. */
    started: number | null;
    grades: QCGradeProjection[];
    defects: QCDefectProjection[];
    submitting: boolean;
    mode?: "close" | "correct";
    initialPartition?: QcPartitionGroup[];
  }>(),
  {
    mode: "close",
    initialPartition: () => [],
  },
);

const emit = defineEmits<{
  back: [];
  confirm: [
    payload: {
      quantity: string;
      partition: QcPartitionGroup[];
      yield_deviation_confirmed: boolean;
      yield_deviation_reason: string;
      reason: string;
    },
  ];
}>();

type QuantityTarget = { kind: "grade"; gradeRef: string } | { kind: "loss" };
type SheetQuestion =
  | { kind: "overshoot" }
  | { kind: "grade_reason"; gradeRef: string }
  | { kind: "loss_reason" };

function quantityOf(group: QcPartitionGroup): number {
  const quantity = Number(group.quantity);
  return Number.isFinite(quantity) && quantity > 0 ? quantity : 0;
}

const correctionTotal = props.initialPartition.reduce(
  (total, group) => total + quantityOf(group),
  0,
);
const correctionLoss = props.initialPartition
  .filter((group) => group.loss)
  .reduce((total, group) => total + quantityOf(group), 0);
const anchor =
  props.mode === "correct"
    ? { anchor: correctionTotal }
    : ovenAnchor(props.planned, props.started);
const orderedGrades = computed(() =>
  [...props.grades].sort((left, right) => right.rank - left.rank),
);
const defaultRef = computed(() => defaultGradeRef(props.grades));

// Chaves por ref tornam impossível repetir um grau no payload.
const gradeQuantities = ref<Record<string, number>>(
  Object.fromEntries(
    props.initialPartition
      .filter((group) => !group.loss && group.quality_grade_ref)
      .map((group) => [group.quality_grade_ref!, quantityOf(group)]),
  ),
);
const gradeDefectRefs = ref<Record<string, string>>(
  Object.fromEntries(
    props.initialPartition
      .filter(
        (group) =>
          !group.loss && group.quality_grade_ref && group.quality_defect_ref,
      )
      .map((group) => [group.quality_grade_ref!, group.quality_defect_ref!]),
  ),
);
const lossQuantity = ref(props.mode === "correct" ? correctionLoss : 0);
const lossDefectRef = ref(
  props.initialPartition.find((group) => group.loss)?.quality_defect_ref ?? "",
);
const overshootConfirmed = ref(false);
const overshootReason = ref("");
const auditReason = ref("");

// Com âncora, Normal é saldo e não exige digitação. Sem âncora, o padrão é um
// bucket editável como os demais para que uma fornada avulsa possa ser fechada.
const activeTarget = ref<QuantityTarget | null>(
  anchor.anchor === null && defaultRef.value
    ? { kind: "grade", gradeRef: defaultRef.value }
    : null,
);
const fresh = ref(true);

function explicitGradeQuantity(gradeRef: string): number {
  return gradeQuantities.value[gradeRef] ?? 0;
}

const explicitTotal = computed(() =>
  orderedGrades.value
    .filter((grade) => grade.ref !== defaultRef.value)
    .reduce((total, grade) => total + explicitGradeQuantity(grade.ref), 0),
);

const defaultQuantity = computed(() => {
  if (!defaultRef.value) return 0;
  if (anchor.anchor === null) return explicitGradeQuantity(defaultRef.value);
  return Math.max(0, anchor.anchor - explicitTotal.value - lossQuantity.value);
});

function gradeQuantity(gradeRef: string): number {
  return gradeRef === defaultRef.value
    ? defaultQuantity.value
    : explicitGradeQuantity(gradeRef);
}

const finishedTotal = computed(() =>
  orderedGrades.value.reduce(
    (total, grade) => total + gradeQuantity(grade.ref),
    0,
  ),
);
const total = computed(() => finishedTotal.value + lossQuantity.value);
const overshootQuantity = computed(() =>
  anchor.anchor === null ? 0 : Math.max(0, total.value - anchor.anchor),
);

const activeGrade = computed(() => {
  const target = activeTarget.value;
  if (target?.kind !== "grade") return null;
  return props.grades.find((grade) => grade.ref === target.gradeRef) ?? null;
});
const activeLabel = computed(() => {
  if (activeTarget.value?.kind === "loss") return "Perda";
  if (activeGrade.value) return activeGrade.value.label;
  const grade = props.grades.find((item) => item.ref === defaultRef.value);
  return grade ? `${grade.label} · saldo automático` : "Escolha um grau";
});
const activeQuantity = computed(() => {
  if (activeTarget.value?.kind === "loss") return lossQuantity.value;
  if (activeGrade.value) return gradeQuantity(activeGrade.value.ref);
  return defaultQuantity.value;
});

function isActiveGrade(gradeRef: string): boolean {
  return (
    activeTarget.value?.kind === "grade" &&
    activeTarget.value.gradeRef === gradeRef
  );
}

function resetOvershootConfirmation() {
  overshootConfirmed.value = false;
  overshootReason.value = "";
}

function setTargetQuantity(quantity: number) {
  const target = activeTarget.value;
  if (!target) return;
  if (target.kind === "loss") {
    lossQuantity.value = quantity;
    if (quantity === 0) lossDefectRef.value = "";
  } else {
    let nextQuantity = quantity;
    if (props.mode === "correct" && target.gradeRef !== defaultRef.value) {
      const otherExplicit = orderedGrades.value
        .filter(
          (grade) =>
            grade.ref !== defaultRef.value && grade.ref !== target.gradeRef,
        )
        .reduce((total, grade) => total + explicitGradeQuantity(grade.ref), 0);
      nextQuantity = Math.min(
        quantity,
        Math.max(0, correctionTotal - correctionLoss - otherExplicit),
      );
    }
    gradeQuantities.value = {
      ...gradeQuantities.value,
      [target.gradeRef]: nextQuantity,
    };
    if (nextQuantity === 0) {
      gradeDefectRefs.value = {
        ...gradeDefectRefs.value,
        [target.gradeRef]: "",
      };
    }
  }
  resetOvershootConfirmation();
}

function onDigit(digit: string) {
  if (!activeTarget.value) return;
  setTargetQuantity(typeDigit(activeQuantity.value, digit, fresh.value));
  fresh.value = false;
}

function onBackspace() {
  if (!activeTarget.value) return;
  setTargetQuantity(typeBackspace(activeQuantity.value));
}

function onClear() {
  if (!activeTarget.value) return;
  setTargetQuantity(0);
  fresh.value = true;
}

function pickGrade(grade: QCGradeProjection) {
  if (grade.ref === defaultRef.value && anchor.anchor !== null) {
    // Normal continua sendo o próprio botão/grau, mas sua quantidade é o
    // saldo: não há um segundo input capaz de duplicá-la.
    activeTarget.value = null;
  } else {
    activeTarget.value = { kind: "grade", gradeRef: grade.ref };
  }
  fresh.value = true;
}

function pickLoss() {
  if (props.mode === "correct") {
    if (lossQuantity.value > 0) {
      openQuestion({ kind: "loss_reason" }, false);
    }
    return;
  }
  activeTarget.value = { kind: "loss" };
  fresh.value = true;
}

function defectLabel(ref: string): string {
  return props.defects.find((defect) => defect.ref === ref)?.label ?? "";
}

function gradeNeedsReason(grade: QCGradeProjection): boolean {
  return isLowerQualityGrade(grade.ref) && gradeQuantity(grade.ref) > 0;
}

function pendingQuestions(): SheetQuestion[] {
  const questions: SheetQuestion[] = [];
  if (
    overshootQuantity.value > 0 &&
    (!overshootConfirmed.value || !overshootReason.value.trim())
  ) {
    questions.push({ kind: "overshoot" });
  }
  for (const grade of orderedGrades.value) {
    if (gradeNeedsReason(grade) && !gradeDefectRefs.value[grade.ref]) {
      questions.push({ kind: "grade_reason", gradeRef: grade.ref });
    }
  }
  if (lossQuantity.value > 0 && !lossDefectRef.value) {
    questions.push({ kind: "loss_reason" });
  }
  return questions;
}

function buildPartition(): QcPartitionGroup[] {
  const groups: QcPartitionGroup[] = [];
  for (const grade of orderedGrades.value) {
    const quantity = gradeQuantity(grade.ref);
    if (quantity <= 0) continue;
    const group: QcPartitionGroup = {
      quantity: String(quantity),
      quality_grade_ref: grade.ref,
    };
    if (isLowerQualityGrade(grade.ref)) {
      group.quality_defect_ref = gradeDefectRefs.value[grade.ref];
    }
    groups.push(group);
  }
  if (lossQuantity.value > 0) {
    groups.push({
      quantity: String(lossQuantity.value),
      quality_defect_ref: lossDefectRef.value,
      loss: true,
    });
  }
  return groups;
}

// Confirmar pergunta apenas o que falta, uma resposta principal por bucket.
const sheetQuestion = ref<SheetQuestion | null>(null);
const submitAfterAnswer = ref(false);
const questionGrade = computed(() => {
  const question = sheetQuestion.value;
  if (question?.kind !== "grade_reason") return null;
  return props.grades.find((grade) => grade.ref === question.gradeRef) ?? null;
});
const activeDefects = computed(() =>
  sheetQuestion.value?.kind === "grade_reason"
    ? props.defects.filter((defect) => !defect.forces_discard)
    : props.defects,
);
const correctionReasonGrades = computed(() =>
  props.mode === "correct"
    ? orderedGrades.value.filter((grade) => gradeNeedsReason(grade))
    : [],
);
const sheetTitle = computed(() => {
  if (sheetQuestion.value?.kind === "overshoot") {
    return `Foram contabilizadas ${total.value} de ${anchor.anchor} unidades?`;
  }
  if (sheetQuestion.value?.kind === "loss_reason") {
    return `Qual o motivo principal da perda de ${lossQuantity.value}?`;
  }
  return questionGrade.value
    ? `Qual o motivo principal de ${gradeQuantity(questionGrade.value.ref)} em ${questionGrade.value.label}?`
    : "Motivo principal";
});

function openQuestion(question: SheetQuestion, thenSubmit: boolean) {
  sheetQuestion.value = question;
  submitAfterAnswer.value = thenSubmit;
}

function advanceQuestions() {
  const remaining = pendingQuestions();
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
  const question = sheetQuestion.value;
  if (question?.kind === "loss_reason") {
    lossDefectRef.value = defect.ref;
  } else if (question?.kind === "grade_reason") {
    // Atribuição substitutiva: cada bucket tem exatamente um motivo principal.
    gradeDefectRefs.value = {
      ...gradeDefectRefs.value,
      [question.gradeRef]: defect.ref,
    };
  }
  advanceQuestions();
}

function confirmOvershoot() {
  const reason = overshootReason.value.trim();
  if (!reason) return;
  overshootConfirmed.value = true;
  overshootReason.value = reason;
  advanceQuestions();
}

function fixOvershoot() {
  sheetQuestion.value = null;
  submitAfterAnswer.value = false;
  fresh.value = true;
}

function onConfirm() {
  if (props.submitting) return;
  if (props.mode === "correct" && !auditReason.value.trim()) {
    useSonner.warning("Informe o motivo da correção.");
    return;
  }
  if (total.value <= 0) {
    useSonner.warning("Informe a quantidade produzida ou a perda da fornada.");
    return;
  }
  const questions = pendingQuestions();
  if (questions.length) {
    openQuestion(questions[0]!, true);
    return;
  }
  submit();
}

function submit() {
  emit("confirm", {
    quantity: String(total.value),
    partition: buildPartition(),
    yield_deviation_confirmed: overshootConfirmed.value,
    yield_deviation_reason: overshootReason.value.trim(),
    reason: auditReason.value.trim(),
  });
}

const isDirty = computed(() =>
  props.mode === "correct"
    ? partitionKey(buildPartition()) !== partitionKey(props.initialPartition) ||
      Boolean(auditReason.value.trim())
    : Object.values(gradeQuantities.value).some((quantity) => quantity > 0) ||
      lossQuantity.value > 0 ||
      Object.values(gradeDefectRefs.value).some(Boolean) ||
      Boolean(lossDefectRef.value || overshootReason.value.trim()),
);

function partitionKey(partition: QcPartitionGroup[]): string {
  return JSON.stringify(
    partition
      .filter((group) => quantityOf(group) > 0)
      .map((group) => ({
        quantity: String(quantityOf(group)),
        quality_grade_ref: group.quality_grade_ref ?? "",
        quality_defect_ref: group.quality_defect_ref ?? "",
        loss: Boolean(group.loss),
      }))
      .sort((left, right) =>
        `${left.loss}:${left.quality_grade_ref}`.localeCompare(
          `${right.loss}:${right.quality_grade_ref}`,
        ),
      ),
  );
}

function requestBack() {
  if (
    isDirty.value &&
    !window.confirm(
      props.mode === "correct"
        ? "Descartar a correção de qualidade?"
        : "Descartar as quantidades e os motivos informados?",
    )
  ) {
    return;
  }
  emit("back");
}

// Teclado físico: os mesmos alvos do numpad, sem criar campos paralelos.
function onKeydown(event: KeyboardEvent) {
  const target = event.target as HTMLElement | null;
  if (event.key === "Escape") {
    sheetQuestion.value = null;
    submitAfterAnswer.value = false;
    return;
  }
  if (
    target?.closest(
      "button, a, input, textarea, select, [role='button'], [contenteditable='true']",
    )
  ) {
    return;
  }
  if (sheetQuestion.value) return;
  if (/^[0-9]$/.test(event.key)) {
    onDigit(event.key);
  } else if (event.key === "Backspace") {
    event.preventDefault();
    onBackspace();
  } else if (event.key === "Enter") {
    event.preventDefault();
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
    <header class="flex h-14 shrink-0 items-center justify-between gap-3">
      <button
        type="button"
        class="flex items-center gap-1 rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent"
        @click="requestBack"
      >
        <Icon name="lucide:chevron-left" class="size-4" />
        Voltar
      </button>
      <div class="min-w-0 text-center">
        <p class="truncate text-base font-semibold">{{ title }}</p>
        <p class="truncate text-xs text-muted-foreground">
          <template v-if="mode === 'correct'"
            >Correção de qualidade ·
          </template>
          {{ subtitle }}
        </p>
      </div>
      <div class="rounded-md border bg-muted/40 px-3 py-2 text-sm tabular-nums">
        <template v-if="anchor.anchor !== null">
          {{ anchor.anchor }} produzidos
        </template>
        <template v-else>Sem quantidade produzida</template>
      </div>
    </header>

    <div class="mt-2 shrink-0">
      <div
        :class="[
          fieldCard,
          activeTarget
            ? 'border-primary ring-2 ring-primary/30'
            : 'border-dashed',
        ]"
        aria-live="polite"
      >
        <span
          class="text-xs font-medium uppercase tracking-wide text-muted-foreground"
        >
          {{ activeLabel }}
        </span>
        <span class="text-4xl font-semibold tabular-nums">
          {{ activeQuantity }}
        </span>
      </div>
    </div>

    <p class="flex h-9 shrink-0 items-center text-sm text-muted-foreground">
      <template v-if="activeTarget">Digitando em: {{ activeLabel }}</template>
      <template v-else>
        Escolha um grau ou Perda; Normal recebe o saldo.
      </template>
    </p>

    <div class="grid shrink-0 grid-cols-[minmax(0,1fr)_12rem] gap-8">
      <OperatorNumpad
        subject="quantidade"
        :disabled="!activeTarget"
        @digit="onDigit"
        @backspace="onBackspace"
        @clear="onClear"
      />

      <div class="flex min-h-0 flex-col">
        <div
          class="flex flex-1 flex-col gap-2"
          role="group"
          aria-label="Graus de qualidade"
        >
          <button
            v-for="grade in orderedGrades"
            :key="grade.ref"
            type="button"
            :data-grade-ref="grade.ref"
            class="relative flex min-h-14 flex-1 items-center justify-between gap-2 overflow-hidden rounded-md border py-2 pl-4 pr-3 text-left transition hover:bg-accent"
            :class="{
              'border-primary bg-accent ring-2 ring-primary/30': isActiveGrade(
                grade.ref,
              ),
            }"
            :aria-label="`${grade.label}: ${gradeQuantity(grade.ref)} unidades${grade.ref === defaultRef && anchor.anchor !== null ? ', saldo' : ''}`"
            :aria-pressed="gradeQuantity(grade.ref) > 0"
            @click="pickGrade(grade)"
          >
            <span
              class="absolute inset-y-0 left-0 w-1.5"
              :class="gradeBandClass(grade, grades)"
            />
            <span class="min-w-0">
              <span class="block font-medium">{{ grade.label }}</span>
              <span
                v-if="grade.ref === defaultRef && anchor.anchor !== null"
                class="block text-xs text-muted-foreground"
              >
                saldo
              </span>
              <span
                v-else-if="gradeDefectRefs[grade.ref]"
                class="block truncate text-xs text-muted-foreground"
              >
                {{ defectLabel(gradeDefectRefs[grade.ref]!) }}
              </span>
            </span>
            <span class="text-sm font-semibold tabular-nums">
              {{ gradeQuantity(grade.ref) }}
            </span>
          </button>
          <button
            v-for="grade in correctionReasonGrades"
            :key="`reason-${grade.ref}`"
            type="button"
            class="flex min-h-10 items-center justify-between gap-2 rounded-md border border-dashed px-3 text-left text-xs text-muted-foreground transition hover:bg-accent hover:text-foreground"
            :aria-label="`Alterar motivo de ${grade.label}`"
            @click="
              openQuestion({ kind: 'grade_reason', gradeRef: grade.ref }, false)
            "
          >
            <span
              >{{ grade.label }} ·
              {{
                defectLabel(gradeDefectRefs[grade.ref] ?? "") || "sem motivo"
              }}</span
            >
            <span class="font-medium">Alterar motivo</span>
          </button>
        </div>

        <button
          type="button"
          class="mt-4 flex min-h-16 items-center justify-between gap-2 rounded-md border border-destructive/50 px-3 text-left transition hover:bg-destructive/10"
          :class="{
            'ring-2 ring-destructive/30': activeTarget?.kind === 'loss',
            'cursor-default opacity-70':
              mode === 'correct' && lossQuantity === 0,
          }"
          :disabled="mode === 'correct' && lossQuantity === 0"
          :aria-label="`Perda: ${lossQuantity} unidades`"
          @click="pickLoss"
        >
          <span class="min-w-0">
            <span class="block font-medium">Perda</span>
            <span
              v-if="lossDefectRef"
              class="block truncate text-xs text-muted-foreground"
            >
              {{ defectLabel(lossDefectRef) }}
            </span>
            <span v-else class="block text-xs text-muted-foreground">
              {{ mode === "correct" ? "sem perda" : "quantidade + motivo" }}
            </span>
          </span>
          <span class="text-sm font-semibold tabular-nums">
            {{ lossQuantity }}
          </span>
        </button>
      </div>
    </div>

    <label v-if="mode === 'correct'" class="mt-4 grid gap-1.5 text-sm">
      <span class="font-medium">Motivo da correção</span>
      <textarea
        v-model="auditReason"
        rows="2"
        maxlength="500"
        required
        class="rounded-md border bg-background px-3 py-2 outline-none focus:ring-1 focus:ring-ring"
        aria-label="Motivo da correção de qualidade"
        placeholder="Ex.: reavaliação feita pelo responsável"
      />
    </label>

    <button
      type="button"
      class="mt-4 h-14 shrink-0 rounded-lg bg-primary text-lg font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-60"
      :disabled="submitting || (mode === 'correct' && !auditReason.trim())"
      @click="onConfirm"
    >
      {{
        submitting
          ? mode === "correct"
            ? "Salvando correção…"
            : "Fechando a fornada…"
          : mode === "correct"
            ? "Salvar correção"
            : "Confirmar"
      }}
    </button>

    <UiSheet
      :open="sheetQuestion !== null"
      @update:open="
        (open: boolean) => {
          if (!open) {
            sheetQuestion = null;
            submitAfterAnswer = false;
          }
        }
      "
    >
      <UiSheetContent side="bottom" :title="sheetTitle">
        <template #content>
          <div
            v-if="sheetQuestion?.kind === 'overshoot'"
            class="grid gap-3 px-4 pb-6"
          >
            <label class="grid gap-1.5 text-sm">
              <span class="font-medium">
                Por que a contagem ficou acima da fornada iniciada?
              </span>
              <textarea
                v-model="overshootReason"
                rows="3"
                maxlength="500"
                required
                class="rounded-md border bg-background px-3 py-2"
                aria-label="Motivo da quantidade acima da fornada produzida"
                placeholder="Ex.: contagem conferida e unidades menores que o padrão"
              />
            </label>
            <div class="grid grid-cols-2 gap-2">
              <button
                type="button"
                class="rounded-md border px-3 py-4 text-base font-medium transition hover:bg-accent active:translate-y-px"
                @click="fixOvershoot"
              >
                Corrigir
              </button>
              <button
                type="button"
                class="rounded-md border border-transparent bg-primary px-3 py-4 text-base font-semibold text-primary-foreground transition hover:bg-primary/90 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-50"
                :disabled="!overshootReason.trim()"
                @click="confirmOvershoot"
              >
                Confirmar {{ total }} unidades
              </button>
            </div>
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
              <span class="text-xs text-muted-foreground">
                {{ defect.hint }}
              </span>
            </button>
          </div>
        </template>
      </UiSheetContent>
    </UiSheet>
  </div>
</template>
