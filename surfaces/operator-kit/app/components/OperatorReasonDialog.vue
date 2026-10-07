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
// A anatomia inteira usa os componentes oficiais de Modal, Select, Textarea, Alert e
// Button do Nuxt UI; os apps consumidores só passam conteúdo e estado.
import { computed, nextTick, ref, watch } from "vue";

import type {
  CodedReason,
  ReasonChoice,
  ReasonPresetGroup,
} from "../types/reason";

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

const presetGroups = computed(() =>
  props.presets.filter((group) => group.presets.length),
);

const dirty = computed(
  () => props.open && Boolean(reason.value.trim() || code.value),
);
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
  const field =
    el?.tagName === "TEXTAREA" ? el : el?.querySelector?.("textarea");
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
</script>

<template>
  <NuxtModal
    :open="open"
    :title="title"
    :description="description"
    @update:open="requestOpen"
  >
    <template #body>
      <div class="grid gap-3" data-reason-dialog>
        <NuxtAlert
          v-if="loading"
          color="neutral"
          variant="subtle"
          icon="i-line-md-loading-loop"
          :title="loadingText"
        />

        <NuxtAlert
          v-else-if="error"
          color="error"
          variant="subtle"
          :title="error"
        >
          <template #actions
            ><NuxtButton
              color="error"
              variant="outline"
              label="Consultar novamente"
              @click="emit('retry')"
          /></template>
        </NuxtAlert>

        <NuxtEmpty
          v-else-if="coded && !codedReasons.length"
          icon="i-lucide-list-x"
          :title="codedEmptyText"
        />

        <NuxtSelect
          v-else-if="coded"
          v-model="code"
          :items="codedReasons"
          value-key="code"
          label-key="description"
          placeholder="Selecione o motivo…"
          :aria-label="codedLabel"
          data-reason-code
          @update:model-value="onCodeChange"
        />

        <template v-else>
          <div
            v-if="presetGroups.length"
            class="space-y-2.5"
            data-testid="reason-presets"
          >
            <div
              v-for="(group, gi) in presetGroups"
              :key="gi"
              role="group"
              :aria-label="group.label || undefined"
              data-testid="reason-preset-group"
            >
              <p
                v-if="group.label"
                class="mb-1 text-xs font-semibold text-muted-foreground"
              >
                {{ group.label }}
              </p>
              <div class="flex flex-wrap gap-1.5">
                <NuxtButton
                  v-for="(preset, i) in group.presets"
                  :key="i"
                  :aria-pressed="presetPressed(preset)"
                  color="neutral"
                  :variant="presetPressed(preset) ? 'soft' : 'outline'"
                  :label="preset"
                  data-reason-preset
                  @click="applyPreset(preset)"
                />
              </div>
            </div>
            <div class="flex flex-wrap gap-1.5">
              <NuxtButton
                :aria-pressed="other"
                color="neutral"
                :variant="other ? 'soft' : 'outline'"
                label="Outros"
                data-testid="reason-other"
                @click="chooseOther"
              />
            </div>
          </div>

          <NuxtFormField :label="reasonLabel">
            <NuxtTextarea
              ref="reasonInput"
              v-model="reason"
              class="w-full"
              :rows="3"
              :maxlength="maxlength"
              :placeholder="
                other ? 'Escreva o motivo que o cliente vai ler…' : placeholder
              "
              data-reason-input
            />
            <template v-if="other && !reason.trim()" #description>
              <span data-testid="reason-other-hint"
                >Com “Outros”, escreva o motivo antes de confirmar.</span
              >
            </template>
          </NuxtFormField>
        </template>

        <NuxtAlert
          v-if="discarding"
          color="warning"
          variant="subtle"
          title="Descartar o motivo digitado?"
          data-reason-discard
        >
          <template #actions>
            <NuxtButton
              color="warning"
              variant="outline"
              label="Continuar escrevendo"
              data-reason-keep
              @click="keepWriting"
            />
            <NuxtButton
              color="warning"
              variant="outline"
              label="Descartar"
              data-reason-discard-confirm
              @click="discard"
            />
          </template>
        </NuxtAlert>

        <div v-else class="flex justify-end gap-2">
          <NuxtButton
            color="neutral"
            variant="outline"
            label="Voltar"
            :disabled="busy"
            data-reason-back
            @click="requestOpen(false)"
          />
          <NuxtButton
            color="error"
            :disabled="busy || !canConfirm"
            :loading="busy"
            :label="confirmLabel"
            data-reason-confirm
            @click="submit"
          />
        </div>
      </div>
    </template>
  </NuxtModal>
</template>
