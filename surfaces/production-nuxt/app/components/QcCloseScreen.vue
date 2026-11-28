<script setup lang="ts">
// Finalização de um único lote. Os quatro botões são buckets de qualidade
// disjuntos; o grau padrão recebe automaticamente o saldo que não foi lançado
// nos demais graus nem em Perda. Quando rendeu menos (beta 05/11), o operador
// toca no grau padrão e digita o que saiu: a diferença para o previsto é
// perda, registrada com a causa escolhida, quem fechou e a hora (dono, 24/11).
import type { QCDefectProjection, QCGradeProjection } from "~/types/production";
import type { OperatorActionBarAction } from "../../../operator-kit/app/presentation/actionBar";
import {
  QUANTITY_MAX,
  backspaceQuantityText,
  defaultGradeRef,
  formatQcNumber,
  formatQcQuantity,
  gradeBandClass,
  isCountUnit,
  isLowerQualityGrade,
  ovenAnchor,
  quantityDecimals,
  quantityText,
  parseQuantityText,
  roundQuantity,
  typeQuantityKey,
  yieldReasons as yieldReasonsFor,
  type QcPartitionGroup,
} from "~/presentation/qc";
import {
  hasOpenDialogOutside,
  isEditableKeyboardTarget,
  isNativeActionTarget,
  productionContextKeysBlocked,
  resolveQuantityKeyboardShortcut,
} from "~/presentation/keyboard";

const props = withDefaults(
  defineProps<{
    title: string;
    subtitle: string;
    planned: number | null;
    /** O lote real que entrou no forno (declarado no start); null sem start. */
    started: number | null;
    grades: QCGradeProjection[];
    defects: QCDefectProjection[];
    submitting: boolean;
    mode?: "close" | "correct";
    initialPartition?: QcPartitionGroup[];
    /** A unidade do lote ("un", "kg", "g"). Peça é inteira; peso aceita vírgula. */
    unit?: string;
  }>(),
  {
    mode: "close",
    initialPartition: () => [],
    unit: "",
  },
);

const countUnit = computed(() => isCountUnit(props.unit));
const decimals = computed(() => quantityDecimals(props.unit));
/** "unidades" na peça; a unidade escrita no peso ("kg"). Para leitor de tela. */
const unitWord = computed(() =>
  countUnit.value ? "unidades" : props.unit.trim().toLowerCase(),
);
/** O número na tela: "32" na peça, "2,5 kg" no peso. */
function qty(value: number): string {
  return countUnit.value ? formatQcNumber(value) : formatQcQuantity(value, props.unit);
}
/** O número com a unidade sempre escrita: "32 un.", "2,5 kg". */
function qtyWithUnit(value: number): string {
  return formatQcQuantity(value, props.unit);
}
function round(value: number): number {
  return roundQuantity(value, decimals.value);
}

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
  | { kind: "shortfall" }
  | { kind: "loss_exceeds" }
  | { kind: "grade_reason"; gradeRef: string }
  | { kind: "loss_reason" }
  | { kind: "correction_reason" };

// Correção (P20): o servidor exige o motivo e ele vai para a auditoria com o
// seu nome. A tela pergunta; nunca escreve o motivo pelo operador. A lista
// curta cobre os casos de sempre e o texto continua editável.
const CORRECTION_REASONS = [
  "Defeito visto depois da finalização",
  "Contagem errada na finalização",
  "Grau ou motivo trocado na finalização",
] as const;

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
// O que o operador digitou no grau padrão (só na Finalização). null = saldo.
const defaultOverride = ref<number | null>(null);
const correctionReason = ref("");
const submitLatched = ref(false);

watch(
  () => props.submitting,
  (value, previous) => {
    if (previous && !value) submitLatched.value = false;
  },
);

// Com âncora, Normal é saldo e não exige digitação. Sem âncora, o padrão é um
// bucket editável como os demais para que um lote avulso possa ser fechado.
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
  if (defaultOverride.value !== null) return defaultOverride.value;
  return Math.max(
    0,
    round(anchor.anchor - explicitTotal.value - lossQuantity.value),
  );
});
// O grau padrão segue o saldo até o operador digitar nele (só na Finalização;
// a correção mantém o total do lote).
const defaultIsBalance = computed(
  () => anchor.anchor !== null && defaultOverride.value === null,
);
const defaultEditable = computed(
  () => anchor.anchor !== null && props.mode === "close",
);

