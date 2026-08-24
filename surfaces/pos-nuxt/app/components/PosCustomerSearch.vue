<script setup lang="ts">
// Shared customer search (Odoo-style get-or-create entry point): one field
// matches any unique key (name/phone/CPF/email), debounced, returning a list to
// pick from. Picking fills the cart + runs the full lookup by ref.
//
// O CLIENTE EM DOIS ENTERS: o Enter decide pela regra pura de
// `presentation/customerSearch` — 1 resultado seleciona; N seleciona o
// destacado (↑/↓ navegam, padrão combobox); 0 + CPF válido cria/resolve direto;
// 0 + telefone/nome transfere a query para o cadastro novo; com cliente já
// associado e campo vazio, Enter conclui. O segundo Enter fecha o modal.
// Used by both the comanda header and the payment screen's customer modal.
import type { POSCustomerSearchResult } from "~/types/pos";
import {
  cpfHint,
  enterAction,
  maskQueryIfCpf,
  moveHighlight,
} from "~/presentation/customerSearch";

const props = defineProps<{
  results: POSCustomerSearchResult[];
  busy: boolean;
  /** Já existe cliente associado: Enter com o campo vazio conclui. */
  hasCustomer?: boolean;
}>();

const emit = defineEmits<{
  search: [string];
  select: [POSCustomerSearchResult];
  /** 0 resultados + CPF válido: criar/resolver direto pelo documento. */
  resolveCpf: [string];
  /** 0 resultados + query não-CPF: levar o que foi digitado ao cadastro novo. */
  transfer: [{ field: "phone" | "name"; value: string }];
  /** Cliente já associado + Enter no campo vazio: concluir e fechar. */
  conclude: [];
}>();

const query = ref("");
const highlighted = ref(0);
// Enter no meio do debounce: dispara a busca JÁ e decide quando ela voltar.
const pendingEnter = ref(false);
let timer: ReturnType<typeof setTimeout> | null = null;
let pendingEnterTimer: ReturnType<typeof setTimeout> | null = null;

function cancelPendingEnter() {
  pendingEnter.value = false;
  if (pendingEnterTimer) {
    clearTimeout(pendingEnterTimer);
    pendingEnterTimer = null;
  }
}

/** O Enter espera a busca disparada agora: decide quando ela responder — e num
 *  teto curto de qualquer jeito, para o Enter nunca ficar preso num caminho que
 *  não mexe nem em `results` nem em `busy`. */
function armPendingEnter() {
  pendingEnter.value = true;
  if (pendingEnterTimer) clearTimeout(pendingEnterTimer);
  pendingEnterTimer = setTimeout(() => {
    pendingEnterTimer = null;
    settlePendingEnter();
  }, 500);
}

function settlePendingEnter() {
  if (!pendingEnter.value) return;
  cancelPendingEnter();
  decide();
}

watch(query, (q) => {
  const masked = maskQueryIfCpf(q);
  if (masked !== q) {
    // Idempotente: o watch roda de novo com o valor mascarado e agenda a busca.
    query.value = masked;
    return;
  }
  highlighted.value = 0;
  cancelPendingEnter();
  if (timer) clearTimeout(timer);
  timer = setTimeout(() => {
    timer = null;
    emit("search", q);
  }, 350);
});

// A busca respondeu (a lista trocou de referência) com um Enter esperando →
// decide agora. `busy` caindo cobre o caso em que a resposta repete a lista.
watch(() => props.results, () => {
  highlighted.value = 0;
  settlePendingEnter();
});
watch(() => props.busy, (busy, was) => {
  if (was && !busy) settlePendingEnter();
});

const hint = computed(() => cpfHint(query.value));

function decide() {
  const action = enterAction({
    query: query.value,
    resultsCount: props.results.length,
    highlightedIndex: highlighted.value,
    hasCustomer: Boolean(props.hasCustomer),
  });
  if (action.type === "pick") {
    const result = props.results[action.index];
    if (result) pick(result);
  } else if (action.type === "resolve_cpf") {
    query.value = "";
    emit("resolveCpf", action.cpf);
  } else if (action.type === "transfer") {
    query.value = "";
    emit("transfer", { field: action.field, value: action.value });
  } else if (action.type === "conclude") {
    emit("conclude");
  }
}

