<script setup lang="ts">
// O diálogo que pergunta o MOTIVO de um gesto destrutivo que o cliente vai ler
// (cancelar, recusar), diz a consequência e confirma. Uma peça só para o PDV, o
// Gestor e o Marketing: antes eram dois diálogos com duas regras para o mesmo ato.
//
// Duas formas, decididas por quem chama:
//   - Motivo da lista (`keyedReasons`, recusar e cancelar pedido): a lista única do
//     backend, cada motivo com a frase revisada que o cliente lê. Escolher é
//     obrigatório; a tela mostra a frase que vai sair, e o texto livre vira a
//     OBSERVAÇÃO INTERNA (opcional, nunca vai ao cliente).
//   - Texto livre (sem lista): o motivo escrito, opcional (recusar um anúncio) ou
//     exigido com `required` (a ouvidoria resolvida).
//
// Fechar com texto digitado pede confirmação DENTRO do diálogo (não `window.confirm`,
// que foge do contrato de modal da casa): o motivo escrito não some por um toque fora.
//
// Apresentacional: quem chama traz os motivos e grava; esta peça guarda só o que está
// sendo escolhido e entrega `{ reason, key }`. A autorização do gerente fica FORA
// (`OperatorManagerAuth` sobe por cima, e o motivo digitado continua aqui embaixo).
//
// O que decide o gesto fica SEMPRE à vista (WP-G06, laudo P2-29): o confirmar, o que
// falta para ele acender, a pergunta de descarte e a falha do gesto moram no rodapé do
// Modal, que não rola. Com oito motivos numa tela de 850 px de altura o botão ficava
// cortado na base do corpo. A falha (`error`) aparece aqui dentro: o toast e o cartão
// de quem chamou ficam ATRÁS do diálogo aberto (P1-11).
//
// A anatomia inteira usa os componentes oficiais de Modal, RadioGroup, Textarea, Alert
// e Button do Nuxt UI; os apps consumidores só passam conteúdo e estado.
import { computed, ref, watch } from "vue";

import type { KeyedReason, ReasonChoice } from "../types/reason";

const props = withDefaults(
  defineProps<{
    open: boolean;
    title: string;
    /** A consequência, dita antes de confirmar (reembolso, para onde vai o motivo). */
    description: string;
    confirmLabel: string;
    /** Texto livre exigido para confirmar (só sem lista). */
    required?: boolean;
    /** Motivos da lista única do backend: escolher um é obrigatório; o texto é interno. */
    keyedReasons?: KeyedReason[];
    /** Motivo da lista já marcado ao abrir, quando a tela sabe o porquê (Pix
     *  vencido abre com "Pagamento não confirmado"). O operador pode trocar. */
    initialKey?: string;
    busy?: boolean;
    /** A falha do gesto, dita dentro do diálogo. Quem chama limpa ao tentar de novo. */
    error?: string;
    /** O campo que a falha aponta: `key` (o motivo da lista) ou `reason` (o texto). */
    errorField?: "" | "key" | "reason";
    /**
     * Por que ainda não dá para confirmar, quando o motivo não é o que falta (quem
     * chama ainda lê o que o gesto faz). Vazio libera; com texto, o confirmar apaga e
     * a linha ao lado dele diz a frase.
     */
    blocked?: string;
    reasonLabel?: string;
    placeholder?: string;
    maxlength?: number;
  }>(),
  {
    required: false,
    keyedReasons: () => [],
    initialKey: "",
    busy: false,
    error: "",
    errorField: "",
    blocked: "",
    reasonLabel: "Motivo",
    placeholder: "",
    maxlength: undefined,
  },
);

const emit = defineEmits<{
  "update:open": [value: boolean];
  "dirty-change": [value: boolean];
  confirm: [payload: ReasonChoice];
}>();

const reason = ref("");
const key = ref("");
const discarding = ref(false);

// Estado limpo a cada abertura: um pedido reaberto não herda a escolha anterior.
watch(
  () => props.open,
  (open) => {
    if (!open) return;
    reason.value = "";
    key.value = props.initialKey;
    discarding.value = false;
  },
);

