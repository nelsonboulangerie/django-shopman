<script setup lang="ts">
// O diálogo que pergunta o MOTIVO de um gesto destrutivo que o cliente vai ler
// (cancelar, recusar), diz a consequência e confirma. Uma peça só para o PDV e o
// Gestor: antes eram dois diálogos com duas regras para o mesmo ato.
//
// Duas formas, decididas por quem chama:
//   - Motivo codificado (`coded`): o marketplace (iFood) EXIGE um dos códigos dele.
//     A descrição escolhida vira o texto que o cliente lê.
//   - Texto da casa: motivos prontos (um toque), agrupados sob os cabeçalhos da casa,
//     mais o "Outros", que entrega o motivo ao texto livre.
//
// "Outros" NÃO é motivo: o cliente lê "Motivo: <texto>.", e "Motivo: Outros." não diz
// nada. Escolher "Outros" limpa o motivo pronto e foca o texto; com "Outros", texto
// vazio nunca sai.
//
// Fechar com texto digitado pede confirmação DENTRO do diálogo (não `window.confirm`,
// que foge do contrato de modal da casa): o motivo escrito não some por um toque fora.
//
// Apresentacional: quem chama busca os motivos e grava; esta peça guarda só o que está
// sendo escolhido e entrega `{ reason, code }`. A autorização do gerente fica FORA
// (`OperatorManagerAuth` sobe por cima, e o motivo digitado continua aqui embaixo).
//
// ⚠️ `UiDialog`, `UiButton` e `UiTextarea` são do app hospedeiro (o kit não registra
// módulo). PDV e Gestor têm os três; é o mesmo limite do `OperatorManagerAuth`.
import { computed, nextTick, ref, watch } from "vue";

import type { CodedReason, ReasonChoice, ReasonPresetGroup } from "../types/reason";

const props = withDefaults(
  defineProps<{
    open: boolean;
    title: string;
    /** A consequência, dita antes de confirmar (reembolso, para onde vai o motivo). */
    description: string;
    confirmLabel: string;
    /** Motivo exigido para confirmar. Sem ele, confirmar em branco é permitido. */
    required?: boolean;
    /** Motivos prontos da casa. Vazio: só o texto livre, sem "Outros". */
    presets?: ReasonPresetGroup[];
    /** Liga o seletor de motivo codificado do marketplace no lugar do texto. */
    coded?: boolean;
    codedReasons?: CodedReason[];
    codedLabel?: string;
    codedEmptyText?: string;
    loading?: boolean;
    loadingText?: string;
    /** Falha ao ler os motivos: bloqueia confirmar e oferece consultar de novo. */
    error?: string;
    busy?: boolean;
    reasonLabel?: string;
    placeholder?: string;
    maxlength?: number;
  }>(),
  {
    required: false,
    presets: () => [],
    coded: false,
    codedReasons: () => [],
    codedLabel: "Motivo exigido",
    codedEmptyText: "Não há motivos disponíveis neste momento.",
    loading: false,
    loadingText: "Carregando motivos…",
    error: "",
    busy: false,
    reasonLabel: "Motivo",
    placeholder: "",
    maxlength: undefined,
  },
);

const emit = defineEmits<{
  "update:open": [value: boolean];
  "dirty-change": [value: boolean];
  retry: [];
  confirm: [payload: ReasonChoice];
}>();

const reason = ref("");
const code = ref("");
const other = ref(false);
const discarding = ref(false);
const reasonInput = ref<{ $el?: HTMLElement } | HTMLElement | null>(null);

// Estado limpo a cada abertura: um pedido reaberto não herda a escolha anterior.
watch(
  () => props.open,
  (open) => {
    if (!open) return;
    reason.value = "";
    code.value = "";
    other.value = false;
    discarding.value = false;
  },
);

const presetGroups = computed(() => props.presets.filter((group) => group.presets.length));

const dirty = computed(() => props.open && Boolean(reason.value.trim() || code.value));
watch(dirty, (value) => emit("dirty-change", value), { immediate: true });

function requestOpen(open: boolean) {
  if (open) {
    emit("update:open", true);
    return;
  }
  if (props.busy) return;
  if (dirty.value) {
    discarding.value = true;
    return;
  }
  emit("update:open", false);
}

function keepWriting() {
  discarding.value = false;
}

function discard() {
  discarding.value = false;
  emit("update:open", false);
}

const canConfirm = computed(() => {
  if (props.loading || props.error) return false;
  if (props.coded) return props.codedReasons.some((r) => r.code === code.value);
  if (other.value || props.required) return reason.value.trim() !== "";
  return true;
});

function onCodeChange() {
  const picked = props.codedReasons.find((r) => r.code === code.value);
  if (picked) reason.value = picked.description;
}

function applyPreset(text: string) {
  other.value = false;
  reason.value = text;
}

function focusReason() {
  const target = reasonInput.value;
  const el = target instanceof HTMLElement ? target : target?.$el;
  const field = el?.tagName === "TEXTAREA" ? el : el?.querySelector?.("textarea");
  (field as HTMLTextAreaElement | null | undefined)?.focus();
}