function gradeQuantity(gradeRef: string): number {
  return gradeRef === defaultRef.value
    ? defaultQuantity.value
    : explicitGradeQuantity(gradeRef);
}

const finishedTotal = computed(() =>
  round(
    orderedGrades.value.reduce(
      (total, grade) => total + gradeQuantity(grade.ref),
      0,
    ),
  ),
);
const total = computed(() => round(finishedTotal.value + lossQuantity.value));
const overshootQuantity = computed(() =>
  anchor.anchor === null ? 0 : Math.max(0, round(total.value - anchor.anchor)),
);
// Rendeu menos que o previsto: é perda, e a causa escolhida a classifica.
const shortfallQuantity = computed(() =>
  anchor.anchor === null ? 0 : Math.max(0, round(anchor.anchor - total.value)),
);
// Perda maior que o lote inteiro é dígito a mais, nunca um caso de "acima".
const lossExceedsLot = computed(
  () => anchor.anchor !== null && lossQuantity.value > anchor.anchor,
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
  if (!grade) return "Escolha um grau";
  return defaultIsBalance.value ? `${grade.label} · Saldo automático` : grade.label;
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
    let nextQuantity = quantity;
    if (props.mode === "correct") {
      const maximum = Math.max(0, correctionTotal - explicitTotal.value);
      nextQuantity = Math.min(quantity, maximum);
      if (quantity > maximum) {
        useSonner.warning(
          `Máximo ${qty(maximum)}; os outros graus já ocupam o restante.`,
        );
      }
    }
    lossQuantity.value = nextQuantity;
    if (nextQuantity === 0) lossDefectRef.value = "";
  } else if (target.gradeRef === defaultRef.value && defaultEditable.value) {
    defaultOverride.value = quantity;
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
        Math.max(0, correctionTotal - lossQuantity.value - otherExplicit),
      );
      if (quantity > nextQuantity) {
        useSonner.warning(
          `Máximo ${qty(nextQuantity)}; Perda e os outros graus já ocupam o restante.`,
        );
      }
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

// O texto do teclado enquanto o operador digita ("2," ainda não é número).
// null = mostra a quantidade do alvo, formatada.
const entryText = ref<string | null>(null);
const activeText = computed(
  () => entryText.value ?? quantityText(activeQuantity.value),
);

function pressQuantityKey(key: string) {
  if (!activeTarget.value) return;
  const result = typeQuantityKey(
    activeText.value,
    key,
    fresh.value,
    decimals.value,
  );
  if (!result.ok) {
    if (result.reason === "max") {
      useSonner.warning(`O teclado vai até ${formatQcNumber(QUANTITY_MAX)}.`);
    } else if (result.reason === "decimals") {
      useSonner.warning(`Até ${decimals.value} casas depois da vírgula.`);
    }
    return;
  }
  entryText.value = result.text;
  setTargetQuantity(round(parseQuantityText(result.text)));
  fresh.value = false;
}

function onDigit(digit: string) {
  pressQuantityKey(digit);
}

function onComma() {
  pressQuantityKey(",");
}

function onBackspace() {
  if (!activeTarget.value) return;
  const next = backspaceQuantityText(activeText.value);
  entryText.value = next;
  setTargetQuantity(round(parseQuantityText(next)));
  fresh.value = false;
}

function onClear() {
  if (!activeTarget.value) return;
  entryText.value = null;
  setTargetQuantity(0);
  fresh.value = true;
}

function pickGrade(grade: QCGradeProjection) {
  if (grade.ref === defaultRef.value && defaultEditable.value) {
    activeTarget.value = { kind: "grade", gradeRef: grade.ref };
  } else if (grade.ref === defaultRef.value && anchor.anchor !== null) {
    // Normal continua sendo o próprio botão/grau, mas sua quantidade é o
    // saldo: não há um segundo input capaz de duplicá-la.
    activeTarget.value = null;
  } else {
    activeTarget.value = { kind: "grade", gradeRef: grade.ref };
  }
  entryText.value = null;
  fresh.value = true;
}

