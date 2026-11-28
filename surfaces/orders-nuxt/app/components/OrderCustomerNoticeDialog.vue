<script setup lang="ts">
// "Avisar o cliente" com um toque (WP-G07; decisão 4 do dono, 17/11/2026: "pela API").
// Abre pelo ⋯ do pedido. De cima para baixo:
//
//   1. "Qual aviso": Vai atrasar, Faltou um item, Precisamos remarcar; o travado
//      escreve o motivo, e nada vem marcado. A exceção é quem chega do "Resolver" da
//      promessa em risco (WP-G08): o aviso e os itens em risco vêm marcados, para
//      conferir, e a pessoa ainda pode trocar;
//   2. o que o aviso pede, com toques e sem campo: a nova previsão entre horas prontas,
//      ou os itens que vão faltar;
//   3. a mensagem como o cliente vai ler, montada pelo servidor;
//   4. no rodapé, que não rola, "Voltar" e "Enviar aviso".
//
// Enviar é a ação do detalhe (`customer-notice`), no protocolo de intenção de sempre: a
// tela diz que o aviso foi para a fila, e o recibo do pedido (Avisos ao cliente) diz o
// que o provedor respondeu. "Enviado" sem o provedor confirmar, nunca.
import { splitRef } from "~/presentation/board";
import {
  DELAY_LEGEND,
  MISSING_LEGEND,
  NOTICE_LEGEND,
  SEND_LABEL,
  SEND_ROUTE,
  delayItems,
  lineItems,
  messageHeading,
  missingStep,
  noticeInputs,
  noticeItems,
  noticeTitle,
  pickedNotice,
  type CustomerNoticeKind,
} from "~/presentation/customerNotice";
import { useCustomerNotice } from "~/composables/useCustomerNotice";

const props = withDefaults(
  defineProps<{
    open: boolean;
    orderRef: string;
    customerName?: string;
    /** A gravação está em curso (o detalhe envia). */
    busy?: boolean;
    /** A recusa do envio, com as palavras do servidor; o diálogo segue aberto. */
    failure?: string;
    /** O aviso que abre marcado (vindo do "Resolver"); vazio: nada marcado. */
    initialKind?: string;
    /** As linhas que o "Faltou um item" abre marcadas. */
    initialLines?: string[];
  }>(),
  { customerName: "", busy: false, failure: "", initialKind: "", initialLines: () => [] },
);

const emit = defineEmits<{
  "update:open": [value: boolean];
  /** Enviar: o corpo pronto para a ação `customer-notice`. */
  send: [inputs: Record<string, unknown>];
}>();

const { options, state, message, preview, previewError, previewing, read, show, clear } =
  useCustomerNotice();

const kind = ref<CustomerNoticeKind | "">("");
const eta = ref("");
const lines = ref<string[]>([]);

function reset() {
  kind.value = "";
  eta.value = "";
  lines.value = [];
}

function load() {
  reset();
  if (props.orderRef) void read(props.orderRef);
}

// Cada abertura lê de novo: as horas prontas são as de agora.
watch(
  () => [props.open, props.orderRef] as const,
  ([open]) => {
    if (open) load();
    else {
      reset();
      clear();
    }
  },
  { immediate: true },
);

const title = computed(() => noticeTitle(splitRef(props.orderRef).code));
const items = computed(() => noticeItems(options.value?.notices ?? []));
const notice = computed(() => pickedNotice(options.value, kind.value));
const pick = computed(() => ({ kind: kind.value, eta: eta.value, lines: lines.value }));
const step = computed(() => missingStep(notice.value, pick.value));
const inputs = computed(() =>
  notice.value && !step.value ? noticeInputs(notice.value, pick.value) : null,
);

// Trocar de aviso apaga a escolha do outro: a hora não vale para o item, e vice-versa.
watch(kind, () => {
  eta.value = "";
  lines.value = [];
});

// Vindo do "Resolver": marca o aviso sugerido (só se ele cabe agora) e, depois que a
// troca de aviso limpou a escolha, os itens em risco que são linhas deste pedido.
watch(state, async (value) => {
  if (value !== "ready" || !props.open || !props.initialKind) return;
  const suggested = (options.value?.notices ?? []).find(
    (entry) => entry.kind === props.initialKind && entry.enabled,
  );
  if (!suggested) return;
  kind.value = suggested.kind as CustomerNoticeKind;
  await nextTick();
  const known = new Set((suggested.lines ?? []).map((line) => line.line_id));
  lines.value = props.initialLines.filter((id) => known.has(id));
});

