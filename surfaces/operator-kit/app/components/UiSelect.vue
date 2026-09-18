<script setup lang="ts" generic="T extends ChoiceValue">
/**
 * Escolher UMA opção com BUSCA, e não rolando uma lista de dezenas.
 *
 * Esta peça NÃO nasceu aqui: ela é o `MaterialPicker` do Compras, promovido ao
 * kit e generalizado de `Material`/SKU para um par de opções qualquer. O que ele
 * já resolvia continua inteiro — inclusive o aviso do `<label>` mais abaixo, que
 * é memória de um defeito pago. O que ganhou na promoção: limiar (lista curta
 * degrada para lista simples, sem campo de busca), contagem de resultados
 * anunciada ao leitor de tela, e opção desabilitada que a seta pula.
 *
 * Um `<select>` nativo com 56 insumos é castigo no celular: o operador tem a
 * caixa na mão, o entregador esperando, e precisa achar "Manteiga francesa"
 * arrastando. Aqui ele digita "mant" e acaba. O `UiNativeSelect` ao lado
 * continua sendo a peça certa para lista curta e fixa — no celular ele abre a
 * roda do sistema, que é ótima.
 *
 * Sem biblioteca de componente (convenção da casa): é um botão que abre um
 * painel com campo de texto e a lista filtrada. A busca ignora acento e casa
 * pelo rótulo, pelo detalhe e por palavras-chave invisíveis — o operador às
 * vezes lê o código da etiqueta, não o nome.
 *
 * O painel é um combobox de verdade: o campo de busca tem `role="combobox"`, a
 * lista tem `role="listbox"`, e o item em destaque é apontado por
 * `aria-activedescendant`. Assim ↑ ↓ Home End Enter Esc andam na lista sem
 * tirar o cursor de dentro do campo, que é onde o operador está digitando.
 * Sem campo de busca (lista curta) quem recebe o foco e o teclado é a lista.
 *
 * ⚠️ Quem usa este componente NÃO pode envolvê-lo num `<label>`. Um `<label>`
 * sem `for` adota o primeiro controle rotulável de dentro — aqui, o botão que
 * abre o painel — e reencaminha para ele todo clique que caia em parte NÃO
 * interativa da label, inclusive o véu de "fechar ao tocar fora" logo abaixo.
 * O painel fechava e reabria no MESMO clique: dropdown que não fecha nunca e
 * escolha que parecia ignorada. Rotule com um `<span id>` e passe `labelledBy`.
 */
import { computed, nextTick, ref, useId, useTemplateRef, watch } from "vue";

import {
  SEARCH_THRESHOLD,
  filterOptions,
  firstEnabledIndex,
  indexOfValue,
  isSearchable,
  lastEnabledIndex,
  resultsAnnouncement,
  selectedOption,
  stepIndex,
} from "../presentation/choice";
import type { ChoiceOption, ChoiceValue } from "../types/choice";

const props = withDefaults(
  defineProps<{
    /** Valor escolhido (v-model). */
    modelValue?: T;
    options: ChoiceOption<T>[];
    /** O que o gatilho diz enquanto nada foi escolhido. */
    placeholder?: string;
    /** `id` do texto que nomeia o campo. Ver o aviso acima: nunca um `<label>`. */
    labelledBy?: string;
    /** Nome acessível quando não há texto na tela para apontar com `labelledBy`. */
    label?: string;
    disabled?: boolean;
    /** Força (ou proíbe) o campo de busca. Sem isto, decide o limiar. */
    searchable?: boolean;
    searchThreshold?: number;
    searchPlaceholder?: string;
    emptyText?: string;
  }>(),
  {
    placeholder: "Selecione",
    // ⚠️ `undefined` EXPLÍCITO: prop booleana sem default declarado vira `false` na
    // conversão que o Vue faz para boolean, e o `??` abaixo nunca chegaria no
    // limiar — o select nasceria sem busca em qualquer tamanho de lista.
    searchable: undefined,
    searchThreshold: SEARCH_THRESHOLD,
    searchPlaceholder: "Buscar",
    emptyText: "Nenhum resultado",
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: T];
  change: [option: ChoiceOption<T>];
}>();

defineSlots<{
  /** Conteúdo de cada linha da lista. */
  option?: (scope: { option: ChoiceOption<T>; active: boolean; selected: boolean }) => unknown;
  /** O que o gatilho mostra quando há escolha. */
  value?: (scope: { option: ChoiceOption<T> }) => unknown;
  /** Estado vazio da busca. */
  empty?: (scope: { query: string }) => unknown;
}>();

const trigger = useTemplateRef<HTMLButtonElement>("trigger");
const search = useTemplateRef<HTMLInputElement>("search");
const list = useTemplateRef<HTMLElement>("list");