// "Usar o saldo" é um botão com nome, à vista no alvo escolhido (P2-09): o
// gesto secreto de dois toques levava o lote inteiro para um grau sem querer.
const balanceAction = computed<
  { kind: "take"; quantity: number } | { kind: "restore" } | null
>(() => {
  const target = activeTarget.value;
  if (!target || anchor.anchor === null) return null;
  if (target.kind === "grade" && target.gradeRef === defaultRef.value) {
    return defaultOverride.value === null ? null : { kind: "restore" };
  }
  const usedElsewhere = orderedGrades.value
    .filter(
      (item) =>
        item.ref !== defaultRef.value &&
        !(target.kind === "grade" && item.ref === target.gradeRef),
    )
    .reduce(
      (sum, item) => sum + explicitGradeQuantity(item.ref),
      target.kind === "loss" ? 0 : lossQuantity.value,
    );
  const available = Math.max(0, round(anchor.anchor - usedElsewhere));
  return available > 0 && available !== activeQuantity.value
    ? { kind: "take", quantity: available }
    : null;
});

function useBalance() {
  const action = balanceAction.value;
  if (!action) return;
  if (action.kind === "restore") {
    defaultOverride.value = null;
    resetOvershootConfirmation();
  } else {
    setTargetQuantity(action.quantity);
  }
  entryText.value = null;
  fresh.value = true;
}