function onEnter(event: KeyboardEvent) {
  event.preventDefault();
  event.stopPropagation();
  // Flush do debounce: o Enter não espera os 350ms.
  if (timer) {
    clearTimeout(timer);
    timer = null;
    emit("search", query.value);
    if (query.value.trim().length >= 2) {
      armPendingEnter();
      return;
    }
  } else if (props.busy) {
    armPendingEnter();
    return;
  }
  decide();
}

function onArrow(event: KeyboardEvent, delta: 1 | -1) {
  if (!props.results.length) return;
  event.preventDefault();
  highlighted.value = moveHighlight(highlighted.value, delta, props.results.length);
  if (import.meta.client) {
    document.getElementById(optionId(highlighted.value))?.scrollIntoView({ block: "nearest" });
  }
}

function optionId(index: number): string {
  return `pos-customer-option-${index}`;
}

function pick(result: POSCustomerSearchResult) {
  emit("select", result);
  query.value = "";
}

// Let the parent reset the field / place focus when its modal (re)opens.
const inputRef = ref<{ inputRef?: HTMLInputElement } | null>(null);
function reset() {
  query.value = "";
}
function focus() {
  inputRef.value?.inputRef?.focus();
}
defineExpose({ reset, focus });
onBeforeUnmount(() => {
  if (timer) clearTimeout(timer);
  if (pendingEnterTimer) clearTimeout(pendingEnterTimer);
});
</script>

<template>
  <div class="grid gap-3">
    <div class="relative">
      <Icon name="lucide:search" class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
      <UiInput
        ref="inputRef"
        v-model="query"
        class="h-11 pl-10 text-base"
        placeholder="Buscar por nome, telefone, CPF ou e-mail"
        autofocus
        role="combobox"
        aria-expanded="true"
        aria-controls="pos-customer-search-listbox"
        :aria-activedescendant="results.length ? optionId(highlighted) : undefined"
        aria-label="Buscar cliente"
        @keydown.enter="onEnter"
        @keydown.down="onArrow($event, 1)"
        @keydown.up="onArrow($event, -1)"
      />
      <Icon v-if="busy" name="lucide:loader-circle" class="absolute right-3 top-1/2 size-4 -translate-y-1/2 animate-spin text-muted-foreground" />
    </div>
    <p v-if="hint === 'valid'" class="flex items-center gap-1.5 text-xs text-muted-foreground">
      <Icon name="lucide:id-card" class="size-3.5 shrink-0" />
      CPF válido. Enter busca o cadastro ou cria um novo com este CPF.
    </p>
    <p v-else-if="hint === 'invalid'" class="flex items-center gap-1.5 text-xs text-destructive" role="status">
      <Icon name="lucide:triangle-alert" class="size-3.5 shrink-0" />
      CPF inválido: confira os dígitos.
    </p>

    <div
      v-if="results.length"
      id="pos-customer-search-listbox"
      role="listbox"
      aria-label="Clientes encontrados"
      class="grid max-h-56 gap-0.5 overflow-auto rounded-md border p-1"
    >
      <button
        v-for="(result, index) in results"
        :id="optionId(index)"
        :key="result.ref"
        type="button"
        role="option"
        :aria-selected="index === highlighted"
        class="flex items-center justify-between gap-2 rounded-md px-3 py-2 text-left transition hover:bg-accent"
        :class="index === highlighted ? 'bg-accent' : ''"
        @mousemove="highlighted = index"
        @click="pick(result)"
      >
        <span class="min-w-0">
          <span class="block truncate text-sm font-medium">{{ result.name || "Sem nome" }}</span>
          <span class="block truncate text-xs tabular-nums text-muted-foreground">{{ [result.phone, result.document, result.email].filter(Boolean).join(" · ") }}</span>
        </span>
        <span class="flex shrink-0 items-center gap-1.5">
          <kbd v-if="index === highlighted" class="rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px] font-medium text-muted-foreground" aria-hidden="true">Enter</kbd>
          <Icon name="lucide:chevron-right" class="size-4 shrink-0 text-muted-foreground" />
        </span>
      </button>
    </div>
    <p v-else-if="query.trim().length >= 2 && !busy" class="text-center text-xs text-muted-foreground">
      {{ hint === "valid"
        ? "Nenhum cadastro com este CPF. Enter cria um novo na hora."
        : "Nenhum cadastro encontrado. Enter preenche o cadastro novo com o que você digitou." }}
    </p>
  </div>
</template>