function chooseOther() {
  other.value = true;
  reason.value = "";
  void nextTick(focusReason);
}

const presetPressed = (text: string) => !other.value && reason.value === text;

function submit() {
  if (!canConfirm.value || props.busy) return;
  emit("confirm", { reason: reason.value.trim(), code: code.value });
}

const chipClass = (pressed: boolean) =>
  pressed ? "border-primary bg-primary/10 text-foreground" : "border-border text-muted-foreground hover:bg-muted";
</script>

<template>
  <!-- `value` anotado: nos apps sem `UiDialog` o tipo do evento não resolve. -->
  <UiDialog :open="open" @update:open="(value: boolean) => requestOpen(value)">
    <UiDialogContent class="sm:max-w-md" data-reason-dialog>
      <UiDialogHeader>
        <UiDialogTitle>{{ title }}</UiDialogTitle>
        <UiDialogDescription>{{ description }}</UiDialogDescription>
      </UiDialogHeader>

      <div class="grid gap-3">
        <p v-if="loading" class="text-sm text-muted-foreground">{{ loadingText }}</p>

        <div v-else-if="error" role="alert" class="grid justify-items-start gap-1 text-sm text-destructive">
          <p>{{ error }}</p>
          <UiButton type="button" variant="link" class="min-h-control px-0" @click="emit('retry')">
            Consultar novamente
          </UiButton>
        </div>

        <p v-else-if="coded && !codedReasons.length" class="text-sm">{{ codedEmptyText }}</p>

        <UiNativeSelect
          v-else-if="coded"
          v-model="code"
          class="w-full"
          :aria-label="codedLabel"
          data-reason-code
          @change="onCodeChange"
        >
          <option value="" disabled>Selecione o motivo…</option>
          <option v-for="r in codedReasons" :key="r.code" :value="r.code">{{ r.description }}</option>
        </UiNativeSelect>

        <template v-else>
          <div v-if="presetGroups.length" class="space-y-2.5" data-testid="reason-presets">
            <div
              v-for="(group, gi) in presetGroups"
              :key="gi"
              role="group"
              :aria-label="group.label || undefined"
              data-testid="reason-preset-group"
            >
              <p v-if="group.label" class="mb-1 text-xs font-semibold text-muted-foreground">{{ group.label }}</p>
              <div class="flex flex-wrap gap-1.5">
                <button
                  v-for="(preset, i) in group.presets"
                  :key="i"
                  type="button"
                  :aria-pressed="presetPressed(preset)"
                  class="inline-flex min-h-control items-center rounded-full border px-3 text-sm transition-colors outline-offset-2 focus-visible:outline-2 focus-visible:outline-ring"
                  :class="chipClass(presetPressed(preset))"
                  data-reason-preset
                  @click="applyPreset(preset)"
                >
                  {{ preset }}
                </button>
              </div>
            </div>
            <div class="flex flex-wrap gap-1.5">
              <button
                type="button"
                :aria-pressed="other"
                data-testid="reason-other"
                class="inline-flex min-h-control items-center rounded-full border px-3 text-sm transition-colors outline-offset-2 focus-visible:outline-2 focus-visible:outline-ring"
                :class="chipClass(other)"
                @click="chooseOther"
              >
                Outros
              </button>
            </div>
          </div>

          <label class="grid gap-1.5">
            <span class="text-sm font-medium">{{ reasonLabel }}</span>
            <UiTextarea
              ref="reasonInput"
              v-model="reason"
              :rows="3"
              :maxlength="maxlength"
              :placeholder="other ? 'Escreva o motivo que o cliente vai ler…' : placeholder"
              class="text-base"
              data-reason-input
            />
          </label>
          <p v-if="other && !reason.trim()" class="text-xs text-muted-foreground" data-testid="reason-other-hint">
            Com “Outros”, escreva o motivo antes de confirmar.
          </p>
        </template>

        <div
          v-if="discarding"
          role="alertdialog"
          aria-label="Descartar o motivo digitado?"
          class="grid gap-2 rounded-md border border-warning/50 bg-warning/10 p-3"
          data-reason-discard
        >
          <p class="text-sm font-medium">Descartar o motivo digitado?</p>
          <div class="flex flex-wrap justify-end gap-2">
            <UiButton type="button" variant="outline" data-reason-keep @click="keepWriting">Continuar escrevendo</UiButton>
            <UiButton type="button" variant="destructive" data-reason-discard-confirm @click="discard">Descartar</UiButton>
          </div>
        </div>

        <UiDialogFooter v-else>
          <UiButton type="button" variant="outline" :disabled="busy" data-reason-back @click="requestOpen(false)">
            Voltar
          </UiButton>
          <UiButton
            type="button"
            variant="destructive"
            :disabled="busy || !canConfirm"
            :loading="busy"
            data-reason-confirm
            @click="submit"
          >
            {{ confirmLabel }}
          </UiButton>
        </UiDialogFooter>
      </div>
    </UiDialogContent>
  </UiDialog>
</template>