function pickLoss() {
  activeTarget.value = { kind: "loss" };
  entryText.value = null;
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
  if (lossExceedsLot.value) {
    // Bloqueia: nenhuma resposta transforma 99 de perda num lote de 3.
    return [{ kind: "loss_exceeds" }];
  }
  if (
    shortfallQuantity.value > 0 &&
    (!overshootConfirmed.value || !overshootReason.value.trim())
  ) {
    questions.push({ kind: "shortfall" });
  }
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
  if (props.mode === "correct" && !correctionReason.value.trim()) {
    questions.push({ kind: "correction_reason" });
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
const sheetTitle = computed(() => {
  if (sheetQuestion.value?.kind === "overshoot") {
    return `Saíram ${qty(total.value)}, mais que os ${qty(anchor.anchor ?? 0)} previstos?`;
  }
  if (sheetQuestion.value?.kind === "shortfall") {
    return `Rendeu ${formatQcNumber(total.value)} de ${qty(anchor.anchor ?? 0)} previstos?`;
  }
  if (sheetQuestion.value?.kind === "loss_exceeds") {
    return `A perda (${qty(lossQuantity.value)}) é maior que o lote (${qty(anchor.anchor ?? 0)}). Confira.`;
  }
  if (sheetQuestion.value?.kind === "loss_reason") {
    return `Qual o motivo principal da perda de ${qty(lossQuantity.value)}?`;
  }
  if (sheetQuestion.value?.kind === "correction_reason") {
    return "Por que a qualidade deste lote está sendo corrigida?";
  }
  return questionGrade.value
    ? `Qual o motivo principal de ${qty(gradeQuantity(questionGrade.value.ref))} em ${questionGrade.value.label}?`
    : "Motivo principal";
});

// "Outro" abre o texto; os motivos prontos fecham em um toque.
const yieldOtherOpen = ref(false);
const yieldReasons = computed(() =>
  yieldReasonsFor(
    sheetQuestion.value?.kind === "overshoot" ? "overshoot" : "shortfall",
    props.unit,
  ),
);

function openQuestion(question: SheetQuestion, thenSubmit: boolean) {
  yieldOtherOpen.value = false;
  sheetQuestion.value = question;
  submitAfterAnswer.value = thenSubmit;
}

function advanceQuestions() {
  yieldOtherOpen.value = false;
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

function answerYieldReason(reason: string) {
  overshootReason.value = reason;
  confirmOvershoot();
}

function openYieldOther() {
  // O texto começa vazio: "Outro" é a palavra do operador, nunca a nossa.
  overshootReason.value = "";
  yieldOtherOpen.value = true;
}

function confirmOvershoot() {
  const reason = overshootReason.value.trim();
  if (!reason) return;
  overshootConfirmed.value = true;
  overshootReason.value = reason;
  advanceQuestions();
}

function confirmCorrectionReason() {
  const reason = correctionReason.value.trim();
  if (!reason) return;
  correctionReason.value = reason;
  advanceQuestions();
}

function fixOvershoot() {
  yieldOtherOpen.value = false;
  sheetQuestion.value = null;
  submitAfterAnswer.value = false;
  fresh.value = true;
}

function fixLoss() {
  fixOvershoot();
  pickLoss();
}

function onConfirm() {
  if (props.submitting || submitLatched.value) return;
  if (total.value <= 0) {
    useSonner.warning("Informe a quantidade realizada ou a perda do lote.");
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
  if (props.submitting || submitLatched.value) return;
  submitLatched.value = true;
  emit("confirm", {
    quantity: String(total.value),
    partition: buildPartition(),
    yield_deviation_confirmed: overshootConfirmed.value,
    yield_deviation_reason: overshootReason.value.trim(),
    reason: props.mode === "correct" ? correctionReason.value.trim() : "",
  });
}

const isDirty = computed(() =>
  props.mode === "correct"
    ? partitionKey(buildPartition()) !== partitionKey(props.initialPartition)
    : Object.values(gradeQuantities.value).some((quantity) => quantity > 0) ||
      lossQuantity.value > 0 ||
      defaultOverride.value !== null ||
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

const confirmDiscard = useConfirm();

/**
 * Pergunta antes de jogar fora o que foi digitado. `leave` é o voltar da tela;
 * `switch` é andar para outro lote (o ‹ › do `OperatorRecordNav`, que a página
 * segura no `onBeforeRouteUpdate`). Sem nada digitado, segue sem perguntar.
 */
function discardQuestion(action: "leave" | "switch") {
  const confirmLabel = action === "switch" ? "Descartar e trocar de lote" : "Descartar e sair";
  return props.mode === "correct"
    ? {
        title: "Descartar a correção de qualidade?",
        description:
          "Os números e os motivos que você mudou neste lote se perdem. A qualidade fica como estava.",
        confirmLabel,
      }
    : {
        title: "Descartar as quantidades e os motivos informados?",
        description:
          "O lote continua aberto na Finalização, sem nada do que você digitou.",
        confirmLabel,
      };
}

function confirmDiscardChanges(action: "leave" | "switch" = "leave"): Promise<boolean> {
  return isDirty.value ? confirmDiscard(discardQuestion(action)) : Promise.resolve(true);
}

defineExpose({ isDirty, confirmDiscardChanges });

async function requestBack() {
  if (isDirty.value && !(await confirmDiscard(discardQuestion("leave")))) return;
  emit("back");
}

// Teclado físico: os mesmos alvos do numpad, sem criar campos paralelos.
function onKeydown(event: KeyboardEvent) {
  if (event.repeat || event.isComposing || productionContextKeysBlocked())
    return;
  if (event.key === "Escape") {
    if (sheetQuestion.value) {
      sheetQuestion.value = null;
      submitAfterAnswer.value = false;
    } else {
      event.preventDefault();
      requestBack();
    }
    return;
  }
  if (sheetQuestion.value) return;
  if (hasOpenDialogOutside()) return;
  if (isEditableKeyboardTarget(event.target)) return;

  // A vírgula do lote que se pesa: "," "." e a tecla decimal do numpad.
  if (
    !countUnit.value &&
    (event.key === "," || event.key === "." || event.code === "NumpadDecimal")
  ) {
    event.preventDefault();
    onComma();
    return;
  }

  const shortcut = resolveQuantityKeyboardShortcut(event);
  if (!shortcut) return;
  // Enter comum mantém a semântica nativa do botão em foco. O Enter do numpad
  // confirma o número, mesmo depois de o operador tocar/clicar no grau.
  if (
    shortcut.kind === "confirm" &&
    event.code !== "NumpadEnter" &&
    isNativeActionTarget(event.target)
  ) {
    return;
  }

  event.preventDefault();
  if (shortcut.kind === "digit") {
    onDigit(shortcut.digit);
  } else if (shortcut.kind === "backspace") {
    onBackspace();
  } else if (shortcut.kind === "clear") {
    onClear();
  } else {
    onConfirm();
  }
}

onMounted(() => window.addEventListener("keydown", onKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));

const fieldCard =
  "flex h-24 flex-col justify-between rounded-md border bg-card p-3 text-left transition";

// A ação da tela é UMA: fechar o lote (ou salvar a correção). Na mesa ela fica sob o
// teclado, como sempre; no celular desce para a base (`OperatorActionBar`), com o
// realizado na linha de contexto. A folha de motivos continua sendo o passo seguinte
// do mesmo gesto: a barra só a abre, e a folha, modal, cobre a barra enquanto pergunta.
const submitBusy = computed(() => props.submitting || submitLatched.value);
const submitDisabled = computed(
  () => submitBusy.value || (props.mode === "correct" && !isDirty.value),
);
const submitLabel = computed(() => {
  if (submitBusy.value) {
    return props.mode === "correct" ? "Salvando correção…" : "Finalizando o lote…";
  }
  return props.mode === "correct" ? "Salvar correção" : "Finalizar";
});
const actionBarAction = computed<OperatorActionBarAction>(() => ({
  label: submitLabel.value,
  icon: "i-lucide-check",
  loading: submitBusy.value,
  disabled: submitDisabled.value,
  reason:
    !submitBusy.value && props.mode === "correct" && !isDirty.value
      ? "Mude um grau, a perda ou um motivo para salvar a correção."
      : "",
  onSelect: () => onConfirm(),
}));
// "Realizado" é só o que se vende (P2-10): a perda não entra na conta.
const actionBarValue = computed(() =>
  anchor.anchor !== null
    ? `${formatQcNumber(finishedTotal.value)} de ${qty(anchor.anchor)}`
    : qty(finishedTotal.value),
);
</script>

<template>
  <div
    class="flex min-h-0 flex-1 flex-col"
    data-production-shortcut-scope="exclusive"
  >
    <div class="min-h-0 flex-1 overflow-y-auto">
      <div class="mx-auto flex w-full max-w-2xl flex-col px-4 pb-6">
        <header
          class="grid shrink-0 grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 gap-y-2 py-2 sm:flex sm:min-h-14 sm:justify-between sm:py-0"
        >
          <NuxtButton
            color="neutral"
            variant="outline"
            icon="i-lucide-chevron-left"
            label="Voltar"
            @click="requestBack"
          />
          <div class="min-w-0 text-center max-sm:text-left">
            <p class="truncate text-base font-semibold">{{ title }}</p>
            <p class="truncate text-xs text-muted-foreground">
              <template v-if="mode === 'correct'"
                >Correção de qualidade ·
              </template>
              {{ subtitle }}
            </p>
          </div>
          <div
            class="col-span-2 rounded-md border bg-muted/40 px-3 py-2 text-center text-sm tabular-nums sm:col-span-1"
            data-qc-anchor
          >
            <template v-if="anchor.anchor !== null">
              Previsto: {{ qtyWithUnit(anchor.anchor) }}
            </template>
            <template v-else>Sem quantidade prevista</template>
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
            <span class="flex items-end justify-between gap-3">
              <span class="text-4xl font-semibold tabular-nums" data-qc-active-qty>
                {{ activeText
                }}<span
                  v-if="!countUnit"
                  class="ml-1 text-xl font-medium text-muted-foreground"
                  >{{ unitWord }}</span
                >
              </span>
              <NuxtButton
                v-if="balanceAction"
                color="neutral"
                variant="outline"
                class="min-h-11 shrink-0"
                :label="
                  balanceAction.kind === 'restore'
                    ? 'Voltar ao saldo automático'
                    : `Usar o saldo: ${qty(balanceAction.quantity)}`
                "
                data-qc-use-balance
                @click="useBalance"
              />
            </span>
          </div>
        </div>

        <p class="flex min-h-9 shrink-0 items-center py-1 text-sm text-muted-foreground">
          <template v-if="activeTarget">Digitando em: {{ activeLabel }}</template>
          <template v-else>Escolha um grau ou Perda para digitar a quantidade.</template>
        </p>

        <!-- Uma coluna no celular (graus em cima, teclado embaixo); duas na mesa. -->
        <div
          class="grid shrink-0 grid-cols-1 items-start gap-4 sm:grid-cols-[minmax(0,1fr)_12rem] sm:gap-8"
          data-qc-layout
        >
          <div class="order-2 flex flex-col gap-1.5 sm:order-none">
            <OperatorNumpad
              class="h-76 self-stretch"
              subject="quantidade"
              :disabled="!activeTarget"
              @digit="onDigit"
              @backspace="onBackspace"
              @clear="onClear"
            />
            <NuxtButton
              v-if="!countUnit"
              color="neutral"
              variant="outline"
              size="xl"
              block
              class="min-h-11 justify-center text-lg font-semibold"
              label=","
              aria-label="Vírgula"
              aria-keyshortcuts=","
              :disabled="!activeTarget"
              data-qc-comma
              @click="onComma"
            />
          </div>

          <div class="order-1 flex flex-col sm:order-none">
            <div
              class="flex flex-col gap-2"
              role="group"
              aria-label="Graus de qualidade"
            >
              <div
                v-for="grade in orderedGrades"
                :key="grade.ref"
                class="relative min-h-14 overflow-hidden rounded-md border bg-card"
                :class="{
                  'bg-accent': isActiveGrade(grade.ref),
                }"
                :data-grade-card="grade.ref"
              >
                <span
                  class="pointer-events-none absolute inset-y-0 left-0 z-30 w-1.5"
                  :class="gradeBandClass(grade, grades)"
                />
                <!-- O cartão divide quantidade e motivo em dois alvos grandes: o da
                     quantidade cobre o cartão; o do motivo fica por cima, embaixo. -->
                <NuxtButton
                  color="neutral"
                  variant="ghost"
                  :data-grade-ref="grade.ref"
                  class="absolute inset-0 z-0 h-auto w-full rounded-none p-0 text-left font-normal focus-visible:ring-[3px] focus-visible:ring-inset focus-visible:ring-ring/50"
                  :aria-label="`${grade.label}: ${formatQcNumber(gradeQuantity(grade.ref))} ${unitWord}${grade.ref === defaultRef && defaultIsBalance ? ', saldo' : ''}`"
                  :aria-pressed="gradeQuantity(grade.ref) > 0"
                  @click="pickGrade(grade)"
                >
                  <span
                    class="absolute inset-x-0 top-0 flex h-14 items-center justify-between gap-2 pl-4 pr-3"
                  >
                    <span class="min-w-0">
                      <span class="block font-medium">{{ grade.label }}</span>
                      <span
                        v-if="grade.ref === defaultRef && defaultIsBalance"
                        class="block text-xs leading-tight text-muted-foreground"
                      >
                        Saldo automático
                      </span>
                      <span
                        v-else-if="mode !== 'correct' && gradeDefectRefs[grade.ref]"
                        class="block truncate text-xs leading-tight text-muted-foreground"
                      >
                        {{ defectLabel(gradeDefectRefs[grade.ref]!) }}
                      </span>
                    </span>
                    <span class="text-sm font-semibold tabular-nums">
                      {{ qty(gradeQuantity(grade.ref)) }}
                    </span>
                  </span>
                </NuxtButton>
                <NuxtButton
                  v-if="mode === 'correct' && gradeNeedsReason(grade)"
                  color="neutral"
                  variant="outline"
                  class="relative z-20 mb-2 ml-3 mr-2 mt-14 flex h-8 w-[calc(100%-1.25rem)] items-center justify-between gap-2 rounded-md bg-background px-3 text-left text-xs font-medium text-muted-foreground"
                  :aria-label="`Editar motivo de ${grade.label}: ${
                    defectLabel(gradeDefectRefs[grade.ref] ?? '') || 'não informado'
                  }`"
                  @click="
                    openQuestion(
                      { kind: 'grade_reason', gradeRef: grade.ref },
                      false,
                    )
                  "
                >
                  <span class="min-w-0 truncate">
                    {{
                      defectLabel(gradeDefectRefs[grade.ref] ?? "") ||
                      "Informar motivo"
                    }}
                  </span>
                  <Icon name="lucide:pencil" class="size-4" aria-hidden="true" />
                </NuxtButton>
              </div>
            </div>

            <div
              class="relative mt-4 min-h-14 overflow-hidden rounded-md border border-destructive/50 bg-card"
              :class="{
                'bg-destructive/10': activeTarget?.kind === 'loss',
              }"
            >
              <!-- Perda replica a geometria dos graus para não trocar o gesto do operador. -->
              <NuxtButton
                color="neutral"
                variant="ghost"
                class="absolute inset-0 z-0 h-auto w-full rounded-none p-0 text-left font-normal hover:bg-destructive/10 focus-visible:ring-[3px] focus-visible:ring-inset focus-visible:ring-destructive/50"
                :aria-label="`Perda: ${formatQcNumber(lossQuantity)} ${unitWord}`"
                @click="pickLoss"
              >
                <span
                  class="absolute inset-x-0 top-0 flex h-14 items-center justify-between gap-2 px-3"
                >
                  <span class="min-w-0">
                    <span class="block font-medium">Perda</span>
                    <span
                      v-if="mode !== 'correct' && lossDefectRef"
                      class="block truncate text-xs leading-tight text-muted-foreground"
                    >
                      {{ defectLabel(lossDefectRef) }}
                    </span>
                    <span
                      v-else-if="mode !== 'correct' || lossQuantity === 0"
                      class="block text-xs leading-tight text-muted-foreground"
                    >
                      {{ lossQuantity ? "Motivo pendente" : "Sem perda" }}
                    </span>
                  </span>
                  <span class="text-sm font-semibold tabular-nums">
                    {{ qty(lossQuantity) }}
                  </span>
                </span>
              </NuxtButton>
              <NuxtButton
                v-if="mode === 'correct' && lossQuantity > 0"
                color="neutral"
                variant="outline"
                class="relative z-20 mx-2 mb-2 mt-14 flex h-8 w-[calc(100%-1rem)] items-center justify-between gap-2 rounded-md bg-background px-3 text-left text-xs font-medium text-muted-foreground hover:bg-destructive/10"
                :aria-label="`Editar motivo da perda: ${
                  defectLabel(lossDefectRef) || 'não informado'
                }`"
                @click="openQuestion({ kind: 'loss_reason' }, false)"
              >
                <span class="min-w-0 truncate">
                  {{ defectLabel(lossDefectRef) || "Informar motivo" }}
                </span>
                <Icon name="lucide:pencil" class="size-4" aria-hidden="true" />
              </NuxtButton>
            </div>
          </div>
        </div>

        <!-- Na mesa, a ação fica sob o teclado; no celular ela mora na base. -->
        <NuxtButton
          size="xl"
          block
          class="mt-4 shrink-0 max-lg:hidden"
          :label="submitLabel"
          :disabled="submitDisabled"
          :aria-busy="submitBusy"
          aria-keyshortcuts="Enter"
          data-qc-submit
          @click="onConfirm"
        />
      </div>
    </div>

    <OperatorActionBar
      :action="actionBarAction"
      context-label="Realizado"
      :context-value="actionBarValue"
      label="Ação do lote"
      data-qc-action-bar
    />

    <NuxtDrawer
      :open="sheetQuestion !== null"
      :title="sheetTitle"
      @update:open="
        (open: boolean) => {
          if (!open) {
            sheetQuestion = null;
            submitAfterAnswer = false;
          }
        }
      "
    >
      <template #body>
        <div
          v-if="sheetQuestion?.kind === 'loss_exceeds'"
          class="grid gap-3"
          data-loss-exceeds
        >
          <p class="text-sm text-muted-foreground">
            A perda não pode passar do que entrou no forno.
          </p>
          <NuxtButton
            size="xl"
            block
            class="h-auto whitespace-normal"
            label="Corrigir a perda"
            @click="fixLoss"
          />
        </div>
        <!-- Rendeu menos ou mais que o previsto: o motivo em um toque, como os
             da perda; "Outro" abre o texto (decisão de 05/11, #2150). -->
        <div
          v-else-if="
            sheetQuestion?.kind === 'shortfall' ||
            sheetQuestion?.kind === 'overshoot'
          "
          class="grid gap-3"
          :data-shortfall="sheetQuestion?.kind === 'shortfall' ? '' : undefined"
          :data-overshoot="sheetQuestion?.kind === 'overshoot' ? '' : undefined"
        >
          <p class="text-sm text-muted-foreground">
            <template v-if="sheetQuestion?.kind === 'shortfall'">
              Por que rendeu menos? A diferença de
              {{ qtyWithUnit(shortfallQuantity) }} fica registrada como perda,
              com este motivo, seu nome e a hora.
            </template>
            <template v-else>
              Por que o realizado ficou acima do previsto? A diferença de
              {{ qtyWithUnit(overshootQuantity) }} fica registrada com este
              motivo, seu nome e a hora.
            </template>
          </p>
          <div
            v-if="!yieldOtherOpen"
            class="grid grid-cols-1 gap-2 sm:grid-cols-2"
            role="group"
            :aria-label="
              sheetQuestion?.kind === 'shortfall'
                ? 'Motivo de ter rendido menos'
                : 'Motivo de ter rendido mais'
            "
          >
            <NuxtButton
              v-for="reason in yieldReasons"
              :key="reason"
              color="neutral"
              variant="outline"
              size="xl"
              block
              class="min-h-14 h-auto justify-start whitespace-normal text-left"
              data-yield-reason
              @click="answerYieldReason(reason)"
            >
              <!-- Slot, e não label: o label do Nuxt UI trunca, e motivo não se corta. -->
              <span class="whitespace-normal text-left">{{ reason }}</span>
            </NuxtButton>
            <NuxtButton
              color="neutral"
              variant="outline"
              size="xl"
              block
              class="min-h-14 h-auto justify-start whitespace-normal text-left"
              label="Outro"
              trailing-icon="i-lucide-pencil"
              data-yield-other
              @click="openYieldOther"
            />
          </div>
          <label v-else class="grid gap-1.5 text-sm">
            <span class="font-medium">Qual foi o motivo?</span>
            <NuxtTextarea
              v-model="overshootReason"
              :rows="3"
              :maxlength="500"
              required
              autofocus
              class="w-full"
              :aria-label="
                sheetQuestion?.kind === 'shortfall'
                  ? 'Motivo de ter rendido menos que o previsto'
                  : 'Motivo do realizado acima do previsto'
              "
            />
          </label>
          <div
            class="grid gap-2"
            :class="yieldOtherOpen ? 'grid-cols-2' : 'grid-cols-1'"
          >
            <NuxtButton
              color="neutral"
              variant="outline"
              size="xl"
              block
              class="h-auto whitespace-normal"
              label="Corrigir a contagem"
              @click="fixOvershoot"
            />
            <NuxtButton
              v-if="yieldOtherOpen"
              size="xl"
              block
              class="h-auto whitespace-normal"
              :label="`Confirmar ${qtyWithUnit(total)}`"
              :disabled="!overshootReason.trim()"
              @click="confirmOvershoot"
            />
          </div>
        </div>
        <div
          v-else-if="sheetQuestion?.kind === 'correction_reason'"
          class="grid gap-3"
          data-correction-reason
        >
          <div
            class="flex flex-wrap gap-2"
            role="group"
            aria-label="Motivos comuns"
          >
            <!-- Motivo pronto preenche o texto (editável); é escolha, não CTA. -->
            <NuxtButton
              v-for="preset in CORRECTION_REASONS"
              :key="preset"
              color="neutral"
              variant="outline"
              size="xl"
              :active="correctionReason === preset"
              active-color="primary"
              active-variant="outline"
              :aria-pressed="correctionReason === preset"
              :label="preset"
              data-correction-preset
              @click="correctionReason = preset"
            />
          </div>
          <label class="grid gap-1.5 text-sm">
            <span class="font-medium">
              Motivo (fica registrado com seu nome)
            </span>
            <NuxtTextarea
              v-model="correctionReason"
              :rows="3"
              :maxlength="500"
              required
              class="w-full"
              aria-label="Motivo da correção de qualidade"
              placeholder="Ex.: duas peças estavam em outra bandeja"
            />
          </label>
          <NuxtButton
            size="xl"
            block
            class="h-auto whitespace-normal"
            label="Salvar correção"
            :disabled="!correctionReason.trim()"
            @click="confirmCorrectionReason"
          />
        </div>
        <div v-else class="grid grid-cols-1 gap-2 min-[400px]:grid-cols-2 sm:grid-cols-3">
          <!-- Motivos são cartões de escolha com título e explicação. -->
          <NuxtButton
            v-for="defect in activeDefects"
            :key="defect.ref"
            color="neutral"
            variant="outline"
            size="xl"
            block
            class="h-auto flex-col items-start justify-start gap-0.5 whitespace-normal text-left"
            @click="answerDefect(defect)"
          >
            <span class="font-medium">{{ defect.label }}</span>
            <span class="text-xs font-normal text-muted-foreground">
              {{ defect.hint }}
            </span>
          </NuxtButton>
        </div>
      </template>
    </NuxtDrawer>
  </div>
</template>