const keyed = computed(() => props.keyedReasons.length > 0);
const keyedItems = computed(() =>
  props.keyedReasons.map((item) => ({
    value: item.key,
    label: item.label,
    "data-reason-key": item.key,
  })),
);
const pickedKeyed = computed(() =>
  props.keyedReasons.find((item) => item.key === key.value),
);

const dirty = computed(
  () =>
    props.open &&
    Boolean(reason.value.trim() || key.value !== props.initialKey),
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

const hasReason = computed(() =>
  keyed.value ? Boolean(pickedKeyed.value) : !props.required || reason.value.trim() !== "",
);
const canConfirm = computed(() => hasReason.value && !props.blocked);

// O Confirmar fica apagado até haver motivo, e apagado sozinho não diz por quê: o
// toque não fazia nada e a pessoa não sabia o que faltava (beta 05/11, GES-14).
// A linha diz, ao lado do botão. Primeiro o que depende de quem está na tela (o
// motivo); depois o que quem chama ainda espera (`blocked`).
const missingHint = computed(() => {
  if (!hasReason.value)
    return keyed.value ? "Escolha um motivo para confirmar." : "Escreva o motivo para confirmar.";
  return props.blocked;
});

function submit() {
  if (!canConfirm.value || props.busy) return;
  emit("confirm", {
    reason: reason.value.trim(),
    key: keyed.value ? key.value : "",
  });
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
        <!-- Sobre o quê é o gesto e o que ele faz (qual pedido, o destino do dinheiro):
             conteúdo de quem chama, antes da pergunta do motivo. -->
        <slot name="summary" />

        <template v-if="keyed">
          <NuxtRadioGroup
            v-model="key"
            :items="keyedItems"
            variant="card"
            :legend="reasonLabel"
            :color="errorField === 'key' ? 'error' : undefined"
            :aria-invalid="errorField === 'key' ? 'true' : undefined"
            data-reason-keyed
          />
          <!-- O lugar da frase existe desde o início (beta test de 05/11/2026, PDV2-19 e
               PDV2-21): ao escolher o motivo ela não empurra o botão para baixo do dedo,
               e antes da escolha diz o que falta em vez de o botão apagado ficar mudo. -->
          <NuxtAlert
            :color="pickedKeyed ? 'info' : 'neutral'"
            variant="subtle"
            icon="i-lucide-message-circle"
            title="O cliente vai ler"
            :description="pickedKeyed ? pickedKeyed.customer_text : 'Escolha o motivo acima para ver a frase.'"
            :data-reason-preview="pickedKeyed ? '' : undefined"
            :data-reason-preview-pending="pickedKeyed ? undefined : ''"
          />
          <NuxtFormField
            label="Observação interna (opcional)"
            description="Fica só no histórico do pedido. O cliente não vê."
            :error="errorField === 'reason'"
          >
            <NuxtTextarea
              v-model="reason"
              class="w-full"
              :rows="2"
              :maxlength="maxlength ?? 200"
              data-reason-input
            />
          </NuxtFormField>
        </template>

        <NuxtFormField
          v-else
          :label="reasonLabel"
          :error="errorField === 'reason'"
        >
          <NuxtTextarea
            v-model="reason"
            class="w-full"
            :rows="3"
            :maxlength="maxlength"
            :placeholder="placeholder"
            data-reason-input
          />
        </NuxtFormField>
      </div>
    </template>

    <!-- O rodapé não rola: a falha, a pergunta de descarte, o que falta e os dois
         botões ficam à vista em qualquer altura de tela. -->
    <template #footer>
      <div class="grid w-full gap-3" data-reason-footer>
        <NuxtAlert
          v-if="error"
          color="error"
          variant="subtle"
          icon="i-lucide-triangle-alert"
          :description="error"
          :data-reason-error="errorField || 'action'"
        />

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

        <p
          v-if="!discarding && missingHint"
          class="text-end text-sm text-muted-foreground"
          data-reason-missing
        >
          {{ missingHint }}
        </p>

        <div v-if="!discarding" class="flex justify-end gap-2">
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