const uid = useId();
const listId = `${uid}-list`;
const valueId = `${uid}-value`;
const labelId = `${uid}-label`;
const optionId = (index: number) => `${uid}-option-${index}`;

const open = ref(false);
const query = ref("");
/** Item em destaque na lista. Só significa algo com o painel aberto. */
const active = ref(0);

const chosen = computed(() => selectedOption(props.options, props.modelValue));
const searchable = computed(() =>
  props.searchable ?? isSearchable(props.options.length, props.searchThreshold),
);
const results = computed(() => (searchable.value ? filterOptions(props.options, query.value) : props.options));

/** O destaque nunca aponta para fora da lista que está na tela. */
const activeIndex = computed(() => {
  if (!results.value.length) return -1;
  return Math.min(Math.max(active.value, 0), results.value.length - 1);
});
const activeId = computed(() => (activeIndex.value < 0 ? undefined : optionId(activeIndex.value)));

/**
 * "Insumo, Manteiga francesa" — o rótulo do campo E o que está escolhido.
 *
 * ⚠️ `aria-labelledby` GANHA de `aria-label`, então o nome do campo não pode vir
 * por `aria-label` quando este atributo existe: ele seria ignorado e o gatilho
 * ficaria se chamando só pelo valor ("Aviso de fornada"), sem dizer de quê. Sem
 * texto na tela para apontar, o `label` vira um `<span>` invisível aqui dentro e
 * entra na mesma cadeia.
 */
const triggerLabelledBy = computed(() => {
  const source = props.labelledBy ?? (props.label ? labelId : null);
  return source ? `${source} ${valueId}` : valueId;
});

/** Nome do campo para o CAMPO DE BUSCA, que não tem valor a compor. */
const searchLabelledBy = computed(() => props.labelledBy ?? (props.label ? labelId : undefined));

// Só anuncia quando há busca em curso: leitor de tela falando "12 resultados"
// numa lista que ninguém filtrou é ruído.
const announcement = computed(() => (query.value ? resultsAnnouncement(results.value.length) : ""));

// Filtrou de novo: o destaque volta para o primeiro resultado utilizável, que é
// o que o Enter vai pegar.
watch(query, () => {
  active.value = Math.max(0, firstEnabledIndex(results.value));
});

async function scrollActiveIntoView() {
  await nextTick();
  const option = list.value?.querySelector<HTMLElement>('[data-active="true"]');
  // `scrollIntoView` não existe no DOM de teste; a ausência dele não pode
  // derrubar a navegação por teclado, que é o que de fato importa aqui.
  if (option && typeof option.scrollIntoView === "function") option.scrollIntoView({ block: "nearest" });
}

async function openPicker() {
  if (props.disabled || open.value) return;
  open.value = true;
  query.value = "";
  await nextTick();
  // Depois do `nextTick` porque o `watch(query)` acima já rodou: abrir com uma
  // opção escolhida deixa o destaque EM CIMA dela, não na primeira da lista.
  const chosenIndex = indexOfValue(results.value, props.modelValue);
  active.value = chosenIndex >= 0 ? chosenIndex : Math.max(0, firstEnabledIndex(results.value));
  (searchable.value ? search.value : list.value)?.focus();
  void scrollActiveIntoView();
}

function closePicker(returnFocus = true) {
  if (!open.value) return;
  open.value = false;
  // O foco volta para o botão: quem abriu pelo teclado não é largado no corpo
  // da página.
  if (returnFocus) void nextTick(() => trigger.value?.focus());
}

function choose(option: ChoiceOption<T> | undefined) {
  if (!option || option.disabled) return;
  emit("update:modelValue", option.value);
  emit("change", option);
  closePicker();
}

function move(delta: number) {
  const next = stepIndex(results.value, activeIndex.value, delta);
  if (next < 0) return;
  active.value = next;
  void scrollActiveIntoView();
}

function moveToEdge(edge: "first" | "last") {
  const next = edge === "first" ? firstEnabledIndex(results.value) : lastEnabledIndex(results.value);
  if (next < 0) return;
  active.value = next;
  void scrollActiveIntoView();
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === "ArrowDown") {
    event.preventDefault();
    move(1);
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    move(-1);
  } else if (event.key === "Home") {
    event.preventDefault();
    moveToEdge("first");
  } else if (event.key === "End") {
    event.preventDefault();
    moveToEdge("last");
  } else if (event.key === "Enter") {
    event.preventDefault();
    choose(results.value[activeIndex.value]);
  } else if (event.key === "Escape") {
    // Fecha SÓ o painel; sem o stop, o Esc atravessaria para quem estiver por
    // cima (modal, gaveta) e fecharia a tela inteira junto.
    event.preventDefault();
    event.stopPropagation();
    closePicker();
  } else if (event.key === "Tab") {
    // Tab é saída legítima: fecha sem roubar o foco de volta.
    closePicker(false);
  }
}