// A mensagem acompanha a escolha completa; incompleta, o lugar diz o que falta.
watch(
  inputs,
  (value) => {
    if (props.open && state.value === "ready") void show(props.orderRef, value);
  },
  { deep: true },
);

const canSend = computed(
  () => Boolean(inputs.value && preview.value && !previewing.value && !props.busy),
);

function close(value: boolean) {
  if (value) return;
  if (props.busy) return;
  emit("update:open", false);
}

function send() {
  if (!canSend.value || !inputs.value) return;
  emit("send", inputs.value);
}
</script>

<template>
  <NuxtModal
    :open="open"
    :title="title"
    description="O aviso sai pela casa, com um toque, e o recibo fica no pedido."
    data-customer-notice-dialog
    @update:open="close"
  >
    <template #body>
      <OperatorScreenState
        v-if="state === 'loading' || state === 'idle'"
        state="loading"
        what="os avisos deste pedido"
        in-card
        data-notice-loading
      />
      <OperatorScreenState
        v-else-if="state === 'error'"
        state="error"
        what="os avisos deste pedido"
        :description="message"
        in-card
        data-notice-load-error
        @retry="load"
      />
      <div v-else-if="options" class="flex min-w-0 flex-col gap-4" data-notice-content>
        <!-- 1. Qual aviso: um por linha; o travado escreve o motivo. -->
        <NuxtRadioGroup
          v-model="kind"
          :items="items"
          variant="card"
          :legend="NOTICE_LEGEND"
          :disabled="busy"
          data-notice-kinds
        />

        <!-- 2. O que o aviso pede, com toques. -->
        <NuxtRadioGroup
          v-if="notice?.kind === 'delayed'"
          v-model="eta"
          :items="delayItems(notice)"
          orientation="horizontal"
          variant="card"
          :legend="DELAY_LEGEND"
          :disabled="busy"
          data-notice-etas
        />
        <NuxtCheckboxGroup
          v-else-if="notice?.kind === 'item_missing'"
          v-model="lines"
          :items="lineItems(notice)"
          variant="card"
          :legend="MISSING_LEGEND"
          :disabled="busy"
          data-notice-lines
        />

        <!-- 3. A mensagem, como o cliente vai ler. O lugar existe desde o início:
             escolher não empurra o resto para baixo do dedo. -->
        <NuxtCard variant="soft" as="section" data-notice-message-block>
          <div class="flex min-w-0 flex-col gap-2">
            <h3 class="text-sm font-medium text-highlighted">
              {{ messageHeading(customerName) }}
            </h3>
            <p
              v-if="preview"
              class="text-sm break-words whitespace-pre-line"
              data-notice-message
            >
              {{ preview.message }}
            </p>
            <p v-else-if="previewError" class="text-sm text-error" data-notice-preview-error>
              {{ previewError }}
            </p>
            <p v-else-if="previewing" class="text-sm text-muted" data-notice-message-loading>
              Montando a mensagem…
            </p>
            <p v-else class="text-sm text-muted" data-notice-message-pending>
              {{ step }}
            </p>
            <p class="text-xs text-muted" data-notice-route>{{ SEND_ROUTE }}</p>
          </div>
        </NuxtCard>
      </div>
    </template>

    <template #footer>
      <div class="grid w-full gap-3" data-notice-footer>
        <NuxtAlert
          v-if="failure"
          color="error"
          variant="subtle"
          icon="i-lucide-triangle-alert"
          :description="failure"
          data-notice-error
        />
        <div class="flex justify-end gap-2">
          <NuxtButton
            type="button"
            color="neutral"
            variant="outline"
            label="Voltar"
            :disabled="busy"
            data-notice-back
            @click="close(false)"
          />
          <NuxtButton
            v-if="state === 'ready'"
            type="button"
            color="primary"
            icon="i-lucide-send"
            :label="SEND_LABEL"
            :disabled="!canSend"
            :loading="busy"
            data-notice-send
            @click="send"
          />
        </div>
      </div>
    </template>
  </NuxtModal>
</template>