/** A lista só ouve o teclado quando ela mesma tem o foco (sem campo de busca). */
function onListKeydown(event: KeyboardEvent) {
  if (!searchable.value) onKeydown(event);
}

function onTriggerKeydown(event: KeyboardEvent) {
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    void openPicker();
  }
}

defineExpose({ focus: () => trigger.value?.focus() });
</script>

<template>
  <div data-slot="select" class="relative">
    <button
      ref="trigger"
      type="button"
      data-slot="select-trigger"
      aria-haspopup="listbox"
      :aria-expanded="open"
      :aria-labelledby="triggerLabelledBy"
      :aria-controls="open ? listId : undefined"
      :disabled="disabled"
      class="flex h-control w-full items-center justify-between gap-2 rounded-md border border-border bg-card px-3 text-left text-sm text-foreground outline-offset-2 transition focus-visible:outline-2 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-50"
      @click="open ? closePicker() : openPicker()"
      @keydown="onTriggerKeydown"
    >
      <span v-if="label && !labelledBy" :id="labelId" class="sr-only">{{ label }}</span>
      <span :id="valueId" class="min-w-0 truncate" :class="chosen ? 'font-medium' : 'text-muted-foreground'">
        <slot v-if="chosen" name="value" :option="chosen">{{ chosen.label }}</slot>
        <template v-else>{{ placeholder }}</template>
      </span>
      <Icon
        :name="searchable ? 'lucide:search' : 'lucide:chevron-down'"
        class="size-4 shrink-0 text-muted-foreground"
      />
    </button>

    <!-- Fecha ao tocar fora. Um `fixed` inerte cobrindo a tela é mais confiável
         no celular que ouvir clique no documento, que briga com o scroll.
         O `.prevent` diz que o clique foi CONSUMIDO pela dispensa: sem ele, um
         `<label>` ancestral rodaria seu comportamento de ativação sobre o botão
         que abre e reabriria o painel no mesmo gesto. -->
    <div v-if="open" class="fixed inset-0 z-40" @click.prevent="closePicker()" />

    <div
      v-if="open"
      data-slot="select-panel"
      class="absolute inset-x-0 top-full z-50 mt-1 rounded-md border border-border bg-card shadow-lg"
    >
      <div v-if="searchable" class="border-b border-border p-2">
        <input
          ref="search"
          v-model="query"
          type="search"
          role="combobox"
          autocomplete="off"
          aria-autocomplete="list"
          aria-expanded="true"
          :aria-controls="listId"
          :aria-activedescendant="activeId"
          :aria-labelledby="searchLabelledBy"
          :placeholder="searchPlaceholder"
          class="h-control w-full rounded-md border border-border bg-background px-3 text-sm text-foreground outline-offset-2 focus-visible:outline-2 focus-visible:outline-ring"
          @keydown="onKeydown"
        />
      </div>

      <p v-if="!results.length" class="px-3 py-3 text-sm text-muted-foreground">
        <slot name="empty" :query="query">{{ emptyText }}</slot>
      </p>
      <ul
        v-else
        :id="listId"
        ref="list"
        role="listbox"
        :tabindex="searchable ? -1 : 0"
        :aria-labelledby="searchLabelledBy"
        :aria-activedescendant="searchable ? undefined : activeId"
        class="max-h-64 overflow-y-auto py-1 outline-none"
        @keydown="onListKeydown"
      >
        <li
          v-for="(option, index) in results"
          :id="optionId(index)"
          :key="String(option.value)"
          role="option"
          :aria-selected="option.value === modelValue"
          :aria-disabled="option.disabled || undefined"
          :data-active="index === activeIndex"
          class="flex min-h-control w-full items-center justify-between gap-2 px-3 py-2.5 text-left text-sm"
          :class="[
            index === activeIndex ? 'bg-accent' : '',
            option.value === modelValue ? 'font-semibold text-primary' : '',
            option.disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer',
          ]"
          @pointerdown.prevent
          @click="choose(option)"
          @pointerenter="active = index"
        >
          <slot name="option" :option="option" :active="index === activeIndex" :selected="option.value === modelValue">
            <span class="min-w-0">
              <span class="block truncate">{{ option.label }}</span>
              <span v-if="option.hint" class="block truncate text-xs text-muted-foreground">{{ option.hint }}</span>
            </span>
            <Icon v-if="option.value === modelValue" name="lucide:check" class="size-4 shrink-0" />
          </slot>
        </li>
      </ul>

      <!-- Região viva: existe desde a abertura, para o leitor de tela ter o que
           observar quando a contagem mudar. Vazia enquanto ninguém buscou. -->
      <p
        role="status"
        aria-live="polite"
        class="px-3 text-xs text-muted-foreground"
        :class="announcement ? 'py-1.5' : 'sr-only'"
      >
        {{ announcement }}
      </p>
    </div>
  </div>
</template>
